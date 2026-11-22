# postgres_fdw, foreign server, user mapping và foreign table

PostgreSQL có thể truy cập dữ liệu nằm trong một PostgreSQL server khác thông qua cơ chế Foreign Data Wrapper (FDW). Với extension **postgres_fdw**, database local định nghĩa một foreign server để mô tả cách kết nối tới database remote, một user mapping để ánh xạ danh tính người dùng local sang tài khoản remote, và các foreign tables đại diện cho bảng ở phía remote. Ứng dụng có thể truy vấn foreign table bằng SQL gần giống truy vấn bảng local; PostgreSQL sẽ chuyển phần công việc phù hợp sang remote server và trả kết quả về local query.

Cơ chế này giúp tích hợp dữ liệu mà không cần sao chép toàn bộ bảng vào database local. Nó hữu ích khi cần đọc dữ liệu từ hệ thống nghiệp vụ khác, hợp nhất dữ liệu theo truy vấn, di chuyển dần ứng dụng, hoặc xây dựng lớp truy cập dữ liệu liên server. Tuy vậy, foreign table không phải bản sao local và cũng không biến hai database thành một transaction engine phân tán hoàn chỉnh. Mỗi truy vấn có thể phát sinh network round trips, remote CPU/I/O, authentication và consistency considerations. Thiết kế đúng cần xem xét quyền truy cập, latency, planner estimates, pushdown, transaction semantics, failure handling và monitoring ở cả hai phía.

Bài học thuộc chương **Tích hợp dữ liệu** của module **Database Engine Relational PostgreSQL**. Nội dung đi từ kiến trúc FDW, cài postgres_fdw, tạo foreign server và user mapping, import hoặc định nghĩa foreign tables, tới truy vấn/DML, tối ưu, bảo mật, transaction behavior và vận hành production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Foreign Data Wrapper, foreign server, user mapping và foreign table.
- Phân biệt extension package với extension installation trong database.
- Cài và bật postgres_fdw trong database local.
- Tạo foreign server với host, port, dbname và connection options.
- Tạo user mapping từ local role sang remote role.
- Cấp quyền đúng scope cho foreign server, schema và foreign tables.
- Dùng IMPORT FOREIGN SCHEMA hoặc CREATE FOREIGN TABLE.
- Hiểu mapping giữa local foreign table metadata và remote relation.
- Truy vấn và cập nhật dữ liệu qua postgres_fdw trong phạm vi được hỗ trợ.
- Hiểu predicate/join/aggregate pushdown và planner costing.
- Điều chỉnh fetch size, batch size và remote estimates theo workload.
- Phân tích transaction, snapshot, connection cache và failure semantics.
- Bảo vệ credentials, search_path và network connections.
- Theo dõi hoạt động ở cả local lẫn remote PostgreSQL.
- Xây dựng troubleshooting, performance testing và lifecycle runbooks.

## 2. Foreign Data Wrapper là gì?

Foreign Data Wrapper là giao diện mở rộng cho phép PostgreSQL truy cập dữ liệu bên ngoài theo một API thống nhất.

### 2.1. FDW handler

FDW cung cấp handler functions để PostgreSQL planner/executor yêu cầu thông tin và thực thi scan/update trên foreign data source.

### 2.2. Foreign server

Foreign server là một object local mô tả nguồn dữ liệu ngoài và các connection/planning options của FDW. Với postgres_fdw, server thường đại diện cho một remote PostgreSQL database.

### 2.3. User mapping

User mapping ánh xạ local database role (hoặc PUBLIC) sang remote identity và các authentication options. Nhiều local users có thể được map tới cùng hoặc khác remote users.

### 2.4. Foreign table

Foreign table là object trong local catalog mô tả columns/options của remote relation. Nó không lưu rows của remote table trong local storage.

### 2.5. SQL interface thống nhất

Ứng dụng truy vấn foreign table bằng SELECT/INSERT/UPDATE/DELETE theo khả năng FDW hỗ trợ. PostgreSQL quyết định phần nào có thể push down để chạy ở remote server.

## 3. Kiến trúc postgres_fdw

postgres_fdw là FDW có sẵn trong hệ sinh thái PostgreSQL contrib, dùng libpq để kết nối tới PostgreSQL remote.

~~~text
Application / local SQL
          |
          v
Local PostgreSQL planner/executor
          |
          v
Foreign table metadata
          |
          v
postgres_fdw
    |         |
    |         +--> User mapping (remote credentials)
    |
    +------------> Foreign server (host/port/dbname/options)
                         |
                         v
                   libpq connection
                         |
                         v
                 Remote PostgreSQL
                         |
                         v
                 Remote tables/indexes
~~~

### 3.1. Local database

Foreign server, user mappings và foreign tables được tạo trong database local. Cấu hình này không tự chia sẻ sang database khác trong cùng cluster.

### 3.2. Remote database

Dữ liệu thật và indexes nằm ở remote server. Remote server thực thi SQL được pushdown và áp dụng quyền của remote role.

### 3.3. Connection layer

postgres_fdw mở kết nối qua libpq. Hostname, port, TLS, authentication và network reachability phải hoạt động từ host/container chạy local PostgreSQL.

### 3.4. Planner/executor integration

Local planner xây plan có Foreign Scan nodes. Executor lấy rows từ remote hoặc gửi DML tới remote tùy statement và khả năng FDW.

### 3.5. Không phải replication

Foreign table đọc dữ liệu remote theo truy vấn; nó không duy trì một bản sao local đồng bộ như physical/logical replication.

## 4. Khi nào dùng postgres_fdw?

FDW phù hợp khi cần truy cập dữ liệu remote theo nhu cầu truy vấn và chấp nhận network dependency.

### 4.1. Hợp nhất dữ liệu theo truy vấn

Một query local có thể join local tables với foreign tables để trả dữ liệu tổng hợp mà không ETL toàn bộ nguồn.

### 4.2. Tích hợp ứng dụng theo giai đoạn

Ứng dụng có thể chuyển dần truy vấn sang local schema trong khi dữ liệu vẫn ở remote database.

### 4.3. Reporting và read access

Foreign tables có thể hỗ trợ báo cáo từ database nguồn. Cần kiểm soát query concurrency để không làm quá tải hệ thống remote.

### 4.4. Data federation nhỏ và vừa

FDW có thể kết hợp các PostgreSQL sources trong một SQL interface. Với data lake, high-volume analytics hoặc nhiều nguồn dị thể, cân nhắc công cụ federation/ETL phù hợp hơn.

### 4.5. Khi không nên dùng

Nếu cần latency thấp ổn định bất chấp network outage, transaction atomic trên nhiều servers, scan toàn bộ dữ liệu liên tục hoặc workload analytics rất lớn, nên cân nhắc replication, materialized copies, ETL/ELT hay data platform chuyên dụng.

## 5. Cài đặt postgres_fdw

postgres_fdw thường được phân phối trong package contrib tương ứng với PostgreSQL. Cần cài package ở server trước khi tạo extension trong database.

### 5.1. Package availability

Trên Linux, tên package thường theo distro/repository và major version, ví dụ package contrib của PostgreSQL. Trên managed services, kiểm tra extension allowlist của provider.

### 5.2. Cài extension trong database local

~~~sql
CREATE EXTENSION postgres_fdw;
~~~

Lệnh tạo FDW handler/validator objects trong current database. Thực hiện ở database sẽ chứa foreign servers/tables.

### 5.3. Kiểm tra extension

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'postgres_fdw';
~~~

### 5.4. Kiểm tra FDW registration

~~~sql
SELECT
    fdwname,
    fdwowner::regrole AS owner,
    fdwhandler::regproc AS handler,
    fdwvalidator::regproc AS validator
FROM pg_foreign_data_wrapper;
~~~

### 5.5. Mỗi database cần installation riêng

Nếu nhiều databases local cần postgres_fdw, chạy CREATE EXTENSION trong từng database. Cài OS package một lần trên server không tạo extension objects trong mọi database.

## 6. Tạo foreign data wrapper object

CREATE EXTENSION postgres_fdw thường tạo foreign data wrapper có tên postgres_fdw. Trong trường hợp đặc biệt, có thể định nghĩa wrapper object trực tiếp, nhưng thông thường dùng extension package.

### 6.1. Foreign data wrapper

~~~sql
SELECT
    fdwname,
    fdwoptions
FROM pg_foreign_data_wrapper;
~~~

### 6.2. Handler và validator

Handler cung cấp callback implementation; validator kiểm tra options của server/user mapping/table có hợp lệ với FDW hay không.

### 6.3. Wrapper ownership

Owner của wrapper quản lý object và các server phụ thuộc. Cần dùng role quản trị phù hợp.

### 6.4. Wrapper options

Một số FDWs có options ở wrapper level. postgres_fdw thường đặt connection/planning options tại server, user mapping hoặc foreign table theo option scope.

### 6.5. Không tạo wrapper trùng

Nếu extension đã tạo postgres_fdw wrapper, không CREATE FOREIGN DATA WRAPPER cùng tên. Kiểm tra catalog trước khi cài đặt thủ công.

## 7. Tạo foreign server

Foreign server mô tả endpoint remote và thuộc về database local.

~~~sql
CREATE SERVER sales_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'sales-db.example.internal',
    port '5432',
    dbname 'sales'
);
~~~

Đây là endpoint minh họa; thay bằng host/database thật từ deployment configuration.

### 7.1. host

Hostname hoặc địa chỉ remote PostgreSQL. Ưu tiên DNS/service name ổn định và TLS hostname verification.

### 7.2. port

Port PostgreSQL remote, thường là 5432 nếu không đổi. Phải được network policy/firewall cho phép từ local server.

### 7.3. dbname

Tên database ở remote server. Foreign server object kết nối vào database này.

### 7.4. OPTIONS

Options là chuỗi key/value do postgres_fdw/libpq xác định. Validator kiểm tra các options được hỗ trợ.

### 7.5. Server name local

