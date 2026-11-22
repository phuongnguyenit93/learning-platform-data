# Cấp quyền tài khoản cơ sở dữ liệu theo nhu cầu tối thiểu

## 1. Vì sao ứng dụng không nên dùng tài khoản database toàn quyền?

Một ứng dụng Spring Data JDBC cần kết nối database để đọc và ghi aggregate. Cách đơn giản nhất khi phát triển local thường là dùng tài khoản có quyền rất rộng, chẳng hạn tài khoản quản trị database hoặc tài khoản sở hữu schema.

Cách này tiện lúc thử nghiệm nhưng nguy hiểm khi đưa lên production. Nếu ứng dụng bị khai thác, lỗi SQL injection, lộ credential hoặc một bug ghi nhầm dữ liệu có thể cho phép kẻ tấn công:

- Đọc dữ liệu ngoài phạm vi nghiệp vụ của ứng dụng.
- Sửa hoặc xóa bảng không liên quan.
- Xóa schema hoặc database.
- Tạo user và cấp quyền cho tài khoản khác.
- Thay đổi cấu trúc bảng hoặc tạo object độc hại.
- Truy cập dữ liệu của một ứng dụng khác dùng chung database server.

Nguyên tắc **least privilege** yêu cầu mỗi tài khoản chỉ có những quyền cần thiết để thực hiện đúng nhiệm vụ của nó. Tài khoản runtime của ứng dụng thường cần đọc và ghi một số bảng cụ thể; nó không cần quyền tạo database, thay đổi schema hoặc quản lý user.

Trong hệ thống Spring Data JDBC, cần xem xét cả thao tác trên aggregate root, bảng con, sequence, view, function và các câu SQL tùy chỉnh. Nếu chỉ cấp quyền trên bảng root nhưng quên bảng con hoặc sequence, repository có thể đọc được một phần nhưng lỗi khi save aggregate.

Bài này trình bày cách tách tài khoản runtime, migration và quản trị; cách cấp quyền theo schema/bảng; cách cấu hình Spring Boot, Flyway và Liquibase; cách kiểm tra quyền thực tế và xử lý các lỗi permission thường gặp.

## 2. Phân biệt tài khoản, role và quyền

Các hệ quản trị database có cách gọi khác nhau, nhưng có thể phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| User/account | Danh tính dùng để xác thực khi mở kết nối |
| Role | Nhóm quyền có thể được gán cho một hoặc nhiều user |
| Privilege | Quyền cụ thể trên database, schema, table, sequence, view hoặc routine |

Thay vì cấp từng quyền trực tiếp cho nhiều user, thường nên tạo role theo chức năng rồi gán user vào role đó.

Ví dụ:

~~~text
orders_runtime
  SELECT, INSERT, UPDATE, DELETE trên các bảng nghiệp vụ cần thiết

orders_readonly
  SELECT trên các view báo cáo được phép

orders_migrator
  CREATE, ALTER, DROP và các quyền DDL cần cho migration

database_admin
  Quyền quản trị database theo nhiệm vụ vận hành
~~~

User runtime được gán role orders_runtime. Tài khoản migration được cấp quyền riêng để tạo hoặc sửa schema. Tài khoản quản trị chỉ được dùng bởi người hoặc quy trình vận hành được ủy quyền.

## 3. Những quyền Spring Data JDBC thường cần

Spring Data JDBC thực hiện persistence theo aggregate boundary. Một repository save có thể đọc hoặc ghi nhiều bảng:

~~~text
PurchaseOrderRepository
       |
       v
purchase_order
       |
       +--> purchase_order_line
       |
       +--> shipment
~~~

Nếu một aggregate chứa collection child, thao tác save có thể insert, update hoặc xóa các hàng con theo semantics của aggregate. Vì vậy, tài khoản runtime cần quyền trên mọi object mà use case thực sự truy cập.

### 3.1. Quyền đọc

Các truy vấn repository thường cần SELECT trên:

- Bảng aggregate root.
- Bảng con thuộc aggregate.
- Bảng được join trong custom query.
- View hoặc materialized view mà ứng dụng đọc.

Nếu repository chỉ cần đọc một số cột nhạy cảm, có thể cân nhắc column-level privileges nếu database hỗ trợ và mapping/query tương thích.

