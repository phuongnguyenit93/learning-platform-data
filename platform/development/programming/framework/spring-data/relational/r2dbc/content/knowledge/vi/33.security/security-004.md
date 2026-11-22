# Phân quyền tài khoản cơ sở dữ liệu theo nhu cầu tối thiểu

Trong Spring Data Relational R2DBC, ứng dụng kết nối database bằng một hoặc nhiều tài khoản được cấu hình trong ConnectionFactory. Tài khoản đó quyết định ứng dụng có thể đọc, thêm, sửa, xóa dữ liệu, gọi stored procedure, tạo object hay thay đổi schema hay không.

Nguyên tắc **least privilege** (quyền tối thiểu) yêu cầu mỗi tài khoản chỉ có những quyền cần thiết để hoàn thành đúng công việc của nó. Tài khoản chạy ứng dụng không nên có quyền quản trị database hoặc quyền thay đổi schema nếu runtime không cần các quyền đó. Tài khoản migration, tài khoản đọc báo cáo và tài khoản xử lý background cũng nên có phạm vi quyền riêng.

Điều này giới hạn thiệt hại khi credential bị lộ, SQL injection xảy ra, một câu query bị viết sai hoặc một service bị xâm nhập. Nếu tài khoản runtime chỉ có SELECT/INSERT/UPDATE trên một schema cụ thể, kẻ tấn công không thể dùng chính credential đó để tạo user mới, xóa database khác hoặc đọc bảng không thuộc phạm vi service.

Spring Data R2DBC không tự cấp quyền database. Repository, DatabaseClient, R2dbcEntityTemplate và transaction manager đều hoạt động dưới quyền của database principal gắn với connection. Quyền phải được thiết kế và cấp tại database, sau đó được kiểm chứng bằng đúng tài khoản mà ứng dụng sử dụng.

## 1. Least privilege là gì?

Least privilege là nguyên tắc chỉ cấp đúng quyền cần thiết, trong đúng phạm vi và thời gian cần thiết.

Ví dụ, một service chỉ đọc danh sách sản phẩm có thể chỉ cần:

- Kết nối đến database sản phẩm.
- Có quyền SELECT trên một số bảng hoặc view cần đọc.
- Không có quyền INSERT, UPDATE, DELETE.
- Không có quyền tạo bảng, index, schema hoặc user.
- Không có quyền truy cập database khách hàng hoặc thanh toán.

Một service tạo đơn hàng có thể cần thêm quyền INSERT/UPDATE trên các bảng đơn hàng và quyền SELECT trên bảng sản phẩm để kiểm tra thông tin. Nó vẫn không cần quyền DROP TABLE, ALTER ROLE, CREATE DATABASE hoặc quyền quản trị toàn hệ thống.

Quyền tối thiểu không chỉ là “không dùng tài khoản admin”. Nó còn bao gồm:

1. Giới hạn đúng database và schema.
2. Giới hạn đúng bảng, view, sequence và procedure.
3. Giới hạn đúng thao tác SELECT, INSERT, UPDATE, DELETE hoặc EXECUTE.
4. Giới hạn cột nếu database hỗ trợ và nghiệp vụ cần.
5. Tách quyền runtime khỏi quyền migration và vận hành.
6. Thu hồi quyền hoặc credential khi không còn cần thiết.

## 2. Vì sao tài khoản runtime không nên là tài khoản quản trị?

Giả sử ứng dụng dùng tài khoản có quyền quản trị toàn database. Một lỗi trong endpoint hoặc một lỗ hổng SQL injection có thể mở rộng thành:

- Đọc toàn bộ bảng nhạy cảm.
- Sửa hoặc xóa dữ liệu ngoài nghiệp vụ của service.
- Tạo user hoặc cấp quyền cho tài khoản khác.
- Thay đổi schema, trigger hoặc stored procedure.
- Xóa bảng, index hoặc database.
- Tắt cơ chế bảo vệ dữ liệu tùy theo quyền được cấp.

Nếu tài khoản chỉ có quyền trên schema của service, phạm vi ảnh hưởng nhỏ hơn đáng kể.

| Tình huống | Tài khoản quá rộng | Tài khoản quyền tối thiểu |
|---|---|---|
| SQL injection trong API đọc đơn hàng | Có thể đọc nhiều database/table | Chỉ đọc object được cấp |
| Endpoint bị lỗi và chạy DELETE | Có thể xóa nhiều dữ liệu | DELETE bị từ chối nếu không được cấp |
| Credential runtime bị lộ | Có thể dùng quyền admin | Kẻ tấn công bị giới hạn theo quyền runtime |
| Ứng dụng cần deploy | Có thể tự thay schema bằng quyền runtime | Dùng pipeline migration với credential riêng |
| Service chỉ cần SELECT | Vẫn có thể ghi/xóa nếu tài khoản admin | Database từ chối thao tác ghi |

Least privilege không thay thế authentication, authorization ở ứng dụng, mã hóa hoặc chống SQL injection. Đây là một lớp phòng vệ bổ sung ở chính database.

## 3. Phân biệt database account và người dùng ứng dụng

Một database account thường đại diện cho tiến trình hoặc service đang mở connection, ví dụ orders_runtime. Nó không nhất thiết đại diện cho người dùng cuối đang đăng nhập.

Ví dụ:

~~~text
Alice ─┐
Bob   ─┼──> Orders API ──> ConnectionFactory ──> orders_runtime
Carol ─┘
~~~

Database có thể chỉ thấy mọi câu SQL đến từ orders_runtime, dù request được gửi bởi Alice, Bob hoặc Carol.

Vì vậy:

- Database account xác định quyền mà service được phép thực hiện.
- Application authorization xác định người dùng cuối được phép thực hiện nghiệp vụ nào.
- Row-level security (nếu dùng) có thể bổ sung ràng buộc ở database theo tenant hoặc actor context.
- Không đưa username/password của từng người dùng cuối vào connection pool để thay thế cơ chế authorization của ứng dụng.

Nếu cần audit actor, truyền thông tin actor theo reactive context và ghi nhận bằng auditing hoặc audit log. Không nhầm actor trong cột updated_by với database login đang chạy câu SQL.

## 4. Tách tài khoản theo workload

Một hệ thống có thể dùng nhiều tài khoản:

| Tài khoản/role | Công việc | Quyền thường cần |
|---|---|---|
| orders_runtime | Xử lý request đơn hàng | SELECT/INSERT/UPDATE trên object cần thiết |
| orders_readonly | Báo cáo hoặc truy vấn chỉ đọc | SELECT trên view/bảng được phép |
| orders_migration | Chạy schema migration | CREATE/ALTER/DROP trong schema sở hữu |
| orders_worker | Xử lý hàng đợi nền | SELECT/UPDATE trạng thái và INSERT kết quả |
| orders_backup | Backup theo quy trình | Quyền backup phù hợp với database |
| DBA/operator | Quản trị hệ thống | Quyền quản trị được kiểm soát riêng |

Không phải ứng dụng nào cũng cần tất cả các tài khoản trên. Chỉ tạo các identity thực sự có workload riêng.

### Tách role và login

Nhiều hệ quản trị hỗ trợ role/group để gom quyền, rồi gán role cho login/user. Cách này giúp:

- Định nghĩa quyền một lần.
- Tạo credential riêng cho từng môi trường hoặc instance.
- Thu hồi một login mà không phải viết lại toàn bộ GRANT.
- Tránh cấp quyền trực tiếp rời rạc cho từng account.

Ví dụ khái niệm:

~~~text
orders_runtime_login ──┐
                      ├──> role_orders_runtime
orders_worker_login ──┘

orders_report_login ─────> role_orders_readonly

orders_migration_login ──> role_orders_migration
~~~

Chỉ gộp hai login vào cùng role khi chúng thật sự cần cùng tập quyền. Worker có thể cần UPDATE trạng thái hàng đợi nhưng API đọc không cần quyền đó.

## 5. Lập ma trận quyền trước khi cấp GRANT

Trước khi viết SQL GRANT, liệt kê thao tác mà từng workload thực hiện:

| Object | Runtime API | Read-only | Worker | Migration |
|---|---:|---:|---:|---:|
| orders | SELECT, INSERT, UPDATE | SELECT | SELECT, UPDATE | ALTER |
| order_line | SELECT, INSERT | SELECT | SELECT, INSERT | ALTER |
| customer_view | SELECT | SELECT | Không cần | Tạo/sửa view |
| outbox_event | INSERT, SELECT | Không cần | SELECT, UPDATE | ALTER |
| Sequence tạo ID | USAGE/NEXT VALUE | Không cần | USAGE/NEXT VALUE | Quản trị |
| Schema | USAGE | USAGE | USAGE | CREATE/ALTER theo nhu cầu |

Đây là ma trận minh họa. Không cấp quyền chỉ vì “có thể sẽ cần”. Nếu ứng dụng hiện tại không DELETE, hãy bắt đầu bằng việc không cấp DELETE.

### Xác định quyền theo từng thao tác

- SELECT: đọc dữ liệu.
- INSERT: thêm row.
- UPDATE: sửa row hoặc cột được phép.
- DELETE: xóa row.
- EXECUTE: gọi procedure/function.
- USAGE/REFERENCES: quyền đặc thù như sử dụng sequence hoặc tham chiếu object, tùy database.
- CREATE/ALTER/DROP: thay đổi schema hoặc object.
- CONNECT/CREATE SESSION: đăng nhập/kết nối database.

Tên quyền và phạm vi GRANT không hoàn toàn giống nhau giữa các hệ quản trị.

## 6. Không dùng quyền schema owner cho runtime

Một schema owner hoặc object owner thường có khả năng thay đổi object mà nó sở hữu. Đây là quyền cần cho migration và quản trị, nhưng quá rộng cho tiến trình xử lý request.

Một mô hình an toàn hơn:

- orders_owner: role không đăng nhập, sở hữu schema và object.
- orders_migration: login được phép chạy migration trong phạm vi schema.
- orders_runtime: login chỉ nhận quyền DML cần thiết.
- orders_readonly: login chỉ nhận SELECT.

Runtime không nên sở hữu bảng nếu database cho phép tách owner khỏi quyền sử dụng bảng. Khi runtime là owner, việc chỉ thu hồi SELECT/UPDATE thường không đủ để ngăn nó thay đổi object.

Migration có thể tạo object dưới owner role hoặc dùng một quy trình triển khai được kiểm soát để bảo đảm object mới thuộc đúng owner và có quyền mặc định đúng.

## 7. Ví dụ PostgreSQL: tạo role quyền runtime

PostgreSQL phân biệt role có quyền đăng nhập và role nhóm. Có thể tạo một role nhóm không đăng nhập rồi gán cho login runtime:

~~~sql
CREATE ROLE orders_runtime_role NOLOGIN;

GRANT CONNECT ON DATABASE orders_db
TO orders_runtime_role;

GRANT USAGE ON SCHEMA orders
TO orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA orders
TO orders_runtime_role;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA orders
TO orders_runtime_role;
~~~

Tạo login riêng:

~~~sql
CREATE ROLE orders_runtime
LOGIN
PASSWORD '<set-through-secure-secret-management>';