sales_server chỉ là tên object trong local database. Nó không bắt buộc trùng với hostname hoặc remote database name.

## 8. Connection options và TLS

postgres_fdw dùng libpq connection parameters, nên có thể cấu hình một số options kết nối tiêu chuẩn.

### 8.1. sslmode

Với production, ưu tiên cấu hình TLS phù hợp. sslmode='verify-full' yêu cầu chứng thư hợp lệ và hostname khớp; target server cần CA trust đúng.

### 8.2. connect_timeout

Giới hạn thời gian thiết lập kết nối để lỗi endpoint/network không làm query chờ quá lâu trong giai đoạn connect.

### 8.3. application_name

Đặt application_name giúp nhận diện kết nối FDW trong pg_stat_activity phía remote.

### 8.4. keepalives

libpq keepalive options có thể giúp phát hiện kết nối TCP bị đứt theo OS/network behavior. Điều chỉnh theo môi trường thực tế.

### 8.5. Không lưu secrets trong server options

Host/port/dbname thường không phải secret. Remote username/password thuộc user mapping và cần được bảo vệ riêng.

## 9. Kiểm tra foreign server

Catalog pg_foreign_server lưu metadata server object.

~~~sql
SELECT
    srvname,
    srvowner::regrole AS owner,
    fdwname,
    srvoptions
FROM pg_foreign_server AS s
JOIN pg_foreign_data_wrapper AS w
  ON w.oid = s.srvfdw
ORDER BY srvname;
~~~

### 9.1. srvname

Tên foreign server trong database local.

### 9.2. srvowner

Role sở hữu server object. Owner có thể ALTER/DROP object và quản lý privileges.

### 9.3. fdwname

Foreign data wrapper được server sử dụng, ví dụ postgres_fdw.

### 9.4. srvoptions

Các connection/planning options được lưu trên server object. Không đưa password vào đây.

### 9.5. Catalog visibility

Quyền đọc metadata có thể phụ thuộc privileges. Tránh cấp catalog access rộng nếu options có thông tin nhạy cảm.

## 10. Tạo remote role và quyền phía remote

Local user mapping xác thực thành một role trên remote. Role remote cần quyền trên database/schema/tables được truy cập.

### 10.1. Tạo role chỉ đọc ở remote

Trên remote database, DBA có thể tạo role chuyên dùng:

~~~sql
CREATE ROLE fdw_sales_reader
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

Thiết lập password qua secret-management/deployment process phù hợp, không ghi secret vào source code hoặc ticket.

### 10.2. Cấp quyền kết nối

~~~sql
GRANT CONNECT ON DATABASE sales TO fdw_sales_reader;
~~~

### 10.3. Cấp quyền schema

~~~sql
GRANT USAGE ON SCHEMA public TO fdw_sales_reader;
~~~

### 10.4. Cấp quyền đọc

~~~sql
GRANT SELECT ON TABLE public.customers, public.orders
TO fdw_sales_reader;
~~~

### 10.5. Least privilege

Không dùng remote superuser cho application FDW. Cấp quyền đúng tables/operations cần thiết; với writes, cấp INSERT/UPDATE/DELETE riêng theo yêu cầu.

## 11. User mapping là gì?

User mapping nối local role với remote user và authentication options cho một foreign server cụ thể.

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER sales_server
OPTIONS (
    user 'fdw_sales_reader',
    password 'REPLACE_WITH_SECRET'
);
~~~

Ví dụ chỉ ra cấu trúc SQL. Giá trị password phải được cung cấp qua quy trình secret an toàn của môi trường.

### 11.1. Local role

app_reader là role trong database local đang thực hiện query.

### 11.2. Remote user

fdw_sales_reader là account remote mà postgres_fdw dùng để kết nối.

### 11.3. Mapping theo server

Một local role có thể có mappings khác nhau cho các foreign servers khác nhau.

### 11.4. Mapping riêng từng user

Có thể tạo mapping cho nhiều local roles, mỗi mapping dùng remote identity/privileges khác nhau.

### 11.5. Mapping cho PUBLIC

Mapping FOR PUBLIC áp dụng cho local users không có mapping riêng, nhưng cần thận trọng vì có thể chia sẻ remote identity quá rộng.

## 12. User mapping và authentication

Authentication diễn ra khi local backend kết nối tới remote PostgreSQL.

### 12.1. Password option

postgres_fdw có thể dùng user/password options trong mapping. Password là credential remote và cần rotation/protection như secret khác.

### 12.2. .pgpass

libpq có thể dùng password file theo rules của client process khi không truyền password qua mapping. Với service account, kiểm soát owner và permissions của file.

### 12.3. Certificate authentication

Có thể dùng client certificate options theo libpq và cấu hình pg_hba.conf phía remote. Bảo vệ private key và certificate lifecycle.

### 12.4. GSS/SSPI và các auth methods

Authentication methods khả dụng phụ thuộc libpq build, OS và remote pg_hba.conf. Kiểm tra compatibility thực tế.

### 12.5. Remote pg_hba.conf

Remote server phải cho phép kết nối từ local PostgreSQL host/container, database và remote user với authentication method phù hợp.

## 13. User mapping catalog và quyền truy cập

pg_user_mapping lưu mapping metadata; view pg_user_mappings cung cấp dạng dễ đọc hơn.

~~~sql
SELECT
    s.srvname,
    u.umuser::regrole AS local_user,
    u.umoptions
FROM pg_user_mapping AS u
JOIN pg_foreign_server AS s
  ON s.oid = u.umserver
ORDER BY s.srvname, local_user;
~~~

### 13.1. Mapping cho PUBLIC

umuser bằng zero biểu thị mapping cho PUBLIC. Có thể kiểm tra bằng catalog query nhưng cần diễn giải cẩn thận.

### 13.2. pg_user_mappings

View này hiển thị user mappings và áp dụng masking cho password option tùy quyền người xem.

### 13.3. Password visibility

Superusers và mapping owner có thể có quyền xem options nhạy cảm; không cấp quyền xem mapping metadata cho người không cần thiết.

### 13.4. Ownership

Role sở hữu mapping/server và quyền USAGE quyết định ai được phép dùng foreign server. Review grants trước khi cấp application access.

### 13.5. Credential rotation

ALTER USER MAPPING có thể cập nhật options, ví dụ password, mà không cần drop/recreate mapping. Sau rotation, test kết nối mới và xác nhận old credential đã bị thu hồi.

## 14. Cấp quyền sử dụng foreign server

Tạo server và user mapping chưa tự động cho mọi role được phép sử dụng.

~~~sql
GRANT USAGE ON FOREIGN SERVER sales_server TO app_reader;
~~~

### 14.1. USAGE privilege

Role cần USAGE trên foreign server để sử dụng server thông qua foreign tables.

### 14.2. Schema privilege local

Role cũng cần USAGE trên local schema chứa foreign tables.

### 14.3. Table privilege local

Cấp SELECT/INSERT/UPDATE/DELETE trên foreign tables theo nhu cầu. Remote permissions vẫn được kiểm tra ở remote server.

### 14.4. Không cấp server usage rộng

USAGE cho PUBLIC hoặc nhiều application roles có thể mở rộng khả năng sử dụng remote connection mappings. Cấp đúng role.

### 14.5. Hai lớp authorization

Local privileges quyết định ai được query foreign table; remote privileges quyết định remote user được đọc/ghi dữ liệu gì. Cần kiểm tra cả hai.

## 15. Tạo schema local cho foreign tables

Foreign tables cần nằm trong schema local, độc lập với schema remote.

~~~sql
CREATE SCHEMA remote_sales AUTHORIZATION db_owner;
GRANT USAGE ON SCHEMA remote_sales TO app_reader;
~~~

### 15.1. Local namespace

remote_sales là schema ở local database, có thể khác remote schema public.

### 15.2. Tách namespace

Schema riêng giúp phân biệt remote objects với local tables và tránh name collisions.

### 15.3. Owner

Chọn deployment/DBA role làm owner. Application runtime chỉ cần grants cần thiết.

### 15.4. Search path

Không nên dựa vào search_path mơ hồ khi tên foreign tables trùng với local relations. Dùng schema-qualified names trong SQL quan trọng.

### 15.5. Schema lifecycle

Schema local không tự được đồng bộ với remote schema. DDL thay đổi ở remote cần migration/refresh thủ công hoặc automation riêng.


## 16. Import foreign schema

IMPORT FOREIGN SCHEMA tạo nhiều foreign tables local từ các relations trong remote schema.

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 16.1. Remote schema

public là schema ở remote database. Đây không nhất thiết là schema local nơi foreign tables được tạo.

### 16.2. LIMIT TO

Chỉ import các tables/views được liệt kê. Hữu ích khi chỉ cần một tập objects nhỏ.

### 16.3. EXCEPT

Có thể dùng EXCEPT để import tất cả objects trong remote schema trừ danh sách loại trừ.

~~~sql
IMPORT FOREIGN SCHEMA public
EXCEPT (audit_log, internal_events)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 16.4. Không copy dữ liệu

IMPORT FOREIGN SCHEMA tạo metadata/foreign table definitions trong local catalog. Rows vẫn nằm trên remote server.

### 16.5. Chạy lại import

IMPORT FOREIGN SCHEMA không phải cơ chế đồng bộ schema tự động. Nếu foreign tables đã tồn tại, cần xử lý conflict và thay đổi DDL theo migration plan.

## 17. Options của IMPORT FOREIGN SCHEMA

IMPORT FOREIGN SCHEMA hỗ trợ options do FDW validator cung cấp.

### 17.1. import_collate

Một số versions hỗ trợ import_collate để điều khiển cách collation metadata được nhập. Kiểm tra documentation của major version đang chạy trước khi dùng.

### 17.2. import_default

Một số versions hỗ trợ import_default để quyết định có nhập default expressions hay không. Default remote expression không nhất thiết có thể thực thi tương đương ở local.

### 17.3. Version awareness

