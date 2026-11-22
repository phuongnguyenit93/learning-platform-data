# Tách kết nối JDBC cho công cụ migration khi cần

Spring Data Relational R2DBC cho phép ứng dụng truy cập database theo mô hình reactive thông qua R2DBC driver và ConnectionFactory. Tuy nhiên, nhiều công cụ quản lý schema như Flyway và Liquibase thường tích hợp với database qua JDBC. Khi dùng các công cụ này cùng ứng dụng R2DBC, một kiến trúc phổ biến là duy trì hai đường kết nối tới cùng database: R2DBC cho truy vấn nghiệp vụ lúc runtime, JDBC dành riêng cho migration.

Hai đường kết nối có mục đích và vòng đời khác nhau. JDBC migration thường chạy khi khởi động ứng dụng hoặc trong một bước triển khai riêng để tạo/cập nhật schema. Sau đó, ứng dụng sử dụng R2DBC để đọc và ghi dữ liệu không blocking. Việc có JDBC driver trong classpath không có nghĩa repository R2DBC chuyển sang JDBC, cũng không có nghĩa hai loại connection có thể dùng chung một transaction.

Bài học này trình bày khi nào cần thêm JDBC cho migration, cách cấu hình Flyway/Liquibase riêng với R2DBC, cách quản lý driver và credentials, thứ tự triển khai schema, giới hạn transaction, kiểm thử và xử lý các lỗi cấu hình thường gặp.

## 1. Vì sao ứng dụng R2DBC đôi khi vẫn cần JDBC?

R2DBC và JDBC là hai SPI khác nhau:

- JDBC cung cấp API truy cập database theo kiểu blocking, thường sử dụng DataSource và Connection.
- R2DBC cung cấp API reactive/non-blocking, sử dụng ConnectionFactory và Publisher.
- Spring Data R2DBC dùng R2DBC cho repository, template và truy vấn runtime.
- Một công cụ migration tích hợp JDBC cần JDBC driver và DataSource để thực thi DDL/DML quản lý schema.

Công cụ migration không nhất thiết phải dùng cùng công nghệ kết nối với phần nghiệp vụ. Nó chỉ cần kết nối tới đúng database và thực hiện các thay đổi schema trước khi ứng dụng phụ thuộc vào schema đó.

Một ví dụ phổ biến:

- Ứng dụng dùng Spring Data R2DBC với PostgreSQL.
- Repository runtime sử dụng R2DBC PostgreSQL driver.
- Flyway dùng PostgreSQL JDBC driver để chạy các file migration.
- Cả hai kết nối cùng server, database và schema đích, nhưng mỗi bên có URL, driver, pool và transaction manager riêng nếu cần.

### Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Spring Data R2DBC]
    B --> C[R2DBC ConnectionFactory]
    C --> D[(Database schema)]
    A --> E[Flyway or Liquibase]
    E --> F[JDBC DataSource]
    F --> D
    G[Versioned migration files] --> E
~~~

Migration và runtime cùng tác động tới một schema. JDBC chỉ được dùng ở đường migration; các thao tác repository vẫn chạy qua R2DBC.

## 2. Khi nào nên tách JDBC connection cho migration?

Tách JDBC connection khi công cụ quản lý schema yêu cầu JDBC hoặc khi cách tích hợp JDBC của công cụ là lựa chọn ổn định, được hỗ trợ cho database mục tiêu.

Các trường hợp thường gặp:

- Dự án dùng Spring Data R2DBC nhưng quản lý schema bằng Flyway.
- Dự án dùng R2DBC runtime nhưng Liquibase được cấu hình với JDBC DataSource.
- Migration cần dùng tính năng hoặc extension của công cụ chỉ có qua JDBC.
- Pipeline triển khai cần chạy migration như một bước riêng trước khi rollout ứng dụng.
- Ứng dụng không cần JDBC cho truy vấn nghiệp vụ nhưng vẫn cần JDBC driver cho công cụ migration.

Không cần thêm JDBC chỉ vì ứng dụng dùng R2DBC. Nếu công cụ migration đã hỗ trợ trực tiếp giao thức hoặc API khác phù hợp, có thể dùng tích hợp đó. Hãy xác nhận yêu cầu của phiên bản công cụ cụ thể trước khi thêm dependency.

