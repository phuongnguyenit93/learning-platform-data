# Lỗi kết nối, xác thực, JDBC và thiếu quyền

Liquibase có thể đọc changelog hoàn chỉnh nhưng vẫn không triển khai được vì không mở được kết nối database, không xác thực được tài khoản, không nạp được JDBC driver hoặc không có quyền trên schema cần thay đổi. Các lỗi này thường xuất hiện khi ứng dụng khởi động, khi chạy lệnh CLI, hoặc ngay sau khi Liquibase kết nối thành công và bắt đầu tạo bảng history hay thực thi changeset.

Điều quan trọng là xác định **lỗi xảy ra ở lớp nào**. Lỗi DNS/firewall cần xử lý mạng; lỗi đăng nhập cần kiểm tra credential và chính sách xác thực; lỗi JDBC cần kiểm tra driver và URL; lỗi permission cần kiểm tra quyền database, schema, object và bảng metadata Liquibase. Thay đổi quyền hoặc cấu hình sai lớp có thể che dấu nguyên nhân và làm tăng phạm vi truy cập không cần thiết.

Bài học thuộc chương **Xử lý sự cố** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này trình bày quy trình chẩn đoán theo lớp, các lỗi JDBC thường gặp, cách kiểm tra xác thực và quyền cho Liquibase, cùng cách xác minh sau khi sửa.

## 1. Nhìn lỗi theo từng lớp

Một lần chạy Liquibase có thể đi qua các lớp sau:

~~~text
Liquibase CLI / Spring Boot
          |
          v
  Cấu hình kết nối
  URL, user, secret, schema
          |
          v
  JDBC driver
  classpath, phiên bản, URL parser
          |
          v
  Mạng và TLS
  DNS, TCP, firewall, certificate
          |
          v
  Xác thực database
  password, account, host policy
          |
          v
  Quyền database và schema
  CONNECT, USAGE, CREATE, ALTER...
          |
          v
  Liquibase metadata
  DATABASECHANGELOG / DATABASECHANGELOGLOCK
          |
          v
  Thực thi changeset
  DDL, DML, sequence, view, routine...
~~~

Không phải mọi lỗi đều đi qua đúng thứ tự này. Ví dụ lỗi driver có thể xuất hiện trước khi mở socket; một kết nối đã mở có thể thất bại khi Liquibase đọc metadata; một changeset có thể chỉ thiếu quyền trên một object cụ thể.

### 1.1. Phân loại theo triệu chứng

| Triệu chứng hoặc thông báo | Lớp thường liên quan | Việc kiểm tra đầu tiên |
|---|---|---|
| **UnknownHostException** | DNS/hostname | Tên host, DNS resolver, network namespace. |
| **Connection refused** | TCP/listener | Host, port, database listener, firewall. |
| **Connection timed out** | Mạng hoặc endpoint | Route, security group, network policy, firewall, port. |
| **SSLHandshakeException** | TLS/certificate | CA, hostname, protocol và truststore. |
| **No suitable driver** | JDBC driver/URL | Driver có trên classpath và URL đúng định dạng không. |
| **ClassNotFoundException** với tên driver | JDBC classpath | Dependency và classloader. |
| **password authentication failed** | Xác thực | User, password, auth policy và database đích. |
| **Access denied / Login failed** | Xác thực hoặc quyền kết nối | Account, host được phép, database và login state. |
| **permission denied for schema** | Quyền schema | USAGE, CREATE, owner và role membership. |
| **must be owner of table** | Quyền sở hữu object | Object owner và role được phép thay đổi. |
| **CREATE command denied** | Quyền DDL | Grant cho database/schema và object cần tạo. |
| Không tạo/ghi được bảng Liquibase history | Metadata permission | Schema metadata, quyền tạo bảng và DML trên history/lock. |

Thông báo chỉ là manh mối. Hãy đọc cả exception chain, SQLState, vendor error code và log phía database nếu có.

## 2. Quy trình chẩn đoán ngắn gọn

Khi một môi trường báo Liquibase không kết nối hoặc không triển khai được, thực hiện theo thứ tự:

1. Xác định chính xác môi trường, host, port, database, schema và thời điểm lỗi.
2. Xác định Liquibase chạy từ CLI, Spring Boot startup hay pipeline; xác định DataSource thực tế được chọn.
3. Kiểm tra URL và driver trước khi kiểm tra password.
4. Kiểm tra DNS và TCP từ chính máy/container/pod chạy Liquibase.
5. Kiểm tra TLS và xác thực bằng cùng host, port, database, user và secret.
6. Nếu kết nối thành công, kiểm tra database hiện tại, user hiện tại, schema hiện tại và quyền.
7. Kiểm tra quyền tạo/đọc/ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK.
8. Xác định changeset cụ thể bị thiếu quyền; chỉ cấp quyền cần thiết cho object đó.
9. Chạy lại validate, status và SQL preview trước khi thực thi update.
10. Sau khi sửa, xác minh history, schema, quyền runtime và kết nối ứng dụng.

