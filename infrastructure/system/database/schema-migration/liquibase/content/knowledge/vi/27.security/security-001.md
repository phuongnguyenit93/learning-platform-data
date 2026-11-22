# Phân quyền tài khoản migration theo nguyên tắc tối thiểu

## 1. Mục tiêu và bối cảnh

Liquibase cần kết nối tới database để đọc lịch sử triển khai, lấy khóa điều phối và thực thi changeset. Các thao tác này thường cần quyền rộng hơn tài khoản mà ứng dụng dùng để đọc và ghi dữ liệu nghiệp vụ. Nếu dùng chung một tài khoản có quyền quản trị cho cả migration lẫn runtime, một lỗi SQL, lỗ hổng ứng dụng hoặc credential bị lộ có thể dẫn tới thay đổi hoặc xóa schema ngoài phạm vi cần thiết.

**Nguyên tắc tối thiểu (least privilege)** yêu cầu mỗi danh tính chỉ có đúng quyền cần cho nhiệm vụ, trên đúng database/schema/đối tượng và trong đúng khoảng thời gian. Với Liquibase, điều đó thường có nghĩa là tách tài khoản migration khỏi tài khoản runtime, giới hạn quyền DDL theo schema, bảo vệ bảng lịch sử, quản lý secret riêng và chỉ cấp quyền production cho job triển khai đã được kiểm soát.

Bài thuộc chương **Bảo mật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **phân quyền tài khoản migration theo nguyên tắc tối thiểu**, từ mô hình danh tính, quyền metadata, quyền DDL/DML theo DBMS đến kiểm thử và thu hồi quyền.

Sau bài học, bạn cần có thể:

1. Phân biệt tài khoản runtime, tài khoản migration, owner schema và tài khoản DBA/break-glass.
2. Xác định quyền Liquibase cần để đọc/ghi DATABASECHANGELOG, DATABASECHANGELOGLOCK và thực thi changeset.
3. Giới hạn quyền migration theo database, schema, loại đối tượng và nhiệm vụ phát hành.
4. Hiểu vì sao quyền ALTER/CREATE không đồng nghĩa quyền sở hữu mọi đối tượng.
5. Cấu hình Spring Boot và CI/CD dùng credential migration riêng, không đưa secret vào changelog.
6. Thiết kế quyền runtime chỉ đủ cho các thao tác ứng dụng cần.
7. Kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối.
8. Lập quy trình cấp, xoay vòng, kiểm toán và thu hồi quyền.

## 2. Least privilege áp dụng cho migration như thế nào?

Một tài khoản migration không nên mặc định là superuser, database owner hoặc tài khoản có quyền quản trị toàn server. Nó chỉ cần quyền để thực hiện những thay đổi đã được phê duyệt trong phạm vi ứng dụng.

Khi thiết kế quyền, hãy trả lời năm câu hỏi:

- **Ai?** Job CI/CD, ứng dụng Spring Boot, DBA hay người phát triển?
- **Ở đâu?** Database, catalog, schema hoặc tập đối tượng nào?
- **Làm gì?** SELECT/INSERT/UPDATE trên bảng metadata, CREATE/ALTER trên schema hay GRANT quyền?
- **Khi nào?** Mọi lúc, chỉ trong cửa sổ release hay chỉ trong một lần bootstrap?
- **Bằng chứng nào?** Ticket, commit, pipeline run, người phê duyệt và log nào chứng minh quyền được dùng đúng?

Quyền nên được cấp theo nhiệm vụ và thu hẹp theo phạm vi. Ví dụ, một job chỉ thêm cột vào schema app không cần quyền tạo login, cài extension toàn server, đọc mọi database hoặc thay đổi cấu hình replication.

### 2.1. Bốn loại danh tính nên phân biệt

| Danh tính | Mục đích | Quyền điển hình |
|---|---|---|
| Runtime application | Xử lý request và nghiệp vụ | SELECT/INSERT/UPDATE/DELETE trên các đối tượng ứng dụng cần dùng; EXECUTE trên routine cần thiết |
| Liquibase migrator | Chạy migration đã review | Đọc/ghi metadata Liquibase và DDL/DML cần cho schema thuộc phạm vi |
| Schema/object owner | Sở hữu đối tượng database | Quản lý vòng đời đối tượng trong schema được giao |
| DBA/break-glass | Bootstrap, phục hồi hoặc xử lý sự cố đặc biệt | Quyền quản trị rộng, dùng có phê duyệt, thời hạn và kiểm toán |

Có thể có thêm tài khoản chỉ đọc cho báo cáo, kiểm tra hoặc giám sát. Không nên dùng tài khoản DBA cho runtime chỉ vì nó làm cho lỗi permission biến mất.

### 2.2. Tách quyền theo vòng đời

Một số thao tác chỉ cần trong giai đoạn bootstrap:

- Tạo database/schema ban đầu.
- Tạo role/login và gán membership.
- Cài extension hoặc cấu hình DBMS.
- Tạo schema metadata Liquibase.
- Thiết lập owner và default privileges.

Sau bootstrap, tài khoản migration thường chỉ cần thay đổi đối tượng trong schema đã được cấp. Không giữ quyền tạo login, cấp quyền tùy ý hoặc quản trị server nếu migration thường ngày không cần chúng.