GRANT orders_runtime_role TO orders_runtime;
~~~

Password trong ví dụ là placeholder. Không ghi password thật vào migration được commit, log, tài liệu hoặc shell history. Hãy đặt credential qua secret manager hoặc quy trình provisioning an toàn.

### Vì sao cần cả CONNECT và USAGE?

- CONNECT cho phép role kết nối vào database.
- USAGE trên schema cho phép tham chiếu object trong schema.
- SELECT/INSERT/UPDATE trên bảng cấp quyền thao tác dữ liệu.
- USAGE/SELECT trên sequence thường cần cho thao tác lấy ID từ sequence.

Quyền schema USAGE không tự cấp quyền đọc bảng. Ngược lại, quyền SELECT trên bảng không thay thế quyền truy cập schema.

### Sequence và generated ID

Với bảng dùng sequence:

~~~sql
INSERT INTO orders (customer_id, status)
VALUES (100, 'NEW');
~~~

Nếu default của ID gọi nextval() trên sequence, role ghi có thể cần quyền USAGE trên sequence đó. Cấp quyền đúng sequence thay vì quyền rộng trên mọi sequence nếu schema có nhiều nhóm dữ liệu nhạy cảm.

SERIAL và IDENTITY có khác biệt về cách database quản lý sequence và quyền. Hãy xác nhận quyền với kiểu cột và câu INSERT thực tế.

## 8. PostgreSQL: quyền cho object được tạo trong tương lai

GRANT trên ALL TABLES IN SCHEMA chỉ áp dụng cho object tồn tại tại thời điểm chạy lệnh. Bảng mới do migration tạo sau đó không tự động nhận cùng quyền nếu không có default privileges.

Ví dụ:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE orders_owner
IN SCHEMA orders
GRANT SELECT, INSERT, UPDATE ON TABLES
TO orders_runtime_role;

ALTER DEFAULT PRIVILEGES
FOR ROLE orders_owner
IN SCHEMA orders
GRANT USAGE, SELECT ON SEQUENCES
TO orders_runtime_role;
~~~

Default privileges được áp dụng cho object mới do role được chỉ định tạo ra trong schema tương ứng. Nếu migration chạy dưới một role khác, cấu hình default privileges cho đúng role tạo object.

Đừng nhầm default privileges với việc tự sửa quyền của các bảng cũ. Vẫn cần GRANT hiện tại cho object đã tồn tại và kiểm tra quyền sau mỗi migration.

## 9. PostgreSQL: cấp quyền theo cột

Nếu runtime chỉ được sửa một số cột, PostgreSQL hỗ trợ column-level privilege:

~~~sql
GRANT SELECT ON orders.customer
TO orders_runtime_role;

GRANT UPDATE (display_name, phone_number)
ON orders.customer
TO orders_runtime_role;
~~~

Ví dụ này cho phép đọc bảng nhưng chỉ UPDATE hai cột được liệt kê. Không cấp UPDATE cấp bảng cho cùng role nếu muốn giới hạn cột, vì quyền rộng hơn sẽ làm mất tác dụng của giới hạn.

Column-level privilege hữu ích khi bảng có cột nhạy cảm như credit_limit, risk_score hoặc is_admin. Tuy nhiên, nó không thay thế kiểm tra nghiệp vụ: service vẫn cần xác thực người dùng có quyền thay đổi giá trị cụ thể hay không.

## 10. PostgreSQL: tránh quyền quản trị và quyền PUBLIC không cần thiết

Runtime không nên có các thuộc tính quyền như:

- SUPERUSER.
- CREATEDB.
- CREATEROLE.
- REPLICATION.
- BYPASSRLS.

Không cấp membership vào role quản trị chỉ để giải quyết một lỗi permission denied.

PostgreSQL có role PUBLIC mà mọi role là thành viên. Một số quyền mặc định có thể được cấp cho PUBLIC, tùy database/schema/object và phiên bản. Hãy kiểm tra các quyền mặc định trong môi trường của mình.

Ví dụ có thể thu hồi quyền CREATE trên schema public nếu ứng dụng không cần:

~~~sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
~~~

Đây là thay đổi ở phạm vi schema, có thể ảnh hưởng ứng dụng khác dùng chung database. Chỉ thực hiện sau khi kiểm tra owner, migration và workload hiện tại. Không chạy các lệnh REVOKE rộng trên production mà chưa đánh giá tác động.

Ngoài ra, kiểm tra search_path. Không để runtime tìm function/table qua schema mà người không tin cậy có thể tạo object cùng tên. Đặt search path an toàn và schema-qualified tên object khi cần.

## 11. Ví dụ MySQL: role và tài khoản runtime

MySQL hỗ trợ role để gom privilege:

~~~sql
CREATE ROLE 'orders_runtime_role';

GRANT SELECT, INSERT, UPDATE
ON orders_db.orders
TO 'orders_runtime_role';

GRANT SELECT, INSERT
ON orders_db.order_line
TO 'orders_runtime_role';

CREATE USER 'orders_runtime'@'10.%'
IDENTIFIED BY '<managed-secret>';

GRANT 'orders_runtime_role'
TO 'orders_runtime'@'10.%';

SET DEFAULT ROLE 'orders_runtime_role'
TO 'orders_runtime'@'10.%';
~~~

Các điểm cần chú ý:

- MySQL account được xác định bởi cả user và host.
- GRANT ... ON database.table giới hạn quyền theo object cụ thể.
- SET DEFAULT ROLE giúp role được kích hoạt mặc định khi login.
- Không dùng GRANT ALL ON *.* cho tài khoản runtime.
- Không cấp FILE, PROCESS, SUPER, CREATE USER, GRANT OPTION hoặc quyền global khác nếu workload không cần.

