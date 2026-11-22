# Tách tài khoản migration khỏi tài khoản chạy ứng dụng

## 1. Vì sao phải tách hai tài khoản?

Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, Liquibase quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Nhóm còn phải kiểm chứng migration, chuẩn bị rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một quyết định bảo mật nền tảng là dùng **tài khoản có quyền thay đổi cấu trúc database cho Liquibase** và **tài khoản có quyền nghiệp vụ cần thiết cho ứng dụng runtime** như hai danh tính riêng.

Liquibase có thể cần tạo bảng, cột, index, sequence, constraint, view, trigger hoặc procedure. Một changeset cũng có thể backfill dữ liệu và ghi trạng thái vào các bảng metadata như DATABASECHANGELOG và DATABASECHANGELOGLOCK. Vì vậy tài khoản migration thường có quyền rộng hơn tài khoản chạy ứng dụng.

Ứng dụng đang phục vụ request thường chỉ cần đọc/ghi dữ liệu, gọi procedure hoặc truy cập một số schema đã định trước. Nếu ứng dụng bị khai thác, gặp lỗi SQL injection hoặc lộ credential, tài khoản runtime không nên có khả năng tùy ý DROP TABLE, sửa cấu trúc, thay procedure hay xóa lịch sử migration.

Tách tài khoản giúp:

- Giảm thiệt hại khi credential runtime bị lộ.
- Giữ quyền DDL trong một bước triển khai có kiểm soát và có audit.
- Không để mỗi replica ứng dụng giữ quyền thay đổi schema.
- Phân biệt tiến trình nào được phép triển khai database với tiến trình xử lý nghiệp vụ.
- Dễ xoay vòng credential, điều tra sự cố và kiểm tra tuân thủ.

Nguyên tắc cốt lõi là **least privilege**: mỗi danh tính chỉ nhận quyền cần cho nhiệm vụ, trên đúng database/schema/object và trong đúng khoảng thời gian.

## 2. Hai danh tính, hai trách nhiệm

### 2.1. Tài khoản migration

Tài khoản này được Liquibase sử dụng khi thực thi changelog. Tùy migration, nó có thể cần:

- Tạo hoặc thay đổi bảng, cột, index, sequence, constraint, view, function, procedure và trigger.
- Đọc metadata schema để chạy precondition hoặc kiểm tra trạng thái.
- Đọc/ghi/cập nhật các bản ghi trong bảng lịch sử và bảng lock của Liquibase.
- Đọc hoặc cập nhật dữ liệu khi changeset có data migration/backfill.
- Thực hiện thao tác trên schema được quản lý và các đối tượng phụ thuộc được phê duyệt.

Quyền của tài khoản này vẫn phải được giới hạn. Một migration user không mặc nhiên cần quyền quản trị server, tạo login, quản lý database khác, đọc mọi schema hoặc cấp quyền cho principal khác.

### 2.2. Tài khoản runtime

Tài khoản runtime là danh tính datasource mà ứng dụng dùng khi xử lý request. Nó thường cần:

- SELECT trên các bảng/view ứng dụng đọc.
- INSERT, UPDATE, DELETE trên các bảng ứng dụng được phép ghi.
- Quyền dùng sequence/identity theo cơ chế DBMS.
- EXECUTE trên function/procedure nếu ứng dụng gọi chúng.
- USAGE hoặc quyền tương đương để truy cập schema và object cần thiết.

Tài khoản runtime thường không cần:

- CREATE, ALTER, DROP trên schema nghiệp vụ.
- Quyền tạo database, schema, user, role hoặc extension.
- Quyền sửa/xóa DATABASECHANGELOG hay DATABASECHANGELOGLOCK.
- Quyền sở hữu database hoặc quyền quản trị toàn server.
- Quyền truy cập schema migration nội bộ nếu ứng dụng không cần đọc nó.

### 2.3. So sánh theo nhiệm vụ