## 3. Mô hình quyền: database, schema và object

Tên và phạm vi quyền khác nhau theo DBMS, nhưng có thể phân tích thành các lớp:

1. **Kết nối database:** cho phép mở phiên làm việc với đúng database.
2. **Quyền schema:** cho phép nhìn thấy hoặc tạo đối tượng trong schema.
3. **Quyền object:** cho phép đọc, ghi hoặc thực thi trên bảng, sequence, view, function.
4. **Quyền sở hữu:** cho phép thay đổi cấu trúc hoặc xóa đối tượng theo mô hình của DBMS.
5. **Quyền quản trị:** tạo role, cấp quyền, quản lý database/server hoặc thay đổi cấu hình toàn cục.

Không phải DBMS nào cũng dùng cùng thuật ngữ. Đặc biệt, **quyền đọc/ghi object không tự động cho phép ALTER hoặc DROP object**. Nhiều hệ quản trị yêu cầu principal sở hữu đối tượng hoặc có quyền quản trị tương ứng.

Vì vậy, trước khi cấp quyền, hãy liệt kê changeset dự kiến cần thao tác gì: CREATE TABLE, ADD COLUMN, CREATE INDEX, ALTER VIEW, CREATE FUNCTION, GRANT, DROP hay backfill dữ liệu. Không cấp một role rộng chỉ dựa trên câu “Liquibase cần quyền ghi database”.

## 4. Tài khoản migration cần những quyền nào?

Liquibase thường cần quyền ở hai nhóm riêng.

### 4.1. Quyền trên bảng metadata

Liquibase sử dụng các bảng lịch sử và khóa, thường là:

- **DATABASECHANGELOG:** ghi nhận changeset đã chạy, checksum, thời điểm và trạng thái thực thi.
- **DATABASECHANGELOGLOCK:** điều phối để tránh nhiều tiến trình Liquibase cập nhật cùng lịch sử đồng thời.

Tài khoản migration cần đọc và cập nhật các bảng này. Nếu Liquibase phải tạo chúng lần đầu, tài khoản cũng cần quyền tạo đối tượng trong schema metadata. Khi các bảng đã được bootstrap và quyền được cấp riêng, có thể thu hẹp quyền tạo schema theo chính sách của tổ chức.

Các thao tác nội bộ cụ thể có thể thay đổi theo phiên bản Liquibase và DBMS. Hãy kiểm thử bằng đúng phiên bản công cụ và quyền production dự kiến; không cấp quyền quản trị toàn database chỉ để tránh một lỗi khởi tạo metadata.

### 4.2. Quyền trên schema ứng dụng

Tùy changeset, migration có thể cần:

- Tạo bảng, view, sequence, function hoặc index.
- Thêm/sửa cột, constraint và default.
- Thay đổi định nghĩa view/function.
- Chèn hoặc cập nhật dữ liệu tham chiếu.
- Cấp quyền cho role runtime nếu quy trình cho phép.
- Xóa đối tượng cũ trong migration đã được phê duyệt.

Không phải mọi dự án đều cần tất cả các quyền này. Một release chỉ thêm cột có thể không cần quyền tạo role, cài extension hoặc drop table.

### 4.3. Quyền runtime khác quyền migration

Runtime thường cần quyền thao tác dữ liệu, không cần tạo bảng hay sửa cấu trúc:

| Nhu cầu ứng dụng | Quyền có thể cần |
|---|---|
| Đọc dữ liệu | SELECT |
| Tạo bản ghi | INSERT |
| Sửa bản ghi | UPDATE |
| Xóa theo nghiệp vụ | DELETE |
| Sinh khóa từ sequence | USAGE/SELECT tùy DBMS |
| Gọi function/procedure | EXECUTE |
| Truy cập schema | USAGE hoặc quyền tương đương |

Không cấp TRUNCATE, ALTER, DROP, CREATE USER, GRANT OPTION hoặc quyền quản trị rộng cho runtime nếu ứng dụng không có yêu cầu đặc biệt được phê duyệt.

## 5. Quyền sở hữu đối tượng quan trọng hơn một danh sách GRANT rộng

Nhiều hệ quản trị phân biệt quyền được cấp trên object với quyền sở hữu object. Ví dụ, một role có thể được phép SELECT hoặc INSERT trên bảng nhưng không thể ALTER TABLE hay DROP TABLE.

Điều này thường gây lỗi khi:

1. DBA tạo bảng dưới owner app_owner.
2. Liquibase kết nối bằng app_migrator.
3. app_migrator có quyền DML hoặc CREATE trong schema.
4. Changeset cần thay đổi bảng do app_owner sở hữu.
5. DBMS từ chối vì migration principal không có quyền sở hữu/điều khiển cần thiết.

Giải pháp là xác định một mô hình owner ổn định:

- Các đối tượng ứng dụng thuộc một owner role được quản lý.
- Liquibase thực thi trong danh tính có quyền owner theo cơ chế đã kiểm thử.
- Runtime chỉ nhận quyền sử dụng object.
- DBA giữ quyền bootstrap và break-glass.

