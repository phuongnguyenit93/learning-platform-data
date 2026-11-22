# Cấu hình kết nối JDBC và chọn cơ sở dữ liệu đích

Liquibase chỉ có thể kiểm tra và áp dụng migration khi kết nối đúng tới database cần quản lý. Vì vậy, cấu hình kết nối JDBC và lựa chọn database đích là bước nền tảng của mọi lần chạy Liquibase. Một cấu hình đúng phải xác định được hệ quản trị cơ sở dữ liệu (DBMS), máy chủ và cổng, database hoặc service cần kết nối, JDBC driver, tài khoản, schema mặc định và nơi lưu bảng lịch sử của Liquibase.

Bài học thuộc chương **Cấu hình** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module này giúp bạn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau bài học, bạn có thể đọc và xây dựng JDBC URL, chọn đúng database đích, phân biệt database với schema và schema metadata của Liquibase, cấu hình kết nối trong Spring Boot hoặc Liquibase CLI, quản lý thông tin xác thực an toàn và kiểm tra kết nối trước khi chạy migration.

## 1. Liquibase kết nối tới database như thế nào?

Liquibase sử dụng JDBC (Java Database Connectivity) để làm việc với cơ sở dữ liệu quan hệ. JDBC cung cấp giao diện chung để ứng dụng Java mở kết nối, gửi câu lệnh SQL và đọc metadata của DBMS. Mỗi hệ quản trị cần JDBC driver tương ứng để chuyển các lời gọi JDBC thành giao thức mà máy chủ database hiểu được.

Một kết nối Liquibase thường cần các thành phần sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| DBMS | Hệ quản trị mà database đang chạy | PostgreSQL, MySQL, SQL Server, Oracle |
| JDBC URL | Xác định máy chủ và database hoặc service đích | jdbc:postgresql://db-dev:5432/orders |
| JDBC driver | Thư viện Java triển khai JDBC cho DBMS | PostgreSQL JDBC Driver |
| Username | Tài khoản Liquibase dùng để đăng nhập | liquibase_migrator |
| Password | Bí mật xác thực của tài khoản | Được cấp từ secret store |
| Default schema | Schema mặc định để phân giải đối tượng không ghi rõ schema | app |
| Liquibase schema | Schema lưu bảng theo dõi của Liquibase, nếu cấu hình riêng | liquibase_meta |

Luồng kết nối ở mức khái quát:

~~~mermaid
flowchart TD
    A[Spring Boot hoặc Liquibase CLI] --> B[JDBC URL và thông tin xác thực]
    B --> C[JDBC Driver]
    C --> D[Database đích]
    D --> E[Đọc metadata và DATABASECHANGELOG]
    E --> F[Đối chiếu changelog và changeset]
    F --> G[Thực thi migration khi được yêu cầu]
    G --> H[Cập nhật lịch sử triển khai]
~~~

Khi kết nối thành công, Liquibase nhận diện loại database thông qua kết nối và metadata JDBC, sau đó sử dụng khả năng tương thích của DBMS để tạo SQL và quản lý các bảng nội bộ. JDBC URL vì thế không chỉ là một chuỗi cấu hình: nó quyết định Liquibase đang làm việc với database nào.

## 2. Đọc cấu trúc JDBC URL

JDBC URL thường bắt đầu bằng tiền tố **jdbc:** và chứa định danh của driver hoặc DBMS, tiếp theo là thông tin máy chủ và database đích. Cú pháp chính xác phụ thuộc nhà cung cấp driver.

Một số dạng phổ biến:

| DBMS | Mẫu JDBC URL | Driver class thường dùng |
|---|---|---|
| PostgreSQL | jdbc:postgresql://HOST:5432/DATABASE | org.postgresql.Driver |
| MySQL | jdbc:mysql://HOST:3306/DATABASE | com.mysql.cj.jdbc.Driver |
| MariaDB | jdbc:mariadb://HOST:3306/DATABASE | org.mariadb.jdbc.Driver |
| SQL Server | jdbc:sqlserver://HOST:1433;databaseName=DATABASE | com.microsoft.sqlserver.jdbc.SQLServerDriver |
| Oracle | jdbc:oracle:thin:@//HOST:1521/SERVICE_NAME | oracle.jdbc.OracleDriver |
| H2 | jdbc:h2:mem:DATABASE | org.h2.Driver |