~~~mermaid
flowchart TD
    A[Liquibase báo lỗi] --> B{Driver và URL hợp lệ?}
    B -->|Không| C[Sửa dependency hoặc JDBC URL]
    B -->|Có| D{DNS/TCP/TLS thông suốt?}
    D -->|Không| E[Sửa DNS, mạng, listener hoặc certificate]
    D -->|Có| F{Đăng nhập thành công?}
    F -->|Không| G[Kiểm tra user, secret và auth policy]
    F -->|Có| H{Đúng database/schema?}
    H -->|Không| I[Sửa URL, profile hoặc default schema]
    H -->|Có| J{Đủ quyền metadata và changeset?}
    J -->|Không| K[Cấp quyền có giới hạn theo object]
    J -->|Có| L[Kiểm tra SQL, precondition và trạng thái schema]
    C --> M[Kiểm chứng lại từ cùng runtime]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

Không chuyển sang bước tiếp theo chỉ vì một lần thử bằng công cụ khác thành công. Hãy bảo đảm phép thử dùng cùng môi trường mạng, driver, credential và cấu hình như Liquibase thật.

## 3. Kiểm tra JDBC URL

JDBC URL xác định driver cần dùng và cách kết nối tới database. Sai một phần nhỏ như port, database name, service name hoặc tham số TLS cũng có thể khiến Liquibase không kết nối được.

### 3.1. Một số định dạng thường gặp

| DBMS | Dạng URL minh họa | Điểm cần xác minh |
|---|---|---|
| PostgreSQL | jdbc:postgresql://db.internal:5432/customer_db | Host, port, database và tham số SSL. |
| MySQL | jdbc:mysql://db.internal:3306/customer_db | Connector/J, database name và sslMode. |
| MariaDB | jdbc:mariadb://db.internal:3306/customer_db | Driver MariaDB và scheme jdbc:mariadb. |
| Oracle | jdbc:oracle:thin:@//db.internal:1521/customer_service | Service name, listener và cú pháp SID/service. |
| SQL Server | jdbc:sqlserver://db.internal:1433;databaseName=customer_db | Instance, database, encryption và trust certificate. |

Không dùng URL của một driver cho driver khác. Ví dụ jdbc:mysql: và jdbc:mariadb: có thể yêu cầu driver khác nhau dù cùng họ database.

### 3.2. Tách host, port, database và schema

Các khái niệm này không đồng nghĩa:

- **Host:** máy chủ hoặc endpoint database.
- **Port:** cổng TCP listener.
- **Database/catalog:** database mà kết nối mở vào.
- **Schema:** namespace chứa bảng, view và object.
- **Default schema:** schema mặc định theo user hoặc cấu hình kết nối.

Một kết nối có thể thành công vào đúng host nhưng sai database; hoặc vào đúng database nhưng Liquibase tạo object trong schema khác. Vì vậy, sau khi kết nối phải xác minh danh tính database và schema bằng truy vấn phù hợp DBMS.

### 3.3. Ví dụ tham số TLS

PostgreSQL có thể dùng chế độ xác minh certificate và hostname:

~~~text
jdbc:postgresql://db.internal:5432/customer_db?sslmode=verify-full&sslrootcert=/etc/db-certs/ca.pem
~~~

MySQL Connector/J có chế độ xác minh danh tính máy chủ:

~~~text
jdbc:mysql://db.internal:3306/customer_db?sslMode=VERIFY_IDENTITY
~~~

SQL Server có thể bật encryption và không tin cậy certificate tùy tiện:

~~~text
jdbc:sqlserver://db.internal:1433;databaseName=customer_db;encrypt=true;trustServerCertificate=false
~~~

Đây là ví dụ; cách chỉ định certificate/truststore phụ thuộc driver và phiên bản. Không tắt xác minh certificate như một cách sửa lâu dài. Nếu chỉ bật TLS mà không xác minh danh tính máy chủ, kết nối vẫn có thể không bảo vệ được trước endpoint giả mạo.

### 3.4. Không nhúng password vào URL

Tránh nối username/password trực tiếp vào JDBC URL. Các ký tự như @, :, /, ?, #, % có ý nghĩa trong URL và có thể cần encode; log hoặc exception cũng có thể vô tình ghi lộ URL.

Ưu tiên cấu hình riêng:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/customer_db
    username: customer_runtime
    password: <secret injected securely>
  liquibase:
    url: jdbc:postgresql://db.internal:5432/customer_db
    user: customer_migrator
    password: <migration secret injected securely>
~~~

Trong ví dụ, hai kết nối trỏ cùng database nhưng dùng hai tài khoản khác nhau. Secret phải được cấp từ secret manager hoặc môi trường triển khai; không ghi giá trị thật vào repository.

## 4. Kiểm tra JDBC driver và classpath

Liquibase cần JDBC driver tương thích với DBMS đích. Ứng dụng Spring Boot và Liquibase CLI có thể có classpath khác nhau: driver có trong ứng dụng chưa chắc đã có trong môi trường CLI, container migration hoặc pipeline.

### 4.1. Dấu hiệu driver thiếu hoặc không tương thích

- **ClassNotFoundException:** class driver được cấu hình không có trên classpath hoặc classloader không nhìn thấy.
- **No suitable driver:** không có driver đăng ký phù hợp với URL; URL sai hoặc driver không được nạp cũng có thể gây ra.
- **NoSuchMethodError / LinkageError:** có thể có xung đột phiên bản driver hoặc thư viện phụ thuộc.
- Kết nối thất bại sau khi nâng DBMS: driver cũ có thể không hỗ trợ giao thức, authentication hoặc TLS mới.

### 4.2. Tên driver thường dùng