| Nhiệm vụ | Tài khoản migration | Tài khoản runtime |
|---|---|---|
| Tạo/sửa bảng, cột, index | Có, trong phạm vi được giao | Không |
| Thêm constraint/default/sequence | Có | Không |
| Tạo hoặc thay view/routine | Có khi changelog yêu cầu | Chỉ được đọc/gọi nếu cần |
| Backfill dữ liệu | Có quyền DML cần thiết cho changeset | DML theo nghiệp vụ |
| Ghi DATABASECHANGELOG và lock | Có | Không |
| Đọc/ghi dữ liệu request | Chỉ khi migration cần | Có theo nghiệp vụ |
| Tạo user/role hoặc cấp quyền | Thường không | Không |
| Quản trị toàn database/server | Không mặc định | Không |

Không nên dùng một user DBA/root cho cả Liquibase lẫn ứng dụng. Quyền migration có thể rộng hơn runtime nhưng vẫn chỉ nên bao phủ các schema và loại object mà module cần quản lý.

## 3. Vòng đời triển khai với tài khoản riêng

Một quy trình có thể chia thành ba giai đoạn:

1. **Bootstrap:** DBA hoặc automation hạ tầng tạo database, schema, role và quyền ban đầu. Giai đoạn này có thể cần quyền quản trị cao hơn, nhưng credential đó không được giữ trong ứng dụng.
2. **Migration:** CI/CD job hoặc tiến trình Liquibase dùng credential migration để validate, xem SQL và thực thi changeset. Liquibase ghi lịch sử vào metadata schema.
3. **Runtime:** ứng dụng khởi động bằng credential runtime, chỉ thao tác trên các object và dữ liệu được cấp quyền.

~~~mermaid
flowchart TD
    A[DBA / Infrastructure bootstrap] --> B[Schema và roles]
    B --> C[CI/CD migration job]
    C --> D[Liquibase validate và update]
    D --> E[DATABASECHANGELOG và schema mới]
    E --> F[Deploy ứng dụng]
    F --> G[Runtime datasource]
    G --> H[Chỉ quyền DML / EXECUTE cần thiết]
~~~

CI/CD job có thể hoàn tất migration trước khi rollout phiên bản ứng dụng mới. Nếu migration thất bại, pipeline dừng trước bước đưa code mới vào phục vụ. Cách này cũng giúp credential DDL chỉ được cấp cho job migration trong thời gian triển khai.

### 3.1. Chọn nơi chạy Liquibase

| Cách chạy | Cách hoạt động | Điểm cần cân nhắc |
|---|---|---|
| Spring Boot tự chạy Liquibase lúc startup | Auto-configuration chạy migration khi ứng dụng khởi động | Mọi instance có thể cần truy cập credential migration; cần quản lý thứ tự startup và secret |
| Job riêng trong CI/CD hoặc nền tảng triển khai | Một bước độc lập chạy Liquibase trước khi deploy ứng dụng | Tách quyền tốt hơn; phải quản lý version/artifact/config giữa job và ứng dụng |

Với production, job migration riêng thường dễ giới hạn quyền và audit hơn. Nếu tổ chức chọn startup migration, vẫn phải cấu hình kết nối Liquibase riêng và tránh để runtime datasource mang quyền DDL.

DATABASECHANGELOGLOCK giúp tuần tự hóa các Liquibase runner cùng sử dụng một bộ bảng metadata. Nó không thay thế quyền database, không ngăn ứng dụng runtime có DDL privilege và không làm một nhóm migration trở thành giao dịch phân tán.

## 4. Cấu hình Spring Boot dùng hai bộ credential

Spring Boot cho phép cấu hình datasource ứng dụng và thông tin kết nối Liquibase riêng. Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: ${MIGRATION_DB_URL}
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
    default-schema: app
    liquibase-schema: liquibase_meta
~~~

Trong cấu hình này, spring.datasource.* là kết nối mà ứng dụng dùng cho hoạt động runtime; spring.liquibase.url/user/password là kết nối riêng Liquibase sử dụng. default-schema chỉ schema mặc định cho object nghiệp vụ khi changeset không chỉ rõ schema; liquibase-schema chỉ schema chứa bảng metadata của Liquibase.

Tên biến môi trường chỉ là ví dụ; giá trị thật phải được inject từ secret manager hoặc nền tảng triển khai. Không ghi mật khẩu trực tiếp vào YAML được commit, Docker image, log hoặc tham số dễ bị lưu trong process list.

### 4.1. Khi nào dùng datasource được đánh dấu Liquibase?