### 3.2. Quyền ghi

Các thao tác CRUD có thể cần:

| Thao tác Spring Data JDBC | Quyền database thường cần |
| --- | --- |
| findById, findAll, derived query | SELECT |
| Insert aggregate root | INSERT |
| Insert child entity | INSERT trên bảng con |
| Update aggregate root | UPDATE và có thể SELECT để đọc dữ liệu |
| Đồng bộ collection child | DELETE và INSERT/UPDATE trên bảng con tùy chiến lược |
| deleteById | DELETE trên root và bảng con liên quan |
| Custom @Modifying UPDATE | UPDATE |
| Custom @Modifying DELETE | DELETE |

Không nên chỉ cấp INSERT/UPDATE/DELETE trên bảng root rồi giả định aggregate save sẽ thành công. Kiểm tra SQL thực tế và các bảng con mà mapping sử dụng.

### 3.3. Quyền sequence và generated ID

Một số database dùng sequence để sinh ID. Với PostgreSQL, tài khoản có thể cần USAGE trên sequence để gọi nextval. Nếu thiếu quyền này, INSERT có thể thất bại dù user đã có INSERT trên bảng.

MySQL AUTO_INCREMENT và SQL Server IDENTITY có cơ chế khác; không cấp quyền sequence kiểu PostgreSQL cho mọi database.

### 3.4. Quyền bổ sung có thể cần

Chỉ cấp khi ứng dụng thực sự sử dụng:

- EXECUTE trên stored procedure hoặc function.
- SELECT trên view.
- USAGE trên schema hoặc sequence.
- Quyền truy cập bảng outbox/audit.
- Quyền đọc metadata nếu ứng dụng có tính năng introspection riêng.

Thông thường, tài khoản runtime không cần:

- CREATE DATABASE hoặc CREATE SCHEMA.
- CREATE, ALTER hoặc DROP TABLE.
- DROP DATABASE.
- TRUNCATE nếu ứng dụng không dùng thao tác này.
- GRANT OPTION.
- Quyền tạo user hoặc role.
- SUPERUSER, DBA, db_owner hoặc quyền quản trị tương đương.

## 4. Tách tài khoản runtime và migration

Một ứng dụng thường có ít nhất hai loại công việc database:

1. Chạy ứng dụng: đọc/ghi dữ liệu nghiệp vụ.
2. Nâng cấp schema: tạo bảng, thêm cột, index, constraint hoặc thay đổi cấu trúc.

Hai công việc này có yêu cầu quyền rất khác nhau.

### 4.1. Tài khoản runtime

Tài khoản runtime được sử dụng bởi DataSource mà Spring Data JDBC repositories dùng trong quá trình phục vụ request.

Ví dụ quyền:

- SELECT, INSERT, UPDATE, DELETE trên schema nghiệp vụ.
- USAGE trên schema.
- USAGE/SELECT trên sequence cần thiết.
- EXECUTE trên routine nếu use case gọi routine.

Không cấp quyền DDL chỉ để ứng dụng tự sửa schema lúc khởi động.

### 4.2. Tài khoản migration

Flyway hoặc Liquibase có thể cần quyền:

- CREATE TABLE.
- ALTER TABLE.
- CREATE INDEX.
- CREATE SEQUENCE.
- CREATE/DROP constraint.
- Thực hiện data migration có kiểm soát.

Tài khoản này nên được dùng trong deployment pipeline hoặc giai đoạn migration có kiểm soát. Không dùng nó làm username mặc định của connection pool phục vụ request.

### 4.3. Tài khoản quản trị

Tài khoản DBA/admin được giữ riêng cho:

- Tạo database và schema.
- Tạo user/role.
- Cấp và thu hồi quyền.
- Thực hiện thao tác vận hành đặc quyền.
- Xử lý sự cố cần quyền quản trị.

Không lưu credential quản trị trong application.yml hoặc container environment của ứng dụng runtime.

### 4.4. Sơ đồ phân tách

~~~text
Deployment pipeline
       |
       v
Migration account
  CREATE / ALTER / INDEX / CONSTRAINT
       |
       v
Database schema
       ^
       |
Application runtime
       |
       v