Tên role và cú pháp có thể khác theo phiên bản MySQL/MariaDB. Hãy kiểm tra đúng sản phẩm và phiên bản đang chạy.

### MySQL: tách quyền migration

Migration account có thể cần CREATE/ALTER/INDEX/DROP trong schema triển khai, nhưng runtime không cần:

~~~sql
CREATE ROLE 'orders_migration_role';

GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, INDEX, DROP
ON orders_db.*
TO 'orders_migration_role';
~~~

Danh sách quyền thực tế phụ thuộc công cụ migration và loại thay đổi schema. Chỉ cấp quyền cần cho migration đang dùng. Tài khoản này không nên được cấu hình trong connection pool của ứng dụng phục vụ request.

## 12. Ví dụ SQL Server: database user và database role

SQL Server phân biệt server login và database user. Sau khi tạo login, tạo user tương ứng trong database rồi gán vào database role:

~~~sql
USE master;
CREATE LOGIN orders_runtime
WITH PASSWORD = '<managed-secret>';
GO

USE orders_db;
CREATE USER orders_runtime
FOR LOGIN orders_runtime;
GO

CREATE ROLE orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON SCHEMA::orders
TO orders_runtime_role;

ALTER ROLE orders_runtime_role
ADD MEMBER orders_runtime;
GO
~~~

Ví dụ cấp SELECT/INSERT/UPDATE trên schema orders. Nếu cần giới hạn object hoặc cột, có thể GRANT trên bảng hoặc cột cụ thể.

Không thêm runtime vào các role rộng như db_owner, db_ddladmin hoặc server role sysadmin để giải quyết lỗi thao tác. Hãy xác định đúng permission thiếu và cấp trong phạm vi hẹp.

### SQL Server: quyền cho stored procedure

Nếu ứng dụng chỉ được thực hiện nghiệp vụ qua stored procedure, có thể chỉ cấp EXECUTE trên procedure hoặc schema chứa procedure:

~~~sql
GRANT EXECUTE
ON OBJECT::orders.CreateOrder
TO orders_runtime_role;
~~~

Khi dùng stored procedure để giới hạn quyền, cần xem xét ownership chaining, execution context và quyền mà procedure sử dụng bên trong. Không cấp thêm quyền trực tiếp trên bảng nếu thiết kế bảo mật không cần.

## 13. Ví dụ Oracle: role và object privilege

Oracle thường dùng role để gom quyền:

~~~sql
CREATE ROLE orders_runtime_role;

GRANT CREATE SESSION
TO orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON orders_owner.orders
TO orders_runtime_role;

GRANT SELECT, INSERT
ON orders_owner.order_line
TO orders_runtime_role;

GRANT SELECT
ON orders_owner.customer_view
TO orders_runtime_role;

GRANT orders_runtime_role
TO orders_runtime;
~~~

CREATE SESSION cho phép user đăng nhập. Các object privilege giới hạn thao tác trên object thuộc schema owner.

Không cấp các system privilege rộng như DBA, CREATE ANY TABLE, ALTER ANY TABLE hoặc SELECT ANY TABLE cho tài khoản runtime nếu không có yêu cầu được phê duyệt.

Với sequence, Oracle dùng quyền trên sequence, ví dụ:

~~~sql
GRANT SELECT ON orders_owner.orders_seq
TO orders_runtime_role;
~~~

Quyền cần thiết phụ thuộc cách câu INSERT gọi NEXTVAL, procedure và object đang được truy cập. Kiểm thử bằng chính user runtime.

## 14. SQLite và giới hạn mô hình user/role

SQLite là database nhúng, không có mô hình user/role và GRANT/REVOKE giống PostgreSQL, MySQL, SQL Server hoặc Oracle.

Trong ứng dụng dùng SQLite, kiểm soát truy cập thường dựa vào:

- Quyền đọc/ghi file database ở hệ điều hành.
- Danh tính process chạy ứng dụng.
- Thư mục chứa database và file journal/WAL.
- Quyền truy cập backup và file tạm.
- Tách file database theo workload hoặc tenant khi kiến trúc yêu cầu.
- Cấu hình connection read-only theo driver/URI nếu cần.

Chế độ read-only và cú pháp URI phụ thuộc driver. Không giả định mọi R2DBC SQLite driver hỗ trợ cùng option.

Vì SQLite không có server-side database user, không thể áp dụng trực tiếp ví dụ CREATE ROLE hoặc GRANT SELECT ở các phần trên. Cần bảo vệ file và tiến trình ở tầng hệ điều hành, đồng thời kiểm soát SQL trong ứng dụng.

## 15. Cấp quyền theo database, schema, bảng và cột

Nên đi từ phạm vi hẹp nhất đáp ứng nhu cầu:

1. Database: cho phép CONNECT hoặc CREATE SESSION.
2. Schema: cho phép USAGE hoặc quyền truy cập schema tương ứng.
3. Table/view: SELECT, INSERT, UPDATE, DELETE.
4. Column: chỉ đọc/sửa cột cần thiết nếu database hỗ trợ.
5. Sequence: quyền lấy giá trị ID.
6. Procedure/function: EXECUTE.

Không cấp quyền toàn database nếu service chỉ dùng một schema. Không cấp quyền toàn schema nếu service chỉ cần một vài bảng hoặc view.

### Dùng view để giới hạn dữ liệu đọc

Nếu báo cáo chỉ cần một tập cột, có thể tạo view:

~~~sql
CREATE VIEW reporting.order_summary AS
SELECT id, tenant_id, status, created_at
FROM orders.orders;
~~~

Sau đó chỉ cấp SELECT trên view cho role báo cáo. Không cấp SELECT trên bảng gốc nếu view đủ đáp ứng nhu cầu.

Khả năng bảo mật của view phụ thuộc database, cấu hình view, owner/invoker semantics và quyền truy cập object bên dưới. Cần kiểm tra cách hệ quản trị thực thi quyền cho view, đặc biệt khi view tham chiếu bảng ở schema khác.

## 16. Quyền DELETE và UPDATE cần được cân nhắc riêng

DELETE có thể gây mất dữ liệu diện rộng. Nếu ứng dụng chỉ đánh dấu bản ghi là inactive hoặc cancelled, có thể chỉ cần UPDATE trên cột trạng thái thay vì DELETE.

Nếu cần xóa:

- Giới hạn đúng bảng.
- Giới hạn đúng tenant/row bằng application authorization hoặc row-level security.
- Cân nhắc soft delete nếu phù hợp nghiệp vụ.
- Dùng transaction và kiểm tra điều kiện trước khi xóa.
- Audit các thao tác xóa quan trọng.

Quyền UPDATE cấp bảng cho phép sửa mọi cột mà database cho phép role truy cập. Nếu cần bảo vệ cột nhạy cảm, dùng column-level privilege hoặc stored procedure phù hợp.

Không cấp TRUNCATE cho runtime chỉ vì nó có thể xóa dữ liệu nhanh. TRUNCATE có semantics và mức ảnh hưởng khác DELETE, tùy database.

## 17. Phân quyền cho migration và runtime

Schema migration cần quyền rộng hơn xử lý request. Hai loại credential nên được tách:

~~~text
Deploy pipeline
      |
      v
orders_migration
      |
      +--> CREATE / ALTER / INDEX / DROP
      |
      v
orders schema

Application runtime
      |
      v
orders_runtime
      |
      +--> SELECT / INSERT / UPDATE
      |
      v
orders schema
~~~

Quy trình đề xuất:

1. Migration job dùng credential migration lấy từ secret store.
2. Migration thay đổi schema theo version.
3. Kiểm tra object owner và quyền mặc định của object mới.
4. Ứng dụng khởi động bằng credential runtime.
5. Runtime chỉ thực hiện DML được cấp.

Không chạy migration tự động bằng tài khoản runtime nếu runtime không cần DDL. Nếu framework hoặc startup hook cố chạy migration, hãy cấu hình migration chạy trong pipeline riêng hoặc dùng credential riêng.

### Default privileges và object mới

Sau khi migration tạo bảng mới, role runtime có thể bị lỗi permission denied nếu quyền chỉ được cấp trên các bảng cũ. Cần:

- Cấu hình default privileges phù hợp với owner role (nếu database hỗ trợ).
- Hoặc để migration cấp quyền cho object mới.
- Kiểm tra sequence, view, procedure và function mới.
- Có test khởi động ứng dụng bằng runtime credential sau migration.

## 18. Tích hợp quyền với Spring Data R2DBC

Spring Data R2DBC sử dụng credential mà ConnectionFactory cung cấp. Ví dụ cấu hình đơn giản:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders_db
    username: ORDERS_DB_USERNAME
    password: ORDERS_DB_PASSWORD
~~~

ORDERS_DB_USERNAME và ORDERS_DB_PASSWORD đại diện cho giá trị được cấp từ environment hoặc secret manager ở runtime. Không commit giá trị thật vào application.yml, Docker image hoặc repository.

Khi ReactiveCrudRepository gọi findById(), save() hoặc deleteById(), database thực thi thao tác dưới quyền của account trong connection. Nếu role không có quyền UPDATE, save() có thể phát lỗi database khi framework chọn nhánh UPDATE.

Tương tự, DatabaseClient không vượt qua database privilege. Việc viết SQL trực tiếp không làm câu lệnh có thêm quyền.

### Phân biệt lỗi mapping và lỗi quyền

Một số lỗi thường thấy:

- Permission denied / insufficient privilege: account thiếu quyền trên database/schema/object.
- Authentication failed: username/password hoặc cơ chế xác thực sai.
- Object not found: schema/search path hoặc tên object sai; đôi khi database cố ý không tiết lộ object.
- SQL syntax/type error: câu lệnh hoặc bind type không hợp lệ.

Không xử lý permission error bằng cách tự động cấp quyền admin. Xác định chính xác object và operation bị từ chối, rồi cấp quyền tối thiểu nếu nghiệp vụ hợp lệ.

## 19. Tách read-only và read-write ConnectionFactory

Một ứng dụng có workload đọc và ghi khác nhau có thể dùng hai account:

~~~text
Read service
    |
    v
readOnlyConnectionFactory
    |
    v
orders_readonly (SELECT)

Write service
    |
    v
readWriteConnectionFactory
    |
    v
orders_runtime (SELECT/INSERT/UPDATE)
~~~

Read-only account có thể kết nối replica hoặc database chính nhưng chỉ được cấp SELECT. Nếu kết nối replica, cần chấp nhận replication lag và semantics đọc nhất quán theo nghiệp vụ.

Ví dụ bean:

~~~java
@Bean("ordersReadOnlyConnectionFactory")
ConnectionFactory ordersReadOnlyConnectionFactory(
        ReadOnlyDatabaseProperties properties) {
    return properties.connectionFactory();
}

@Bean("ordersReadWriteConnectionFactory")
ConnectionFactory ordersReadWriteConnectionFactory(
        ReadWriteDatabaseProperties properties) {
    return properties.connectionFactory();
}
~~~