Import options có thể thay đổi theo PostgreSQL major version. Dùng pg_available_extension_versions và documentation tương ứng, không copy options không được version hỗ trợ.

### 17.4. Type mapping

FDW ánh xạ remote column types sang local types. Kiểm tra numeric precision, timestamp/time zone, arrays, enums, domains và extension types.

### 17.5. Review generated definitions

Sau import, đọc foreign table definitions/catalog options và test representative queries. Không coi import thành công là bảo đảm schema contract hoàn toàn tương thích.

## 18. Tạo foreign table thủ công

Có thể định nghĩa một foreign table cụ thể bằng CREATE FOREIGN TABLE.

~~~sql
CREATE FOREIGN TABLE remote_sales.orders (
    order_id bigint,
    customer_id bigint,
    status text,
    created_at timestamptz,
    total_amount numeric(12,2)
)
SERVER sales_server
OPTIONS (
    schema_name 'public',
    table_name 'orders'
);
~~~

### 18.1. Column definitions

Columns local cần khớp types/semantics remote đủ để đọc và ghi an toàn. FDW không lưu data để tự chuyển đổi mọi mismatch.

### 18.2. SERVER clause

Liên kết foreign table với foreign server object đã tạo.

### 18.3. schema_name

Chỉ định schema remote chứa relation. Nếu bỏ qua, postgres_fdw dùng schema mặc định theo behavior của FDW.

### 18.4. table_name

Tên relation remote. Có thể khác tên foreign table local.

### 18.5. Foreign table name

remote_sales.orders là tên local. Remote relation được xác định bởi server cùng schema_name/table_name options.

## 19. Mapping column names

Foreign table local có thể dùng tên columns khác với remote relation thông qua column options.

~~~sql
CREATE FOREIGN TABLE remote_sales.customer_summary (
    customer_key bigint OPTIONS (column_name 'customer_id'),
    customer_name text OPTIONS (column_name 'name'),
    lifetime_value numeric OPTIONS (column_name 'total_value')
)
SERVER sales_server
OPTIONS (
    schema_name 'reporting',
    table_name 'customer_summary'
);
~~~

### 19.1. column_name

Option này map local column sang remote column name. Hữu ích khi local naming conventions khác nguồn.

### 19.2. Column order

Không nên dựa vào thứ tự columns để map. Column names/options và types phải được xác định rõ.

### 19.3. Type compatibility

Local type phải tương thích với remote type representation. Type mismatch có thể gây error khi fetch/convert hoặc làm semantics khác.

### 19.4. Quoted identifiers

Remote identifiers có chữ hoa/chữ thường hoặc ký tự đặc biệt cần được ghi đúng theo PostgreSQL identifier rules và option values.

### 19.5. Schema drift

Nếu remote rename/drop column, foreign table definition local không tự đổi. Query có thể fail tới khi local metadata được cập nhật.

## 20. Foreign table metadata và catalog

pg_foreign_table lưu server reference và options cho mỗi foreign table.

~~~sql
SELECT
    n.nspname AS local_schema,
    c.relname AS foreign_table,
    s.srvname AS foreign_server,
    ft.ftoptions
FROM pg_foreign_table AS ft
JOIN pg_class AS c ON c.oid = ft.ftrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_foreign_server AS s ON s.oid = ft.ftserver
ORDER BY 1, 2;
~~~

### 20.1. pg_foreign_table

Catalog này chứa metadata riêng của foreign table, bao gồm server OID và table options.

### 20.2. pg_class

Foreign tables là relations trong catalog và có relkind tương ứng foreign table. Có thể inspect qua pg_class.

### 20.3. pg_attribute

Column definitions nằm trong catalog attributes. Dùng information_schema.columns hoặc pg_attribute để xem local schema.

### 20.4. information_schema.foreign_tables

View information_schema.foreign_tables cung cấp inventory ở dạng chuẩn SQL.

### 20.5. DDL source of truth

Giữ foreign table definitions trong migration/source control. Không dựa duy nhất vào catalog queries khi cần tái tạo môi trường.

## 21. Thay đổi foreign table definition

ALTER FOREIGN TABLE sửa metadata local của foreign table.

### 21.1. Đổi remote table mapping

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (SET table_name 'orders_archive');
~~~

Thao tác này thay option local; nó không đổi tên relation ở remote.

### 21.2. Đổi schema remote

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (SET schema_name 'sales');
~~~

Sau khi đổi, kiểm tra relation tồn tại và quyền remote role.

### 21.3. Add/drop column

ALTER FOREIGN TABLE có thể cập nhật local column definition. Cần phối hợp với remote DDL và application code.

### 21.4. Không đồng bộ remote DDL

ALTER FOREIGN TABLE không thực hiện ALTER TABLE trên remote server. Nó chỉ thay metadata local.

### 21.5. Migration an toàn

Thay đổi remote schema trước/sau local theo compatibility plan. Nếu remote drop column trước khi local queries ngừng dùng, requests có thể fail.

## 22. Kiểm tra định nghĩa foreign tables

Dùng psql meta-command hoặc catalog queries để xem foreign table definitions.

~~~sql
\d+ remote_sales.orders
~~~

### 22.1. psql describe

\d+ hiển thị columns, foreign server và options tùy psql version.

### 22.2. pg_get_userbyid

Có thể kết hợp pg_class.relowner và pg_get_userbyid để kiểm tra owner.

### 22.3. Column inventory

Đối chiếu local foreign columns với remote information_schema.columns qua query/metadata workflow được kiểm soát.

### 22.4. Server association

Mỗi foreign table gắn với một foreign server. Đổi server thường cần tạo foreign table mới hoặc migration có kiểm soát.

### 22.5. Review options

Kiểm tra schema_name/table_name, column_name mappings và planner/fetch options trước khi chạy workload.

## 23. Truy vấn foreign tables

Sau khi có server, mapping, privileges và foreign table, truy vấn như relation local.

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM remote_sales.orders
WHERE status = 'open'
ORDER BY created_at DESC
LIMIT 50;
~~~

### 23.1. Remote execution

postgres_fdw có thể chuyển phần scan/filter/order/limit phù hợp sang remote server thay vì tải toàn bộ rows về local.

### 23.2. Network dependency

Query phụ thuộc network, DNS, TLS, remote availability và remote load. Local server không thể trả dữ liệu mới nếu remote unavailable.

### 23.3. Result transfer

Rows không được pushdown phải được truyền qua network về local executor. Result set lớn làm tăng bandwidth, memory và latency.

### 23.4. Local joins

Foreign tables có thể join với local tables. Planner quyết định join location; không phải mọi join đều được pushdown.

### 23.5. Read semantics

Foreign table query trả dữ liệu theo remote transaction/snapshot behavior. Không mặc định nó có cùng freshness với local cache/replica.

## 24. DML qua postgres_fdw

postgres_fdw hỗ trợ thao tác ghi trên foreign tables khi remote relation và mapping cho phép.

### 24.1. INSERT

~~~sql
INSERT INTO remote_sales.orders
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (9001, 101, 'new', now(), 125.50);
~~~

### 24.2. UPDATE

~~~sql
UPDATE remote_sales.orders
SET status = 'shipped'
WHERE order_id = 9001;
~~~

### 24.3. DELETE

~~~sql
DELETE FROM remote_sales.orders
WHERE order_id = 9001;
~~~

### 24.4. Remote privileges

Remote role cần quyền INSERT/UPDATE/DELETE tương ứng. Local table grants và remote table grants đều phải đúng.

### 24.5. Updatability

Một số foreign tables/queries không updatable hoặc bị hạn chế theo relation/FDW options. Xem postgres_fdw documentation và EXPLAIN cho statement cụ thể.

## 25. UPDATE và DELETE row identity

Để cập nhật/xóa row remote, postgres_fdw cần xác định row identity đủ chính xác.

### 25.1. Primary key

Remote primary key giúp xác định row ổn định và là lựa chọn tốt cho foreign table definition.

### 25.2. Row identity

PostgreSQL có cơ chế row identity cho foreign tables; postgres_fdw sử dụng columns phù hợp để xác định tuple remote cần update/delete.

### 25.3. Không có primary key

Một số foreign tables có thể update/delete theo các columns được chọn làm row identity hoặc theo behavior/version cụ thể. Không nên thiết kế write workload dựa trên identity không duy nhất.

### 25.4. Concurrent changes

Remote row có thể bị thay đổi bởi sessions khác. Remote constraints/transaction isolation quyết định kết quả; xử lý serialization/conflict errors ở application.

### 25.5. Test DML

Test insert/update/delete trên staging, gồm concurrent updates, constraints, triggers, defaults và remote generated values.

## 26. TRUNCATE và foreign tables

postgres_fdw hỗ trợ TRUNCATE foreign tables khi FDW/table configuration cho phép và remote role có quyền.

### 26.1. Remote truncation

TRUNCATE trên foreign table gửi thao tác tương ứng tới remote relation. Nó có thể ảnh hưởng nhiều rows ngay lập tức.

### 26.2. Privileges

Remote role cần TRUNCATE privilege ở remote table. Local user cũng cần quyền tương ứng trên foreign table.

### 26.3. Cascading behavior

Không giả định local TRUNCATE CASCADE sẽ hoạt động giống mọi local table relationship; foreign relations và remote dependencies có giới hạn riêng.

### 26.4. Explicit approval

TRUNCATE là destructive. Hạn chế grants và dùng transaction/change controls phù hợp.

### 26.5. Validation

Xác nhận remote row counts/constraints và downstream effects trước khi đưa vào application workflow.

## 27. Local constraints và remote constraints

Foreign table definition có thể mô tả columns và một số constraints, nhưng cần hiểu constraints nào thực sự được enforce.

### 27.1. Remote constraints

Primary keys, unique constraints, foreign keys, CHECK constraints và NOT NULL trên remote relation được enforce bởi remote PostgreSQL.

### 27.2. Local metadata

Foreign table local không tự import đầy đủ indexes/constraints như một bản sao của remote table. IMPORT FOREIGN SCHEMA chủ yếu tạo column/table definitions.