| DBMS | Driver class thường gặp |
|---|---|
| PostgreSQL | org.postgresql.Driver |
| MySQL Connector/J | com.mysql.cj.jdbc.Driver |
| MariaDB | org.mariadb.jdbc.Driver |
| Oracle JDBC | oracle.jdbc.OracleDriver |
| Microsoft SQL Server | com.microsoft.sqlserver.jdbc.SQLServerDriver |

JDBC 4 thường tự đăng ký driver qua service provider nên không phải lúc nào cũng cần khai báo driver-class-name. Nếu khai báo thủ công, tên class phải khớp đúng driver đã cài.

### 4.3. Dependency phải nằm trong runtime classpath

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Ví dụ Gradle Kotlin DSL để tham khảo:

~~~kotlin
runtimeOnly("org.postgresql:postgresql")
~~~

Phiên bản có thể được quản lý bởi Spring Boot dependency management hoặc khóa rõ theo policy dự án. Với Liquibase CLI, cần cài driver vào classpath mà CLI sử dụng theo cách triển khai của phiên bản đó. Không giả định driver được đóng gói trong artifact ứng dụng sẽ tự xuất hiện trong CLI container.

### 4.4. Kiểm tra xung đột phiên bản

Khi có nhiều phiên bản cùng một driver hoặc nhiều thư viện JDBC trong classpath:

1. Xác định driver class được nạp.
2. Kiểm tra phiên bản artifact thực tế trong runtime image.
3. Đối chiếu DBMS server version và yêu cầu TLS/authentication.
4. Loại bỏ dependency trùng hoặc khóa phiên bản tương thích.
5. Chạy thử bằng đúng image/artifact sẽ triển khai.

Không nâng driver production một cách ngẫu nhiên chỉ để thử. Thay đổi driver có thể ảnh hưởng cách parse URL, kiểu dữ liệu, transaction, TLS và authentication.

## 5. Phân biệt lỗi DNS, TCP, timeout và TLS

Kết nối database không chỉ phụ thuộc cấu hình ứng dụng. Mạng từ container hoặc pod tới database có thể khác mạng trên máy developer.

### 5.1. DNS và hostname

Dấu hiệu:

- UnknownHostException.
- Tên host phân giải ra IP không đúng.
- Kết nối thành công trên laptop nhưng thất bại trong container.

Kiểm tra từ đúng môi trường chạy Liquibase:

~~~bash
nslookup db.internal
~~~

Trên Windows có thể dùng Resolve-DnsName db.internal; trong Linux có thể dùng getent hosts db.internal nếu có. Kiểm tra search domain, DNS resolver, private zone và cấu hình service discovery.

Không thay hostname bằng IP như một cách sửa lâu dài nếu TLS certificate xác minh theo hostname hoặc IP database thay đổi theo failover.

### 5.2. TCP và port

Dấu hiệu:

- Connection refused: thường endpoint không lắng nghe ở port đó hoặc có thiết bị mạng chủ động từ chối.
- Connection timed out: gói tin không tới được hoặc phản hồi không quay lại trong thời hạn.
- No route to host: route/network policy hoặc host không thể tiếp cận.

Kiểm tra port từ cùng máy/container:

~~~powershell
Test-NetConnection db.internal -Port 5432
~~~

~~~bash
nc -vz db.internal 5432
~~~

Chỉ dùng port phù hợp DBMS. Nếu TCP không thông, kiểm tra listener, firewall, security group, network ACL, Kubernetes NetworkPolicy, VPN, route và allowlist IP nguồn. Không thay đổi firewall diện rộng khi chưa xác định luồng nguồn/đích.

### 5.3. Timeout có nhiều loại

Không nhầm các timeout sau:

| Timeout | Ý nghĩa | Nơi cần kiểm tra |
|---|---|---|
| DNS timeout | Không phân giải được hostname kịp thời. | DNS resolver và network. |
| TCP connect timeout | Không thiết lập được socket. | Route, firewall, endpoint. |
| Login timeout | Không hoàn tất kết nối/xác thực trong thời gian cho phép. | DBMS load, network, authentication service. |
| Socket/read timeout | Đã kết nối nhưng chờ phản hồi quá lâu. | DBMS load, query, network, driver properties. |
| Pool connection timeout | Không lấy được connection từ pool trong thời gian chờ. | Pool size, connection leak, connection đang bận. |
| Liquibase lock wait timeout | Chờ lock Liquibase hoặc lock DBMS. | Migration khác, DBMS lock, thời gian changeset. |

Tăng mọi timeout lên giá trị lớn không sửa được nguyên nhân gốc. Trước tiên xác định đang chờ DNS, TCP, login, pool, Liquibase lock hay SQL.

### 5.4. TLS và certificate

Dấu hiệu:

- SSLHandshakeException.
- PKIX path building failed.
- Certificate expired, unknown CA hoặc hostname mismatch.
- Server yêu cầu TLS version/cipher mà client không hỗ trợ.

Kiểm tra:

- Certificate server còn hạn và đúng hostname.
- CA chain đã có trong truststore hoặc driver trust configuration.
- Clock hệ thống/container chính xác.
- JDBC driver hỗ trợ TLS version và cipher suite của server.
- Endpoint qua proxy/load balancer có certificate phù hợp.

Không tắt TLS hoặc bật chế độ trust mọi certificate để bỏ qua lỗi. Hãy cài CA đúng, cấu hình hostname và xác minh danh tính server.

## 6. Lỗi xác thực và tài khoản database