Runtime account
  SELECT / INSERT / UPDATE / DELETE

DBA / operator
       |
       v
Admin account
  USER / ROLE / DATABASE / SCHEMA administration
~~~

## 5. Cấp quyền trên PostgreSQL

PostgreSQL phân biệt quyền database, schema, table, sequence, function và các object khác. Để truy cập một bảng trong schema, user thường cần CONNECT trên database, USAGE trên schema và quyền phù hợp trên bảng.

### 5.1. Tạo role runtime

Ví dụ:

~~~sql
CREATE ROLE orders_runtime LOGIN PASSWORD 'replace-with-secret';
~~~

Trong production, mật khẩu phải được cấp từ secret manager hoặc quy trình bảo mật phù hợp. Không commit mật khẩu thật vào migration hoặc source control.

### 5.2. Cấp quyền kết nối và schema

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_runtime;
GRANT USAGE ON SCHEMA app TO orders_runtime;
~~~

CONNECT cho phép mở session vào database. USAGE cho phép resolve object trong schema, nhưng chưa tự cấp quyền đọc/ghi bảng.

### 5.3. Cấp quyền trên các bảng hiện có

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO orders_runtime;
~~~

Lệnh này áp dụng cho các bảng đã tồn tại trong schema app tại thời điểm chạy. Nếu ứng dụng không cần xóa dữ liệu, bỏ DELETE. Nếu một số bảng chỉ đọc, cấp SELECT riêng thay vì cấp cùng quyền ghi cho toàn schema.

### 5.4. Cấp quyền trên sequence

~~~sql
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA app
TO orders_runtime;
~~~

USAGE cho phép sử dụng sequence theo các thao tác được database quy định. SELECT cho phép đọc trạng thái sequence như currval. Chỉ cấp UPDATE nếu ứng dụng thực sự cần thao tác đặc quyền như setval.

### 5.5. Cấp default privileges cho object tạo trong tương lai

Nếu migration tiếp tục tạo bảng mới, quyền trên các bảng hiện có không tự động áp dụng cho object mới. Có thể đặt default privileges:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE orders_migrator
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
TO orders_runtime;

ALTER DEFAULT PRIVILEGES
FOR ROLE orders_migrator
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES
TO orders_runtime;
~~~

Điểm quan trọng: default privileges áp dụng cho object được tạo trong tương lai bởi role được chỉ định. Nếu migration thực tế tạo object dưới một owner role khác, phải cấu hình default privileges cho role tạo object đó.

ALTER DEFAULT PRIVILEGES không sửa quyền của các object đã tồn tại. Cần chạy cả GRANT cho object hiện có và default privileges cho object tương lai.

### 5.6. Kiểm tra quyền

PostgreSQL có các hàm kiểm tra quyền:

~~~sql
SELECT has_schema_privilege(
    'orders_runtime',
    'app',
    'USAGE'
);

SELECT has_table_privilege(
    'orders_runtime',
    'app.purchase_order',
    'SELECT'
);

SELECT has_sequence_privilege(
    'orders_runtime',
    'app.purchase_order_id_seq',
    'USAGE'
);
~~~

Trong psql, có thể dùng các lệnh metadata như \du, \dn+ và \dp để kiểm tra role, schema và table privileges.

### 5.7. Chú ý quyền PUBLIC

PostgreSQL có một số quyền mặc định cấp cho PUBLIC trên một số loại object, chẳng hạn CONNECT/TEMPORARY trên database và EXECUTE trên function theo cấu hình mặc định. Nếu ứng dụng cần mức kiểm soát chặt, hãy kiểm tra và thu hồi quyền PUBLIC không cần thiết.

Không chạy REVOKE hàng loạt mà chưa hiểu tác động tới các ứng dụng khác. Thay đổi quyền dùng chung có thể làm hỏng các workload hiện hữu.

## 6. Cấp quyền trên MySQL

MySQL hỗ trợ cấp quyền theo global, database, table, column và routine. Với ứng dụng runtime, nên giới hạn ở database hoặc table cần dùng.

### 6.1. Tạo user giới hạn host

~~~sql
CREATE USER 'orders_runtime'@'10.%'
IDENTIFIED BY 'replace-with-secret';
~~~