### Lợi ích của việc tách kết nối

- Giữ repository runtime ở mô hình reactive.
- Dùng công cụ migration đã được kiểm chứng với JDBC.
- Tách credentials: ứng dụng có thể chỉ có quyền DML, migration có quyền DDL.
- Chạy migration trong pipeline hoặc job độc lập.
- Quản lý thời điểm cập nhật schema trước khi phiên bản ứng dụng mới bắt đầu chạy.

Nếu dự án không có công cụ hoặc thư viện nào cần JDBC, việc thêm driver và pool JDBC chỉ làm tăng dependency và cấu hình. Không thêm JDBC starter một cách tự động khi chỉ cần một JDBC driver cho migration; kiểm tra chính xác những module mà công cụ migration yêu cầu.

## 3. Hai loại URL và hai loại connection

Một lỗi cấu hình phổ biến là dùng nhầm JDBC URL cho R2DBC hoặc ngược lại.

Ví dụ với PostgreSQL:

| Mục đích | URL scheme | API Spring |
| --- | --- | --- |
| Truy cập runtime bằng R2DBC | r2dbc:postgresql://... | ConnectionFactory, R2dbcEntityTemplate, repository |
| Migration bằng JDBC | jdbc:postgresql://... | DataSource, Flyway, Liquibase |

Với MySQL, MariaDB, SQL Server và các hệ quản trị khác, tên scheme và driver tương ứng cũng khác nhau. Không tự thay tiền tố URL mà không kiểm tra driver hỗ trợ.

Hai kết nối phải trỏ tới cùng mục tiêu schema:

- Cùng database server hoặc cluster.
- Cùng database/catalog.
- Cùng schema nếu database phân biệt schema.
- Cùng các tham số SSL, timezone, search path hoặc cấu hình session cần thiết.
- Tài khoản có quyền phù hợp với vai trò của từng kết nối.

Không nên chỉ so sánh hostname. Một URL JDBC có thể trỏ tới database tên khác hoặc schema khác với URL R2DBC, khiến migration thành công nhưng ứng dụng vẫn báo thiếu bảng.

## 4. Dependency cho R2DBC runtime và JDBC migration

Một ứng dụng có thể cần các nhóm dependency sau:

| Nhóm | Vai trò |
| --- | --- |
| Spring Data R2DBC | Repository và mapping reactive. |
| R2DBC driver | Kết nối runtime tới database. |
| R2DBC pool (nếu dùng) | Quản lý pool cho ConnectionFactory. |
| Công cụ migration | Flyway hoặc Liquibase. |
| JDBC driver | Kết nối migration nếu công cụ dùng JDBC. |
| JDBC pool (nếu cần) | Quản lý DataSource cho migration; migration một lần khi startup thường không cần pool lớn. |

Ví dụ minh họa với PostgreSQL và Flyway:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Với một số phiên bản Flyway mới, hỗ trợ từng database được tách thành module riêng. Khi dùng phiên bản đó, thêm module database tương ứng, ví dụ PostgreSQL module, theo hướng dẫn dependency của phiên bản Flyway đang được quản lý bởi Spring Boot hoặc dependency management của dự án.

Nếu dùng Liquibase, nhóm dependency thường gồm Liquibase core và JDBC driver của database. Không thêm Flyway và Liquibase cùng chạy trên một schema nếu dự án không có chủ đích phối hợp hai hệ migration; thông thường nên chọn một công cụ làm nguồn lịch sử schema duy nhất.

### Không nhầm starter JDBC với JDBC driver

JDBC driver là thư viện giao tiếp với database qua JDBC. Spring Boot JDBC starter thường kéo thêm các thành phần Spring JDBC và connection pool. Nếu chỉ cần công cụ migration dùng JDBC, có thể chỉ cần driver và các dependency migration được hỗ trợ, tùy cách auto-configuration của phiên bản Spring Boot.

Chỉ thêm starter JDBC khi ứng dụng thực sự cần DataSource/JdbcTemplate hoặc cấu hình migration của dự án yêu cầu nó. Nếu thêm cả JDBC và R2DBC, hãy xác định rõ bean nào dành cho migration và bean nào dành cho runtime.