Các cổng trong bảng là cổng mặc định thường gặp; môi trường thực tế có thể dùng cổng khác. Driver class cũng có thể được JDBC tự phát hiện qua cơ chế đăng ký driver, nhưng khai báo rõ ràng giúp việc chẩn đoán và cấu hình dễ đọc hơn.

### 2.1. Thành phần máy chủ và database

Với PostgreSQL, URL:

~~~text
jdbc:postgresql://db-staging.internal:5432/orders
~~~

có nghĩa là kết nối tới máy chủ db-staging.internal, cổng 5432, database orders. Schema như app hoặc reporting là namespace bên trong database đó, không phải phần thay thế cho tên database trong URL.

Với SQL Server, tên database thường được truyền bằng thuộc tính databaseName:

~~~text
jdbc:sqlserver://sql-staging.internal:1433;databaseName=orders
~~~

Với Oracle, phần cuối của dạng URL service name xác định dịch vụ database mà client kết nối:

~~~text
jdbc:oracle:thin:@//oracle-staging.internal:1521/ORDERS_SVC
~~~

Không nên sao chép nguyên JDBC URL của một DBMS sang DBMS khác. Mỗi driver có quy tắc riêng cho host, port, database, service name, tham số mã hóa, timeout và các tùy chọn kết nối.

### 2.2. Tham số bổ sung

Một số driver cho phép thêm thuộc tính vào JDBC URL để cấu hình TLS, timeout, encoding, timezone hoặc hành vi kết nối. Ví dụ, driver PostgreSQL hỗ trợ tham số URL theo dạng query string; SQL Server sử dụng cú pháp thuộc tính phân tách bằng dấu chấm phẩy.

Chỉ thêm tham số theo tài liệu của đúng driver và phiên bản đang sử dụng. Không bật tùy chọn bỏ qua kiểm tra chứng chỉ TLS trong môi trường thật để chữa lỗi kết nối. Khi database yêu cầu mã hóa, cần cấu hình xác minh chứng chỉ và hostname theo chính sách bảo mật của tổ chức.

Tránh đặt username hoặc password trực tiếp trong URL. Tách thông tin xác thực thành cấu hình riêng để dễ cấp quyền, luân chuyển secret và tránh lộ bí mật trong log.

## 3. Phân biệt DBMS, database, catalog và schema

Các khái niệm này thường bị nhầm lẫn, dẫn tới việc Liquibase kết nối thành công nhưng tạo đối tượng ở sai nơi.

- **DBMS** là phần mềm quản trị, ví dụ PostgreSQL hoặc SQL Server.
- **Database** là cơ sở dữ liệu cụ thể trên một máy chủ hoặc dịch vụ.
- **Catalog** là cấp định danh database hoặc tập hợp đối tượng theo mô hình của DBMS; cách sử dụng thay đổi giữa các hệ quản trị.
- **Schema** là namespace chứa bảng, view, sequence, procedure và các đối tượng khác trong database.
- **Default schema** là schema mặc định dùng khi câu lệnh không chỉ rõ schema.
- **Liquibase schema** là schema được chọn để lưu các bảng metadata như DATABASECHANGELOG và DATABASECHANGELOGLOCK.

Quan hệ giữa database và schema không giống nhau ở mọi DBMS:

| DBMS | Database đích | Schema |
|---|---|---|
| PostgreSQL | Chọn trong JDBC URL | Nhiều schema có thể cùng tồn tại trong một database |
| SQL Server | Chọn bằng databaseName | Schema như dbo, sales, app nằm trong database |
| Oracle | Chọn dịch vụ hoặc database qua kết nối | Schema gắn với user; current schema có thể khác user đăng nhập |
| MySQL | Phần lớn thao tác gọi database và schema gần như đồng nghĩa | Database thường là namespace chính được chọn trong URL |