Phần host giới hạn nơi user có thể kết nối theo quy tắc account của MySQL. Chọn phạm vi phù hợp với mạng triển khai; không dùng wildcard rộng hơn nhu cầu.

### 6.2. Cấp quyền DML trên database

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders.*
TO 'orders_runtime'@'10.%';
~~~

Nếu ứng dụng chỉ cần một nhóm bảng, cấp quyền theo từng bảng:

~~~sql
GRANT SELECT, INSERT, UPDATE
ON orders.purchase_order
TO 'orders_runtime'@'10.%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON orders.purchase_order_line
TO 'orders_runtime'@'10.%';
~~~

Không cấp ALL PRIVILEGES hoặc GRANT OPTION nếu ứng dụng không có nhu cầu quản trị quyền.

### 6.3. Xác minh quyền

~~~sql
SHOW GRANTS FOR 'orders_runtime'@'10.%';
~~~

MySQL không dùng sequence object theo cách giống PostgreSQL cho AUTO_INCREMENT. Nếu ứng dụng dùng stored procedure hoặc function, cấp EXECUTE trên routine cụ thể thay vì cấp quyền toàn cục.

## 7. Cấp quyền trên SQL Server

SQL Server hỗ trợ database role và schema-level permission. Có thể tạo một role riêng cho ứng dụng:

~~~sql
CREATE ROLE orders_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON SCHEMA::orders
TO orders_runtime;

ALTER ROLE orders_runtime
ADD MEMBER orders_app;
~~~

Trong ví dụ:

- orders_runtime là database role.
- orders_app là database user đã được tạo và ánh xạ với login phù hợp.
- Quyền DML được cấp trên schema orders.
- User được thêm vào role để nhận các quyền đó.

Schema-level grant áp dụng cho object trong schema theo quyền được cấp. Nếu schema chứa cả bảng nhạy cảm mà ứng dụng không cần truy cập, hãy tách schema hoặc cấp quyền theo từng object.

Không thêm tài khoản runtime vào db_owner hoặc db_ddladmin. Các role đó có phạm vi quyền rộng hơn nhu cầu DML thông thường.

Có thể kiểm tra quyền hiệu lực bằng:

~~~sql
SELECT *
FROM fn_my_permissions('orders.purchase_order', 'OBJECT');
~~~

## 8. Cấu hình Spring Boot dùng tài khoản runtime

DataSource chính của ứng dụng nên dùng tài khoản runtime:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/orders
    username: ${DB_RUNTIME_USER}
    password: ${DB_RUNTIME_PASSWORD}
~~~

Các biến môi trường hoặc secret tương ứng được cung cấp từ môi trường triển khai. Không ghi mật khẩu thật vào file cấu hình được commit.

Spring Data JDBC repositories, JdbcTemplate và transaction manager nên dùng DataSource runtime này để thực hiện thao tác nghiệp vụ.

### 8.1. Cấu hình Flyway bằng tài khoản migration riêng

Spring Boot cho phép Flyway dùng credential riêng:

~~~yaml
spring:
  flyway:
    url: jdbc:postgresql://db-host:5432/orders
    user: ${DB_MIGRATION_USER}
    password: ${DB_MIGRATION_PASSWORD}
~~~

Khi cấu hình Flyway datasource riêng, các migration có thể chạy bằng tài khoản có quyền DDL trong khi ứng dụng vẫn dùng tài khoản runtime giới hạn.

Nếu không cấu hình thông tin kết nối riêng, Flyway có thể dùng DataSource chính của ứng dụng. Khi đó, migration sẽ chạy bằng quyền của runtime account và có thể thất bại khi cần ALTER hoặc CREATE.

### 8.2. Cấu hình Liquibase bằng tài khoản riêng

Tương tự, Liquibase có các thuộc tính riêng:

~~~yaml
spring:
  liquibase:
    url: jdbc:postgresql://db-host:5432/orders
    user: ${DB_MIGRATION_USER}
    password: ${DB_MIGRATION_PASSWORD}
~~~

Chỉ cấu hình một công cụ migration làm chủ quy trình schema. Không để Flyway và Liquibase cùng sửa một schema nếu chưa có thiết kế phối hợp rõ ràng.