## 5. Cấu hình R2DBC và Flyway riêng biệt

Spring Boot có namespace cấu hình riêng cho R2DBC và Flyway. Ví dụ cấu hình YAML cho PostgreSQL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders
    username: app_runtime
    password: runtime-secret

  flyway:
    url: jdbc:postgresql://db-host:5432/orders
    user: schema_migrator
    password: migration-secret
    locations: classpath:db/migration
    schemas: app
    default-schema: app
    validate-on-migrate: true
~~~

Ví dụ này minh họa hai credentials khác nhau. Thông tin thật nên lấy từ secret manager hoặc biến môi trường của deployment, không commit password vào source control.

Các thuộc tính Flyway phổ biến gồm:

- url: JDBC URL dùng cho Flyway.
- user/password: credentials của migration.
- locations: nơi chứa migration script.
- schemas/default-schema: schema được quản lý.
- validate-on-migrate: kiểm tra lịch sử/checksum trước khi áp dụng migration.
- baseline-on-migrate: chỉ bật khi có chủ đích baseline một schema đã tồn tại; không dùng như cách che lỗi migration.

Tên property và khả năng auto-configure DataSource riêng phụ thuộc Spring Boot version. Đọc reference documentation của phiên bản dự án để xác nhận cách Boot tạo DataSource cho Flyway khi ứng dụng chính dùng R2DBC.

### Biến môi trường

Có thể ánh xạ cấu hình thành biến môi trường khi triển khai, ví dụ:

~~~text
SPRING_R2DBC_URL
SPRING_R2DBC_USERNAME
SPRING_R2DBC_PASSWORD
SPRING_FLYWAY_URL
SPRING_FLYWAY_USER
SPRING_FLYWAY_PASSWORD
~~~

Tên biến môi trường theo quy tắc relaxed binding của Spring Boot. Hãy giữ credentials ở secret store và cấp quyền riêng cho runtime/migration.

### Cùng server nhưng khác user

Runtime user thường chỉ cần các quyền SELECT, INSERT, UPDATE, DELETE cần cho ứng dụng. Migration user có thể cần CREATE, ALTER, DROP hoặc quyền quản lý schema. Tách tài khoản giúp giảm ảnh hưởng nếu credentials runtime bị lộ.

Không cấp quyền DDL cho runtime chỉ để migration tự chạy dưới cùng tài khoản. Nếu migration được chạy trong pipeline riêng, tài khoản quyền cao chỉ cần có mặt ở bước triển khai.

## 6. Cấu hình JDBC DataSource riêng khi cần

Có dự án có cả DataSource JDBC và ConnectionFactory R2DBC, ví dụ vì còn một thư viện JDBC khác hoặc cần migration bean được cấu hình thủ công.

Khi có nhiều DataSource, cần xác định rõ DataSource nào dành cho Flyway hoặc Liquibase. Spring Boot cung cấp các qualifier/annotation chuyên biệt cho datasource của công cụ tương ứng, chẳng hạn Flyway-specific hoặc Liquibase-specific datasource annotation ở những phiên bản hỗ trợ.

Ví dụ cấu hình Flyway tường minh theo ý tưởng:

~~~java
@Configuration
public class MigrationConfiguration {

    @Bean
    @FlywayDataSource
    DataSource migrationDataSource(
            @Value("${migration.jdbc.url}") String url,
            @Value("${migration.jdbc.username}") String username,
            @Value("${migration.jdbc.password}") String password) {

        return DataSourceBuilder.create()
            .url(url)
            .username(username)
            .password(password)
            .build();
    }
}
~~~

Ví dụ này minh họa DataSource được đánh dấu dành cho Flyway; cách cấu hình driver, pool, bean name và việc Boot có tự tạo Flyway bean cần đối chiếu với phiên bản đang dùng. Nếu tự cấu hình Flyway bean, tránh tạo hai cấu hình cùng chạy migration.

Với Liquibase, dùng datasource qualifier tương ứng nếu Spring Boot version hỗ trợ, hoặc khai báo Liquibase bean với DataSource rõ ràng. Đừng để migration vô tình dùng primary DataSource JDBC của một tích hợp khác.