### 27.3. Planner assumptions

Nếu khai báo constraints local trên foreign table, planner có thể dựa vào chúng như metadata. Chỉ khai báo khi đảm bảo chúng luôn đúng ở remote; local FDW không kiểm tra mọi thay đổi remote.

### 27.4. Remote DDL drift

Nếu remote constraints/data semantics thay đổi, local assumptions có thể sai và dẫn tới kết quả query không đúng nếu planner dựa vào chúng.

### 27.5. Data integrity

Đặt constraints chính thức ở remote owner database. Local layer nên phản ánh assumptions đã được xác minh, không tự tạo ràng buộc giả.


## 28. Predicate pushdown

Predicate pushdown là chuyển điều kiện lọc sang remote server để remote chỉ trả rows cần thiết.

### 28.1. Filter local hay remote

Nếu điều kiện WHERE được pushdown, remote PostgreSQL thực hiện filter trước khi truyền rows về local. Nếu không, local executor có thể phải nhận nhiều rows rồi mới lọc.

### 28.2. Shippable expressions

postgres_fdw chỉ pushdown expressions mà nó xác định an toàn và có semantics tương thích ở remote. Built-in operators/functions phù hợp thường có thể được pushdown.

### 28.3. Functions và operators

Function volatility, collation, type semantics và extension availability ảnh hưởng khả năng pushdown. Không giả định mọi function trong WHERE đều chạy remote.

### 28.4. Kiểm tra remote SQL

Dùng EXPLAIN VERBOSE để xem Remote SQL trong Foreign Scan node. Đây là cách thực tế để biết filter nào được gửi sang remote.

### 28.5. Giảm data transfer

Predicate pushdown thường giảm network bytes, remote result size và local executor work. Viết query rõ ràng, tránh wrapping columns bằng expressions không cần thiết.

## 29. Join pushdown

postgres_fdw có thể thực hiện join trên remote khi các foreign tables cùng server và planner xác định phép join có thể ship an toàn.

### 29.1. Same foreign server

Foreign tables gắn cùng foreign server có cơ hội join pushdown. Tables từ hai servers khác nhau thường không thể được join thành một remote query duy nhất.

### 29.2. Safe join conditions

Join expressions và collations phải có semantics tương thích. Điều kiện chứa local-only expressions có thể khiến join diễn ra ở local.

### 29.3. Remote join

Khi join pushdown thành công, remote PostgreSQL xử lý join và chỉ trả result rows cần thiết về local.

### 29.4. Local/remote join

Nếu join không pushdown, local executor có thể fetch rows từ từng foreign relation rồi join tại local. Network transfer có thể tăng mạnh.

### 29.5. EXPLAIN evidence

Xem Foreign Scan/Remote SQL và rows estimates. Kiểm tra remote query có chứa JOIN hay local plan có nhiều foreign scans độc lập.

## 30. Aggregate, sort và LIMIT pushdown

Một số operations có thể được thực hiện trên remote để giảm lượng dữ liệu truyền.

### 30.1. Aggregate pushdown

Các aggregate/grouping expressions phù hợp có thể được ship nếu semantics và safety requirements được đáp ứng.

### 30.2. ORDER BY

Sort có thể được pushdown khi remote ordering semantics tương thích. Collation differences có thể ngăn pushdown.

### 30.3. LIMIT/OFFSET

LIMIT/OFFSET có thể được pushdown trong điều kiện phù hợp. Nếu local executor còn cần xử lý rows trước khi kết quả cuối cùng được xác định, LIMIT có thể ở local.

### 30.4. HAVING

HAVING có thể được ship cùng aggregate khi các expressions liên quan đều shippable.

### 30.5. Verify, do not assume

Dùng EXPLAIN VERBOSE để xem Remote SQL thực tế. Một query syntax gọn không chứng minh mọi operation được thực thi remote.

## 31. EXPLAIN foreign query

EXPLAIN giúp phân biệt network transfer, remote execution và local processing.

~~~sql
EXPLAIN (VERBOSE, COSTS, SETTINGS)
SELECT
    customer_id,
    count(*)
FROM remote_sales.orders
WHERE status = 'open'
GROUP BY customer_id;
~~~

### 31.1. Foreign Scan

Foreign Scan node biểu thị local executor lấy rows từ foreign data source.

### 31.2. Remote SQL

VERBOSE thường hiển thị câu SQL được gửi tới remote server. Kiểm tra filter/join/group/order/limit có được pushdown không.

### 31.3. Estimated rows

So estimated rows của Foreign Scan với actual rows trong EXPLAIN ANALYZE trên test environment. Estimate sai có thể dẫn tới local join order kém.

### 31.4. EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi query thật và có thể tạo tải trên remote. Chỉ chạy khi workload, side effects và remote capacity đã được xem xét.

### 31.5. Remote-side plan

Local EXPLAIN không phải lúc nào cũng cung cấp đầy đủ chi tiết plan bên trong remote query. Chạy EXPLAIN/monitoring ở remote server với câu Remote SQL khi cần.


## 32. use_remote_estimate

postgres_fdw có option use_remote_estimate để yêu cầu remote server cung cấp estimates thay vì chỉ dựa trên local estimates.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD use_remote_estimate 'true');
~~~

### 32.1. Local estimates

Mặc định, local planner có thể ước lượng foreign table scan dựa trên local metadata/statistics có sẵn và FDW cost settings.

### 32.2. Remote estimates

Khi bật use_remote_estimate, postgres_fdw gửi EXPLAIN tới remote để lấy estimates. Điều này có thể cải thiện planning cho remote data distribution phức tạp.

### 32.3. Planning overhead

Remote EXPLAIN cần network round trips và remote planning CPU. Với nhiều foreign scans/queries, planning latency có thể tăng.

### 32.4. Statistics locality

Local ANALYZE trên foreign table có thể lấy sample từ remote để tạo local stats. Cân nhắc remote estimates và local stats theo workload.

### 32.5. Chọn bằng benchmark

So planning time, plan quality, execution time và remote load trước/sau. Không bật global cho mọi server mà không đo.

## 33. FDW cost options

postgres_fdw cung cấp cost parameters để local planner ước lượng foreign scan.

### 33.1. fdw_startup_cost

Đại diện chi phí khởi tạo foreign scan, bao gồm kết nối/remote query setup ở mức planner model.

### 33.2. fdw_tuple_cost

Đại diện chi phí xử lý/truyền mỗi tuple từ remote về local.

### 33.3. Cost model không phải runtime guarantee

Các costs là planner units, không phải milliseconds. Điều chỉnh dựa trên observed network/remote behavior.

### 33.4. Per-server behavior

Có thể đặt options trên foreign server để phản ánh latency/throughput khác nhau giữa remote endpoints.

### 33.5. Tránh ép plan

Cost tuning sai có thể khiến planner chọn join order hoặc scan strategy kém. Dùng EXPLAIN và workload benchmark để xác nhận.

## 34. fetch_size và network round trips

fetch_size điều khiển số rows postgres_fdw lấy mỗi batch trong quá trình scan.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD fetch_size '500');
~~~

### 34.1. Batch fetching

Lấy nhiều rows mỗi round trip có thể giảm protocol/network overhead khi result set lớn.

### 34.2. Memory trade-off

fetch_size lớn hơn có thể tăng memory giữ rows ở local backend. Với nhiều concurrent foreign scans, memory pressure có thể tăng.

### 34.3. Small result sets

Với queries trả ít rows, tăng fetch_size có thể không mang lại lợi ích đáng kể.

### 34.4. Table-level override

Có thể đặt fetch_size ở foreign table nếu một relation có access pattern khác với các tables cùng server, theo option support của version.

### 34.5. Benchmark

Đo latency, network round trips, backend memory và concurrency. Không có một fetch_size tối ưu cho mọi workloads.

## 35. batch_size cho bulk inserts

batch_size cho phép postgres_fdw gom nhiều inserted rows vào một remote INSERT statement khi điều kiện hỗ trợ.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD batch_size '100');
~~~

### 35.1. Giảm round trips

Batch insert có thể giảm số lần trao đổi network và cải thiện throughput cho bulk DML.

### 35.2. Giới hạn batch

Batch size quá lớn có thể tăng memory, statement size, lock duration và chi phí rollback.

### 35.3. Row compatibility

Các rows phải phù hợp với batch execution conditions; triggers/defaults/returning semantics hoặc query shape có thể ảnh hưởng batching.

### 35.4. Table-specific setting

Nếu chỉ một foreign table nhận bulk inserts, cân nhắc cấu hình riêng theo supported table options.

### 35.5. Test remote capacity

Remote server vẫn thực hiện writes, WAL, indexes và triggers. Batching không làm giảm công việc dữ liệu thực tế, chỉ giảm overhead giao tiếp.

## 36. Async-capable foreign scans

Một số PostgreSQL versions hỗ trợ async execution cho foreign scans khi FDW và plan có thể thực hiện song song/asynchronously.

### 36.1. async_capable option

postgres_fdw cung cấp option async_capable ở các versions hỗ trợ. Mặc định và behavior cần xác nhận theo major version.

### 36.2. Parallel foreign scans

Asynchronous execution có thể cho phép local executor overlap remote operations thay vì chờ từng foreign scan tuần tự.

### 36.3. Điều kiện plan

Không phải mọi foreign scans đều có thể async. Plan shape, remote server association và executor support ảnh hưởng khả năng sử dụng.

### 36.4. Remote concurrency

Async có thể làm nhiều remote queries chạy cùng lúc, tăng tải remote server và network. Kiểm soát concurrency theo capacity.

### 36.5. Validate execution

Xem EXPLAIN output và remote pg_stat_activity để xác nhận query concurrency thực tế. Không bật chỉ vì option tồn tại.

## 37. ANALYZE trên foreign tables

ANALYZE có thể lấy sample từ foreign tables để tạo local planner statistics.