Không giải quyết lỗi ownership bằng cách cấp db_owner, ALL PRIVILEGES trên toàn database hoặc superuser một cách mặc định.

## 6. Ví dụ mô hình role trên PostgreSQL

PostgreSQL phân biệt role có thể đăng nhập và role nhóm. Một mô hình tham khảo:

~~~sql
-- Các lệnh bootstrap này do DBA/role có thẩm quyền thực hiện.
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_runtime NOLOGIN;
CREATE ROLE app_migrator LOGIN;
CREATE ROLE app_runtime_login LOGIN;

GRANT app_owner TO app_migrator;
GRANT app_runtime TO app_runtime_login;
~~~

Ý nghĩa:

- app_owner là role sở hữu schema/đối tượng ứng dụng.
- app_migrator là danh tính kết nối của job migration.
- app_runtime là nhóm quyền dữ liệu cần cho ứng dụng.
- app_runtime_login là login của tiến trình ứng dụng.

Đây là ví dụ kiến trúc, không phải script có thể chạy nguyên trạng trong mọi hệ thống. Cần đặt mật khẩu bằng quy trình secret an toàn, xác định membership options và phiên bản PostgreSQL.

**Lưu ý về role owner:** chỉ GRANT membership không có nghĩa mọi đối tượng do app_migrator tạo sẽ tự động thuộc app_owner. Nếu muốn object mới có owner là app_owner, phiên Liquibase phải thực sự chạy với current role phù hợp, ví dụ qua cơ chế SET ROLE được cấu hình và kiểm thử trên connection. Nếu không có cơ chế đó, hãy chọn mô hình owner đơn giản hơn và nhất quán, chẳng hạn để principal migration là owner của schema được giao. Luôn kiểm tra current_user và owner của object sau migration.

### 6.1. Cấp kết nối và schema

Giả sử DBA đã tạo database orders, schema app thuộc owner role và schema metadata liquibase_meta thuộc migrator:

~~~sql
CREATE SCHEMA app AUTHORIZATION app_owner;
CREATE SCHEMA liquibase_meta AUTHORIZATION app_migrator;

GRANT CONNECT ON DATABASE orders TO app_migrator;
GRANT CONNECT ON DATABASE orders TO app_runtime_login;
~~~

Nếu phiên migration chạy dưới app_owner, hãy bảo đảm cơ chế role switch đã được thiết lập trước khi chạy DDL. Nếu migration principal trực tiếp sở hữu schema, điều chỉnh owner/grant theo mô hình đó.

Không cấp CREATE ON DATABASE cho migration chỉ để nó có thể thay đổi bảng trong schema đã tồn tại. Quyền tạo schema/database là một phạm vi khác và chỉ nên cấp khi changeset thực sự cần.

### 6.2. Quyền metadata Liquibase

Nếu liquibase_meta được tạo và sở hữu bởi app_migrator, tài khoản đó có thể tạo bảng lịch sử trong schema này. Nếu DBA tạo trước các bảng metadata, hãy cấp đúng quyền cần cho các thao tác đọc/ghi trên hai bảng và quyền sequence nếu phiên bản/DBMS sử dụng.

Cấu hình Spring Boot có thể chỉ định schema metadata riêng:

~~~yaml
spring:
  liquibase:
    liquibase-schema: liquibase_meta
    database-change-log-table: DATABASECHANGELOG
    database-change-log-lock-table: DATABASECHANGELOGLOCK
~~~

Tên property và cách hoạt động cần xác minh theo phiên bản Spring Boot. Không để runtime role có quyền UPDATE/DELETE trên bảng lịch sử Liquibase nếu ứng dụng không có nhiệm vụ quản trị chúng.

### 6.3. Quyền runtime trên bảng và sequence

Sau khi schema được tạo, DBA hoặc owner role có thể cấp quyền runtime:

~~~sql
GRANT USAGE ON SCHEMA app TO app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO app_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA app
TO app_runtime;
~~~

Đây là ví dụ PostgreSQL. Chỉ cấp các quyền DML mà ứng dụng thực sự cần; có thể thu hẹp theo bảng hoặc nhóm bảng thay vì toàn schema. Nếu dùng identity/sequence, kiểm tra chính xác quyền cần cho thao tác sinh khóa.

### 6.4. Default privileges cho object mới

Quyền đã cấp trên các bảng hiện có không tự động áp dụng cho bảng được tạo trong tương lai. PostgreSQL hỗ trợ default privileges:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
~~~

Default privileges gắn với role tạo object. Nếu Liquibase tạo object dưới một role khác app_owner, các thiết lập trên có thể không áp dụng. Hãy xác minh role thực sự tạo object và kiểm thử bằng một bảng/sequence mới trong môi trường test.

Không cấp mặc định quyền DML cho mọi object trong mọi schema nếu runtime chỉ cần một tập nhỏ. Default privileges là thay đổi dài hạn, cần được review như code bảo mật.

## 7. Quyền PostgreSQL cho schema và object

Một số quyền PostgreSQL thường gặp:

| Phạm vi | Quyền | Ý nghĩa và giới hạn |
|---|---|---|
| Database | CONNECT | Mở kết nối tới database |
| Database | CREATE | Tạo schema hoặc object cấp database được hỗ trợ; không phải quyền ALTER mọi bảng |
| Schema | USAGE | Tra cứu/truy cập object trong schema khi có quyền object tương ứng |
| Schema | CREATE | Tạo object mới trong schema |
| Table | SELECT/INSERT/UPDATE/DELETE | Thao tác dữ liệu |
| Table | REFERENCES | Tạo foreign key tham chiếu bảng khi đáp ứng quyền |
| Table | TRIGGER | Tạo trigger trên bảng trong trường hợp phù hợp |
| Sequence | USAGE/SELECT/UPDATE | Sử dụng hoặc đọc/cập nhật sequence |
| Function | EXECUTE | Gọi function/procedure |
| Object ownership | Owner/role phù hợp | Thay đổi định nghĩa hoặc xóa object theo quy tắc ownership |

PostgreSQL không có một GRANT đơn giản tương đương quyền ALTER mọi object do role khác sở hữu. Quyền owner và membership cần được thiết kế riêng. GRANT ALL PRIVILEGES ON ALL TABLES cũng không biến grantee thành owner.

## 8. Quyền trên MySQL và MariaDB

MySQL/MariaDB sử dụng tài khoản theo cặp user và host, ví dụ app_migrator kết nối từ một subnet hoặc runner cụ thể. Không nên tạo tài khoản cho host wildcard rộng nếu hạ tầng cho phép giới hạn nguồn kết nối.

Một mô hình thường gặp:

- Tài khoản migration có quyền DDL/DML trên đúng database ứng dụng.
- Tài khoản runtime chỉ có quyền SELECT/INSERT/UPDATE/DELETE và EXECUTE cần thiết.
- Role nhóm được sử dụng nếu phiên bản hỗ trợ và tổ chức quản lý role.
- Không cấp quyền toàn server như SUPER hoặc quyền quản trị tài khoản cho migration thông thường.

Ví dụ quyền runtime minh họa:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders.*
TO 'app_runtime'@'10.%';
~~~

Phần host 10.% chỉ là ví dụ. Hãy thay bằng phạm vi mạng thực tế và chính sách xác thực của hệ thống.

Migration có thể cần các quyền như CREATE, ALTER, INDEX, REFERENCES, CREATE VIEW, SHOW VIEW, TRIGGER hoặc DROP tùy changeset. Không cấp tất cả theo thói quen; lấy danh sách từ migration đã review và thử bằng tài khoản có quyền dự kiến.

DROP có thể phá hủy bảng hoặc object. Nếu quy trình production không cho phép drop trong release thường, có thể tách thao tác phá hủy sang quy trình DBA được phê duyệt thay vì cấp quyền rộng cho mọi pipeline.

MySQL không có mô hình schema/object ownership giống PostgreSQL. Quyền được đánh giá theo account, database/table/routine và các role đang active. Hãy kiểm tra grants hiệu lực của đúng account/host và trạng thái role khi kết nối.

## 9. Quyền trên SQL Server

SQL Server phân biệt server login, database user, schema và database role. Một ứng dụng thường dùng login/user runtime, còn pipeline migration dùng một database user riêng.

Tránh cấp các role tích hợp quá rộng như db_owner hoặc db_ddladmin chỉ để Liquibase chạy thành công. Thay vào đó, xem từng thao tác cần quyền gì, chẳng hạn:

- CONNECT vào database.
- CREATE TABLE/VIEW/PROCEDURE khi cần.
- ALTER trên schema được giao.
- SELECT/INSERT/UPDATE/DELETE trên các bảng runtime.
- EXECUTE trên stored procedure/function.
- Quyền trên sequence hoặc type nếu changeset sử dụng.

SQL Server có các quyền cấp database và schema khác nhau. Tạo object có thể cần quyền CREATE tương ứng ở database và quyền ALTER trên schema đích. Quyền ALTER trên schema cũng có phạm vi rộng, vì vậy schema cần được cô lập theo ứng dụng.

Ví dụ nguyên tắc:

~~~sql
-- Minh họa; thực hiện bằng principal có thẩm quyền.
CREATE ROLE app_runtime_role;
GRANT SELECT, INSERT, UPDATE, DELETE
ON SCHEMA::app TO app_runtime_role;
~~~

Nếu ứng dụng chỉ cần một số bảng, cấp quyền theo object thay vì toàn schema. Với migration, tạo role riêng và chỉ cấp quyền DDL trên schema thuộc phạm vi. Kiểm tra owner/schema và quyền hiệu lực bằng một migration test; không suy ra từ việc user đã được thêm vào một role chung.

## 10. Quyền trên Oracle

Trong Oracle, schema thường gắn với user sở hữu các object. Tài khoản migration cần quyền tạo hoặc sửa loại object tương ứng trong schema của mình, ví dụ quyền tạo table, view, sequence, procedure hoặc trigger.

Cần thận trọng với các system privilege có hậu tố ANY, như CREATE ANY TABLE hoặc ALTER ANY TABLE, vì chúng có thể cho phép thao tác trên schema khác. Không cấp DBA, SYSDBA hoặc UNLIMITED TABLESPACE chỉ để tránh lỗi quota/quyền.