### Khi có cả primary DataSource và R2DBC ConnectionFactory

Spring có thể auto-configure hai loại bean nếu classpath và property phù hợp. Một số auto-configuration hoặc thư viện có thể ưu tiên JDBC DataSource, vì vậy cần kiểm tra điều kiện khởi tạo bean và transaction manager.

Các nguyên tắc:

- Không đặt tên bean mơ hồ nếu có nhiều DataSource.
- Chỉ định rõ datasource của Flyway/Liquibase.
- Dùng R2dbcTransactionManager cho các thao tác R2DBC runtime.
- Nếu có JDBC transaction riêng, dùng transaction manager JDBC riêng cho phần JDBC đó.
- Không giả định một transaction manager điều khiển đồng thời JDBC Connection và R2DBC Connection.

## 7. Cấu hình Liquibase với JDBC

Liquibase cũng có thể chạy migration qua JDBC DataSource trong ứng dụng R2DBC. Ví dụ Spring Boot:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders
    username: app_runtime
    password: runtime-secret

  liquibase:
    url: jdbc:postgresql://db-host:5432/orders
    user: schema_migrator
    password: migration-secret
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: app
~~~

Các property chính:

- url/user/password: JDBC connection cho Liquibase.
- change-log: changelog gốc.
- default-schema: schema mặc định của đối tượng database.
- liquibase-schema: schema chứa các bảng metadata của Liquibase nếu được cấu hình riêng.
- contexts/labels: chọn nhóm changeset phù hợp với môi trường nếu dự án dùng chúng.

Tên property chính xác và cách Boot tạo DataSource có thể thay đổi theo phiên bản. Dùng tài liệu của Spring Boot và Liquibase tương ứng, đặc biệt nếu có nhiều DataSource.

Liquibase quản lý lịch sử changeset qua các bảng metadata, thường là DATABASECHANGELOG và DATABASECHANGELOGLOCK. Không xóa hoặc chỉnh sửa các bảng này thủ công để bỏ qua lỗi; hãy xử lý changeset và checksum theo hướng dẫn công cụ.

## 8. Chọn Flyway hay Liquibase

Cả hai đều có thể quản lý schema bằng JDBC trong ứng dụng R2DBC. Việc chọn công cụ phụ thuộc cách nhóm quản lý thay đổi:

| Tiêu chí | Flyway | Liquibase |
| --- | --- | --- |
| Cách mô tả migration | Thường dùng SQL versioned migration; cũng có hỗ trợ các dạng khác theo edition/cấu hình. | Changelog XML, YAML, JSON hoặc SQL. |
| Lịch sử | Bảng schema history. | DATABASECHANGELOG và DATABASECHANGELOGLOCK. |
| Phong cách | Tập trung vào chuỗi migration có thứ tự. | Có metadata changeset, context, label và precondition. |
| SQL đặc thù database | Có thể viết script theo vendor hoặc location riêng. | Có thể dùng changeset SQL và precondition/context theo database. |
| JDBC trong Spring Boot | Cấu hình Flyway DataSource/URL. | Cấu hình Liquibase DataSource/URL. |

Không nên chạy cả hai công cụ để cùng quản lý một tập bảng trong cùng schema nếu không có ranh giới sở hữu rõ. Điều đó dễ tạo hai lịch sử migration cạnh tranh và thứ tự cập nhật khó dự đoán.

## 9. Tổ chức file migration

Với Flyway, một cấu trúc phổ biến:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_customers.sql
      V2__create_orders.sql
      V3__add_order_status_index.sql
~~~

Tên versioned migration thường theo dạng V{version}__{description}.sql. Flyway ghi nhận migration đã áp dụng trong schema history table. Không sửa file migration đã chạy ở môi trường dùng chung; hãy thêm migration mới để thay đổi schema.

Với Liquibase:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-customers.yaml
        002-create-orders.yaml
~~~

Master changelog include các changeset theo thứ tự. Mỗi changeset nên có id và author ổn định. Khi changeset đã được áp dụng, tránh chỉnh sửa nội dung theo cách làm thay đổi checksum ngoài quy trình quản lý của Liquibase.

### Tách migration dùng chung và migration theo vendor