Nếu ứng dụng cần nhiều datasource hoặc cấu hình datasource bằng Java, Spring Boot có thể chọn bean được đánh dấu @LiquibaseDataSource làm datasource cho Liquibase trong các cấu hình auto-configuration tương ứng. Cách này hữu ích khi:

- Ứng dụng có datasource runtime và datasource migration riêng.
- Cần custom pool/driver/credential cho kết nối Liquibase.
- Không muốn dựa vào một URL/user/password khai báo bằng spring.liquibase.*.

Phải xác minh điều kiện auto-configuration của đúng phiên bản Spring Boot. Khi cấu hình datasource riêng không đúng, Liquibase có thể quay về datasource mặc định hoặc ứng dụng có thể khởi động với target database ngoài dự kiến. Hãy kiểm tra bean được chọn, URL đã làm sạch thông tin nhạy cảm, database/catalog và schema trước khi cho phép update.

### 4.2. Chạy ứng dụng sau khi migration đã hoàn tất

Nếu CI/CD job đã chạy Liquibase riêng, ứng dụng runtime có thể tắt auto migration:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Điều này tránh việc mỗi instance ứng dụng tự yêu cầu credential migration. Chỉ tắt trong các tiến trình thực sự không chịu trách nhiệm migration; cấu hình job riêng vẫn phải bật Liquibase và dùng đúng artifact/changelog. Với local hoặc môi trường developer, có thể tiếp tục dùng startup migration nếu chính sách cho phép.

### 4.3. Không dùng cùng username cho hai kết nối

Việc chỉ đặt hai connection pool khác nhau nhưng cùng username không tạo ra ranh giới bảo mật. Cần hai principal database thật sự khác nhau, với quyền khác nhau được xác minh ở DBMS. Đặt tên biến APP_DB_USER và MIGRATION_DB_USER nhưng truyền cùng một giá trị cũng không đạt mục tiêu tách quyền.

## 5. Ví dụ phân quyền trên PostgreSQL

Ví dụ sau minh họa một database orders với schema nghiệp vụ app và schema metadata liquibase_meta. Lệnh bootstrap được chạy bởi DBA hoặc principal có quyền tạo role/schema; mật khẩu được cấp qua quy trình quản lý credential riêng.

~~~sql
CREATE ROLE orders_migrator LOGIN;
CREATE ROLE orders_runtime LOGIN;

CREATE SCHEMA app AUTHORIZATION orders_migrator;
CREATE SCHEMA liquibase_meta AUTHORIZATION orders_migrator;

GRANT CONNECT ON DATABASE orders TO orders_runtime;
GRANT USAGE ON SCHEMA app TO orders_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO orders_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA app
TO orders_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE orders_migrator
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO orders_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE orders_migrator
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES TO orders_runtime;
~~~

Ở ví dụ này:

- orders_migrator sở hữu hai schema nên có thể tạo object trong phạm vi đó và quản lý metadata Liquibase.
- orders_runtime có quyền truy cập schema app và DML trên các bảng/sequence hiện có.
- Default privileges cấp quyền DML cho các bảng/sequence mới do orders_migrator tạo trong schema app.
- Runtime không được cấp quyền trên schema liquibase_meta và không có quyền DDL trong app.

Đây là mô hình đơn giản để minh họa; database thật còn cần xem quyền CONNECT, quyền PUBLIC, owner của từng object, function/procedure, view, sequence và các schema khác. ALTER DEFAULT PRIVILEGES chỉ áp dụng cho object do role được nêu tạo ra trong schema tương ứng; nếu migration chạy dưới owner khác, phải cấu hình default privileges cho đúng owner. Khi cần mô hình chặt hơn, có thể dùng role owner NOLOGIN và một principal migration được phép đảm nhận role đó theo cơ chế SET ROLE/membership đã cấu hình, thay vì để login migration trực tiếp sở hữu object.

### 5.1. Kiểm tra quyền theo object

Với PostgreSQL, quyền trên schema và quyền trên table là hai lớp khác nhau. USAGE ON SCHEMA cho phép phân giải object trong schema; nó không tự cấp SELECT hoặc DML trên bảng. Ngược lại, grant trên bảng không tự bảo đảm user có thể truy cập schema nếu thiếu USAGE.