Ví dụ, với PostgreSQL, URL chọn database orders, còn defaultSchemaName có thể chọn schema app. Nếu Liquibase cần lưu lịch sử trong schema riêng, có thể cấu hình liquibaseSchemaName là liquibase_meta.

Hai cấu hình này có mục đích khác nhau:

- **defaultSchemaName**: schema mặc định cho các đối tượng ứng dụng mà changelog thao tác khi không chỉ rõ schema.
- **liquibaseSchemaName**: schema lưu các bảng theo dõi nội bộ của Liquibase.

Nếu không cấu hình schema metadata riêng, các bảng theo dõi thường được tạo trong schema mặc định mà kết nối đang sử dụng. Hãy xác minh schema thực tế và quyền của tài khoản trước khi triển khai. Việc đặt defaultSchemaName không có nghĩa là đã chọn đúng database; database đích vẫn do JDBC URL và cấu hình kết nối quyết định.

## 4. Chọn đúng database đích

Một máy chủ có thể chứa nhiều database, nhiều cluster hoặc nhiều service. Tên database gần giống nhau giữa development, test, staging và production làm tăng nguy cơ chạy migration nhầm môi trường.

Trước khi cấu hình, hãy xác định rõ:

1. **Môi trường**: local, development, test, staging hay production.
2. **Máy chủ**: hostname hoặc endpoint chính xác, cổng và vùng mạng được phép truy cập.
3. **Database hoặc service**: tên database PostgreSQL/MySQL/SQL Server hoặc Oracle service name.
4. **Schema ứng dụng**: schema mà changeset cần tạo hoặc thay đổi đối tượng.
5. **Schema metadata**: nơi lưu DATABASECHANGELOG và DATABASECHANGELOGLOCK.
6. **Tài khoản**: principal được cấp đúng quyền cho migration tại database và schema đó.

Không dùng localhost theo thói quen trong mọi môi trường. Trong container, localhost trỏ về chính container đang chạy Liquibase hoặc ứng dụng; database ở container khác thường cần tên service hoặc hostname trong mạng container. Trong CI runner, localhost cũng không tự động trỏ tới database của máy phát triển.

Nên dùng endpoint riêng cho từng môi trường và cấu hình chúng qua Spring profile, biến môi trường hoặc secret manager. Không dựa vào tên branch hoặc context để tự động suy ra database đích. Context và label lọc changeset nào được áp dụng sau khi Liquibase đã kết nối; chúng không thay thế cấu hình endpoint.

### 4.1. Không nhầm database với schema

Giả sử hệ thống PostgreSQL có database orders, chứa hai schema app và liquibase_meta.

- JDBC URL chọn database orders.
- defaultSchemaName: app giúp các đối tượng ứng dụng không ghi rõ schema được phân giải theo app.
- liquibaseSchemaName: liquibase_meta đặt bảng lịch sử của Liquibase vào schema metadata.

Nếu URL vô tình trỏ tới database orders_test, việc đặt default schema thành app vẫn không đưa kết nối trở lại database orders. Vì vậy, phải xác nhận URL và database trước, sau đó mới cấu hình schema.

### 4.2. Kiểm tra danh tính database sau khi kết nối

Trước khi chạy update, có thể thực hiện truy vấn chỉ đọc phù hợp với DBMS để xác nhận kết nối đang dùng đúng database và user.

PostgreSQL:

~~~sql
SELECT current_database(), current_schema(), current_user;
~~~

MySQL:

~~~sql
SELECT DATABASE(), CURRENT_USER();
~~~

SQL Server:

~~~sql
SELECT DB_NAME(), SCHEMA_NAME(), SYSTEM_USER;
~~~

Oracle:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    USER AS connected_user
FROM dual;
~~~