Nếu ứng dụng hỗ trợ nhiều hệ quản trị, có thể tổ chức location hoặc changelog riêng theo database. Ví dụ, Flyway hỗ trợ nhiều locations và có thể chọn location theo profile. Liquibase có thể dùng dbms, context hoặc precondition để chọn changeset.

Không nên tạo một script chứa nhiều cú pháp vendor rồi kỳ vọng database bỏ qua nhánh không hiểu. SQL parser thường phải parse toàn bộ câu lệnh trước khi biết điều kiện. Hãy phân tách migration theo database hoặc dùng tính năng conditional chính thức của công cụ.

## 10. Thứ tự chạy migration và khởi động ứng dụng

Ứng dụng chỉ nên nhận traffic khi schema đã ở phiên bản tương thích. Có hai mô hình phổ biến.

### Migration tự chạy khi ứng dụng khởi động

Spring Boot có thể auto-configure Flyway/Liquibase và chạy migration trong quá trình khởi tạo application context. Nếu cấu hình đúng, các bean phụ thuộc schema được sử dụng sau khi migration hoàn tất.

Ưu điểm:

- Dễ thiết lập cho ứng dụng đơn giản.
- Migration chạy tự động khi deployment khởi động.
- Có thể fail fast nếu migration thất bại.

Hạn chế:

- Mỗi replica có thể khởi động cùng lúc và cùng yêu cầu migration.
- Runtime instance cần credentials DDL.
- Thời gian startup phụ thuộc thời gian migration.
- Migration dài có thể làm rollout khó kiểm soát.

Các công cụ migration thường có cơ chế khóa/lịch sử để tránh áp dụng cùng migration nhiều lần, nhưng vẫn phải kiểm tra hành vi concurrency của phiên bản công cụ và database. Không dùng cơ chế đó thay cho kế hoạch rollout.

### Chạy migration như bước triển khai riêng

Trong production, thường dễ kiểm soát hơn nếu pipeline chạy migration một lần trước khi triển khai phiên bản ứng dụng mới:

~~~mermaid
flowchart TD
    A[Build application artifact] --> B[Run migration job with JDBC]
    B --> C{Migration succeeds?}
    C -->|No| D[Stop deployment and investigate]
    C -->|Yes| E[Deploy application replicas]
    E --> F[Application connects with R2DBC]
    F --> G[Health checks and traffic]
~~~

Ưu điểm:

- Credentials DDL chỉ được cấp cho migration job.
- Migration có thể được phê duyệt và quan sát riêng.
- Tránh nhiều replica cùng chạy DDL.
- Có thể kiểm tra schema trước khi rollout.

Nếu chọn mô hình này, tắt auto migration trong runtime app hoặc bảo đảm nó không chạy lần thứ hai ngoài ý muốn. Đừng vừa chạy migration trong pipeline vừa để mỗi replica tự chạy migration mà không có chính sách rõ ràng.

## 11. Tương thích schema khi rollout nhiều phiên bản

Khi ứng dụng có nhiều replica hoặc triển khai rolling update, schema có thể được dùng đồng thời bởi phiên bản cũ và mới. Migration cần cân nhắc tương thích ngược.

Một cách triển khai phổ biến là expand-and-contract:

1. **Expand:** thêm cột nullable, bảng mới hoặc index mà phiên bản cũ vẫn chạy được.
2. **Deploy application:** phiên bản mới đọc/ghi theo cách tương thích với schema mở rộng.
3. **Backfill:** chuyển đổi dữ liệu theo batch nếu cần.
4. **Switch:** chuyển code sang cấu trúc mới sau khi dữ liệu sẵn sàng.
5. **Contract:** xóa cột hoặc cấu trúc cũ trong một release sau khi không còn phiên bản nào sử dụng.

Không xóa hoặc đổi tên cột ngay trong migration đầu tiên nếu replica cũ vẫn đang chạy query dựa vào cột đó.

R2DBC runtime và JDBC migration cùng truy cập một schema nên phải phối hợp theo hợp đồng version. Việc migration hoàn tất không tự bảo đảm code cũ và code mới đều tương thích; cần thiết kế migration theo trình tự rollout.