Sequence cũng cần được xem riêng. Một ứng dụng insert vào bảng có cột dùng sequence có thể cần quyền USAGE trên sequence, tùy cách cấp giá trị. Với function/procedure, kiểm tra quyền EXECUTE. Với view dùng security_invoker hoặc các tùy chọn bảo mật liên quan, đánh giá quyền theo semantics của phiên bản PostgreSQL.

## 6. Các DBMS khác cũng cần phân tách role

Khái niệm role/user khác nhau giữa các hệ quản trị; không sao chép nguyên lệnh PostgreSQL sang engine khác. Hướng thiết kế:

| DBMS | Tài khoản migration | Tài khoản runtime |
|---|---|---|
| PostgreSQL | Owner hoặc role được phép DDL trong schema ứng dụng và metadata Liquibase | USAGE schema cùng DML/sequence/function đúng nhu cầu |
| MySQL | Quyền DDL cần thiết trên database/schema được quản lý và DML cho changeset | SELECT, INSERT, UPDATE, DELETE và quyền routine cần thiết |
| SQL Server | User/role có quyền tạo/sửa object trong schema được quản lý và cập nhật metadata | Quyền schema/object như SELECT, DML, EXECUTE theo nghiệp vụ |
| Oracle | Schema owner hoặc principal được cấp quyền DDL phù hợp; metadata Liquibase được bảo vệ | Quyền object hoặc role ứng dụng được cấp cụ thể |

### 6.1. MySQL

Trong MySQL, schema thường tương ứng database. Tài khoản runtime có thể được cấp DML trên database nghiệp vụ:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders_app.*
TO 'orders_runtime'@'app-host';
~~~

Tài khoản migration cần thêm các quyền DDL phù hợp như CREATE, ALTER, DROP, INDEX, REFERENCES, cùng quyền cần thiết để tạo view/routine/trigger nếu changelog có các object đó. Bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK cũng cần được tạo/cập nhật. Chỉ cấp quyền cho database mục tiêu, không cấp trên *.* nếu không có yêu cầu vận hành cụ thể.

### 6.2. SQL Server

Có thể tách login/user và database role. Tài khoản runtime được cấp quyền trên schema hoặc object; tài khoản migration được cấp quyền DDL có phạm vi trong schema cần quản lý. Tránh đưa runtime user vào db_owner hoặc các server role quản trị. Kiểm tra ownership chaining, quyền trên sequence, schema và stored procedure; GRANT EXECUTE có thể phù hợp hơn cấp quyền trực tiếp trên mọi bảng nếu ứng dụng chỉ truy cập dữ liệu qua procedure.

### 6.3. Oracle

Oracle gắn schema với user sở hữu object. Nhiều hệ thống dùng schema owner riêng cho object ứng dụng và user runtime được cấp quyền object qua role/grant. Migration cần chạy bằng schema owner hoặc user được cấp các quyền DDL cụ thể. Không cấp DBA cho user runtime; các quyền hệ thống như CREATE ANY TABLE có phạm vi rất rộng và cần tránh nếu không thật sự cần.

Trong cả ba DBMS, cần xác minh quyền của bảng metadata Liquibase, quyền lock, quyền DDL của từng change type và hành vi của precondition. Một migration có thể chạy được trên PostgreSQL nhưng thiếu quyền CREATE ROUTINE ở MySQL hoặc quyền tương đương trên SQL Server/Oracle.

## 7. Quyền cần thiết cho metadata và changeset

Liquibase duy trì ít nhất hai bảng quản lý:

- DATABASECHANGELOG: ghi nhận changeset đã xử lý, checksum, thời điểm, execution type và thông tin liên quan.
- DATABASECHANGELOGLOCK: điều phối runner để tránh nhiều Liquibase process cùng cập nhật một lịch sử tại một thời điểm.

Tài khoản migration phải có quyền đọc và cập nhật hai bảng này. Nếu chúng chưa tồn tại, Liquibase cần quyền tạo chúng trong schema metadata hoặc DBA phải bootstrap trước. Tài khoản runtime thông thường không cần đọc hay sửa hai bảng này.

Ngoài metadata, hãy xem changeset thực tế:

- createTable, addColumn, createIndex, addForeignKeyConstraint cần quyền DDL tương ứng.
- sql/sqlFile có thể cần quyền rộng hơn change type chuẩn, tùy câu SQL.
- Backfill cần quyền đọc và cập nhật dữ liệu trên bảng đích.
- Tạo function/procedure/trigger cần quyền tương ứng và có thể cần quyền tham chiếu object khác.
- Precondition có thể đọc catalog hoặc dữ liệu; cần quyền đọc tối thiểu để kiểm tra.

Không suy ra một danh sách grant duy nhất cho mọi module. Hãy lấy changelog và loại object thực tế làm cơ sở lập ma trận quyền.

## 8. Tổ chức CI/CD để credential migration không đi vào runtime

Một pipeline production có thể thực hiện:

1. Build artifact chứa đúng master changelog và file SQL được tham chiếu.
2. Chạy validate và các kiểm tra cấu trúc changelog.
3. Kết nối database kiểm thử bằng principal migration, chạy status và update-sql.
4. Thử update thật trên database đại diện; kiểm tra schema, dữ liệu, quyền và rollback/forward-fix.
5. Phê duyệt release và target database.
6. Cấp credential migration từ secret store cho migration job trong thời gian cần thiết.
7. Chạy update, ghi log/audit không chứa secret.
8. Thu hồi hoặc xoay vòng credential theo chính sách; triển khai ứng dụng với runtime credential.
9. Xác minh ứng dụng hoạt động bằng runtime account không có quyền DDL.

Ví dụ lệnh kiểm tra với file cấu hình Liquibase riêng:

~~~bash
liquibase --defaults-file=config/liquibase-migration.properties validate
liquibase --defaults-file=config/liquibase-migration.properties status --verbose
liquibase --defaults-file=config/liquibase-migration.properties update-sql
~~~

File properties trong ví dụ phải được cung cấp an toàn cho job, có quyền đọc hạn chế và không được commit secret. Có thể inject cấu hình bằng biến môi trường hoặc secret manager theo cách nền tảng CI/CD hỗ trợ. Tránh đặt password trực tiếp trong command line, vì có thể bị lưu trong shell history, log hoặc process metadata.

### 8.1. Đồng bộ artifact và cấu hình

Job migration và ứng dụng phải dùng cùng release artifact hoặc cùng commit đã được xác định. Nếu job chạy changelog từ commit A nhưng ứng dụng đóng gói commit B, lịch sử database có thể không tương ứng với source đang chạy. Ghi nhận version/commit, Liquibase version, DBMS version, contexts/labels và target database trong log triển khai, nhưng không ghi credential.

### 8.2. Không để replica tự tranh quyền migration

Nếu mọi replica Spring Boot cùng khởi động Liquibase, lock giúp tuần tự hóa phần cập nhật lịch sử, nhưng mỗi replica vẫn phải có khả năng lấy credential migration và quyền DDL. Điều đó mở rộng bề mặt rủi ro. Với production, một migration job có danh tính riêng trước rollout thường dễ kiểm soát hơn. Nếu startup migration là yêu cầu kiến trúc, hãy giới hạn số runner, bảo đảm mọi replica dùng cùng artifact và cấu hình, và tách credential runtime khỏi credential Liquibase.

## 9. Quản lý secret và vòng đời credential

Credential migration có giá trị cao hơn credential runtime vì có thể thay đổi cấu trúc hoặc dữ liệu. Cần:

- Lưu trong secret manager/vault hoặc cơ chế secret của nền tảng.
- Chỉ cấp cho pipeline/job hoặc workload có nhiệm vụ migration.
- Hạn chế người có quyền đọc secret và ghi nhận truy cập.
- Không commit vào Git, Docker image, file cấu hình đóng gói hoặc tài liệu.
- Không in password, JDBC URL có thông tin xác thực, token hoặc secret trong log.
- Xoay vòng định kỳ và sau sự cố/lộ credential.
- Thu hồi quyền hoặc credential migration cũ khi không còn cần.
- Dùng TLS và xác minh certificate khi kết nối database qua mạng.

### 9.1. Xoay vòng không làm gián đoạn ứng dụng

Một quy trình xoay vòng an toàn thường gồm:

1. Tạo credential mới cho đúng principal hoặc tạo principal migration thay thế.
2. Cấp secret mới cho job migration và kiểm tra kết nối trên môi trường test.
3. Chuyển pipeline sang credential mới.
4. Xác minh migration job hoạt động và audit ghi đúng danh tính.
5. Thu hồi credential cũ sau khi không còn job nào sử dụng.