Khi TCP/TLS đã thành công nhưng database từ chối login, tập trung vào user, secret và chính sách xác thực.

### 6.1. Những nguyên nhân phổ biến

- Username/password sai hoặc secret của môi trường khác.
- Password đã hết hạn, tài khoản bị khóa hoặc bị disable.
- Tài khoản chỉ được phép kết nối từ một host/IP cụ thể.
- Database yêu cầu authentication method mà driver/client chưa hỗ trợ.
- Password chứa ký tự đặc biệt bị cắt hoặc encode sai khi truyền qua URL/config.
- Secret đã xoay vòng nhưng pod/container vẫn giữ giá trị cũ.
- Liquibase đang dùng DataSource hoặc credential khác với ứng dụng.
- Database/catalog/service name sai khiến xác thực vào endpoint khác.

Không giả định login thất bại là password sai. Cần xem vendor error code và log database để phân biệt account, host policy, auth method và database access.

### 6.2. PostgreSQL

Các lỗi thường gặp:

- password authentication failed for user: kiểm tra user, password, secret source và phương thức auth.
- no pg_hba.conf entry: host/database/user không khớp quy tắc truy cập trong pg_hba.conf.
- role does not exist: tên role sai hoặc kết nối tới cluster khác.
- database does not exist: database name sai hoặc chưa được tạo.

SQLState thường hữu ích:

| SQLState | Ý nghĩa thường gặp |
|---|---|
| 28P01 | Password không hợp lệ. |
| 28000 | Invalid authorization specification. |
| 08001 | Không thiết lập được kết nối SQL. |
| 42501 | Insufficient privilege. |

SQLState và thông báo cụ thể cần được đọc cùng server log; không suy ra mọi nguyên nhân chỉ từ một mã.

### 6.3. MySQL/MariaDB

Các thông báo có thể gồm:

- Error 1045: access denied khi đăng nhập; kiểm tra user, password, host part của account và authentication plugin.
- Error 1044: account không được phép truy cập database được chỉ định.
- Error 1130: host không được phép kết nối.
- Error 1142: command cụ thể bị từ chối do thiếu quyền.

Trong MySQL, account thường có dạng user và host, ví dụ liquibase_migrator tại host pattern 10.%. Grant cho account localhost không nhất thiết áp dụng cho kết nối từ pod hoặc server khác. Dùng SHOW GRANTS để kiểm tra đúng account được database chọn.

### 6.4. SQL Server và Oracle

Với SQL Server, phân biệt login ở cấp server với user trong database. Login thành công không bảo đảm user có quyền truy cập database mục tiêu. Kiểm tra default database, database user mapping, authentication mode và trạng thái login.

Với Oracle, kiểm tra service name/SID, trạng thái account, password expiry/lock, listener và quyền schema. User kết nối không nhất thiết là owner của schema chứa object; cần xác minh current schema và grants.

### 6.5. Kiểm tra secret mà không làm lộ secret

- Xác nhận secret reference đúng môi trường và đúng version.
- Kiểm tra thời điểm xoay vòng và thời điểm workload nhận secret.
- Không in password vào terminal, log hoặc ticket.
- Không truyền password dưới dạng command-line argument nếu có nguy cơ lộ qua process list/history.
- Dùng secret manager, mounted secret hoặc cơ chế bảo mật được nền tảng hỗ trợ.
- Nếu cần thử login thủ công, dùng client bảo mật và cùng host/network path với Liquibase.

## 7. Kiểm tra DataSource mà Liquibase thực sự sử dụng

Một ứng dụng có thể có DataSource runtime, DataSource read-only và DataSource migration. Kết nối thành công bằng JdbcTemplate không chứng minh Liquibase dùng cùng kết nối.

### 7.1. Spring Boot

Các property thường gặp:

| Property | Vai trò |
|---|---|
| spring.datasource.url | URL của DataSource ứng dụng. |
| spring.datasource.username | User của DataSource ứng dụng. |
| spring.liquibase.url | URL riêng của Liquibase nếu được cấu hình. |
| spring.liquibase.user | User riêng của Liquibase. |
| spring.liquibase.password | Secret riêng của Liquibase. |
| spring.liquibase.driver-class-name | Driver class riêng khi cần. |
| spring.liquibase.default-schema | Schema mặc định cho changeset theo cấu hình hỗ trợ. |
| spring.liquibase.liquibase-schema | Schema chứa metadata Liquibase theo cấu hình hỗ trợ. |

Nếu không cấu hình kết nối riêng, Liquibase thường dùng DataSource chính do Spring Boot cung cấp. Nếu có bean @LiquibaseDataSource, bean đó có thể được chọn cho Liquibase. Chi tiết ưu tiên phụ thuộc phiên bản Spring Boot và cấu hình bean.

Kiểm tra profile đang hoạt động, biến môi trường override và auto-configuration report. Không chỉ xem file YAML trong repository: cấu hình runtime có thể bị ghi đè bởi profile, environment variable, command line, secret mount hoặc deployment platform.

### 7.2. Liquibase CLI

CLI có thể lấy cấu hình từ command option, properties file, environment hoặc cơ chế triển khai. Kiểm tra:

- --url trỏ đúng DBMS/database.
- --username đúng migration account.
- Secret password được cấp an toàn.
- Driver có trong classpath CLI.
- Changelog file và schema option đúng.
- Liquibase version trong pipeline khớp version đã kiểm thử.

Ví dụ lệnh không đưa password vào command:

~~~bash
liquibase \
  --url="jdbc:postgresql://db.internal:5432/customer_db" \
  --username="customer_migrator" \
  --changelog-file="db/changelog/master.yaml" \
  status --verbose
~~~

Password được cấp qua secret/config bảo mật của pipeline theo cách hỗ trợ bởi phiên bản CLI đang dùng. Tránh bật debug hoặc in toàn bộ resolved configuration nếu có thể làm lộ thông tin xác thực.

### 7.3. Xác minh danh tính kết nối

Sau khi kết nối thành công, chạy truy vấn chỉ đọc phù hợp DBMS:

~~~sql
-- PostgreSQL
SELECT current_database(), current_user, current_schema();
~~~

~~~sql
-- MySQL / MariaDB
SELECT DATABASE(), CURRENT_USER(), USER();
~~~

~~~sql
-- SQL Server
SELECT DB_NAME(), SUSER_SNAME(), USER_NAME();
~~~

Kết quả giúp xác minh database, user và schema thực tế. Nếu Liquibase dùng kết nối riêng, cần chạy phép kiểm tra bằng chính Liquibase connection hoặc một client dùng đúng credential và endpoint.

## 8. Phân biệt quyền kết nối, quyền schema và quyền object

Đăng nhập thành công chỉ chứng minh database chấp nhận session. Liquibase còn phải đọc/ghi metadata và thực hiện changeset.

| Tầng quyền | Ví dụ | Lỗi có thể gặp |
|---|---|---|
| Instance/login | Login được phép vào DBMS. | Login failed, account locked. |
| Database | CONNECT hoặc quyền truy cập database. | Database access denied. |
| Schema | USAGE, CREATE, owner/schema privileges. | Permission denied for schema. |
| Object | ALTER table, CREATE index, DROP constraint, SELECT/UPDATE rows. | Must be owner, command denied. |
| Sequence/routine | Sequence usage, execute function, create/alter routine. | Permission denied for sequence/function. |
| Liquibase metadata | Tạo hoặc đọc/ghi history và lock table. | Cannot create/read/update DATABASECHANGELOG. |

Phân quyền phải theo các change type thực tế trong changelog. Một changeset tạo bảng có thể cần quyền schema; changeset tạo sequence, trigger, view, procedure hoặc index có thể cần quyền khác.

## 9. Quyền Liquibase metadata

Liquibase thường cần hai bảng quản lý:

- **DATABASECHANGELOG:** lưu changeset đã được xử lý, thời điểm, execution type và checksum.
- **DATABASECHANGELOGLOCK:** điều phối một tiến trình Liquibase cập nhật history tại một thời điểm.

Khi các bảng chưa tồn tại, Liquibase cần quyền tạo chúng trong schema metadata. Khi đã tồn tại, Liquibase cần quyền đọc và cập nhật history, đọc/ghi lock; quyền cụ thể còn phụ thuộc phiên bản và thao tác quản trị.

### 9.1. Lỗi thường gặp

- User có quyền tạo bảng nghiệp vụ nhưng không có quyền tạo bảng metadata ở schema riêng.
- DBA đã tạo metadata tables nhưng chưa cấp DML cho migration user.
- liquibase-schema trỏ tới schema khác với schema đã cấp quyền.
- Lock table có owner khác và migration user không được cập nhật.
- Default schema khác nhau giữa CLI và Spring Boot.
- Một pipeline dùng user khác hoặc schema metadata khác nên nhìn thấy history riêng.

### 9.2. Quy trình kiểm tra

1. Xác định schema thực tế chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK.
2. Kiểm tra hai bảng có tồn tại và migration user có đọc được không.
3. Kiểm tra migration user có thể cập nhật lock row không.
4. Nếu bảng chưa tồn tại, kiểm tra quyền tạo object trong metadata schema.
5. Nếu DBA quản lý trước metadata tables, xác nhận owner và DML grants phù hợp.
6. Kiểm tra các môi trường cùng dùng một schema metadata dự kiến.

Không xóa bảng history hoặc lock để sửa lỗi permission. Nếu lock đang được giữ, xác định tiến trình và session giữ lock trước khi xử lý theo runbook.

## 10. Quyền DDL và DML cho changeset

### 10.1. PostgreSQL

Một migration role thường cần:

- CONNECT vào database.
- USAGE trên schema để truy cập object.
- CREATE trên schema nếu tạo object mới.
- Quyền sở hữu hoặc quyền phù hợp để sửa object đã tồn tại.
- Quyền DML nếu changeset backfill/seed dữ liệu.
- Quyền trên sequence, routine hoặc object đặc thù nếu changeset sử dụng.
- Quyền đọc/ghi Liquibase metadata.

Ví dụ grant cơ bản cho schema do DBA quản lý:

~~~sql
GRANT CONNECT ON DATABASE customer_db TO customer_migrator;
GRANT USAGE, CREATE ON SCHEMA customer TO customer_migrator;
~~~

Đây chưa phải bộ quyền hoàn chỉnh cho mọi migration. PostgreSQL yêu cầu owner hoặc quyền membership phù hợp cho nhiều thao tác ALTER/DROP object hiện có; GRANT CREATE trên schema không tự cấp quyền sửa mọi bảng thuộc user khác. DBA cần thống nhất ownership/role membership và quyền theo object.