Mỗi repository group hoặc DatabaseClient cần được gắn đúng ConnectionFactory thông qua cấu hình entity operations/qualifier. Không dựa vào tên method find... để database tự áp dụng read-only account; credential được chọn từ connection factory.

@Transactional(readOnly = true) có thể cung cấp hint cho transaction infrastructure hoặc database, nhưng không thay thế quyền SELECT-only ở database. Muốn database từ chối ghi, hãy dùng account/role không có quyền ghi hoặc transaction read-only được database thực thi.

## 20. Phân quyền theo tenant và row-level security

Quyền SELECT trên bảng cho phép account đọc mọi row mà privilege đó bao phủ. Nếu bảng chứa dữ liệu của nhiều tenant, việc chỉ dùng application filter có thể chưa đủ khi có lỗi query hoặc một endpoint quên điều kiện tenant.

Một số database hỗ trợ row-level security (RLS), policy hoặc view có điều kiện. Với PostgreSQL, ví dụ:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::bigint
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::bigint
);
~~~

Ứng dụng thiết lập tenant context trong transaction:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

Tham số thứ ba true làm cấu hình chỉ tồn tại trong transaction hiện tại (tương đương local setting). Cần bảo đảm lệnh thiết lập context và mọi query tenant chạy trên cùng transaction/connection.

### RLS không thay thế xác thực tenant

Giá trị tenant phải được lấy từ principal đã xác thực hoặc một nguồn tin cậy. Không nhận tenant ID tùy ý từ request rồi xem đó là quyền truy cập hợp lệ.

Với connection pool:

- Ưu tiên transaction-local setting thay cho session-level setting.
- Không để tenant context của request trước rò sang request sau.
- Nếu transaction bị hủy hoặc lỗi, bảo đảm context được rollback/reset theo semantics database.
- Kiểm thử tái sử dụng cùng pooled connection giữa hai tenant.

PostgreSQL superuser và role có BYPASSRLS có thể bỏ qua RLS; table owner thường cũng được miễn trừ trừ khi dùng FORCE ROW LEVEL SECURITY. Vì vậy runtime không nên là superuser hoặc owner nếu mục tiêu là dựa vào RLS để giới hạn row.

RLS, policy và session context khác nhau giữa PostgreSQL, SQL Server, Oracle và các database khác. Không dùng cú pháp PostgreSQL ở trên như giải pháp portable.

## 21. Quyền EXECUTE cho stored procedure/function

Nếu ứng dụng chỉ cần gọi một số nghiệp vụ đã được đóng gói trong stored procedure, có thể cấp EXECUTE thay vì quyền DML trực tiếp trên tất cả bảng.

Ví dụ khái niệm:

~~~sql
GRANT EXECUTE ON PROCEDURE orders.create_order
TO orders_runtime_role;
~~~

Tên cú pháp khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Cũng cần xem procedure chạy dưới quyền owner hay invoker, ownership chaining và cách database kiểm tra quyền object bên trong.

Stored procedure không tự động an toàn chỉ vì người gọi không có SELECT/UPDATE trên bảng. Procedure có thể chứa SQL động hoặc thực thi với quyền rộng. Review procedure như một ranh giới bảo mật:

- Chỉ nhận tham số cần thiết.
- Kiểm tra tenant/actor nếu procedure chịu trách nhiệm authorization.
- Không ghép input vào SQL động không kiểm soát.
- Không cấp EXECUTE trên mọi procedure nếu chỉ cần một số procedure.
- Audit các thao tác nhạy cảm.

## 22. SQL injection và quyền tối thiểu

Bind parameter vẫn là biện pháp cơ bản:

~~~java
return databaseClient.sql(
        "SELECT id, status FROM orders WHERE customer_id = :customerId"
    )
    .bind("customerId", customerId)
    .map((row, metadata) -> new OrderSummary(
        row.get("id", Long.class),
        row.get("status", String.class)
    ))
    .all();
~~~

Không nối giá trị đầu vào vào SQL:

~~~java
// Không an toàn
String sql = "SELECT * FROM orders WHERE customer_id = " + customerId;
~~~

Bind parameter dùng cho value, không dùng để bind tên bảng, tên cột hoặc keyword. Nếu cần dynamic identifier:

- Dùng danh sách allowlist cố định.
- Chọn identifier từ enum/config đã kiểm soát.
- Quote identifier theo database/dialect.
- Không cho client gửi một đoạn SQL tùy ý.

Least privilege giảm phạm vi tác động nếu injection xảy ra, nhưng không biến SQL injection thành lỗi có thể chấp nhận. Vẫn phải dùng bind parameter và kiểm soát dynamic SQL.

## 23. Credential và secret management

Tài khoản quyền tối thiểu vẫn có thể gây rủi ro nếu password bị lộ. Quản lý credential cần:

- Lưu trong secret manager hoặc hệ thống quản lý secret của môi trường.
- Không commit vào Git, file mẫu có giá trị thật, log hoặc exception.
- Không in toàn bộ R2DBC URL nếu URL có thông tin xác thực.
- Hạn chế quyền đọc secret cho đúng workload.
- Dùng credential khác nhau giữa development, test, staging và production.
- Theo dõi việc truy cập và thay đổi secret.
- Thu hồi credential khi service/instance không còn hoạt động.

Không dùng chung một password cho runtime, migration, backup và DBA. Một lần lộ credential không nên mở quyền truy cập cho mọi workload.

### Rotation credential

Quy trình rotation có thể gồm:

1. Tạo credential mới với cùng role/quyền cần thiết.
2. Cập nhật secret store.
3. Khởi động hoặc reload ứng dụng theo cơ chế hỗ trợ.
4. Xác nhận connection pool mới dùng credential mới.
5. Kiểm tra request và job hoạt động.
6. Thu hồi credential cũ sau khi không còn connection phụ thuộc.

Connection pool giữ connection đã xác thực. Chỉ đổi secret trong environment không nhất thiết làm các connection hiện tại đổi credential ngay. Cần hiểu cách triển khai refresh/restart pool của ứng dụng.

## 24. Connection pool và danh tính database

Mỗi connection trong pool được mở bằng credential của ConnectionFactory. Các request dùng lại connection đó dưới cùng database principal.

Điều này có một số hệ quả:

- Không thay đổi database user theo từng request trên cùng pool.
- Không lưu tenant context dạng session-level mà quên reset.
- Không để connection có quyền admin trong pool của runtime.
- Nếu tách read-only/write, tạo ConnectionFactory/pool với account tương ứng.
- Đặt pool size và timeout phù hợp với giới hạn database.

Khi một account bị khóa hoặc password bị rotate, connection hiện có có thể còn sống đến khi bị đóng. Quy trình vận hành cần xử lý cả connection pool, không chỉ thay password trong secret store.

## 25. Audit và giám sát quyền database

Nên có khả năng trả lời:

- Account nào kết nối từ service/instance nào?
- Account nào thực hiện thao tác nhạy cảm?
- Có lần đăng nhập thất bại hoặc permission denied bất thường không?
- Role nào được gán cho runtime?
- Khi nào quyền hoặc credential được thay đổi?
- Có tài khoản cũ không còn sử dụng nhưng vẫn tồn tại không?

Các database cung cấp audit log hoặc cơ chế giám sát khác nhau. Chọn mức log phù hợp để tránh lưu dữ liệu nhạy cảm hoặc làm tăng chi phí quá mức.

Ứng dụng cũng nên log correlation ID, service identity và actor nghiệp vụ (nếu được phép) để nối request với database activity. Không ghi password, token hoặc toàn bộ bind value nhạy cảm.

Định kỳ rà soát:

- Role membership.
- Grant trên schema/table/sequence/procedure.
- Account không hoạt động.
- Credential hết hạn hoặc cần rotation.
- Quyền được cấp tạm thời cho incident.

## 26. Xử lý permission denied trong ứng dụng

Khi database từ chối thao tác, R2DBC thường phát lỗi data access qua reactive pipeline. Không nên:

- Retry vô hạn một lỗi thiếu quyền.
- Tự động cấp thêm quyền từ code ứng dụng.
- Nuốt lỗi rồi trả thành công.
- Trả nguyên thông tin schema, SQL hoặc quyền nội bộ cho client cuối.

Nên:

1. Giữ lỗi ở tầng service để request/job thất bại rõ ràng.
2. Ghi log nội bộ với correlation ID và operation đã được che dữ liệu.
3. Phân biệt lỗi cấu hình quyền với lỗi nghiệp vụ.
4. Chỉ cấp thêm quyền sau khi xác nhận operation là hợp lệ và quyền đó thực sự cần.
5. Không lặp lại một thao tác ghi nếu chưa rõ lần đầu có thực thi một phần hay không.

Một permission error thường không phải lỗi transient để retry. Retry chỉ phù hợp với lỗi tạm thời được xác định rõ như connection reset hoặc deadlock theo chính sách.

## 27. Kiểm thử bằng đúng runtime account

Test chạy bằng tài khoản developer hoặc admin có thể che giấu việc runtime thiếu quyền. Integration test bảo mật cần kết nối bằng credential giống production runtime.

Ví dụ test matrix:

| Thao tác | Runtime role | Read-only role | Migration role |
|---|---|---|---|
| SELECT orders | Thành công | Thành công | Theo nhu cầu |
| INSERT orders | Thành công nếu cần | Bị từ chối | Theo nhu cầu |
| UPDATE orders | Thành công nếu cần | Bị từ chối | Theo nhu cầu |
| DELETE orders | Bị từ chối nếu không cần | Bị từ chối | Theo nhu cầu |
| CREATE TABLE | Bị từ chối | Bị từ chối | Thành công nếu cần |
| ALTER TABLE | Bị từ chối | Bị từ chối | Thành công nếu cần |
| Đọc billing schema | Bị từ chối nếu không thuộc service | Bị từ chối | Theo phạm vi migration |

Kiểm tra cả hành vi được phép và bị từ chối. Nếu chỉ test SELECT thành công, chưa chứng minh được tài khoản runtime không thể DROP TABLE.

### Kiểm thử sau migration

Một quy trình CI/CD nên:

1. Tạo database/schema test.
2. Chạy migration bằng credential migration.
3. Chuyển sang credential runtime.
4. Khởi động ứng dụng hoặc integration test.
5. Chạy CRUD/query/procedure mà service cần.
6. Thử một số thao tác ngoài phạm vi để xác nhận bị từ chối.
7. Kiểm tra quyền trên object mới tạo.

Không chạy test phá hoại trên database dùng chung hoặc production. Dùng database test riêng và dữ liệu giả.

## 28. Ví dụ kiến trúc quyền cho một ứng dụng R2DBC

Một service orders có thể tổ chức:

~~~text
                    Database: orders_db
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
   orders_runtime    orders_readonly   orders_migration
          |                 |                 |
          v                 v                 v
   SELECT/INSERT/      SELECT trên        DDL theo
   UPDATE cần thiết    view/bảng cần      schema scope
          |                 |                 |
          v                 v                 v
   Write Connection   Read Connection    Migration job
       Factory            Factory
          |                 |
          v                 v
   R2dbcEntityTemplate  R2dbcEntityTemplate
          |                 |
          v                 v
   Write repositories  Read repositories