Runtime credential được xoay vòng theo vòng đời riêng. Không cần cấp quyền DDL cho runtime chỉ để đơn giản hóa việc đổi password.

### 9.2. Phân biệt quyền truy cập secret với quyền database

Một service account CI có thể đọc secret nhưng điều đó không có nghĩa nó nên được cấp quyền truy cập database trực tiếp ngoài thời gian chạy migration. Ngược lại, user database có quyền DDL không nên được cấp cho mọi developer hoặc mọi pod ứng dụng. Kiểm soát hai lớp: ai được lấy credential và credential đó có thể làm gì trong database.

## 10. Kiểm chứng việc tách quyền

Không chỉ nhìn tên hai user trong file cấu hình. Cần chứng minh bằng hành vi và metadata quyền:

### 10.1. Kiểm tra tích cực với migration account

Trong database test dùng để kiểm chứng:

- Kết nối bằng migration principal thành công.
- validate, status và update-sql đọc được changelog/metadata cần thiết.
- update có thể tạo object và cập nhật DATABASECHANGELOG.
- Một changeset có backfill thực hiện được đúng DML được cấp.
- Liquibase lock được lấy và giải phóng đúng cách.

### 10.2. Kiểm tra phủ định với runtime account

Kết nối bằng runtime principal và xác minh:

- Các truy vấn/DML hợp lệ của ứng dụng hoạt động.
- Không thể tạo bảng hoặc index trong schema nghiệp vụ.
- Không thể ALTER hoặc DROP object nghiệp vụ.
- Không thể sửa/xóa DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Không thể tạo role/user hoặc truy cập schema ngoài phạm vi.
- Không thể gọi routine nhạy cảm nếu không được cấp EXECUTE.

Các thử nghiệm quyền phủ định nên chạy trên database/schema dùng riêng cho test; một số DDL có thể commit ngầm hoặc không rollback như DML. Có thể kiểm tra thêm qua catalog/permission view của DBMS và review grant script.

### 10.3. Kiểm tra sau khi deploy

Sau migration, xác nhận:

1. Liquibase đã ghi nhận changeset trong đúng schema metadata.
2. Schema nghiệp vụ có object và constraint mong đợi.
3. Runtime user có quyền đọc/ghi/gọi đúng phạm vi.
4. Runtime user không có quyền DDL và không truy cập schema metadata.
5. Ứng dụng khởi động, health check và các luồng nghiệp vụ chính hoạt động.
6. Log/audit xác định được principal migration và release đã thực thi.

DATABASECHANGELOG chứng minh Liquibase ghi nhận trạng thái changeset; nó không chứng minh runtime user đã bị giới hạn đúng. Cần kiểm tra quyền độc lập.

## 11. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Dùng chung một username cho app và Liquibase | Mọi tiến trình có cùng quyền DDL | Tạo hai principal database thật sự khác nhau |
| Cấp db_owner, DBA hoặc superuser cho runtime | Lộ credential có thể phá hủy database/server | Chỉ cấp DML/EXECUTE trên schema/object cần dùng |
| Tách datasource nhưng không tách DB role | Hai pool vẫn có cùng quyền | Review grant trong database, không chỉ review YAML |
| Quên quyền sequence hoặc routine | Ứng dụng lỗi khi insert/gọi procedure | Bổ sung quyền object đúng nhu cầu và test integration |
| Quên default privileges | Bảng mới được tạo nhưng runtime không truy cập được | Cấu hình default grants theo object owner/DBMS |
| Runtime đọc được metadata Liquibase | Lộ lịch sử nội bộ hoặc cho phép sửa metadata nếu grant quá rộng | Giới hạn schema metadata cho migration principal |
| Migration job và app dùng artifact khác nhau | Source/changelog không khớp trạng thái database | Pin cùng commit/artifact và version |
| Secret migration nằm trong image hoặc Git | Credential khó thu hồi và dễ bị sao chép | Inject từ secret manager lúc chạy |
| Dựa vào Liquibase lock như cơ chế bảo mật | Runtime vẫn có thể DDL nếu được cấp quyền | Dùng database grants và network identity riêng |
| Migration account là DBA vì “cho chắc” | Blast radius quá lớn | Liệt kê change type và cấp quyền theo schema |
| Không kiểm tra quyền sau deploy | Grant sai có thể tồn tại lâu dài | Chạy permission tests và audit định kỳ |