~~~sql
ANALYZE remote_sales.orders;
~~~

### 37.1. Remote sampling

postgres_fdw đọc sample rows từ remote theo cơ chế FDW sampling. Điều này tạo network/remote I/O và có thể ảnh hưởng source workload.

### 37.2. Local pg_stats

Statistics được lưu trong local database và giúp local planner ước lượng foreign relation khi không dùng remote estimates.

### 37.3. Freshness

Nếu remote data thay đổi nhanh, local stats có thể nhanh chóng stale. Lên lịch analyze phù hợp hoặc dùng remote estimates nếu benchmark chứng minh lợi ích.

### 37.4. Auto-analyze

Autovacuum/analyze behavior trên foreign tables phụ thuộc PostgreSQL version và FDW support; không giả định remote source tự kích hoạt local auto-analyze khi data đổi.

### 37.5. Sampling cost

Analyze foreign tables có thể đọc nhiều dữ liệu qua network. Giới hạn phạm vi/columns và theo dõi impact ở remote.


## 38. Remote-side indexes và query optimization

Index nằm trên remote server. Local foreign table không tạo index vật lý cho dữ liệu remote.

### 38.1. Index remote

Tạo index trên remote relation theo query patterns được pushdown. Dùng remote EXPLAIN để xác nhận remote plan dùng index.

### 38.2. Local index metadata

Foreign table không lưu remote index definitions như local indexes. Local planner cần estimates/options riêng.

### 38.3. Pushdown trước index

Index chỉ giúp nếu remote query chứa predicates/join/order có thể sử dụng index. Nếu filter được thực hiện local, remote vẫn có thể scan nhiều rows.

### 38.4. Remote statistics

ANALYZE remote tables để remote planner có statistics tốt. Local ANALYZE foreign table không thay thế analyze trên source.

### 38.5. Workload isolation

Foreign query có thể chiếm CPU/I/O ở source. Dùng remote roles, statement_timeout, resource controls và workload scheduling.

## 39. Join foreign và local tables

Join giữa local table và foreign table có thể được thực hiện local, trừ khi có cơ hội pushdown trong cùng remote server.

### 39.1. Local-to-foreign join

Ví dụ join local customers với foreign orders. Local executor có thể phải fetch một phía hoặc cả hai tùy plan.

~~~sql
SELECT c.customer_name, o.order_id
FROM app.customers AS c
JOIN remote_sales.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region = 'north';
~~~

### 39.2. Data transfer

Nếu remote filter không nhận được local join keys, có thể phải truyền nhiều rows về local. Query shape và join order rất quan trọng.

### 39.3. Parameterized paths

Planner có thể dùng parameterized foreign paths trong một số điều kiện để gửi lookup keys/predicates sang remote. Xem plan và remote SQL.

### 39.4. Materialize local keys

Với một số workloads, tạm đưa key set vào remote staging table hoặc ETL có thể hiệu quả hơn nhiều round trips. Cần thiết kế consistency/lifecycle.

### 39.5. Federation boundary

Nếu query thường xuyên join lượng dữ liệu lớn giữa nhiều remote servers, cân nhắc materialized copy/replication hoặc data integration pipeline.

## 40. Remote query timeout và connection behavior

Một foreign query có thể chờ lâu do connect, remote execution hoặc transfer.

### 40.1. connect_timeout

Giới hạn thời gian mở kết nối qua libpq. Nó không giới hạn thời gian query remote sau khi đã kết nối.

### 40.2. statement_timeout

Có thể cấu hình timeout phù hợp ở local session/role và remote role. Kiểm tra statement thực sự được cancel ở cả hai phía.

### 40.3. lock_timeout

Remote DML/DDL có thể chờ locks tại remote. Lock timeout cần được áp dụng ở nơi statement thực thi.

### 40.4. Network interruption

TCP connection drop có thể làm local query fail. Không tự động giả định remote transaction đã rollback nếu client không nhận được kết quả cuối.

### 40.5. Retry safety

Retry SELECT thường đơn giản hơn DML. Với write có thể remote đã commit nhưng local client mất response; dùng idempotency keys/unique constraints và reconciliation.

## 41. Transaction behavior qua postgres_fdw

postgres_fdw mở remote transactions để thực hiện các operations trong local transaction.

### 41.1. Remote transaction

Khi foreign table được truy cập, FDW có thể mở connection và transaction remote tương ứng. Remote statements chạy trong transaction đó.

### 41.2. Local commit/rollback

Local COMMIT/ROLLBACK điều khiển kết thúc remote transaction theo FDW transaction callbacks. DML remote có thể được commit/rollback theo transaction local trong các điều kiện hoạt động bình thường.

### 41.3. Snapshot behavior

Queries trong một local transaction cần quan sát remote data theo transaction/snapshot behavior mà postgres_fdw và isolation level hỗ trợ. Test semantics với isolation levels cụ thể nếu ứng dụng phụ thuộc repeatable reads.

### 41.4. Savepoints/subtransactions

FDW có hỗ trợ subtransaction handling theo cơ chế PostgreSQL; lỗi trong subtransaction có thể rollback phần work tương ứng. Test các edge cases và version behavior.

### 41.5. Không phải distributed 2PC

postgres_fdw không cung cấp distributed two-phase commit đầy đủ cho nhiều remote servers. Transaction ghi qua nhiều remotes có thể không atomic nếu một remote commit thành công và một remote khác thất bại.

## 42. Nhiều foreign servers trong cùng transaction

Một local query có thể truy cập nhiều remote servers, nhưng distributed transaction guarantees có giới hạn.

### 42.1. Independent remote connections

Mỗi foreign server/user mapping có thể sử dụng connection riêng. Một local transaction có thể mở nhiều remote transactions.

### 42.2. Commit ordering

Remote transactions được commit thông qua FDW transaction handling. Không có coordinator 2PC đảm bảo atomic commit trên tất cả remote servers.

### 42.3. Partial commit risk

Nếu một remote commit thành công rồi remote khác lỗi, trạng thái có thể không đồng nhất. Application cần reconciliation/compensation strategy.

### 42.4. Local rollback limits

Local rollback không thể đảo ngược một remote transaction đã commit thành công trước đó.

### 42.5. Transaction boundary design

Tránh business-critical atomic writes trên nhiều remote servers. Ưu tiên một authoritative writer, outbox/saga pattern hoặc replication pipeline.

## 43. Isolation levels và consistency

Consistency cần được thiết kế theo cách ứng dụng đọc và ghi qua FDW.

### 43.1. Local transaction isolation

Local isolation level ảnh hưởng snapshots và concurrency semantics. postgres_fdw ánh xạ remote transaction behavior theo implementation/version; kiểm tra tài liệu và test khi cần guarantees cụ thể.

### 43.2. Remote concurrent writers

Remote applications khác có thể sửa rows cùng lúc. Local foreign query không ngăn các remote writers trừ khi lock/transaction semantics áp dụng.

### 43.3. Read-after-write

Sau khi ghi qua foreign table trong cùng transaction, các reads remote tiếp theo có thể thấy thay đổi theo transaction semantics. Kiểm tra với isolation level/connection thực tế.

### 43.4. Cross-database snapshots

Không có một global snapshot đồng bộ giữa nhiều remote PostgreSQL servers. Query join nhiều sources có thể quan sát các thời điểm khác nhau.

### 43.5. Business consistency

Nếu nghiệp vụ cần global consistency, dùng data ownership, event ordering, distributed coordination hoặc materialized synchronized data thay vì dựa vào FDW alone.

## 44. Remote locks và contention

DML qua postgres_fdw lấy locks ở remote server, có thể chờ transaction remote khác.

### 44.1. Lock location

Foreign table DML không chỉ lock local metadata; thao tác ghi/lock tương ứng diễn ra trên remote relation.

### 44.2. Blocking sessions

Điều tra pg_stat_activity và pg_locks ở remote để tìm blocker. Local session có thể đang chờ network/remote response.

### 44.3. Deadlocks

Deadlock có thể xảy ra giữa remote transactions hoặc phối hợp với local locks. Thiết kế lock acquisition order và transaction scope ngắn.

### 44.4. Lock timeout

Đặt lock_timeout phù hợp ở remote role/session để ngăn FDW write chờ vô hạn. Test timeout propagation.

### 44.5. Long transactions

Transaction local dài có thể giữ remote transaction/connection lâu. Commit sớm và tránh chờ user/external services trong transaction.


## 45. Connection caching

postgres_fdw có thể giữ và tái sử dụng remote connections trong vòng đời local backend process.

### 45.1. Giảm connect overhead

Tái sử dụng connection tránh phải thiết lập TCP/TLS/authentication cho mỗi statement.

### 45.2. Connection theo mapping

Remote connection gắn với foreign server và local user mapping/remote identity. Một local backend có thể mở nhiều connections tới các servers/mappings khác nhau.

### 45.3. Pool multiplication

Nếu application có nhiều local PostgreSQL backends, mỗi backend có thể duy trì remote connections riêng. Remote connection count có thể lớn hơn dự kiến.

### 45.4. Credentials thay đổi

Sau khi ALTER USER MAPPING, kiểm tra behavior của các connections đang cache và tạo kết nối mới để xác nhận credential rotation có hiệu lực.

### 45.5. Quản lý disconnect

postgres_fdw cung cấp helper functions để xem/ngắt cached connections ở các versions hỗ trợ, như postgres_fdw_get_connections và postgres_fdw_disconnect. Kiểm tra function signature của version trước khi dùng.

## 46. Quản lý server và user mappings

Các DDL commands cho phép thay đổi endpoint, credentials và privileges mà không phải tạo lại mọi foreign tables.

### 46.1. ALTER SERVER

~~~sql
ALTER SERVER sales_server
OPTIONS (SET host 'sales-db-new.example.internal');
~~~

Thay endpoint cần kiểm tra TLS, DNS, remote pg_hba.conf và availability trước khi mở workload.

### 46.2. ALTER USER MAPPING