Đối chiếu kết quả với môi trường dự kiến và thông tin phát hành. Các truy vấn này giúp xác nhận phiên kết nối hiện tại; chúng không thay thế kiểm tra quyền hoặc kiểm tra nội dung migration.

## 5. JDBC driver và dependency

Liquibase cần driver tương ứng có mặt trên classpath tại nơi Liquibase chạy. Cài driver cho ứng dụng không đồng nghĩa mọi cách chạy Liquibase đều tự động nhìn thấy driver đó.

Ví dụ các artifact Maven phổ biến:

| DBMS | Maven artifact |
|---|---|
| PostgreSQL | org.postgresql:postgresql |
| MySQL | com.mysql:mysql-connector-j |
| MariaDB | org.mariadb.jdbc:mariadb-java-client |
| SQL Server | com.microsoft.sqlserver:mssql-jdbc |
| Oracle | com.oracle.database.jdbc:ojdbc11 |
| H2 | com.h2database:h2 |

Tên artifact và phiên bản cần chọn theo Java runtime, DBMS và ma trận tương thích của nhà cung cấp. Với Oracle, cách lấy dependency có thể phụ thuộc phiên bản và repository được tổ chức sử dụng.

Có ba tình huống thường gặp:

- **Spring Boot application**: driver phải nằm trong runtime classpath của ứng dụng. Nếu Liquibase khởi chạy cùng ứng dụng và dùng DataSource của ứng dụng, driver đó thường được dùng chung.
- **Liquibase CLI**: driver phải có trong classpath của CLI, chẳng hạn được cung cấp qua thư mục thư viện hoặc tùy chọn classpath phù hợp. Dependency của một ứng dụng khác không tự động được CLI nhìn thấy.
- **Liquibase Maven/Gradle plugin**: cần cấu hình driver trong phạm vi classpath mà plugin sử dụng. Kiểm tra tài liệu của plugin và phiên bản đang chạy.

Driver không tương thích có thể khiến kết nối thất bại dù JDBC URL nhìn đúng. Cần kiểm tra phiên bản driver, Java, Liquibase và DBMS cùng nhau, đặc biệt khi nâng cấp một thành phần.

## 6. Cấu hình kết nối trong Spring Boot

Spring Boot có thể tự động cấu hình Liquibase khi ứng dụng có dependency Liquibase và cấu hình được bật. Trong trường hợp thông thường, Liquibase dùng DataSource của ứng dụng. Các thuộc tính spring.datasource.* xác định kết nối chính của ứng dụng.

Ví dụ PostgreSQL với một DataSource dùng chung:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-dev.internal:5432/orders
    username: app_migrator
    password: "<inject-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: liquibase_meta
~~~

Trong ví dụ này, Liquibase sử dụng kết nối datasource được Spring Boot cung cấp. Tài khoản app_migrator cần quyền thực hiện migration và quản lý các bảng metadata trong schema được chọn. Nếu tài khoản runtime của ứng dụng không nên có quyền DDL, hãy cân nhắc cấu hình kết nối migration riêng.

### 6.1. Dùng kết nối riêng cho Liquibase

Trong hệ thống production, tài khoản ứng dụng thường chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ, còn tài khoản migration cần quyền tạo hoặc sửa đối tượng database. Có thể cấu hình kết nối Liquibase riêng bằng các thuộc tính spring.liquibase.*:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-prod.internal:5432/orders
    username: orders_app
    password: "<inject-app-secret>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: jdbc:postgresql://db-prod.internal:5432/orders
    user: orders_migrator
    password: "<inject-migration-secret>"
    driver-class-name: org.postgresql.Driver
    default-schema: app
    liquibase-schema: liquibase_meta
~~~

Ở đây, ứng dụng và Liquibase kết nối cùng database nhưng dùng principal khác nhau. Tài khoản orders_migrator được cấp quyền DDL và quyền cần thiết cho các bảng theo dõi; tài khoản orders_app chỉ nhận quyền runtime cần thiết.