Một số điểm cần kiểm tra:

- CREATE SESSION để kết nối.
- Quyền tạo object cụ thể trong schema migration sở hữu.
- Tablespace quota phù hợp thay vì unlimited nếu có thể.
- Quyền truy cập object ở schema khác được cấp tường minh.
- Quyền EXECUTE trên package/procedure cần dùng.
- Cách quản lý synonym, role và quyền trong stored procedure.

Cách phân quyền chính xác phụ thuộc phiên bản Oracle và thiết kế schema. DBA nên bootstrap user/role/quota; Liquibase chỉ nhận quyền cần cho các changeset đã duyệt.

## 11. Tách schema metadata khỏi schema ứng dụng

Có thể lưu DATABASECHANGELOG và DATABASECHANGELOGLOCK trong schema riêng, ví dụ liquibase_meta, để:

- Giới hạn người được đọc/sửa lịch sử triển khai.
- Tách quyền quản trị metadata khỏi quyền runtime.
- Dễ sao lưu và giám sát lịch sử migration.
- Tránh để ứng dụng vô tình truy cập bảng nội bộ.
- Quản lý owner và quyền metadata độc lập với object nghiệp vụ.

Cấu hình minh họa:

~~~yaml
spring:
  liquibase:
    liquibase-schema: liquibase_meta
    default-schema: app
~~~

liquibase-schema và default-schema có ý nghĩa khác nhau. Một schema dùng lưu metadata không nhất thiết là schema mặc định của các bảng ứng dụng.

Trước khi dùng schema metadata riêng, xác minh DBMS hỗ trợ cấu hình, schema đã tồn tại hoặc Liquibase có quyền tạo nó, và tài khoản migration có quyền đọc/ghi các bảng. Không cấp quyền metadata cho runtime nếu không có yêu cầu cụ thể.

## 12. Cấu hình Spring Boot dùng tài khoản riêng

Spring Boot có thể dùng datasource chính của ứng dụng để chạy Liquibase hoặc kết nối riêng qua các thuộc tính spring.liquibase.*. Cụ thể, spring.liquibase.url, spring.liquibase.user và spring.liquibase.password định nghĩa kết nối migration riêng; spring.datasource.* vẫn mô tả datasource ứng dụng. Chỉ đặt các thuộc tính này khi thực sự muốn hai kết nối có danh tính khác nhau.

Ví dụ tách hai danh tính:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: app_runtime
    password: ${APP_DB_PASSWORD}

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: jdbc:postgresql://db.internal:5432/orders
    user: app_migrator
    password: ${MIGRATION_DB_PASSWORD}
    default-schema: app
    liquibase-schema: liquibase_meta
~~~

Ở đây:

- Datasource chính dùng app_runtime cho các thao tác nghiệp vụ.
- Liquibase dùng app_migrator để đọc/ghi metadata và thực thi migration.
- Hai kết nối cùng trỏ tới database orders trong ví dụ.
- Mật khẩu được resolve từ nguồn cấu hình môi trường, không nằm trong repository.

Tên property và cách auto-configuration có thể khác theo phiên bản Spring Boot. Hãy kiểm tra cấu hình metadata của phiên bản dự án.

### 12.1. Vì sao cần cùng database đích?

Nếu datasource ứng dụng trỏ tới database A nhưng spring.liquibase.url trỏ tới database B, migration có thể thành công ở B trong khi ứng dụng truy vấn A. Điều này tạo ra lỗi khó chẩn đoán sau khởi động.

Trong môi trường có nhiều database, kiểm tra host, port, database, schema và danh tính tài khoản của cả hai kết nối. Có thể log một database identifier không nhạy cảm trong bước preflight để xác nhận đúng đích; không log password hoặc toàn bộ JDBC URL nếu chứa secret.

### 12.2. Tắt migration tự động khi CI/CD sở hữu migration

Nếu pipeline là chủ sở hữu duy nhất của migration production, ứng dụng có thể tắt Liquibase auto-run ở profile production:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Khi đó job CI/CD cần chạy migration bằng tài khoản riêng trước khi rollout ứng dụng. Không tắt auto-run nếu chưa có cơ chế thay thế, vì database có thể chưa được cập nhật.

Không để credential migration trong secret set mà mọi replica runtime đều truy cập được nếu ứng dụng không cần chạy migration.

## 13. Tài khoản migration trong CI/CD

Một pipeline an toàn nên tách các bước:

1. Build artifact changelog bất biến.
2. Validate và review update-sql.
3. Xác minh môi trường/database đích.
4. Xin phê duyệt cho production nếu chính sách yêu cầu.
5. Cấp hoặc lấy credential migration từ secret store cho đúng job.
6. Chạy một migration job có quyền trong schema được giao.
7. Hậu kiểm history, schema và dữ liệu.
8. Thu hồi hoặc hết hạn credential tạm thời.
9. Ghi log người phê duyệt, job, commit, artifact và kết quả.

Một tài khoản migration production không nên được cấp cho mọi nhánh feature hoặc mọi pull request. Pull request có thể dùng database test và credential test riêng. Credential production chỉ được cung cấp cho pipeline release đã qua điều kiện bảo vệ.