Nếu changeset dùng sequence, cần kiểm tra quyền sequence riêng. Nếu runtime role cần dùng sequence do migration tạo, phải có grants thích hợp; quyền trên table không tự động bao gồm mọi quyền sequence.

### 10.2. MySQL/MariaDB

Quyền được cấp theo account và database/object. Một migration có thể cần CREATE, ALTER, DROP, INDEX, REFERENCES, CREATE VIEW, TRIGGER, hoặc quyền routine tùy change type.

Ví dụ kiểm tra:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
SELECT CURRENT_USER(), DATABASE();
~~~

Không cấp toàn bộ quyền server nếu chỉ cần thay đổi một database. Grant theo database và host cụ thể; kiểm tra đúng account host mà server chọn khi login.

### 10.3. SQL Server và Oracle

SQL Server phân biệt login, database user, schema owner và role. Quyền tạo schema/object hoặc alter object cần được cấp ở đúng scope; membership db_owner là rộng và không nên là mặc định.

Oracle thường dùng schema gắn với user. Các quyền CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE PROCEDURE, quota tablespace và quyền trên object khác nhau. Role được cấp có thể không hoạt động như mong đợi trong một số ngữ cảnh PL/SQL hoặc dynamic SQL; cần kiểm tra quyền trực tiếp và quyền thực thi.

Các lệnh grant cụ thể phải được DBA xác nhận theo DBMS/version và policy bảo mật.

## 11. Xác định changeset nào cần quyền gì

Không cấp quyền DDL rộng trước khi biết câu lệnh nào thất bại. Đối chiếu changeset với SQL được Liquibase sinh ra:

| Change type | Quyền có thể cần |
|---|---|
| createTable | CREATE trên schema/database, quyền tạo object và metadata liên quan. |
| addColumn / modifyDataType | ALTER object; thường cần owner hoặc quyền tương ứng DBMS. |
| createIndex | Quyền tạo index trên table/schema; một số DBMS yêu cầu owner. |
| addForeignKeyConstraint | ALTER table và quyền tham chiếu phù hợp. |
| insert / update / delete | DML trên bảng và quyền đọc các bảng nguồn nếu có. |
| createView | CREATE VIEW và quyền đọc các bảng nguồn. |
| createSequence | Quyền tạo sequence; quyền sử dụng sequence cho runtime có thể riêng. |
| sql / stored procedure / trigger | Phụ thuộc câu lệnh native và quyền DBMS cụ thể. |

SQL preview là công cụ quan trọng để thấy Liquibase thực sự định chạy gì. Nếu changeset dùng SQL native, không suy luận quyền chỉ từ tên changeset.

## 12. Phân biệt quyền của Liquibase và quyền runtime

Khi dùng chung một DataSource, tài khoản có thể vừa thực thi DDL vừa phục vụ truy vấn ứng dụng. Cách này đơn giản nhưng tăng quyền của runtime. Với môi trường cần least privilege, có thể tách:

| Tài khoản | Quyền nên có |
|---|---|
| customer_runtime | SELECT/INSERT/UPDATE/DELETE trên object nghiệp vụ cần dùng; sequence/routine cần thiết. |
| customer_migrator | DDL trong schema sở hữu, DML chỉ khi changeset cần, quyền history/lock. |
| customer_reader | SELECT trên view/bảng được phép. |
| DBA/platform | Quản trị database, user, backup và cấu hình theo nhiệm vụ. |

Không để ứng dụng runtime giữ ALTER, DROP hoặc quyền owner rộng chỉ vì Liquibase startup đang dùng chung credential. Nếu migration chạy trong pipeline, runtime có thể khởi động sau migration bằng role hạn chế hơn.

### 12.1. Quyền cho object được tạo về sau

Một migration role tạo bảng mới không đồng nghĩa runtime role tự có quyền đọc/ghi bảng đó. Cần thiết kế grants/default privileges cho object mới, hoặc changeset cấp quyền phù hợp.

Ví dụ PostgreSQL có thể dùng default privileges theo owner/schema để cấp quyền cho object tạo về sau. Cú pháp và phạm vi phụ thuộc role tạo object; cần kiểm tra sequence và routine riêng. Không giả định grant trên các bảng hiện tại tự áp dụng cho bảng được tạo trong tương lai.

## 13. Chẩn đoán bằng log, SQLState và DBMS session

### 13.1. Bật log vừa đủ

Trong quá trình điều tra, có thể tăng log Liquibase lên info hoặc debug tạm thời theo phiên bản. Mục tiêu là xác định:

- Driver và URL được chọn (đã che thông tin nhạy cảm).
- Thời điểm mở connection và thời điểm thất bại.
- Database/schema/user nếu log có thể cung cấp an toàn.
- Changeset đang chạy và SQL liên quan.
- Exception gốc, SQLState và vendor code.

Không bật debug kéo dài trên production nếu log có thể chứa SQL nhạy cảm, URL hoặc thông tin xác thực. Không gửi log chưa che secret ra kênh công khai.

### 13.2. SQLState giúp khoanh vùng

| Nhóm SQLState | Ý nghĩa tổng quát |
|---|---|
| 08 | Connection exception. |
| 28 | Invalid authorization specification. |
| 42 | Syntax error hoặc access rule violation tùy mã cụ thể. |
| 40 | Transaction rollback. |

SQLState là chuẩn phân loại tổng quát; vendor code và server log thường cung cấp chi tiết hơn. Ví dụ một lỗi thuộc class 42 có thể là cú pháp sai hoặc quyền truy cập, cần đọc mã đầy đủ.