### 8.3. Khi dùng nhiều DataSource

Nếu ứng dụng khai báo DataSource riêng cho Flyway hoặc Liquibase và vẫn giữ DataSource runtime:

- Đảm bảo bean migration không vô tình trở thành DataSource chính của repository.
- Dùng cấu hình Flyway/Liquibase phù hợp với phiên bản Spring Boot.
- Nếu tạo bean thủ công, kiểm tra qualifier, Primary và transaction manager.
- Xác nhận repository Spring Data JDBC vẫn dùng runtime account.

## 9. Tài khoản read-only cho báo cáo

Một số ứng dụng có luồng báo cáo không cần ghi dữ liệu. Có thể tạo role riêng chỉ có SELECT trên các view hoặc bảng báo cáo:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_report;
GRANT USAGE ON SCHEMA reporting TO orders_report;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO orders_report;
~~~

Tài khoản này không nên được dùng bởi repository hoặc service có thao tác ghi. Việc tách role read-only giúp giới hạn hậu quả nếu credential báo cáo bị lộ.

Nếu chỉ muốn hiển thị một số cột hoặc hàng, có thể tạo view chỉ phơi bày dữ liệu cần thiết rồi cấp SELECT trên view đó.

## 10. Cấp quyền cho bảng audit, outbox và custom SQL

Ứng dụng Spring Data JDBC có thể dùng thêm các bảng kỹ thuật:

- audit_log.
- outbox_message.
- import_checkpoint.
- job_execution.
- idempotency_record.

Nếu callback, application service hoặc batch job ghi các bảng này, tài khoản runtime cần quyền phù hợp trên chúng.

Không cấp quyền trên toàn database chỉ vì một use case cần thêm một bảng. Bổ sung quyền đúng object:

~~~sql
GRANT SELECT, INSERT
ON TABLE app.outbox_message
TO orders_runtime;

GRANT SELECT, INSERT, UPDATE
ON TABLE app.import_checkpoint
TO orders_runtime;
~~~

Nếu custom query gọi stored procedure, cấp EXECUTE cho routine cụ thể. Nếu query dùng view, cấp SELECT trên view và xác nhận quyền truy cập bảng nền theo cơ chế bảo mật của database.

## 11. Quyền database không thay thế domain authorization

Least privilege ở database giới hạn những gì một connection có thể làm. Nó không tự quyết định người dùng cuối có được xem hoặc sửa một đơn hàng cụ thể hay không.

Ví dụ, tài khoản runtime có SELECT trên bảng purchase_order thì về mặt database nó có thể đọc mọi hàng trong bảng. Ứng dụng vẫn phải kiểm tra:

- User hiện tại có quyền truy cập đơn hàng này không?
- Đơn hàng có thuộc tenant của request không?
- Vai trò người dùng có được phép chuyển trạng thái không?
- Dữ liệu nhạy cảm nào được phép trả về?

Với hệ thống multi-tenant, có thể kết hợp:

- Predicate tenant_id trong query.
- View giới hạn dữ liệu.
- Row-level security nếu database hỗ trợ.
- Tách schema/database theo tenant khi kiến trúc yêu cầu.

Không dựa vào việc client gửi tenant ID để quyết định quyền. Tenant context phải được xác thực ở server và áp dụng nhất quán vào query hoặc policy.

## 12. Quyền trên schema và search path

Trong PostgreSQL, tài khoản có thể có SELECT trên bảng nhưng vẫn không truy cập được nếu thiếu USAGE trên schema chứa bảng.

Ngoài ra, search_path quyết định schema nào được tìm khi SQL dùng tên bảng không kèm schema. Hãy:

- Dùng schema rõ ràng trong cấu hình hoặc mapping nếu cần.
- Giữ search_path theo một danh sách schema tin cậy.
- Không thêm schema mà runtime user có thể tự tạo object vào search_path nếu không cần.
- Kiểm tra schema ownership và CREATE privilege.

Quyền CREATE trên schema cho phép tạo object trong schema đó. Tài khoản runtime thường không cần quyền này.

## 13. Kiểm thử bằng chính tài khoản runtime

Một ứng dụng chạy thành công bằng tài khoản admin không chứng minh tài khoản runtime có đủ quyền hoặc được giới hạn đúng.