### 13.1. Giới hạn nguồn kết nối

Nếu DBMS và hạ tầng hỗ trợ, chỉ cho phép kết nối migration từ runner, subnet hoặc workload identity được phê duyệt. Kết hợp:

- Network policy/firewall.
- TLS và xác thực phù hợp.
- Secret ngắn hạn hoặc credential rotation.
- Database allowlist.
- Audit log.
- Giới hạn số session và timeout.

Không dùng IP allowlist thay cho xác thực. Cần cả kiểm soát mạng lẫn danh tính database.

### 13.2. Một chủ sở hữu migration

Không để CI job và mọi replica Spring Boot cùng sử dụng quyền migration mà thiếu điều phối. Liquibase có DATABASECHANGELOGLOCK, nhưng quyền và khóa ở tầng pipeline vẫn cần được thiết kế.

Dùng concurrency group hoặc lock theo database/environment để bảo đảm chỉ một job release sở hữu migration tại một thời điểm. Các job khác phải chờ hoặc dừng rõ ràng.

## 14. Không đưa credential vào changelog

Changelog là mã nguồn migration, thường được lưu trong Git và đóng gói trong artifact. Không đặt trong đó:

- Username/password.
- Token hoặc private key.
- JDBC URL có thông tin xác thực.
- Secret của cloud/database.
- Lệnh tạo tài khoản kèm mật khẩu rõ.
- Thông tin kết nối production.

Dùng biến môi trường hoặc secret manager cho cấu hình kết nối. Ví dụ:

~~~yaml
spring:
  liquibase:
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
~~~

Các placeholder chỉ minh họa tên biến. Cần cấu hình nguồn secret trong CI/CD hoặc nền tảng runtime và tránh in giá trị đã resolve ra log.

Nếu migration cần cấp GRANT, hãy viết quyền đích một cách tường minh, nhưng không nhúng secret của role vào changeset. Việc tạo login/password thường thuộc quy trình provisioning của DBA/identity platform, không phải changelog schema ứng dụng.

## 15. Quyền GRANT trong changeset và ranh giới trách nhiệm

Một changeset có thể cần cấp quyền cho runtime role sau khi tạo bảng. Ví dụ trên PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 410-grant-customer-read
      author: platform-team
      dbms: postgresql
      changes:
        - sql:
            sql: GRANT SELECT ON app.customer TO app_runtime;
      rollback:
        - sql:
            sql: REVOKE SELECT ON app.customer FROM app_runtime;
~~~

Ví dụ này chỉ phù hợp nếu role app_runtime đã được bootstrap và principal thực thi có quyền cấp GRANT. Rollback chỉ thu hồi đúng quyền được changeset cấp; nếu quyền đã tồn tại trước đó do một nguồn khác, việc revoke có thể làm mất quyền hợp lệ.

Trước khi quản lý GRANT bằng Liquibase, xác định:

- Ai tạo role và quản lý membership?
- Ai sở hữu object và có quyền grant?
- Quyền có được cấp bởi một hệ thống khác không?
- Rollback có thể thu hồi nhầm quyền đã tồn tại không?
- Mọi DBMS mục tiêu có cú pháp và semantics tương đương không?

Không cho migration tự cấp thêm quyền cho chính nó hoặc tạo principal có quyền rộng hơn nếu không có quy trình quản trị riêng. Đây là ranh giới quan trọng giữa schema migration và identity/access management.

## 16. Quyền cho changeset có DDL đặc thù

Các changeset có thể yêu cầu quyền cao hơn DDL thông thường:

| Thao tác | Rủi ro/quyền cần xem xét |
|---|---|
| CREATE TABLE/ALTER TABLE | Tác động cấu trúc và dữ liệu; cần owner/ALTER phù hợp |
| DROP TABLE/COLUMN | Có thể phá hủy dữ liệu; cần phê duyệt riêng |
| CREATE INDEX CONCURRENTLY/ONLINE | Cần quyền tạo index và hiểu trạng thái khi lỗi |
| CREATE FUNCTION/PROCEDURE | Quyền tạo routine, owner và quyền EXECUTE |
| CREATE EXTENSION | Có thể cần quyền quản trị/DBMS-specific; nên bootstrap riêng |
| CREATE USER/ROLE | Thay đổi danh tính, thường thuộc DBA/identity provisioning |
| GRANT/REVOKE | Cần quyền grantor phù hợp; có thể làm lộ dữ liệu hoặc gây outage |
| Thay đổi owner | Có thể ảnh hưởng toàn bộ quyền và vòng đời object |
| Thay đổi cấu hình server | Không thuộc quyền migration schema thông thường |

Một changeset cần quyền quản trị đặc biệt không có nghĩa mọi migration đều cần quyền đó. Có thể tách bước bootstrap do DBA thực hiện khỏi migration ứng dụng để giữ quyền thường ngày hẹp hơn.

## 17. Kiểm thử quyền theo nguyên tắc allow và deny

Không chỉ kiểm tra migration thành công. Cần chứng minh tài khoản cũng **không thể làm những việc ngoài phạm vi**.

### 17.1. Kiểm tra thao tác được phép

Với migration role trong database test:

- Kết nối tới đúng database.
- Đọc và ghi DATABASECHANGELOG.
- Lấy và giải phóng DATABASECHANGELOGLOCK.
- Tạo/sửa đối tượng thuộc schema được giao.
- Chạy DML cần thiết cho migration.
- Hoàn tất changeset và ghi history.

### 17.2. Kiểm tra thao tác phải bị từ chối

Thử bằng migration role:

- Đọc database khác ngoài phạm vi.
- Tạo login/role tùy ý.
- Thay đổi schema của ứng dụng khác.
- Drop database hoặc thay đổi cấu hình server.
- Cấp quyền cho một principal không được phê duyệt.
- Truy cập secret hoặc dữ liệu không liên quan.

Kết quả từ chối là một phần của kiểm thử bảo mật. Nếu mọi thao tác đều thành công, tài khoản có thể đang được cấp quá rộng.

### 17.3. Kiểm tra runtime role

Runtime role cần thực hiện được các thao tác nghiệp vụ đã định nghĩa và bị từ chối với DDL:

- Đọc/ghi bảng theo use case.
- Gọi function/procedure được cho phép.
- Không CREATE/ALTER/DROP schema.
- Không UPDATE/DELETE bảng lịch sử Liquibase.
- Không tạo role hoặc cấp quyền.
- Không truy cập bảng nội bộ/nhạy cảm ngoài phạm vi.

Chạy test bằng đúng danh tính runtime, không dùng owner hoặc superuser trong integration test rồi kết luận quyền production đúng.

## 18. Kiểm thử migration trên database sạch và database đã tồn tại

Quyền có thể khác nhau giữa hai tình huống:

- **Database mới:** Liquibase có thể cần tạo bảng metadata, schema hoặc toàn bộ đối tượng ứng dụng.
- **Database đã tiếp nhận:** schema và metadata có thể đã được bootstrap; migration chỉ cần thay đổi các object hiện có.
- **Database được restore:** owner/grant có thể khác với môi trường nguồn.
- **Database có nhiều schema:** migration role chỉ nên có quyền ở schema thuộc ứng dụng.

Hãy thử ít nhất hai kịch bản: bootstrap database từ trạng thái rỗng và nâng cấp database từ phiên bản đã phát hành. Nếu chỉ test trên database do cùng một tài khoản superuser tạo, bạn chưa kiểm tra được mô hình quyền thực tế.

## 19. Audit và truy vết quyền migration

Một lần migration production cần trả lời được:

- Job nào đã kết nối?
- Danh tính database nào được dùng?
- Ai phê duyệt release?
- Commit và artifact changelog nào được chạy?
- Changeset nào đã áp dụng?
- Tài khoản đã thực hiện những thao tác nào?
- Có lỗi permission, grant hoặc truy cập ngoài phạm vi không?
- Credential đã được thu hồi/hết hạn chưa?

Kết hợp log Liquibase, audit log của DBMS, log CI/CD và hệ thống secret manager. Tránh ghi password/token hoặc dữ liệu nhạy cảm trong log. Giữ log theo chính sách lưu trữ và phân quyền truy cập.

DATABASECHANGELOG giúp truy vết changeset, nhưng không thay thế audit log về principal, câu lệnh trực tiếp ngoài Liquibase hoặc thao tác DBA.

## 20. Xoay vòng và thu hồi credential

Credential migration thường có giá trị cao hơn credential runtime vì có thể thay đổi cấu trúc database. Hãy:

- Dùng secret riêng cho từng môi trường.
- Không tái sử dụng mật khẩu dev/test/production.
- Xoay vòng theo chính sách và sau sự cố nghi lộ.
- Ưu tiên credential ngắn hạn/workload identity nếu nền tảng hỗ trợ.
- Thu hồi credential của runner hoặc nhân sự không còn nhiệm vụ.
- Không để secret production trong máy phát triển hoặc log CI.
- Kiểm tra connection pool/session cũ sau khi đổi credential.

Khi thu hồi quyền, xem xét các session đang mở và job đang chạy. Đừng revoke giữa một migration production nếu chưa có kế hoạch dừng/khôi phục; thay đổi quyền có thể khiến job đang thực hiện thất bại ở giữa.

## 21. Chẩn đoán lỗi permission phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không kết nối được database | Thiếu CONNECT, sai host/user hoặc network | Kiểm tra identity, network và quyền kết nối |
| Không tạo được DATABASECHANGELOG | Thiếu CREATE trong schema metadata | Bootstrap schema/bảng hoặc cấp đúng quyền tạo |
| Không cập nhật được DATABASECHANGELOGLOCK | Thiếu UPDATE/SELECT trên bảng khóa | Cấp quyền metadata tối thiểu và thử lock lifecycle |
| CREATE TABLE bị từ chối | Thiếu CREATE schema/database hoặc sai owner | Kiểm tra phạm vi schema và principal thực thi |
| ALTER TABLE bị từ chối dù có GRANT DML | Quyền dữ liệu không phải quyền sở hữu/DDL | Kiểm tra owner/role membership và current role |
| Không tạo được index | Thiếu quyền trên table/schema hoặc DBMS hạn chế | Xác định quyền cụ thể theo DBMS và loại index |
| Function tạo được nhưng runtime gọi lỗi | Thiếu EXECUTE hoặc quyền object bên trong routine | Cấp quyền thực thi tối thiểu và kiểm tra security mode |
| Ứng dụng không dùng được sequence | Thiếu USAGE/SELECT hoặc quyền tương đương | Kiểm tra sequence/identity grants |
| Bảng mới không cho runtime ghi | Default privileges chưa cấu hình cho owner tạo object | Xác minh object creator và default privileges |
| GRANT thất bại | Migration principal không có quyền grant phù hợp | Tách provisioning/DBA hoặc điều chỉnh grantor |
| Migration chạy được ở test nhưng lỗi production | Test dùng owner/superuser, production dùng role hẹp | Test bằng đúng quyền và phiên bản DBMS production |
| Runtime có thể DROP bảng | Role runtime được cấp quyền DDL quá rộng | Thu hồi quyền và kiểm tra nguồn grant kế thừa |