~~~sql
ALTER USER MAPPING FOR app_reader
SERVER sales_server
OPTIONS (SET password 'REPLACE_WITH_ROTATED_SECRET');
~~~

Thực hiện qua secret-safe deployment path; không commit secret literal vào migration repository.

### 46.3. DROP USER MAPPING

~~~sql
DROP USER MAPPING FOR app_reader
SERVER sales_server;
~~~

Lệnh này xóa mapping local, không xóa remote role.

### 46.4. DROP SERVER

~~~sql
DROP SERVER sales_server RESTRICT;
~~~

RESTRICT mặc định ngăn drop nếu foreign tables/user mappings phụ thuộc. CASCADE có thể xóa dependent objects và cần impact review.

### 46.5. Foreign data wrapper lifecycle

DROP FOREIGN DATA WRAPPER bị chặn nếu còn servers phụ thuộc trừ khi dùng CASCADE. Thông thường chỉ gỡ postgres_fdw extension sau khi đã xử lý mọi foreign servers/tables.

## 47. Monitoring ở local PostgreSQL

Local server cho biết ứng dụng nào đang dùng FDW và query đang chờ/thực thi.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

### 47.1. Application identity

Đặt application_name ở local app và remote connection options để trace request qua hai servers.

### 47.2. Query duration

Local query duration bao gồm planning/execution và có thể bao gồm remote connect, remote work, network transfer và local processing.

### 47.3. Wait events

Kiểm tra wait_event_type/event theo PostgreSQL version để nhận diện backend đang chờ resource hoặc FDW-related activity nếu được instrument.

### 47.4. Connection count

Đếm local sessions theo app/user và so sánh remote pg_stat_activity. Chênh lệch có thể do connection caching, pooling và backend lifecycle.

### 47.5. Query logging

Dùng log_min_duration_statement hoặc tracing ở local; tránh ghi secrets hoặc sensitive result values.

## 48. Monitoring ở remote PostgreSQL

Remote server là nơi thực thi pushed SQL và giữ data/locks/indexes.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE application_name LIKE 'fdw-%'
   OR application_name = 'fdw-local-reporting'
ORDER BY query_start NULLS LAST;
~~~

### 48.1. Remote application_name

Cấu hình application_name trong foreign server options để nhận diện FDW sessions dễ hơn.

### 48.2. Client address

Xác định connections đến từ local PostgreSQL hosts, NAT/proxy hoặc application nodes.

### 48.3. Remote query plan

Lấy Remote SQL từ local EXPLAIN VERBOSE và chạy EXPLAIN ở remote để xem index usage, rows estimates và remote execution cost.

### 48.4. Remote locks

Kiểm tra pg_locks, pg_blocking_pids và long transactions trên remote. Local backend có thể đang chờ một blocker mà chỉ remote mới nhìn thấy.

### 48.5. Source workload impact

Theo dõi remote CPU, disk I/O, buffer cache, connections, WAL và p95/p99 của native remote applications. FDW không được phép làm suy giảm source service ngoài budget.

## 49. Connection count và capacity planning

FDW tạo workload trên cả hai database và network path giữa chúng.

### 49.1. Local backends

Mỗi local client backend có thể tạo remote connection theo foreign server/user mapping khi cần.

### 49.2. Remote sessions

Ước lượng remote sessions theo số local backend processes, active mappings và connection reuse. Không chỉ tính số application instances.

### 49.3. Remote max_connections

Giữ headroom cho native applications, administration, replication và FDW traffic. Tránh để FDW consume toàn bộ remote connection slots.

### 49.4. Pooling

Connection pooler trước local PostgreSQL có thể giảm local backends; tuy nhiên transaction/session pooling mode và FDW connection cache behavior cần được test.

### 49.5. Concurrency caps

Giới hạn parallel queries, application concurrency và scheduled FDW jobs để bảo vệ remote capacity.

## 50. Schema drift và đồng bộ metadata

Foreign table metadata không tự cập nhật khi remote schema thay đổi.

### 50.1. Remote add column

Remote thêm column không tự thêm column vào foreign table local. Cần ALTER FOREIGN TABLE hoặc import/update definition theo migration plan.

### 50.2. Remote rename/drop column

Local foreign table vẫn tham chiếu remote column cũ và queries có thể fail. Thay đổi cần được phối hợp hai phía.

### 50.3. Type changes

Remote type widening/narrowing có thể không tương thích với local definition. Kiểm tra precision, nullability, casts và application expectations.

### 50.4. Migration order

Dùng expand-and-contract: thêm remote structure tương thích, cập nhật local foreign table, deploy consumers, rồi mới loại bỏ legacy structure.

### 50.5. Schema contract

Lưu DDL remote/local trong source control và có automated drift detection. IMPORT FOREIGN SCHEMA là thao tác tạo metadata, không phải continuous schema sync.


## 51. Troubleshooting: connection refused hoặc timeout

### 51.1. DNS và hostname

Kiểm tra hostname resolve được từ host/container local PostgreSQL. Máy developer resolve được không chứng minh database server resolve được.

### 51.2. Network/firewall

Xác nhận route, security groups, firewall, port và egress/ingress policies giữa hai server.

### 51.3. Remote listen addresses

Remote PostgreSQL phải listen trên interface phù hợp, không chỉ localhost.

### 51.4. pg_hba.conf

Rule phải match remote database, remote user, source address và auth method. Reload HBA sau khi thay đổi và xem server logs.

### 51.5. TLS

Kiểm tra CA chain, certificate expiry, hostname verification và client certificate requirements nếu dùng verify-full/cert auth.

## 52. Troubleshooting: password authentication failed hoặc permission denied

### 52.1. Local mapping

Xác nhận đúng mapping cho local role đang chạy query và đúng foreign server.

### 52.2. Remote identity

Kiểm tra remote username, password rotation state, role LOGIN và account validity.

### 52.3. Database/schema/table grants

Remote role cần CONNECT, USAGE và table privileges. DML cần quyền tương ứng cho từng operation.

### 52.4. Local grants

Local role cần USAGE trên foreign server/schema và SELECT/INSERT/UPDATE/DELETE trên foreign table.

### 52.5. PUBLIC mapping

Nếu nhiều users dùng cùng PUBLIC mapping, một remote identity có thể cấp quyền quá rộng. Tạo per-role mappings và audit access.

## 53. Troubleshooting: relation/column does not exist

### 53.1. Remote schema/table options

Kiểm tra schema_name/table_name của foreign table có đúng remote relation không.

### 53.2. Column mapping

Kiểm tra column_name options, identifier case và local column definitions.

### 53.3. Remote search_path

postgres_fdw gửi relation names có schema qualification theo foreign table metadata; không dựa vào remote session search_path để sửa mapping sai.

### 53.4. DDL drift

Remote table có thể đã rename/drop column. Đối chiếu information_schema.columns ở remote và local foreign table definition.

### 53.5. Permissions

Một số access errors có thể biểu hiện như không thể truy cập relation. Xem remote logs để phân biệt missing object với privilege failure.

## 54. Troubleshooting: query chậm hoặc pushdown không xảy ra

### 54.1. EXPLAIN VERBOSE

Xem Remote SQL để biết filter/join/order/aggregate nào thực sự được ship.

### 54.2. Expression shippability

Kiểm tra function/operator, volatility, collation và extension compatibility. Một local-only expression có thể giữ operation ở local.

### 54.3. Remote EXPLAIN

Chạy câu Remote SQL trên remote với parameters đại diện. Xem remote indexes, statistics, joins và rows estimates.

### 54.4. Network transfer

Ước lượng số rows/bytes truyền về. Tăng fetch_size có thể giảm round trips nhưng không chữa việc query trả quá nhiều rows.

### 54.5. Local join order

Local planner có thể chọn join order kém nếu foreign estimates không chính xác. Thử use_remote_estimate hoặc ANALYZE foreign table trên staging rồi benchmark.

## 55. Troubleshooting: type mismatch và dữ liệu sai semantics

### 55.1. Numeric precision

Local numeric precision/scale phải phù hợp remote values. Narrower local type có thể gây overflow/rounding errors.

### 55.2. Timestamp semantics

Phân biệt timestamp without time zone và timestamptz. Không tự chuyển timezone nếu nghiệp vụ yêu cầu giữ wall-clock time.

### 55.3. Enum/domain/custom types

Extension-defined types cần có type support tương thích ở local/remote và mapping được FDW hỗ trợ.

### 55.4. Collation

Text comparison/sort có thể khác do collation provider/version. Pushdown chỉ an toàn khi semantics tương thích.

### 55.5. Null/default behavior

Remote defaults, generated columns và triggers thực thi ở remote. Local foreign table defaults không tự phản ánh remote default changes.

## 56. Troubleshooting: remote transaction hoặc commit outcome không rõ

### 56.1. Client disconnect

Nếu network mất sau khi remote đã nhận COMMIT nhưng trước khi local nhận response, outcome có thể không rõ với caller.

### 56.2. Kiểm tra remote state

Dùng transaction/business identifiers, audit records và remote query logs để xác định thay đổi đã commit chưa.

### 56.3. Idempotent writes

Dùng unique keys/request IDs và conflict handling phù hợp để retry an toàn. Không retry blind một payment/order write.

### 56.4. Multiple remote servers

Nếu local transaction ghi nhiều remotes, một số có thể commit trước khi lỗi xảy ra ở server khác. Cần reconciliation hoặc compensating actions.

### 56.5. Application contract

Expose operation status/uncertain outcome và có recovery worker thay vì báo đơn giản failed rồi tạo write mới.


## 57. Foreign server và foreign table options

postgres_fdw hỗ trợ options ở nhiều cấp; mỗi option có scope và precedence riêng theo PostgreSQL version.

### 57.1. use_remote_estimate

Có thể đặt trên server hoặc foreign table để điều khiển cách planner lấy estimates. Table-level option hữu ích khi một relation có đặc tính khác biệt.

### 57.2. fetch_size