## 12. Tình huống thực tế: phát hành một cột mới

Một dịch vụ đơn hàng cần thêm cột delivery_note vào bảng purchase_order. Ứng dụng mới đọc/ghi cột này; migration cần thêm cột và có thể backfill dữ liệu từ một nguồn đã thống nhất.

Quy trình:

1. DBA bootstrap app_migrator, app_runtime, schema nghiệp vụ và schema metadata.
2. app_migrator có quyền DDL trong schema được quản lý và quyền DML cần thiết cho backfill.
3. app_runtime chỉ có DML trên bảng nghiệp vụ cùng quyền sequence/routine cần thiết.
4. CI chạy validate, status, update-sql bằng credential migration trên database test.
5. CI thực hiện migration và kiểm tra DATABASECHANGELOG, cấu trúc bảng, dữ liệu backfill.
6. CI xác minh runtime account không thể ALTER TABLE hoặc DROP TABLE trong schema.
7. Production migration job nhận credential migration ngắn hạn và chạy release đã phê duyệt.
8. Ứng dụng được triển khai bằng runtime credential; không cần quyền DDL để đọc/ghi delivery_note.

Nếu migration thất bại, dừng rollout ứng dụng và điều tra trạng thái database. Nếu thay đổi đã được áp dụng một phần theo đặc tính transaction của DBMS, dùng lịch sử Liquibase, metadata schema và trạng thái object thực tế để quyết định retry hoặc forward-fix. Không sửa tay DATABASECHANGELOG để che lỗi.

## 13. Checklist trước khi đưa vào production

- [ ] Có hai principal database khác nhau cho migration và runtime.
- [ ] Runtime chỉ có DML/EXECUTE/sequence/schema access thực sự cần.
- [ ] Runtime không có CREATE/ALTER/DROP hoặc quyền quản trị ngoài yêu cầu.
- [ ] Migration có DDL/DML cần thiết nhưng chỉ trong database/schema được giao.
- [ ] Migration principal có quyền đọc/ghi bảng Liquibase metadata và lock.
- [ ] Schema metadata được bảo vệ khỏi runtime account.
- [ ] Đã xem quyền trên table, sequence, view, function, procedure, trigger và object mới.
- [ ] Đã cấu hình default privileges cho object do đúng owner tạo ra.
- [ ] Spring Boot dùng spring.datasource.* cho runtime và kết nối Liquibase riêng khi startup migration.
- [ ] Nếu dùng datasource Liquibase riêng, đã xác minh đúng bean và đúng target database.
- [ ] Nếu migration chạy trong CI/CD, credential chỉ được cấp cho job và ứng dụng không giữ secret DDL.
- [ ] Secret không nằm trong Git, image, command line hoặc log; có quy trình xoay vòng/thu hồi.
- [ ] validate, status, update-sql và update thử đã chạy bằng migration account.
- [ ] Runtime account đã qua kiểm tra quyền hợp lệ và kiểm tra quyền DDL bị từ chối.
- [ ] Có audit principal, release, target database và thời điểm migration.
- [ ] Có phương án rollback/forward-fix và kiểm tra trạng thái sau migration.

**Kết luận:** tách tài khoản migration khỏi tài khoản chạy ứng dụng tạo ra ranh giới quyền rõ ràng cho toàn bộ vòng đời database. Liquibase dùng principal riêng để quản lý DDL, dữ liệu migration và lịch sử; ứng dụng dùng principal runtime chỉ có quyền nghiệp vụ cần thiết. Spring Boot hỗ trợ cấu hình kết nối Liquibase riêng hoặc datasource được chọn rõ ràng; CI/CD có thể cấp credential migration trong một job độc lập rồi triển khai ứng dụng bằng credential runtime. Khi quyền được giới hạn theo schema/object, secret được quản lý riêng và cả quyền được phép lẫn quyền bị từ chối đều được kiểm chứng, DATABASE_SCHEMA_MIGRATION_LIQUIBASE có thể triển khai thay đổi database an toàn hơn mà không trao quyền DDL cho mọi tiến trình phục vụ request.