Khi gặp permission error, không cấp ngay quyền cao nhất. Xác định chính xác câu lệnh, principal hiệu lực, object owner và phạm vi quyền đang thiếu.

## 22. Quy trình cấp quyền cho một dự án Liquibase

Một quy trình có thể áp dụng:

1. **Liệt kê changeset:** phân loại DDL, DML, metadata, GRANT và thao tác quản trị.
2. **Xác định phạm vi:** database, schema, object và DBMS/version.
3. **Thiết kế danh tính:** runtime, migrator, owner và DBA/break-glass.
4. **Bootstrap:** DBA/identity platform tạo database, schema, role, owner và secret.
5. **Cấp quyền metadata:** tạo hoặc cấp quyền cần cho DATABASECHANGELOG và DATABASECHANGELOGLOCK.
6. **Cấp quyền migration:** chỉ quyền cần cho changeset thuộc phạm vi.
7. **Cấp quyền runtime:** DML/EXECUTE tối thiểu, không có DDL nếu không cần.
8. **Cấu hình Spring Boot/CI:** tách credential và kiểm tra database đích.
9. **Kiểm thử allow/deny:** xác minh thao tác đúng thành công và thao tác ngoài phạm vi thất bại.
10. **Phát hành:** một job sở hữu migration, có phê duyệt và log.
11. **Hậu kiểm:** kiểm tra object owner, grants, history và chức năng ứng dụng.
12. **Thu hồi:** hết hạn hoặc thu hồi quyền tạm thời sau khi hoàn tất.

Nếu một changeset mới yêu cầu quyền ngoài mô hình hiện tại, cập nhật thiết kế quyền qua quy trình review bảo mật. Không âm thầm cấp thêm quyền cho tài khoản production chỉ để pipeline xanh.

## 23. Checklist trước khi cấp quyền production

- [ ] Runtime và migration dùng danh tính riêng.
- [ ] Owner schema/object được xác định và nhất quán.
- [ ] Migration chỉ truy cập đúng database/schema thuộc phạm vi.
- [ ] Metadata Liquibase có schema/owner và quyền đọc/ghi phù hợp.
- [ ] Tài khoản migration không có superuser/DBA/db_owner mặc định.
- [ ] Không cấp quyền tạo login, quản trị server hoặc GRANT OPTION nếu không cần.
- [ ] Quyền DDL được suy ra từ changeset đã review.
- [ ] Runtime chỉ có DML/EXECUTE cần thiết.
- [ ] Default privileges áp dụng cho đúng role tạo object.
- [ ] Spring Boot dùng credential migration riêng hoặc CI/CD sở hữu migration rõ ràng.
- [ ] Secret nằm trong secret manager/environment, không ở changelog/Git/log.
- [ ] Network/TLS/identity giới hạn nguồn kết nối.
- [ ] Kiểm thử allow và deny bằng đúng danh tính.
- [ ] Có audit log gắn với job, commit, artifact và người phê duyệt.
- [ ] Có kế hoạch xoay vòng/thu hồi credential và xử lý session đang mở.
- [ ] Có runbook khi thiếu quyền, stale lock hoặc migration lỗi một phần.

## 24. Kết luận

Phân quyền tài khoản migration theo nguyên tắc tối thiểu bắt đầu bằng việc **tách runtime, migrator, owner và DBA**, sau đó cấp quyền theo database/schema/object và theo đúng các thao tác mà changeset cần. Liquibase cần quyền đọc/ghi bảng metadata và thực thi migration, nhưng điều đó không đồng nghĩa nó cần quyền quản trị toàn database hoặc toàn server.

Mô hình bền vững giữ quyền sở hữu object nhất quán, để runtime chỉ có DML/EXECUTE cần thiết, dùng credential migration riêng trong job được kiểm soát và kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối. Quyền GRANT, bootstrap role và thao tác quản trị đặc biệt cần có ranh giới trách nhiệm, phê duyệt và audit rõ ràng.

Cách làm này phục vụ mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**: quản lý changelog, changeset, precondition, checksum và lịch sử triển khai có kiểm chứng; phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD mà vẫn bảo vệ database bằng danh tính rõ ràng, quyền vừa đủ và dấu vết kiểm toán.