Có thể đặt ở server/table để kiểm soát số rows lấy mỗi batch. Kiểm tra option inheritance/override trong documentation của version.

### 57.3. updatable

Option này điều khiển foreign table có được coi là updatable hay không theo postgres_fdw behavior. Dù bật, remote grants và relation capabilities vẫn quyết định thao tác thành công.

### 57.4. truncatable

Option truncatable điều khiển khả năng TRUNCATE foreign table. Chỉ bật khi remote operation được phép và đã có change controls.

### 57.5. async_capable và batch_size

Các options này có thể điều khiển asynchronous execution và batched inserts trên versions hỗ trợ. Kiểm tra compatibility, defaults và impact trước khi áp dụng.

## 58. Extensions option cho pushdown functions

postgres_fdw có server option extensions để khai báo các extensions được phép ship functions/operators sang remote trong điều kiện tương thích.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD extensions 'some_extension');
~~~

### 58.1. Cùng extension ở hai phía

Extension được liệt kê cần được cài đặt tương thích ở local và remote. Semantics/versions phải phù hợp để kết quả thực thi giống nhau.

### 58.2. Function safety

Chỉ các expressions đáp ứng shippability/safety rules mới được ship. Extensions option không ép mọi function của extension chạy remote.

### 58.3. Security implications

Function execution ở remote có thể có privileges và side effects khác local. Review code, owner và remote role permissions.

### 58.4. Update compatibility

Khi nâng extension version, xác nhận local/remote versions đồng bộ và plan behavior không đổi ngoài dự kiến.

### 58.5. Verify Remote SQL

Dùng EXPLAIN VERBOSE và remote logs để xác nhận function thực sự được pushdown.


## 59. Ví dụ end-to-end: cấu hình read-only integration

Kịch bản này tạo local foreign table để đọc dữ liệu từ database sales remote.

### 59.1. Trên remote

DBA tạo role fdw_sales_reader, cấp CONNECT, USAGE trên schema và SELECT trên tables cần expose.

### 59.2. Trên local

Cài extension và tạo server:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER sales_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'sales-db.example.internal',
    port '5432',
    dbname 'sales',
    sslmode 'verify-full',
    application_name 'fdw-local-reporting'
);
~~~

### 59.3. Tạo user mapping

~~~sql
CREATE USER MAPPING FOR reporting_app
SERVER sales_server
OPTIONS (
    user 'fdw_sales_reader',
    password 'REPLACE_WITH_SECRET'
);
~~~

Secret phải được inject từ hệ thống quản lý credentials, không hard-code vào repository.

### 59.4. Tạo schema và import

~~~sql
CREATE SCHEMA remote_sales AUTHORIZATION db_owner;

IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 59.5. Cấp local privileges

~~~sql
GRANT USAGE ON FOREIGN SERVER sales_server TO reporting_app;
GRANT USAGE ON SCHEMA remote_sales TO reporting_app;
GRANT SELECT ON ALL TABLES IN SCHEMA remote_sales TO reporting_app;
~~~

Sau đó test bằng đúng reporting_app role và xác nhận remote pg_stat_activity cho thấy remote identity/application_name mong đợi.

## 60. Ví dụ end-to-end: foreign table thủ công và DML

Kịch bản này minh họa một foreign table ghi vào remote relation.

### 60.1. Remote permissions

Remote role cần CONNECT, schema USAGE và INSERT/UPDATE/DELETE trên target table. Xác định unique key/constraints ở remote.

### 60.2. Local mapping

Tạo mapping riêng cho local writer role, dùng remote account có đúng quyền cần thiết.

### 60.3. Foreign table definition

~~~sql
CREATE FOREIGN TABLE remote_sales.order_updates (
    order_id bigint,
    status text,
    updated_at timestamptz
)
SERVER sales_server
OPTIONS (
    schema_name 'public',
    table_name 'order_updates',
    updatable 'true'
);
~~~

### 60.4. DML test

~~~sql
INSERT INTO remote_sales.order_updates
    (order_id, status, updated_at)
VALUES
    (9001, 'processed', now());

UPDATE remote_sales.order_updates
SET status = 'shipped'
WHERE order_id = 9001;
~~~

### 60.5. Validate remote outcome

Query trực tiếp remote table bằng remote DBA/read role và xác nhận row values. Kiểm tra transaction commit, triggers, constraints và audit records.

## 61. Ví dụ: kiểm tra pushdown và remote plan

### 61.1. Query local

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT order_id, total_amount
FROM remote_sales.orders
WHERE customer_id = 101
  AND status = 'open'
ORDER BY created_at DESC
LIMIT 20;
~~~

### 61.2. Xem Remote SQL

Kiểm tra Foreign Scan node có Remote SQL chứa WHERE/ORDER BY/LIMIT phù hợp hay không.

### 61.3. Remote EXPLAIN

Chạy câu Remote SQL trên remote với role tương ứng để xem index scan, row estimates và sort behavior.

### 61.4. Thử fetch size

Chạy workload với vài fetch_size values ở staging, giữ dataset/parameters/concurrency tương đương.

### 61.5. So sánh toàn đường đi

Ghi local planning time, execution time, rows/bytes transfer, remote CPU/I/O và native remote workload latency.

## 62. Lab: kết nối hai PostgreSQL databases

Dùng hai instances hoặc databases trên môi trường lab. Một instance đóng vai trò remote source, instance còn lại local consumer.

### 62.1. Chuẩn bị remote schema

Tạo bảng customers/orders, insert representative rows, tạo index và role read-only.

### 62.2. Chuẩn bị network/authentication

Xác nhận DNS/host, port, TLS và pg_hba.conf cho local PostgreSQL host.

### 62.3. Cài postgres_fdw

Cài package cần thiết ở server và CREATE EXTENSION trong local database.

### 62.4. Tạo server/mapping/table

Tạo foreign server, user mapping, local schema và IMPORT FOREIGN SCHEMA LIMIT TO.

### 62.5. Truy vấn

Chạy SELECT và join foreign tables; xác nhận dữ liệu đến từ remote bằng remote activity/logs.

## 63. Lab: pushdown và query tuning

### 63.1. Query có selective filter

Tạo remote index trên filter column và chạy EXPLAIN VERBOSE.

### 63.2. Predicate pushdown

Xác nhận WHERE nằm trong Remote SQL và remote plan dùng index phù hợp.

### 63.3. Join pushdown

Join hai foreign tables cùng server và xem remote SQL có JOIN hay không.

### 63.4. Local/remote join

Join một local table với foreign table; quan sát rows transfer và local plan.

### 63.5. Tune fetch_size/estimates

Thử fetch_size và use_remote_estimate trên staging, so planning/execution time, network và remote load.

## 64. Lab: security và failure handling

### 64.1. Least-privilege role

Tạo remote read role chỉ được SELECT trên một schema/table subset.

### 64.2. Local authorization

Tạo local role mapping riêng và chỉ GRANT USAGE/SELECT trên server/schema/table cần thiết.

### 64.3. Negative test

Thử query table không được cấp quyền và xác nhận remote từ chối. Thử user không có local USAGE để xác nhận local admission.

### 64.4. Network failure

Trong lab, tạm ngắt remote endpoint hoặc chặn port rồi chạy query để quan sát timeout/error. Khôi phục network sau test.

### 64.5. DML retry

Mô phỏng response loss sau write nếu môi trường cho phép; xây idempotency/reconciliation logic và không retry blind.


## 65. Những lỗi thường gặp khi dùng postgres_fdw

1. Nghĩ foreign table lưu bản copy dữ liệu remote.
2. Quên CREATE EXTENSION trong database local cần dùng.
3. Cài package cho sai PostgreSQL major version.
4. Tạo foreign server nhưng remote host không reachable từ local database host.
5. Nhầm local role với remote user.
6. Quên CREATE USER MAPPING cho application role thực tế.
7. Dùng PUBLIC mapping với remote superuser.
8. Quên GRANT USAGE ON FOREIGN SERVER.
9. Chỉ cấp local SELECT mà quên remote CONNECT/schema/table privileges.
10. Đưa password vào server options hoặc source control.
11. Cho rằng IMPORT FOREIGN SCHEMA đồng bộ DDL tự động.
12. Không kiểm tra type/column mapping.
13. Cho rằng mọi WHERE/JOIN/ORDER BY đều pushdown.
14. Không xem Remote SQL trong EXPLAIN VERBOSE.
15. Tăng fetch_size mà không đo memory/concurrency.
16. Bật use_remote_estimate mà không tính planning overhead.
17. Để FDW reporting làm quá tải remote OLTP source.
18. Không tính remote sessions do local backend/pool multiplication.
19. Giả định nhiều remote servers có distributed atomic commit.
20. Retry DML sau network error mà không kiểm tra remote commit outcome.
21. Chỉ monitor local database, bỏ qua remote locks/CPU/I/O.
22. Không cài shared libraries trên standby/DR nodes.
23. Không có schema drift process giữa local foreign table và remote table.
24. Dùng FDW cho bulk federation mà không benchmark so với replication/ETL.

## 66. Bài tập thực hành

### Bài 1 — Khái niệm

Foreign Data Wrapper có vai trò gì?

**Đáp án:** Cung cấp giao diện để PostgreSQL truy cập nguồn dữ liệu bên ngoài.

### Bài 2 — Foreign server

Foreign server mô tả điều gì?

**Đáp án:** Endpoint và options kết nối tới foreign data source.

### Bài 3 — User mapping

User mapping nối những identities nào?

**Đáp án:** Local PostgreSQL role với remote user/authentication options.

### Bài 4 — Foreign table

Foreign table có lưu rows remote trong local database không?

**Đáp án:** Không; nó là metadata đại diện cho remote relation.

### Bài 5 — Extension

CREATE EXTENSION postgres_fdw phải chạy ở đâu?

**Đáp án:** Trong database local sẽ chứa foreign server/tables.

### Bài 6 — Server options

host/port/dbname xác định điều gì?