Nên có integration smoke test bằng runtime account:

1. Kết nối database bằng runtime credential.
2. Đọc một aggregate root.
3. Đọc aggregate có child collection.
4. Insert aggregate mới.
5. Update aggregate và child.
6. Xóa aggregate nếu use case cho phép.
7. Ghi audit/outbox/checkpoint nếu ứng dụng sử dụng các bảng này.
8. Xác nhận thao tác DDL bị từ chối.
9. Xác nhận truy cập schema/bảng ngoài phạm vi bị từ chối.

### 13.1. Kiểm thử quyền cần có

Ví dụ kiểm tra PostgreSQL:

~~~sql
SELECT has_table_privilege(
    current_user,
    'app.purchase_order',
    'SELECT'
);
~~~

### 13.2. Kiểm thử quyền không nên có

Tài khoản runtime nên bị từ chối khi thử các thao tác như:

~~~sql
CREATE TABLE app.unexpected_table (
    id BIGINT PRIMARY KEY
);

DROP TABLE app.purchase_order;
~~~

Thực hiện các phép thử âm này trong môi trường test hoặc database thử nghiệm, không chạy lệnh phá hủy trên production.

## 14. Quản lý và xoay vòng credential

Least privilege sẽ mất tác dụng nếu credential được chia sẻ rộng hoặc lưu ở nhiều nơi.

Nguyên tắc:

- Mỗi ứng dụng hoặc workload có credential riêng.
- Không dùng chung password giữa runtime, migration và admin.
- Lưu secret trong secret manager hoặc hệ thống quản lý bí mật của nền tảng.
- Không commit password vào Git.
- Không đưa password vào log, exception message hoặc metric label.
- Giới hạn host/network được phép kết nối.
- Theo dõi lần đăng nhập và hoạt động bất thường.
- Xoay vòng credential theo chính sách.

Khi đổi password của runtime account, cần cập nhật secret và connection pool. Pool có thể đang giữ các connection đã xác thực bằng credential cũ; triển khai quy trình refresh/restart phù hợp trước khi thu hồi credential cũ.

Không xoay password migration account cùng lịch với runtime account nếu hai tài khoản có vòng đời và chủ sở hữu khác nhau.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Permission denied for schema | Thiếu USAGE trên schema PostgreSQL | Cấp USAGE đúng schema |
| Permission denied for table | Thiếu SELECT/INSERT/UPDATE/DELETE trên bảng | Cấp đúng quyền DML trên object cần dùng |
| Permission denied for sequence | Runtime user thiếu USAGE trên sequence | Cấp quyền sequence phù hợp |
| Save root thành công nhưng child insert lỗi | Chưa cấp quyền trên bảng con | Kiểm tra toàn bộ bảng trong aggregate |
| Repository đọc được nhưng save thất bại | Có SELECT nhưng thiếu quyền ghi | Cấp INSERT/UPDATE/DELETE theo use case |
| Flyway báo không thể ALTER TABLE | Migration đang dùng runtime credential | Cấu hình migration account riêng |
| Bảng mới tạo xong nhưng app không truy cập được | Default privileges chưa được cấu hình cho object creator | Cập nhật ALTER DEFAULT PRIVILEGES cho đúng owner role |
| Ứng dụng dùng được quá nhiều bảng | Cấp quyền toàn database hoặc role rộng | Thu hẹp về schema, table hoặc view cần thiết |
| Runtime account có thể DROP/ALTER | Dùng owner, db_owner hoặc quyền DDL | Chuyển ownership sang role quản trị và thu hồi quyền DDL |
| App chạy được local nhưng lỗi production | Local dùng tài khoản admin, production dùng runtime role | Test integration bằng đúng runtime account |

## 16. Quy trình cấp quyền tối thiểu

Khi chuẩn bị database cho một ứng dụng Spring Data JDBC:

1. **Liệt kê use case:** xác định repository, custom query, batch job và bảng kỹ thuật được dùng.
2. **Liệt kê object:** root table, child table, sequence, view, function, audit và outbox.
3. **Phân loại tài khoản:** runtime, read-only, migration và admin.
4. **Tạo role:** gom các quyền có cùng mục đích vào role riêng.
5. **Cấp quyền hiện có:** chỉ cấp SELECT/DML/EXECUTE cần thiết.
6. **Cấp default privileges:** bảo đảm object mới được tạo bởi migration owner có quyền phù hợp cho runtime role.
7. **Cấu hình credential:** runtime DataSource dùng runtime account; Flyway/Liquibase dùng migration account.
8. **Kiểm tra bằng runtime user:** chạy smoke test trên database thật.
9. **Thử quyền bị cấm:** xác nhận runtime user không thể ALTER, DROP, CREATE hoặc GRANT.
10. **Theo dõi và rà soát:** kiểm tra grant sau mỗi lần migration hoặc thay đổi use case.

## 17. Bài tập tự thực hành

**Bài tập 1 — Tạo role runtime.** Tạo tài khoản chỉ có SELECT, INSERT, UPDATE và DELETE trên schema nghiệp vụ. Xác nhận tài khoản không thể tạo hoặc xóa bảng.

**Bài tập 2 — Sequence PostgreSQL.** Tạo bảng dùng sequence, cấp quyền trên bảng nhưng cố ý bỏ quyền sequence. Thực hiện insert để quan sát lỗi, sau đó cấp USAGE và chạy lại.

**Bài tập 3 — Child table.** Tạo aggregate có collection con. Chỉ cấp quyền trên root table, gọi save và xác định quyền nào còn thiếu.

**Bài tập 4 — Default privileges.** Cấu hình ALTER DEFAULT PRIVILEGES cho migration owner, tạo bảng mới và xác nhận runtime role có thể truy cập bảng đó.

**Bài tập 5 — Tách Flyway.** Cấu hình Flyway dùng migration account và DataSource chính dùng runtime account. Xác nhận migration chạy được nhưng ứng dụng không có quyền DDL.

**Bài tập 6 — MySQL.** Tạo user giới hạn host, cấp DML trên một database và kiểm tra bằng SHOW GRANTS.

**Bài tập 7 — SQL Server.** Tạo database role, cấp quyền trên schema và thêm runtime user vào role. Xác nhận quyền hiệu lực trên một bảng.

**Bài tập 8 — Read-only reporting.** Tạo view báo cáo và role chỉ có SELECT trên view. Xác nhận role không đọc được bảng nghiệp vụ không được cấp quyền.

**Bài tập 9 — Kiểm tra negative permissions.** Chạy test bằng runtime account và xác nhận CREATE, ALTER, DROP, GRANT đều bị từ chối.

**Bài tập 10 — Xoay vòng credential.** Thay password runtime account trong secret store, refresh connection pool và xác nhận ứng dụng kết nối lại bằng credential mới.

## 18. Ghi nhớ

Tài khoản runtime của Spring Data JDBC chỉ nên có quyền cần thiết để thực hiện các use case nghiệp vụ. Với thao tác aggregate, cần tính cả bảng root, bảng con, sequence, view, function, audit và outbox. Quyền trên bảng root không tự cấp quyền trên các object khác.

Tách tài khoản runtime khỏi migration và admin. Runtime thường cần SELECT/INSERT/UPDATE/DELETE trên object được phép; Flyway hoặc Liquibase dùng credential riêng có quyền DDL; tài khoản quản trị không được nhúng trong cấu hình ứng dụng.

PostgreSQL cần chú ý CONNECT, schema USAGE, table privileges, sequence privileges và ALTER DEFAULT PRIVILEGES cho object được tạo trong tương lai. MySQL hỗ trợ grant theo database/table và host. SQL Server hỗ trợ database role và schema-level permissions. Luôn xác minh quyền bằng chính runtime account và kiểm tra cả quyền được phép lẫn quyền phải bị từ chối.

### Tài liệu tham khảo

- [PostgreSQL – Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [PostgreSQL – ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [MySQL 8.4 – GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)
- [SQL Server – Getting Started with Database Engine Permissions](https://learn.microsoft.com/en-us/sql/relational-databases/security/authentication-access/getting-started-with-database-engine-permissions)
- [SQL Server – GRANT Schema Permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-schema-permissions-transact-sql)
- [Spring Boot – Database Initialization and Flyway/Liquibase DataSources](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