### 13.3. Kiểm tra session trên database

Nếu có quyền xem session, DBA có thể xác nhận:

- Session đến từ IP/host nào.
- User/login nào đang kết nối.
- Database và schema hiện tại.
- Session có đang chờ lock hoặc bị giới hạn connection không.
- Server log ghi nhận lý do từ chối login/statement nào.

Thông tin session giúp phân biệt Liquibase chưa tới được DBMS với trường hợp đã kết nối nhưng bị từ chối ở tầng SQL.

## 14. Các tình huống thực tế và cách xử lý

### Tình huống A — No suitable driver

**Nguyên nhân có thể:** driver không nằm trong classpath CLI, URL sai scheme, dependency bị loại khỏi runtime image hoặc classloader không nạp service provider.

**Cách xử lý:**

1. Đọc URL và xác định DBMS/driver cần dùng.
2. Xác nhận artifact driver có trong đúng runtime image hoặc Liquibase CLI classpath.
3. Kiểm tra tên driver nếu cấu hình tường minh.
4. Kiểm tra phiên bản driver và dependency conflict.
5. Thử kết nối bằng đúng artifact/pipeline, không chỉ trên IDE.

### Tình huống B — Connection refused hoặc timeout

**Nguyên nhân có thể:** sai host/port, listener chưa chạy, firewall, network policy, route hoặc endpoint không sẵn sàng.

**Cách xử lý:**

1. Xác nhận hostname và port từ cấu hình runtime.
2. Kiểm tra DNS và TCP từ cùng container/pod/host.
3. Xác nhận database listener đang lắng nghe trên interface/port mong muốn.
4. Kiểm tra allowlist IP nguồn và rule mạng.
5. Nếu có proxy/load balancer, kiểm tra health và routing.

### Tình huống C — Login thành công bằng client nhưng Liquibase login thất bại

**Nguyên nhân có thể:** client dùng host khác, profile khác, credential khác, driver khác hoặc authentication plugin khác.

**Cách xử lý:**

1. So sánh URL, database, user và endpoint; che password.
2. Xác nhận Liquibase dùng DataSource nào.
3. Xác nhận secret version mà process thực tế nhận.
4. Kiểm tra driver/JDBC authentication support.
5. Đối chiếu DBMS server log và source host.

### Tình huống D — Login thành công nhưng không tạo được DATABASECHANGELOG

**Nguyên nhân có thể:** thiếu CREATE trên metadata schema, schema không tồn tại, sai liquibase-schema, hoặc user không có quyền tạo object.

**Cách xử lý:**

1. Xác minh schema metadata.
2. Kiểm tra quyền tạo bảng trong schema đó.
3. Nếu DBA tạo trước metadata tables, kiểm tra owner và DML grants.
4. Kiểm tra default schema và profile.
5. Chạy lại status sau khi quyền được cấp và xác minh metadata được ghi đúng nơi.

### Tình huống E — History được ghi nhưng changeset báo permission denied

**Nguyên nhân có thể:** migration role có quyền metadata nhưng thiếu quyền trên object nghiệp vụ, hoặc changeset cần quyền DDL/DML riêng.

**Cách xử lý:**

1. Xác định changeset và câu SQL thất bại.
2. Xác định object/schema bị từ chối.
3. Kiểm tra owner, grant và role membership.
4. Cấp đúng quyền cho đúng object và đúng account.
5. Kiểm tra schema có bị thay đổi một phần trước khi retry.

### Tình huống F — Migration thành công nhưng ứng dụng báo permission denied

**Nguyên nhân có thể:** runtime role không có quyền trên object mới hoặc sequence/view/routine vừa tạo.

**Cách xử lý:**

1. Kiểm tra runtime user thực tế.
2. Xác định object và thao tác bị từ chối.
3. Cấp quyền runtime cần thiết hoặc bổ sung grant/default privileges vào quy trình migration.
4. Kiểm tra lại cả thao tác SELECT và DML/sequence.
5. Không cấp DDL cho runtime để chữa lỗi DML.

## 15. Lỗi sau khi sửa kết nối hoặc quyền

Khi kết nối được khôi phục, không mặc định rằng có thể chạy update ngay. Một lần chạy trước có thể đã tạo một phần object hoặc commit DDL trước khi thất bại.

Trước khi retry:

- Kiểm tra changeset nào đã ghi trong DATABASECHANGELOG.
- Kiểm tra schema thật có object được tạo một phần không.
- Xác định DBMS có transactional DDL cho câu lệnh đó không.
- Kiểm tra trạng thái DATABASECHANGELOGLOCK.
- Chạy status --verbose và validate.
- Sinh SQL preview cho changeset pending.
- Nếu schema lệch history, lập kế hoạch remediation; không xóa hàng history hoặc dùng changelogSync tùy tiện.

Nếu một changeset đã chạy một số câu SQL nhưng chưa được ghi nhận, cần xác định trạng thái object và dữ liệu trước khi quyết định sửa tiến, rollback thủ công có kiểm chứng hoặc khôi phục. Không retry mù quáng.

## 16. Bài thực hành có kiểm chứng

**Bối cảnh:** một ứng dụng Spring Boot dùng PostgreSQL, Liquibase chạy bằng tài khoản customer_migrator, ứng dụng runtime dùng customer_runtime.

### Giai đoạn A — Kiểm tra driver và URL