## 12. JDBC migration và R2DBC transaction là hai ranh giới riêng

Một R2dbcTransactionManager quản lý transaction qua R2DBC ConnectionFactory. Flyway/Liquibase chạy qua JDBC DataSource và JDBC Connection. Hai connection này không tự tham gia cùng một transaction.

Không thể giả định đoạn code sau tạo transaction nguyên tử xuyên qua cả hai công nghệ:

~~~text
R2DBC transaction:
    update application data

JDBC migration connection:
    alter table

Expected: both commit or both rollback
~~~

Đây không phải distributed transaction. Nếu migration thành công rồi thao tác runtime thất bại, schema vẫn đã thay đổi. Nếu runtime transaction rollback, nó không thể rollback DDL đã được commit bởi migration connection.

Quản lý schema nên là một giai đoạn triển khai riêng, không trộn với transaction nghiệp vụ. Với ứng dụng runtime, dùng R2DBC transaction manager cho các thao tác repository cần nguyên tử. Với migration, để công cụ migration sở hữu transaction và connection của nó.

### DDL transactionality phụ thuộc database

Một số database hỗ trợ transactional DDL cho nhiều thao tác; một số lệnh hoặc hệ quản trị có implicit commit hoặc giới hạn rollback. Không giả định một migration gồm nhiều câu DDL luôn rollback toàn bộ nếu câu cuối thất bại. Kiểm tra semantics của database và khả năng transaction của công cụ migration.

## 13. Quyền truy cập và bảo mật credentials

Tách JDBC connection là cơ hội tách quyền theo vai trò:

| Tài khoản | Quyền điển hình |
| --- | --- |
| R2DBC runtime user | SELECT/INSERT/UPDATE/DELETE trên đối tượng ứng dụng cần dùng. |
| JDBC migration user | CREATE/ALTER/DROP và cập nhật metadata schema history/changelog. |
| Read-only/reporting user (nếu có) | SELECT trên các bảng hoặc view được phép. |

Nguyên tắc:

- Không hard-code mật khẩu trong YAML được commit.
- Dùng secret manager, environment variables hoặc cơ chế secret của nền tảng.
- Không log URL chứa username/password.
- Cấp quyền DDL chỉ trong bước migration.
- Xoay vòng credentials theo chính sách vận hành.
- Kiểm tra migration user có quyền trên cả schema ứng dụng và schema metadata của công cụ.
- Không dùng tài khoản superuser nếu quyền tối thiểu đủ để migration chạy.

Nếu ứng dụng tự chạy migration lúc startup, runtime process cần có quyền DDL. Nếu tách migration job, có thể loại bỏ credentials DDL khỏi deployment runtime.

## 14. Connection pool cho JDBC migration

R2DBC pool và JDBC pool độc lập. Không dùng cấu hình spring.r2dbc.pool để điều khiển JDBC DataSource.

Migration thường là workload ngắn và tuần tự. Một connection JDBC hoặc pool nhỏ có thể đủ. Tránh tạo pool lớn chỉ để chạy một lần migration khi startup.

Các yếu tố cần xem xét:

- Migration chạy một lần trong mỗi deployment hay mỗi application instance?
- DataSource được tạo bởi Spring Boot hay cấu hình thủ công?
- Connection có được đóng sau khi migration hoàn tất?
- Có nhiều công cụ JDBC cùng dùng DataSource không?
- Timeout kết nối và statement có đủ cho migration dài không?

Nếu dùng HikariCP hoặc pool JDBC khác, cấu hình riêng cho DataSource migration. Không dùng chung connection pool với R2DBC vì hai SPI và loại connection khác nhau.

## 15. Kiểm thử migration cùng R2DBC

Integration test nên xác nhận cả hai đường kết nối cùng nhìn thấy một schema.

Một mô hình kiểm thử với Testcontainers:

1. Khởi động một database container.
2. Tạo JDBC URL cho Flyway/Liquibase.
3. Tạo R2DBC URL cho ứng dụng.
4. Chạy migration qua JDBC.
5. Khởi tạo repository R2DBC.
6. Thực hiện insert/select qua R2DBC.
7. Xác nhận bảng, cột, constraint và index đã được tạo như mong đợi.