~~~

Mỗi ConnectionFactory được cấu hình bằng credential phù hợp. Repository group được gắn với đúng R2dbcEntityOperations, còn transaction manager sử dụng cùng ConnectionFactory tương ứng.

Migration job là tiến trình riêng, không phải một endpoint runtime. Khi triển khai xong, ứng dụng request chỉ cần quyền DML đã định nghĩa.

## 29. Checklist thiết kế quyền tối thiểu

Trước khi triển khai:

1. Liệt kê service, worker, reporting và migration workload.
2. Xác định database/schema/table/view/sequence/procedure mỗi workload cần.
3. Liệt kê thao tác SELECT, INSERT, UPDATE, DELETE, EXECUTE cụ thể.
4. Xác định có thể giới hạn theo cột hoặc view không.
5. Tách object owner/migration account khỏi runtime account.
6. Tạo role nhóm không đăng nhập nếu database hỗ trợ.
7. Tạo login riêng cho từng workload/môi trường.
8. Không cấp quyền quản trị, GRANT OPTION hoặc quyền global không cần thiết.
9. Cấu hình ConnectionFactory với credential đúng từ secret store.
10. Kiểm tra connection pool và transaction manager dùng đúng account/database.
11. Nếu multi-tenant, đánh giá RLS hoặc policy phù hợp và bảo vệ tenant context.
12. Kiểm soát dynamic SQL bằng bind parameter và allowlist identifier.
13. Cấu hình default privileges hoặc migration grants cho object mới.
14. Kiểm thử quyền thành công và quyền bị từ chối bằng runtime account.
15. Theo dõi login, permission error, grant và credential rotation.
16. Rà soát, thu hồi quyền không còn cần.

## 30. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng tài khoản DBA cho R2DBC runtime | Lỗi ứng dụng có thể ảnh hưởng toàn database | Tạo runtime role riêng |
| Dùng chung credential runtime và migration | Service request có thể thay schema | Tách migration identity |
| GRANT ALL trên mọi database | Phạm vi truy cập quá rộng | Cấp quyền theo schema/object/operation |
| Runtime sở hữu bảng | Có thể thay đổi object ngoài nhu cầu DML | Dùng owner role riêng |
| Chỉ cấp quyền trên bảng cũ | Bảng mới migration tạo bị permission denied | Default privileges hoặc migration grant |
| Quên quyền sequence | INSERT sinh ID thất bại | Cấp quyền đúng sequence theo database |
| Cấp DELETE/TRUNCATE không cần thiết | Tăng nguy cơ mất dữ liệu | Chỉ cấp thao tác nghiệp vụ cần |
| Nghĩ @Transactional(readOnly=true) là rào chắn bảo mật | Database có thể vẫn cho ghi | Dùng read-only database role |
| Nhầm database account với end user | Không kiểm soát được quyền từng actor | Authorization ở ứng dụng và RLS nếu phù hợp |
| Tin tenant ID từ request | Có thể truy cập tenant khác | Lấy tenant từ principal tin cậy |
| Dùng session-level tenant setting với pool | Context có thể rò giữa request | Transaction-local setting và kiểm thử pool reuse |
| Dùng SQL động từ input | SQL injection hoặc truy cập object ngoài dự kiến | Bind value và allowlist identifier |
| Cấp role admin để sửa permission error | Mở rộng quyền quá mức | Xác định đúng object/operation bị từ chối |
| Chỉ test bằng tài khoản developer | Không phát hiện runtime thiếu quyền | Test bằng runtime credential |
| Đổi secret nhưng không làm mới pool | Connection cũ vẫn dùng credential cũ | Có kế hoạch refresh/restart pool |
| Không audit role membership | Quyền cũ tồn tại lâu dài | Rà soát và thu hồi định kỳ |

## 31. Ghi nhớ

- Least privilege nghĩa là mỗi database account chỉ có quyền cần cho đúng workload.
- Database account đại diện cho service/connection; nó không thay thế authorization của người dùng cuối.
- Tách runtime, read-only, worker, migration và DBA khi chúng có nhu cầu quyền khác nhau.
- Dùng role để gom quyền và login riêng để quản lý credential theo môi trường/workload.
- Không để runtime sở hữu schema/table hoặc có quyền SUPERUSER, DBA, db_owner, CREATEROLE hay quyền tương đương nếu không cần.
- Cấp CONNECT/session, schema usage, table DML, sequence và procedure EXECUTE theo phạm vi thực tế.
- Quyền trên bảng hiện có không tự bao phủ object được tạo trong tương lai; cấu hình default privileges hoặc cấp quyền trong migration.
- PostgreSQL, MySQL, SQL Server và Oracle có cú pháp/semantics GRANT khác nhau; SQLite không có server-side user/role.
- @Transactional(readOnly = true) không thay thế database role chỉ đọc.
- Spring Data R2DBC và DatabaseClient luôn chạy dưới quyền của principal gắn với ConnectionFactory.
- Với multi-tenant, kết hợp application authorization với RLS/policy nếu phù hợp; tenant context phải được thiết lập an toàn trong transaction.
- Dùng bind parameter cho value, allowlist cho identifier và không ghép SQL từ input.
- Quản lý password bằng secret store, tách credential giữa môi trường và có quy trình rotation/revocation.
- Kiểm thử cả thao tác được phép lẫn bị từ chối bằng đúng runtime account sau migration.
- Theo dõi database grants, login, permission error và rà soát quyền định kỳ.