1. Xác nhận PostgreSQL driver nằm trong runtime classpath của ứng dụng.
2. Xác minh URL, host, port và database.
3. Chạy kiểm tra DNS/TCP từ cùng runtime environment.
4. Xác minh TLS/certificate nếu database yêu cầu.
5. Ghi nhận SQLState/vendor code khi tạo kết nối thử.

### Giai đoạn B — Kiểm tra xác thực

1. Cấp secret migration qua secret manager hoặc cơ chế test an toàn.
2. Xác nhận account tồn tại, không bị khóa/hết hạn và được phép từ host nguồn.
3. Đăng nhập bằng đúng endpoint/user từ cùng môi trường.
4. Chạy truy vấn xác minh database/user/schema hiện tại.
5. Thử một secret sai trên database lab để nhận diện thông báo xác thực; không thử lặp trên production.

### Giai đoạn C — Kiểm tra quyền metadata và changeset

1. Tạo schema nghiệp vụ và schema metadata trong database lab.
2. Cấp quyền tối thiểu cho migration role.
3. Chạy Liquibase để tạo history/lock và áp dụng changeset tạo bảng, index, sequence hoặc view.
4. Cố tình thu hồi một quyền cần thiết trong lab, quan sát lỗi và xác định object bị từ chối.
5. Cấp lại quyền cụ thể, kiểm tra schema/history trước khi chạy lại.

### Giai đoạn D — Kiểm tra runtime role

1. Kết nối bằng customer_runtime.
2. Thử SELECT/INSERT/UPDATE trên object nghiệp vụ cần thiết.
3. Xác minh runtime không thể ALTER/DROP schema nếu policy yêu cầu.
4. Kiểm tra quyền trên sequence, view và object vừa tạo.
5. Ghi nhận kết quả và quyền còn thiếu nếu có.

**Tiêu chí đạt:** phân biệt được lỗi driver, mạng, TLS, xác thực và permission; chứng minh Liquibase dùng đúng URL/user; history được tạo trong schema dự kiến; migration role có quyền cần thiết; runtime role có quyền nghiệp vụ nhưng không giữ DDL rộng.

## 17. Checklist xử lý sự cố kết nối và quyền

- [ ] Xác định đúng môi trường và nơi Liquibase thực thi.
- [ ] Kiểm tra JDBC URL, host, port, database/service name và schema.
- [ ] Xác nhận driver đúng DBMS, có trong đúng classpath và tương thích.
- [ ] Kiểm tra DNS/TCP từ cùng container/pod/host.
- [ ] Xác minh TLS, CA, hostname và thời hạn certificate.
- [ ] Xác nhận profile và DataSource thực tế Liquibase đang dùng.
- [ ] Xác minh secret version, user, host policy và account state.
- [ ] Không ghi password hoặc URL chứa secret vào log.
- [ ] Kiểm tra database, schema, user thực tế sau khi login.
- [ ] Phân biệt quyền database, schema, object, sequence/routine và metadata.
- [ ] Xác nhận quyền tạo/đọc/ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- [ ] Xác định changeset/SQL cụ thể cần quyền gì.
- [ ] Không cấp superuser hoặc db_owner chỉ để vượt qua lỗi.
- [ ] Kiểm tra trạng thái schema/history/lock trước khi retry.
- [ ] Chạy validate, status và SQL preview trước update.
- [ ] Xác minh runtime role sau khi migration hoàn tất.

## 18. Câu hỏi tự kiểm tra

1. Vì sao Connection refused khác Connection timed out?
2. No suitable driver thường chỉ ra những khả năng nào?
3. Vì sao driver có trong Spring Boot application chưa chắc có trong Liquibase CLI?
4. JDBC URL của PostgreSQL và MySQL khác nhau ở điểm nào?
5. Vì sao không nên nhúng password trực tiếp vào JDBC URL?
6. UnknownHostException nên được điều tra ở lớp nào?
7. TLS handshake thất bại có thể do những nguyên nhân nào?
8. Trong PostgreSQL, pg_hba.conf ảnh hưởng xác thực ra sao?
9. Vì sao MySQL account cần xét cả user và host?
10. Login thành công có chứng minh migration user có quyền tạo bảng không?
11. Liquibase cần truy cập những bảng metadata nào và để làm gì?
12. USAGE/CREATE trên schema PostgreSQL khác quyền sở hữu table như thế nào?
13. Vì sao migration role có thể chạy DDL nhưng runtime role vẫn không đọc được bảng mới?
14. Khi changeset lỗi giữa chừng, vì sao không nên retry ngay?
15. Làm thế nào xác minh Liquibase và ứng dụng đang trỏ cùng database?

## Kết luận

Lỗi kết nối, xác thực, JDBC và thiếu quyền cần được xử lý theo đúng lớp: **URL/driver, DNS/TCP/TLS, account authentication, database/schema/object privileges và Liquibase metadata**. Khi đã kết nối, hãy xác minh database, user và schema thực tế; khi changeset thất bại, hãy xem SQL cụ thể và quyền cần thiết thay vì cấp quyền quản trị rộng. Trước khi retry, đối chiếu schema thật với DATABASECHANGELOG và lock để tránh chạy lại trên trạng thái dở dang. Quy trình chẩn đoán có bằng chứng và phân tách runtime/migration role giúp **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** triển khai đáng tin cậy hơn qua Spring Boot, CLI và CI/CD.