Ví dụ kiểm thử theo ý tưởng:

~~~java
@Test
void migrationSchemaCanBeUsedThroughR2dbc() {
    // Migration runner dùng JDBC DataSource trên database container.
    // Sau khi migration hoàn tất, repository R2DBC dùng cùng database.
    StepVerifier.create(customerRepository.save(sampleCustomer()))
        .assertNext(saved -> assertNotNull(saved.id()))
        .verifyComplete();
}
~~~

Test thực tế cần cấu hình container, credentials và URL tương ứng. JDBC URL và R2DBC URL phải trỏ tới cùng container/database/schema; không chỉ dùng chung hostname giả định.

### Test từ schema trống

Luôn có một test hoặc pipeline job khởi tạo database mới từ schema rỗng. Nó giúp phát hiện:

- Migration thiếu file hoặc sai thứ tự.
- JDBC driver không có trong runtime classpath của migration job.
- Sai schema/default schema.
- Changelog hoặc Flyway location không được tìm thấy.
- SQL chỉ chạy được trên một database khác.
- Runtime mapping không khớp schema sau migration.

### Test nâng cấp từ phiên bản cũ

Ngoài schema trống, nên test nâng cấp từ phiên bản schema đang được triển khai. Một migration có thể chạy tốt từ đầu nhưng thất bại khi có dữ liệu cũ, index tồn tại hoặc constraint đã được tạo.

Dữ liệu test nên bao gồm các trường hợp NULL, duplicate, giá trị ngoài phạm vi và bảng lớn nếu migration có backfill.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Flyway báo không tìm thấy driver | Thiếu JDBC driver hoặc database module của Flyway. | Kiểm tra runtime classpath và dependency version. |
| R2DBC hoạt động nhưng migration không kết nối | JDBC URL/driver/credentials sai. | Kiểm tra spring.flyway.url hoặc spring.liquibase.url và driver tương ứng. |
| Migration thành công nhưng repository báo thiếu bảng | JDBC và R2DBC trỏ khác database/schema. | So sánh host, database, schema, search path và user. |
| Boot không tạo migration DataSource | Cấu hình property hoặc auto-configuration không phù hợp phiên bản. | Kiểm tra reference docs, condition report và bean DataSource. |
| Có hai lần migration lúc startup | Vừa chạy pipeline vừa auto-run trong runtime hoặc nhiều cấu hình. | Chọn một nơi sở hữu migration. |
| Permission denied khi migrate | Migration user thiếu quyền DDL hoặc metadata schema. | Kiểm tra quyền trên schema đích và bảng history/changelog. |
| Checksum validation failed | Migration đã sửa sau khi được áp dụng hoặc artifact khác nhau. | Khôi phục file lịch sử hoặc tạo migration mới theo hướng dẫn công cụ. |
| Runtime user không thể tạo bảng | Runtime credentials cố chạy DDL nhưng chỉ có quyền DML. | Chạy migration bằng user riêng có quyền DDL. |
| Schema thay đổi nhưng app cũ lỗi | Migration phá tương thích ngược trong rolling deployment. | Áp dụng expand-and-contract. |
| JDBC migration chạy nhưng R2DBC type mapping lỗi | DDL tạo kiểu hoặc default không phù hợp driver/runtime mapping. | Kiểm tra schema, R2DBC converter và integration test. |

### Driver not found

Nếu lỗi nhắc tới không tìm thấy JDBC driver hoặc không có driver phù hợp với URL, hãy kiểm tra:

- JDBC driver có ở runtime classpath của tiến trình chạy migration không?
- Driver có đúng database vendor không?
- JDBC URL có đúng scheme không?
- Module database của Flyway có cần thêm riêng theo version không?
- Dependency bị exclude hoặc scope chỉ compile/test không?

Không sửa bằng cách thêm một driver khác bất kỳ. Driver phải tương thích database server và phiên bản công cụ.

### Migration chạy vào sai schema

Nếu bảng history cho biết migration thành công nhưng repository R2DBC không tìm thấy bảng, kiểm tra default schema và search path của hai connection. JDBC session và R2DBC session có thể có cấu hình session khác nhau dù cùng database.