Nếu cấu hình nhiều DataSource trong Spring Boot, hãy chỉ định rõ DataSource dành cho Liquibase, chẳng hạn bằng bean được đánh dấu **@LiquibaseDataSource**, hoặc cấu hình URL/user/password Liquibase riêng theo cách phù hợp với phiên bản Spring Boot. Tránh để Liquibase vô tình nhận một DataSource không phải database cần migration.

### 6.2. Cấu hình theo profile và môi trường

Có thể dùng profile để tách endpoint development, staging và production:

~~~yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:postgresql://db-dev.internal:5432/orders_dev
    username: orders_app_dev
  liquibase:
    url: jdbc:postgresql://db-dev.internal:5432/orders_dev
    user: orders_migrator_dev
~~~

~~~yaml
# application-staging.yml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_app_staging
  liquibase:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    user: orders_migrator_staging
~~~

Các ví dụ chỉ minh họa cách tách endpoint và username; password nên được tiêm từ secret manager hoặc hệ thống cấu hình runtime. Không đưa password thật vào file profile được commit vào Git.

Hãy kiểm tra profile đang hoạt động trong môi trường triển khai. Một profile sai có thể khiến ứng dụng khởi động và migration chạy trên database ngoài dự kiến.

## 7. Cấu hình bằng Liquibase CLI

Khi chạy Liquibase độc lập, cấu hình thường được đặt trong file liquibase.properties hoặc truyền qua tham số dòng lệnh. File properties giúp lưu những giá trị không nhạy cảm và tái sử dụng cấu hình.

Ví dụ:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://localhost:5432/orders_dev
username=orders_migrator
driver=org.postgresql.Driver
defaultSchemaName=app
liquibaseSchemaName=liquibase_meta
~~~

Không lưu password thật trong file cấu hình nằm trong repository. Cấp password ở thời điểm chạy qua secret store, cơ chế bảo mật của CI/CD hoặc phương thức nhập bí mật được tổ chức phê duyệt. Cẩn thận với tham số dòng lệnh vì một số hệ điều hành và công cụ giám sát có thể ghi lại command line.

Ví dụ lệnh kiểm tra trạng thái:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml \
  --url=jdbc:postgresql://localhost:5432/orders_dev \
  --username=orders_migrator \
  --driver=org.postgresql.Driver \
  status --verbose
~~~

Cú pháp tùy chọn và cách nạp file cấu hình có thể khác giữa các phiên bản Liquibase. Hãy kiểm tra liquibase --help và tài liệu của phiên bản đang dùng trước khi đưa lệnh vào pipeline.

Một cấu hình dùng chung nên giữ đường dẫn changelog và các thiết lập ổn định. URL, username và secret thay đổi theo môi trường nên được truyền từ cấu hình triển khai của môi trường tương ứng.

## 8. Quyền database dành cho Liquibase

Tài khoản kết nối cần đủ quyền để thực hiện các changeset trong changelog và quản lý bảng metadata. Quyền cụ thể phụ thuộc DBMS, schema, loại change type và chính sách bảo mật.

Thông thường, tài khoản migration có thể cần:

- Quyền kết nối tới database hoặc service đích.
- Quyền đọc metadata cần thiết để kiểm tra schema.
- Quyền tạo, sửa hoặc xóa đối tượng theo phạm vi migration được phê duyệt.
- Quyền tạo và cập nhật DATABASECHANGELOG, DATABASECHANGELOGLOCK trong schema metadata.
- Quyền thao tác trên sequence, procedure, view, trigger hoặc dữ liệu nếu changelog có các thay đổi đó.

Không cấp quyền quản trị toàn bộ máy chủ database nếu migration chỉ cần quản lý một database và một số schema. Tài khoản Liquibase nên tuân theo nguyên tắc quyền tối thiểu cần thiết.

Nên phân biệt hai nhóm tài khoản:

| Tài khoản | Mục đích | Quyền điển hình |
|---|---|---|
| Migration user | Chạy Liquibase trong startup hoặc pipeline được kiểm soát | Quyền DDL/DML cần thiết cho changeset và quyền quản lý bảng lịch sử |
| Application runtime user | Phục vụ truy vấn của ứng dụng sau triển khai | Quyền đọc/ghi nghiệp vụ theo yêu cầu, thường không cần quyền DDL |

Nếu Liquibase chạy mỗi lần ứng dụng khởi động, cần xem xét tài khoản ứng dụng và cơ chế triển khai có phù hợp để mang quyền migration hay không. Nhiều hệ thống chọn một bước migration riêng trong pipeline để kiểm soát quyền và thời điểm thực thi.

## 9. Kiểm tra kết nối trước khi chạy migration

Không nên bắt đầu bằng update ngay sau khi sửa URL. Hãy kiểm tra lần lượt từ cấu hình tới trạng thái database.

Quy trình kiểm tra gợi ý:

1. Xác nhận JDBC URL trỏ tới đúng hostname, port và database/service.
2. Xác nhận driver có trên classpath và tương thích với DBMS.
3. Kiểm tra DNS, routing, firewall, VPN hoặc mạng container.
4. Xác nhận username/password được cấp từ đúng secret của môi trường.
5. Xác nhận user có thể đăng nhập và nhìn thấy database/schema mong muốn.
6. Xác nhận quyền tạo hoặc cập nhật đối tượng và bảng metadata của Liquibase.
7. Chạy lệnh kiểm tra trạng thái và xác thực changelog.
8. Sinh SQL dự kiến, review nội dung rồi mới chạy update.

Các lệnh Liquibase thường được dùng:

~~~bash
liquibase status --verbose
liquibase validate
liquibase update-sql
liquibase update
~~~

- **status --verbose** cho biết changeset nào đang chờ áp dụng theo lịch sử và điều kiện hiện tại.
- **validate** kiểm tra tính hợp lệ của changelog theo các quy tắc của Liquibase; lệnh này không thực thi migration.
- **update-sql** tạo SQL dự kiến cho những changeset đủ điều kiện mà không áp dụng chúng vào database.
- **update** thực thi các thay đổi được chọn trên database đích.

status và update-sql vẫn cần cấu hình kết nối phù hợp để đối chiếu với database. validate không thay thế việc xác minh endpoint. Chỉ chạy update sau khi đã xác nhận môi trường, quyền và SQL dự kiến.

Trong pipeline, nên ghi nhận môi trường, định danh database không nhạy cảm, phiên bản artifact changelog và kết quả review. Tránh ghi password, token hoặc toàn bộ JDBC URL nếu URL chứa bí mật.

## 10. Tách cấu hình kết nối khỏi logic changelog

Changelog nên mô tả thay đổi schema và dữ liệu. Endpoint, username và password nên được cung cấp bởi cấu hình triển khai. Nhờ đó, cùng một artifact changelog có thể đi qua development, test, staging và production theo quy trình kiểm soát.

Không nên tạo bản changelog riêng chỉ để thay URL hoặc mật khẩu cho mỗi môi trường. Các khác biệt thực sự về DBMS hoặc cấu trúc môi trường có thể được biểu diễn bằng thuộc tính phù hợp như dbms, context, label hoặc precondition; nhưng việc chọn database đích vẫn phải nằm trong cấu hình kết nối.

Ví dụ, nếu một changeset chỉ dành cho PostgreSQL, có thể giới hạn DBMS trong changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: db-team
      dbms: postgresql
      changes:
        - createTable:
            schemaName: app
            tableName: migration_audit
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Thuộc tính dbms giúp Liquibase quyết định changeset có phù hợp với DBMS của kết nối hiện tại hay không. Nó không chuyển kết nối sang PostgreSQL và cũng không bảo vệ khỏi việc cấu hình nhầm database PostgreSQL khác.