**Đáp án:** Remote PostgreSQL endpoint và database đích.

### Bài 7 — Remote role

Remote role cần quyền gì để đọc table?

**Đáp án:** CONNECT database, USAGE schema và SELECT table.

### Bài 8 — Local privilege

GRANT USAGE ON FOREIGN SERVER dùng để làm gì?

**Đáp án:** Cho phép role local sử dụng foreign server.

### Bài 9 — Import

IMPORT FOREIGN SCHEMA có copy data không?

**Đáp án:** Không; nó tạo foreign table definitions local.

### Bài 10 — Column mapping

Option column_name có tác dụng gì?

**Đáp án:** Ánh xạ local column name sang remote column name.

### Bài 11 — Schema

Schema local có bắt buộc trùng schema remote không?

**Đáp án:** Không; INTO xác định local schema, schema_name xác định remote schema.

### Bài 12 — Pushdown

Predicate pushdown giúp gì?

**Đáp án:** Lọc ở remote trước khi truyền rows về local.

### Bài 13 — Join pushdown

Hai foreign tables cùng server có cơ hội gì?

**Đáp án:** Planner có thể pushdown join sang remote nếu expressions an toàn.

### Bài 14 — EXPLAIN

Dùng option nào để xem Remote SQL?

**Đáp án:** EXPLAIN VERBOSE.

### Bài 15 — Remote estimate

use_remote_estimate có trade-off nào?

**Đáp án:** Estimates sát remote hơn nhưng planning cần thêm remote round trips/CPU.

### Bài 16 — fetch_size

Tăng fetch_size có thể cải thiện gì?

**Đáp án:** Giảm network round trips khi fetch nhiều rows, đổi lại memory use có thể tăng.

### Bài 17 — batch_size

batch_size hữu ích với workload nào?

**Đáp án:** INSERT nhiều rows có thể được gom thành batches.

### Bài 18 — ANALYZE

ANALYZE foreign table tạo statistics ở đâu?

**Đáp án:** Trong local database để local planner dùng.

### Bài 19 — Remote indexes

Tạo index cho foreign table ở đâu?

**Đáp án:** Trên remote relation.

### Bài 20 — DML

Remote role thiếu UPDATE privilege thì sao?

**Đáp án:** UPDATE qua foreign table sẽ bị remote từ chối.

### Bài 21 — Transaction

postgres_fdw có distributed 2PC atomic commit cho nhiều remote servers không?

**Đáp án:** Không; multi-remote commits có thể partial commit khi failure.

### Bài 22 — Retry

Vì sao không retry blind DML sau network error?

**Đáp án:** Remote có thể đã commit dù local không nhận được response.

### Bài 23 — Connection count

Vì sao remote sessions có thể nhiều hơn local app instances?

**Đáp án:** Mỗi local backend/mapping có thể giữ remote connection riêng.

### Bài 24 — Schema drift

Remote rename column có tự cập nhật foreign table không?

**Đáp án:** Không; local metadata phải được migration đồng bộ.

### Bài 25 — Monitoring

Cần monitor ở những phía nào?

**Đáp án:** Cả local PostgreSQL, remote PostgreSQL và network/application path.

### Bài 26 — TLS

sslmode verify-full kiểm tra điều gì?

**Đáp án:** TLS certificate chain và hostname identity.

### Bài 27 — PUBLIC mapping

Rủi ro của PUBLIC mapping là gì?

**Đáp án:** Nhiều local users có thể dùng chung remote identity/privileges.

### Bài 28 — Server lifecycle

DROP SERVER RESTRICT có tác dụng gì?

**Đáp án:** Từ chối drop khi còn dependent foreign tables/mappings.

### Bài 29 — Async

async_capable có nghĩa mọi foreign queries chạy parallel không?

**Đáp án:** Không; chỉ các plans/operations thỏa điều kiện executor/FDW mới tận dụng async.

### Bài 30 — Chọn công nghệ

Khi nào nên cân nhắc replication/ETL thay vì FDW?

**Gợi ý:** Khi cần local low-latency copy, scan volume lớn, resilience khi remote outage hoặc consistency/transaction semantics FDW không đáp ứng.


## 67. Checklist triển khai postgres_fdw

- [ ] Extension package đúng PostgreSQL major version đã được cài?
- [ ] CREATE EXTENSION chạy trong đúng local database?
- [ ] Remote host/port/dbname và TLS đã kiểm tra từ local server?
- [ ] Remote role có least-privilege grants?
- [ ] Foreign server options không chứa secrets?
- [ ] User mapping đúng local role/remote user?
- [ ] Password/certificate được quản lý qua secret process?
- [ ] Local USAGE server/schema/table grants đã cấu hình?
- [ ] Foreign table columns/types/schema/table mappings khớp remote?
- [ ] IMPORT FOREIGN SCHEMA scope được giới hạn phù hợp?
- [ ] EXPLAIN VERBOSE xác nhận pushdown mong muốn?
- [ ] Remote query/index plans đã được kiểm tra?
- [ ] Fetch/batch/estimate options đã benchmark?
- [ ] Connection count và remote capacity có headroom?
- [ ] Monitoring/logging ở cả local và remote đã sẵn sàng?
- [ ] Schema drift, credential rotation và package upgrade có runbook?

## 68. Checklist vận hành và troubleshooting

- [ ] Local query errors được đối chiếu với remote logs?
- [ ] DNS/network/firewall/TLS được kiểm tra khi connect fail?
- [ ] pg_hba.conf và remote grants đã xác nhận?
- [ ] Local user mapping và remote identity đúng?
- [ ] Remote locks/long transactions được kiểm tra?
- [ ] Remote SQL và plan được xem khi query chậm?
- [ ] Data transfer/result size và fetch_size được đo?
- [ ] Transaction commit outcome được xác minh khi network error?
- [ ] DML retry có idempotency/reconciliation?
- [ ] Remote session count được so với local backends?
- [ ] Foreign table metadata được cập nhật theo remote DDL?
- [ ] HA/standby/DR có package và credentials cần thiết?
- [ ] Backup/restore và failover rehearsal có foreign objects?
- [ ] Extension/server/mapping lifecycle được inventory và audit?

## 69. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| FDW | Giao diện truy cập foreign data |
| postgres_fdw | FDW cho remote PostgreSQL |
| CREATE EXTENSION | Cài postgres_fdw trong database local |
| CREATE SERVER | Định nghĩa remote endpoint |
| CREATE USER MAPPING | Ánh xạ local role sang remote identity |
| CREATE FOREIGN TABLE | Định nghĩa relation remote trong local catalog |
| IMPORT FOREIGN SCHEMA | Sinh foreign tables từ remote schema |
| pg_foreign_data_wrapper | Catalog FDW objects |
| pg_foreign_server | Catalog foreign servers |
| pg_user_mapping | Catalog user mappings |
| pg_foreign_table | Catalog foreign table options |
| pg_extension | Extension installations trong database |
| GRANT USAGE ON FOREIGN SERVER | Cho phép role local sử dụng server |
| schema_name/table_name | Chọn remote relation |
| column_name | Map local/remote column |
| use_remote_estimate | Lấy planner estimates từ remote |
| fdw_startup_cost | Startup cost model |
| fdw_tuple_cost | Per-tuple cost model |
| fetch_size | Rows mỗi fetch batch |
| batch_size | Rows mỗi INSERT batch khi hỗ trợ |
| async_capable | Cho phép async foreign execution khi hỗ trợ |
| updatable | Điều khiển khả năng DML theo FDW |
| truncatable | Điều khiển TRUNCATE support |
| EXPLAIN VERBOSE | Xem Remote SQL |
| ANALYZE foreign table | Tạo local planner statistics |
| postgres_fdw_get_connections | Xem cached remote connections ở versions hỗ trợ |
| postgres_fdw_disconnect | Ngắt cached connection ở versions hỗ trợ |
| application_name | Nhận diện FDW session phía remote |
| Pushdown | Chạy filter/join/aggregate ở remote |
| User mapping | Remote authentication mapping |
| Foreign table | Metadata local đại diện remote relation |
| Distributed 2PC | Không được postgres_fdw cung cấp đầy đủ cho multi-remote atomic commit |

## 70. Kết luận

**postgres_fdw cho phép truy vấn dữ liệu PostgreSQL remote bằng foreign tables, nhưng thành công phụ thuộc cả cấu hình local lẫn remote.** Foreign server mô tả endpoint, user mapping xác định remote identity, còn foreign table mô tả relation và columns ở local catalog. CREATE EXTENSION chỉ bật FDW trong database local; package phải có trên server và remote role phải được cấp quyền phù hợp. IMPORT FOREIGN SCHEMA tạo metadata, không copy dữ liệu hay tự đồng bộ remote DDL.

Hiệu năng phụ thuộc predicate/join/aggregate pushdown, remote indexes/statistics, planner estimates, network latency, result size, fetch_size và concurrency. EXPLAIN VERBOSE cho biết Remote SQL; remote EXPLAIN và pg_stat_activity cho biết source server đang thực thi ra sao. Local ANALYZE foreign table giúp local planner có statistics nhưng không thay thế ANALYZE trên remote. Cần monitor cả hai phía và tính số remote sessions do local backends tạo ra.

postgres_fdw hỗ trợ nhiều thao tác đọc/ghi và transaction coordination trong các tình huống thông thường, nhưng không cung cấp distributed two-phase commit đầy đủ cho atomic commit trên nhiều remote servers. Network failures có thể làm write outcome không rõ; ứng dụng cần idempotency và reconciliation. Nếu workload cần data locality, high-volume scans, global consistency hoặc resilience độc lập với remote availability, hãy đánh giá replication/materialization/ETL thay thế.

Nguyên tắc vận hành: **thiết kế remote identity với least privilege, kiểm tra schema/column mapping, xác minh pushdown bằng EXPLAIN, benchmark network/concurrency, monitor remote source và chuẩn bị xử lý transaction outcome trước khi dùng FDW cho writes quan trọng.**