Hãy đặt schema tường minh trong cấu hình migration hoặc tên đối tượng theo quy ước thống nhất. Nếu database hỗ trợ schema search path, xác minh nó cho cả hai loại connection.

## 17. Chạy migration trong pipeline thay vì startup

Với môi trường production, có thể tạo một migration job/artifact riêng dùng JDBC:

~~~text
Build:
  application artifact
  migration artifact/configuration

Deploy:
  1. Start database dependency
  2. Run migration job with JDBC credentials
  3. Verify migration result
  4. Deploy R2DBC application with runtime credentials
  5. Run health checks
  6. Route traffic
~~~

Migration job có thể dùng cùng codebase và cùng migration files, nhưng chỉ cần dependency JDBC và công cụ migration. Runtime application chỉ cần R2DBC driver và credentials DML.

Cách này giúp rollback deployment ứng dụng độc lập với schema migration, nhưng không có nghĩa schema tự động rollback. Nếu migration phá tương thích, cần migration bù hoặc triển khai tiến về phía trước theo chiến lược đã định.

Không chạy migration đồng thời từ nhiều pipeline cho cùng một schema nếu không có cơ chế điều phối. Công cụ có lock không thay thế quy trình release rõ ràng.

## 18. Những điều không nên làm

- Không dùng JDBC repository/JdbcTemplate cho toàn bộ runtime chỉ vì đã thêm JDBC driver để chạy Flyway.
- Không dùng JDBC URL cho spring.r2dbc.url.
- Không dùng R2dbcTransactionManager để quản lý JDBC connection.
- Không giả định JDBC migration và R2DBC write nằm trong cùng transaction.
- Không cấp quyền DDL cho runtime user nếu có thể tách migration job.
- Không chạy cả Flyway và Liquibase trên cùng schema mà không có ranh giới sở hữu.
- Không sửa migration versioned đã áp dụng ở môi trường dùng chung.
- Không chạy migration trên mỗi replica nếu pipeline/job riêng phù hợp hơn.
- Không giả định schema được tạo trên JDBC chắc chắn tương thích với mapping R2DBC; cần test read/write.
- Không để JDBC DataSource hoặc driver tồn tại chỉ vì một cấu hình cũ không còn dùng.

## 19. Quy trình triển khai

Khi một ứng dụng R2DBC cần dùng công cụ migration JDBC, có thể triển khai theo thứ tự:

1. **Xác định công cụ migration:** kiểm tra phiên bản Flyway/Liquibase và giao thức kết nối được hỗ trợ.
2. **Chọn driver:** thêm R2DBC driver cho runtime và JDBC driver cho migration nếu cần.
3. **Tách URL:** dùng R2DBC URL cho ConnectionFactory, JDBC URL cho DataSource migration.
4. **Tách credentials:** runtime user có quyền DML; migration user có quyền schema.
5. **Cấu hình công cụ:** đặt location/changelog, schema, validate và các thuộc tính cần thiết.
6. **Chọn nơi chạy:** startup auto-migration hoặc pipeline migration job; chỉ chọn một cơ chế chủ đạo.
7. **Bảo đảm thứ tự:** migration hoàn tất trước khi phiên bản ứng dụng phụ thuộc schema được nhận traffic.
8. **Giữ tương thích rollout:** dùng expand-and-contract khi có nhiều phiên bản chạy đồng thời.
9. **Kiểm thử cả hai đường:** chạy migration bằng JDBC rồi đọc/ghi qua R2DBC trên cùng database container.
10. **Quan sát vận hành:** theo dõi migration history, lỗi quyền, connection, checksum và schema version.

Tách JDBC cho migration là một lựa chọn kiến trúc bình thường trong ứng dụng Spring Data Relational R2DBC. R2DBC tiếp tục đảm nhiệm truy vấn reactive lúc runtime; JDBC chỉ cung cấp kết nối cho công cụ cần nó để quản lý schema. Khi cấu hình hai URL, driver, credentials và transaction boundary riêng, đồng thời bảo đảm migration chạy trước ứng dụng và kiểm thử schema bằng cả hai giao thức, dự án có thể sử dụng công cụ migration JDBC mà vẫn giữ phần truy cập dữ liệu nghiệp vụ theo mô hình reactive.