Precondition có thể kiểm tra một số giả định về database, schema hoặc đối tượng trước khi thực thi. Đây là lớp kiểm soát bổ sung; không nên dùng precondition để thay thế việc cấu hình đúng URL và xác nhận môi trường.

## 11. Bảo vệ thông tin kết nối

Thông tin kết nối thường bao gồm endpoint nội bộ, username, password và tham số TLS. Cần quản lý chúng như cấu hình vận hành có kiểm soát.

- Không commit password, token hoặc private key vào Git.
- Lấy secret từ secret manager, vault, nền tảng triển khai hoặc cơ chế bảo mật tương đương.
- Dùng tài khoản riêng cho từng môi trường để giới hạn phạm vi khi thông tin bị lộ.
- Luân chuyển credential theo quy trình và kiểm tra lại pipeline sau khi đổi.
- Hạn chế quyền đọc file cấu hình và log có chứa thông tin kết nối.
- Không bật chế độ bỏ qua xác minh chứng chỉ trong production.
- Tránh truyền password trực tiếp trong command line nếu công cụ có thể ghi lại tham số.
- Không ghi secret vào changelog, precondition, comment hoặc tham số migration.

Một số driver hỗ trợ truyền thông tin xác thực qua thuộc tính riêng hoặc DataSource. Chọn cơ chế được framework và secret manager hỗ trợ, đồng thời bảo đảm secret không xuất hiện trong log lỗi hoặc báo cáo triển khai.

## 12. Các lỗi kết nối thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| No suitable driver | Thiếu JDBC driver hoặc URL không được driver hỗ trợ | Kiểm tra dependency, classpath và tiền tố JDBC URL. |
| ClassNotFoundException cho driver | Khai báo driver class nhưng thiếu JAR tương ứng | Bổ sung đúng artifact và kiểm tra classpath tại nơi Liquibase thực sự chạy. |
| Connection refused | Sai host/port, database chưa lắng nghe hoặc firewall từ chối | Kiểm tra endpoint, trạng thái dịch vụ, port và network route. |
| Unknown host | DNS sai hoặc hostname không phân giải được từ runtime | Kiểm tra DNS trong chính máy/container/runner chạy Liquibase. |
| Authentication failed | Sai username/password, user bị khóa hoặc phương thức xác thực không khớp | Kiểm tra secret của đúng môi trường và chính sách xác thực DBMS. |
| Database hoặc service không tồn tại | Sai tên database, catalog hoặc Oracle service name | Kiểm tra JDBC URL và danh mục database/service trên máy chủ. |
| Permission denied | User thiếu quyền kết nối, schema hoặc quyền DDL/metadata | Kiểm tra grants trên database đích và schema metadata. |
| SSL handshake hoặc certificate error | TLS chưa được cấu hình đúng hoặc chứng chỉ không được tin cậy | Kiểm tra truststore, certificate chain, hostname và tham số của driver. |
| Migration tạo bảng sai schema | Default schema hoặc Liquibase schema không đúng | Xác minh current schema, defaultSchemaName và liquibaseSchemaName. |
| Ứng dụng kết nối đúng nhưng Liquibase kết nối sai | Liquibase có URL/user riêng hoặc được gắn nhầm DataSource | Kiểm tra spring.datasource.*, spring.liquibase.* và DataSource được chọn. |
| Chạy được local nhưng lỗi trong CI | Khác DNS, mạng, secret, driver classpath hoặc profile | Kiểm tra cấu hình và quyền từ chính CI runner. |

Khi điều tra, hãy lấy thông tin lỗi đầy đủ nhưng che password, token và các tham số bí mật. Một thông báo Connection refused thường là vấn đề mạng hoặc dịch vụ; Permission denied thường cần xem grants; còn No suitable driver thường liên quan classpath hoặc URL.

## 13. Bài thực hành: cấu hình Liquibase tới PostgreSQL development

Mục tiêu là cấu hình Liquibase kết nối tới database orders_dev, sử dụng schema ứng dụng app và schema metadata liquibase_meta.

### Bước 1: Chuẩn bị database và tài khoản

Nhờ quản trị viên hoặc môi trường local tạo database orders_dev, các schema cần dùng và tài khoản migration. Tài khoản phải có quyền kết nối, quyền cần thiết trên schema ứng dụng và quyền quản lý bảng lịch sử trong schema metadata.

Không giả định rằng việc database đã tồn tại đồng nghĩa các schema cũng đã tồn tại hoặc user có đủ quyền.

### Bước 2: Kiểm tra JDBC driver

Đảm bảo PostgreSQL JDBC Driver có trong runtime classpath của ứng dụng hoặc classpath của Liquibase CLI. Kiểm tra phiên bản driver phù hợp với Java runtime và PostgreSQL server.

### Bước 3: Khai báo kết nối

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
    username: orders_app
    password: "<inject-app-secret>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: jdbc:postgresql://localhost:5432/orders_dev
    user: orders_migrator
    password: "<inject-migration-secret>"
    driver-class-name: org.postgresql.Driver
    default-schema: app
    liquibase-schema: liquibase_meta
~~~

Thay endpoint và secret theo môi trường thực tế. Không dùng cấu hình local này cho production nếu chưa thay đổi endpoint, principal, secret và chính sách mạng.

### Bước 4: Xác nhận danh tính kết nối

Chạy truy vấn chỉ đọc:

~~~sql
SELECT current_database(), current_schema(), current_user;
~~~

Đảm bảo database là orders_dev và user là tài khoản dự kiến. Kiểm tra riêng schema metadata đã tồn tại hoặc có thể được tạo theo quyền được cấp.

### Bước 5: Xem trạng thái và SQL dự kiến

Chạy status --verbose, validate và update-sql với cùng cấu hình kết nối. Review SQL được sinh ra để xác nhận changeset hướng tới đúng schema và không có thao tác ngoài dự kiến.

### Bước 6: Thực thi và xác minh

Chỉ sau khi review, chạy update trên database development. Sau đó kiểm tra:

- Đối tượng ứng dụng xuất hiện trong schema app.
- DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm trong schema metadata dự kiến.
- Lịch sử ghi nhận đúng changeset, tác giả, file và kết quả.
- Ứng dụng có thể kết nối bằng tài khoản runtime riêng.
- Log không làm lộ credential.

Lặp lại quy trình trên staging bằng cấu hình môi trường staging. Không sao chép dữ liệu lịch sử DATABASECHANGELOG từ development sang staging.

## 14. Checklist trước khi chạy Liquibase

- [ ] JDBC URL xác định đúng host, port và database/service.
- [ ] DBMS và JDBC driver tương thích với phiên bản Java, Liquibase và database.
- [ ] Driver có trên classpath của đúng tiến trình chạy Liquibase.
- [ ] Username/password lấy từ nguồn secret của đúng môi trường.
- [ ] Tài khoản có quyền kết nối, quyền migration và quyền quản lý bảng lịch sử.
- [ ] Database, default schema và Liquibase schema được phân biệt rõ.
- [ ] Đã xác nhận database/user hiện tại bằng truy vấn chỉ đọc hoặc công cụ tương đương.
- [ ] Spring profile, DataSource hoặc Liquibase CLI đang dùng cấu hình dự kiến.
- [ ] Đã xem trạng thái, xác thực changelog và review SQL dự kiến.
- [ ] Endpoint và secret không bị ghi vào log hoặc repository.
- [ ] Chỉ chạy update sau khi môi trường và thay đổi được xác nhận.

Cấu hình kết nối tốt giúp Liquibase thực thi migration đúng database, đúng schema và đúng quyền. Khi tách rõ JDBC URL, DBMS, schema ứng dụng, schema metadata và tài khoản migration, nhóm phát triển có thể tái sử dụng cùng changelog qua nhiều môi trường mà vẫn kiểm soát được nơi thay đổi được áp dụng.

