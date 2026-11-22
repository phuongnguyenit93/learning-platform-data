# Bảo vệ mật khẩu, chuỗi kết nối và chứng thư

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Bảo mật**, Liquibase cần kết nối tới database để đọc lịch sử changeset, kiểm tra checksum và triển khai DDL/DML. Ứng dụng Spring Boot cũng cần kết nối để đọc và ghi dữ liệu. Những kết nối này có thể dùng tài khoản, quyền và chứng thư khác nhau. Nếu mật khẩu được ghi thẳng vào source code, chuỗi kết nối bị lộ trong log hoặc chứng thư TLS không được xác minh, kẻ tấn công có thể truy cập database hoặc can thiệp vào đường truyền.

Bài học tập trung vào **bảo vệ mật khẩu, chuỗi kết nối và chứng thư** trong quy trình Liquibase. Cần quản lý bí mật theo vòng đời: tạo, cấp phát, sử dụng, luân chuyển, thu hồi và kiểm toán. Chuỗi kết nối phải chỉ rõ đúng máy chủ, database, schema và chế độ mã hóa. Chứng thư phải được xác minh về chuỗi tin cậy, tên máy chủ, thời hạn và quyền sử dụng khóa riêng.

Mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bảo vệ thông tin kết nối và chứng thư là điều kiện để những quy trình đó hoạt động an toàn trên development, staging và production.

## 1. Những tài sản cần bảo vệ

Một kết nối database không chỉ có một mật khẩu. Cần nhận diện toàn bộ thông tin có thể giúp truy cập hoặc xác định hạ tầng:

| Tài sản | Ví dụ | Rủi ro khi bị lộ hoặc bị sửa |
|---|---|---|
| **Mật khẩu database** | Tài khoản ứng dụng, tài khoản migration | Truy cập trái phép, đọc hoặc sửa dữ liệu |
| **Tên người dùng** | app_runtime, liquibase_migrator | Hỗ trợ dò tìm tài khoản và phân tích quyền |
| **JDBC URL** | Host, port, database, schema và tham số TLS | Lộ topology nội bộ; URL chứa credential có thể làm lộ bí mật trực tiếp |
| **Chứng thư CA** | Root/intermediate CA | Nếu trust sai, client có thể tin nhầm máy chủ |
| **Chứng thư máy chủ** | Certificate của database endpoint | Giả mạo server hoặc kết nối tới endpoint không mong muốn |
| **Khóa riêng** | Private key cho client certificate hoặc TLS endpoint | Mạo danh client/server hoặc ký trái phép |
| **Truststore/keystore password** | Mật khẩu bảo vệ file PKCS12/JKS | Truy cập hoặc sử dụng khóa/chứng thư trái phép |
| **Token/secret của pipeline** | Secret lấy credential từ vault | Chiếm quyền chạy migration hoặc truy cập môi trường |
| **Backup và dump** | File backup chứa dữ liệu và metadata | Lộ dữ liệu, cấu trúc và có thể cả bí mật |
| **Log và báo cáo triển khai** | JDBC URL, command line, lỗi kết nối | Vô tình ghi credential hoặc chi tiết hạ tầng |

Không phải mọi thành phần trong JDBC URL đều là bí mật. Hostname, database name và schema thường là metadata cấu hình, nhưng vẫn có thể nhạy cảm trong môi trường nội bộ. **Mật khẩu, token và private key luôn phải được xử lý như bí mật**. Không nhúng chúng vào URL, changelog hoặc log.

## 2. Nguyên tắc quản lý secret

Một quy trình quản lý bí mật tốt cần có những nguyên tắc sau:

1. **Không hard-code**: không ghi password, token, private key hoặc nội dung bí mật trực tiếp vào source code, changelog hay file cấu hình được commit.
2. **Cấp đúng quyền**: mỗi tài khoản chỉ có quyền cần cho nhiệm vụ và schema tương ứng.
3. **Tách theo môi trường**: development, staging và production dùng secret riêng; không tái sử dụng password production ở máy cá nhân.
4. **Tách theo vai trò**: tài khoản chạy ứng dụng và tài khoản chạy migration có quyền khác nhau.
5. **Truyền secret khi chạy**: lấy từ secret manager, hệ thống quản lý credential hoặc cơ chế cấp phát được tổ chức phê duyệt.
6. **Không ghi secret vào log**: che dữ liệu nhạy cảm trong command, exception, telemetry và báo cáo.
7. **Luân chuyển có kế hoạch**: đổi credential và chứng thư trước khi hết hạn hoặc khi nghi ngờ bị lộ.
8. **Thu hồi kịp thời**: tài khoản, token và chứng thư không còn cần dùng phải bị vô hiệu hóa.
9. **Kiểm toán được**: biết workload nào đã lấy secret, dùng vào thời điểm nào và cho mục đích gì.
10. **Kiểm thử cấu hình an toàn**: xác minh TLS thực sự được bật và chứng thư được xác minh, không chỉ nhìn thấy tham số trong file.

Secret manager có thể là dịch vụ quản lý bí mật của cloud, Vault, hệ thống secrets của nền tảng container hoặc giải pháp nội bộ. Chọn công cụ theo hạ tầng của tổ chức; điểm quan trọng là quyền truy cập, audit, rotation và cách workload nhận secret phải được kiểm soát.

## 3. Không ghi mật khẩu trong repository

Một cấu hình không an toàn:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-prod.internal:5432/orders
    username: app_admin
    password: PlainTextPassword123
~~~

Nếu file được commit, mật khẩu có thể tồn tại lâu dài trong Git history, pull request, bản clone, cache CI và bản sao lưu repository. Xóa dòng password trong commit sau **không làm bí mật cũ an toàn trở lại**.

Cấu hình an toàn hơn tách secret khỏi file:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/appdb
    username: app_runtime
  liquibase:
    url: jdbc:postgresql://db-host:5432/appdb
    user: liquibase_migrator
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Spring Boot có thể nhận password từ biến môi trường như **SPRING_DATASOURCE_PASSWORD** và **SPRING_LIQUIBASE_PASSWORD**, hoặc từ secret manager/config provider được cấu hình. Các giá trị này được cấp cho process tại runtime, không commit vào YAML.

Tách secret khỏi file cấu hình không tự mã hóa mật khẩu. Nếu giá trị môi trường bị ghi vào log, dump process hoặc chia sẻ qua kênh không an toàn, secret vẫn có thể bị lộ.

### 3.1. Nếu bí mật đã từng được commit

Khi phát hiện password hoặc private key đã vào repository:

1. Xem bí mật đó là đã bị lộ, kể cả repository private.
2. Thu hồi hoặc đổi credential/chứng thư ngay theo quy trình ứng phó.
3. Kiểm tra log truy cập, audit database và hoạt động CI có liên quan.
4. Cập nhật secret manager và workload đang sử dụng.
5. Xóa bí mật khỏi source hiện tại; nếu cần làm sạch Git history, thực hiện theo quy trình quản trị repository.
6. Thông báo cho những người/nhóm có bản clone hoặc artifact chứa secret cũ để họ không tiếp tục dùng.
7. Ghi nhận sự cố và xác minh secret cũ đã không còn hiệu lực.

**Xóa file khỏi commit mới không thay thế rotation**. Mục tiêu trước hết là vô hiệu hóa bí mật đã lộ.

## 4. Bảo vệ JDBC URL và tham số kết nối

JDBC URL xác định driver, máy chủ, cổng, database và các tham số kết nối. Ví dụ PostgreSQL:

~~~text
jdbc:postgresql://db.internal.example:5432/orders
~~~

Thông tin đăng nhập nên được truyền qua cấu hình username/password riêng. Không viết dạng URL có chứa user/password hoặc query parameter bí mật. Tránh đưa token, password hay private key path có quyền truy cập rộng vào URL được log.

Các tham số quan trọng có thể bao gồm:

- **Host và port**: endpoint database dự kiến.
- **Database/catalog**: database ứng dụng cần kết nối.
- **Schema**: namespace mặc định cho đối tượng.
- **TLS mode**: có mã hóa và xác minh server certificate hay không.
- **Timeout**: thời gian chờ kết nối và socket.
- **Application name**: nhận diện workload trong audit/monitoring.
- **Connection properties**: các tùy chọn driver phù hợp với DBMS.

### 4.1. Xác minh đúng endpoint

Một JDBC URL hợp lệ về cú pháp vẫn có thể trỏ nhầm database. Cần kiểm tra hostname thuộc môi trường dự kiến; port và database name đúng; DNS không bị trỏ tới endpoint giả mạo; tài khoản được cấp quyền trên đúng database/schema; TLS xác minh hostname của endpoint; ứng dụng và Liquibase không vô tình dùng hai database khác nhau.

Nên log một định danh môi trường không nhạy cảm như tên dịch vụ, tên môi trường và database identifier đã được cho phép; không log password hoặc toàn bộ cấu hình kết nối chứa secret.

### 4.2. Không dùng cấu hình dev cho production

Profile hoặc biến môi trường phải phân biệt endpoint. Không để application-prod.yml kế thừa nhầm host local, user development hoặc TLS mode yếu. Trong pipeline, có thể kiểm tra host/domain allowlist và yêu cầu secret production chỉ được cấp cho job chạy ở môi trường production được bảo vệ.

## 5. Tách tài khoản ứng dụng và tài khoản Liquibase

Ứng dụng Spring Boot thường chỉ cần đọc/ghi dữ liệu nghiệp vụ. Liquibase cần thêm quyền DDL để tạo hoặc sửa bảng, cột, constraint, index và có thể quản lý bảng lịch sử. Nếu dùng chung một tài khoản toàn quyền, lỗi SQL injection trong ứng dụng hoặc rò rỉ credential runtime có thể cho phép kẻ tấn công sửa schema.

Một mô hình tối thiểu:

| Tài khoản | Nhiệm vụ | Quyền điển hình |
|---|---|---|
| **app_runtime** | Kết nối từ ứng dụng | SELECT/INSERT/UPDATE/DELETE trên đối tượng cần thiết; không cấp quyền DDL nếu không cần |
| **liquibase_migrator** | Chạy migration | Quyền tạo/sửa/xóa object trong schema được quản lý và quyền cần cho DATABASECHANGELOG/LOCK |
| **report_reader** | Báo cáo chỉ đọc | SELECT trên view/bảng được phê duyệt |
| **backup_operator** | Sao lưu/khôi phục | Quyền backup/restore theo công cụ, tách khỏi tài khoản ứng dụng |

Quyền cụ thể phụ thuộc DBMS và cách quản lý schema. Liquibase có thể cần quyền tạo bảng lịch sử, cập nhật DATABASECHANGELOG, quản lý lock và thực hiện changeset. Cấp quyền theo danh sách thao tác thực tế, không mặc định cần superuser/DBA toàn cục.

### 5.1. Cấu hình datasource riêng cho Liquibase trong Spring Boot

Spring Boot có thể dùng cấu hình riêng cho Liquibase:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/appdb
    username: app_runtime
  liquibase:
    url: jdbc:postgresql://db-host:5432/appdb
    user: liquibase_migrator
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Password của datasource ứng dụng và Liquibase được cấp riêng qua **SPRING_DATASOURCE_PASSWORD** và **SPRING_LIQUIBASE_PASSWORD**. Spring Boot có các thuộc tính Liquibase riêng như URL, user, password và change-log; cần xác nhận tên property và hành vi auto-configuration của phiên bản dự án.

Nếu cấu hình Java tạo datasource riêng, có thể dùng cơ chế đánh dấu datasource dành cho Liquibase như **@LiquibaseDataSource** khi phiên bản Spring Boot hỗ trợ. Điều quan trọng là xác minh Liquibase và JPA kết nối tới đúng database/schema dự kiến. Nếu Liquibase cập nhật database A còn Hibernate dùng database B, migration có thể thành công nhưng ứng dụng vẫn lỗi mapping.

### 5.2. Quyền đối với schema và bảng lịch sử

Tài khoản migration cần được cấp quyền phù hợp cho:

- Tạo và cập nhật DATABASECHANGELOG.
- Tạo và cập nhật DATABASECHANGELOGLOCK.
- Đọc metadata/schema để kiểm tra precondition hoặc snapshot khi cần.
- Thực hiện changeset được phê duyệt trong schema ứng dụng.
- Thực hiện rollback hoặc thao tác DDL theo quy trình release.

Không cấp quyền drop toàn bộ database nếu migration chỉ quản lý một schema. Nếu DBMS cho phép phân quyền theo schema, object hoặc role, hãy giới hạn phạm vi ở đó. Tài khoản runtime không nên được dùng để chạy migration chỉ vì cấu hình đơn giản hơn.

## 6. Truyền secret vào Liquibase CLI và CI/CD

Liquibase CLI cần thông tin kết nối để chạy validate, update-sql, update hoặc rollback. Tránh truyền password trực tiếp trong command line:

~~~bash
liquibase --url=jdbc:postgresql://db.internal:5432/appdb --username=liquibase_migrator --password=PlainTextSecret update
~~~

Cách này có thể làm bí mật xuất hiện trong shell history, process arguments, log hoặc hệ thống thu thập lệnh. Nên dùng secret injection của pipeline, biến môi trường được bảo vệ, hoặc defaults file nằm trong vùng chỉ workload được phép đọc.

Một ví dụ defaults file không chứa password:

~~~properties
url=jdbc:postgresql://db.internal:5432/appdb
username=liquibase_migrator
changeLogFile=db/changelog/db.changelog-master.yaml
~~~

Job CI cấp password qua secret store theo cơ chế môi trường mà phiên bản Liquibase hỗ trợ. Với Liquibase CLI, các biến cấu hình môi trường như **LIQUIBASE_COMMAND_URL**, **LIQUIBASE_COMMAND_USERNAME** và **LIQUIBASE_COMMAND_PASSWORD** có thể được dùng theo quy ước phiên bản. Hãy kiểm tra tài liệu/runtime thực tế trước khi chuẩn hóa tên biến. Không in giá trị biến ra log để debug.

Nếu defaults file bắt buộc chứa secret, file phải được tạo tạm ở nơi chỉ job đọc được, có quyền file hạn chế, không nằm trong workspace được publish và được xóa sau job. Không commit file thật vào repository hoặc đính kèm nó vào artifact.

### 6.1. CI secret và phạm vi cấp phát

Một pipeline an toàn nên:

- Chỉ cấp secret production cho workflow/release được bảo vệ.
- Giới hạn branch/tag được phép chạy job production.
- Dùng approval gate và environment protection nếu nền tảng hỗ trợ.
- Không cấp secret production cho pull request từ fork hoặc mã chưa tin cậy.
- Dùng identity workload/federation nếu hạ tầng hỗ trợ để giảm secret tĩnh.
- Không truyền secret vào build argument hoặc image layer.
- Che giá trị secret trong log và kiểm tra command output.
- Thu hồi token/credential của runner sau khi job hoặc vòng đời workload kết thúc.

Một build artifact nên chứa changelog và ứng dụng, không chứa mật khẩu hoặc private key. Cùng một artifact có thể được triển khai ở nhiều môi trường bằng cách inject cấu hình và secret riêng.

## 7. Bảo vệ mật khẩu ở hệ điều hành và môi trường chạy

Ngay cả khi secret không nằm trong Git, nó vẫn có thể bị lộ qua nơi lưu hoặc cách process nhận giá trị.

Cần kiểm soát:

- **Quyền file**: chỉ user/service account cần thiết được đọc file secret, truststore và keystore.
- **Quyền thư mục**: không để thư mục chứa secret có quyền đọc cho mọi người dùng.
- **Process environment**: biến môi trường có thể được đọc bởi tiến trình hoặc người có quyền quản trị phù hợp; không coi chúng là kho bí mật tuyệt đối.
- **Shell history**: không gõ password trực tiếp vào lệnh được lưu lịch sử.
- **Crash dump**: có thể chứa vùng nhớ ứng dụng và cấu hình; kiểm soát quyền truy cập, retention và chia sẻ.
- **Container image**: không COPY secret vào image hoặc ghi secret trong build layer.
- **Volume mount**: chỉ mount secret vào container cần dùng, ở chế độ read-only khi phù hợp.
- **Backup**: bảo vệ bản sao secret, truststore, keystore và file cấu hình có thông tin nhạy cảm.
- **Debug/actuator endpoint**: không để endpoint cấu hình hoặc environment hiển thị giá trị bí mật cho người dùng không được phép.

Với Kubernetes hoặc nền tảng container, dùng Secret/CSI driver/external secret integration hoặc giải pháp được tổ chức phê duyệt; cấu hình RBAC và encryption at rest của secret store. Base64 chỉ là encoding, **không phải mã hóa**.

## 8. TLS: mã hóa đường truyền và xác minh máy chủ

Mật khẩu được bảo vệ trong cấu hình vẫn có thể bị đánh cắp nếu gửi qua kết nối database không mã hóa hoặc kết nối tới server giả mạo. TLS bảo vệ dữ liệu trên đường truyền và cho phép client xác minh danh tính server khi cấu hình đúng.

~~~text
Spring Boot / Liquibase client
          |
          | 1. Gửi ClientHello và thương lượng TLS
          v
Database server
          |
          | 2. Gửi server certificate + certificate chain
          v
Client kiểm tra:
  - CA có được tin cậy?
  - Certificate còn hạn?
  - SAN/hostname có khớp endpoint?
  - Chain có hợp lệ theo trust policy?
          |
          v
Thiết lập khóa phiên và mã hóa dữ liệu
~~~

Chỉ bật mã hóa mà bỏ qua xác minh chứng thư có thể vẫn cho phép kết nối tới máy chủ giả mạo. Tùy chọn tin cậy server certificate mà không kiểm tra identity hoặc tắt hostname verification có thể mã hóa đường truyền nhưng không xác minh đúng danh tính endpoint.

Các nguyên tắc:

- Dùng TLS theo chính sách của DBMS và tổ chức.
- Xác minh certificate chain tới CA tin cậy.
- Xác minh hostname với SAN phù hợp.
- Kiểm tra thời hạn và chuỗi intermediate.
- Không tắt certificate validation để “sửa nhanh” lỗi kết nối.
- Giới hạn phiên bản/cipher suite theo chính sách nền tảng.
- Theo dõi ngày hết hạn và chuẩn bị rotation trước thời hạn.

## 9. Truststore, keystore và private key

Hai khái niệm thường gặp:

- **Truststore** chứa CA hoặc certificate mà client tin cậy để xác minh server.
- **Keystore** chứa certificate và private key của một bên, thường dùng khi client cần chứng minh danh tính bằng mutual TLS hoặc ứng dụng cung cấp TLS endpoint.

Trong Java, keystore/truststore có thể dùng định dạng PKCS12 hoặc JKS tùy runtime và hệ thống. PKCS12 là định dạng liên thông phổ biến, nhưng cần kiểm tra công cụ và driver tương thích.

Ví dụ cấu hình JVM tổng quát:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/db-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<provided-at-runtime>
~~~

Đây là ví dụ tham số JVM. Không đặt password thật trong script hoặc command line được lưu. Nếu driver hỗ trợ cấu hình truststore riêng theo connection, hãy dùng cơ chế tương ứng và xác nhận nó không bị ghi ra log.

**Private key phải được bảo vệ nghiêm ngặt hơn certificate công khai.** Certificate server/CA thường có thể được phân phối trong phạm vi tin cậy; private key không được commit, gửi qua chat hoặc đặt trong image. Quyền đọc private key chỉ cấp cho process cần sử dụng. Nếu key bị lộ, phải thu hồi/đổi certificate liên quan theo quy trình CA.

## 10. Xác minh TLS theo từng JDBC driver

Tên tham số TLS khác nhau giữa DBMS và JDBC driver. Không có một JDBC URL chung cho mọi hệ quản trị.

### 10.1. PostgreSQL JDBC

PostgreSQL JDBC hỗ trợ các chế độ SSL khác nhau. Trong production, cần cấu hình chế độ xác minh server phù hợp; **verify-full** yêu cầu kiểm tra cả certificate chain và hostname.

Ví dụ minh họa:

~~~text
jdbc:postgresql://db.example.internal:5432/appdb?sslmode=verify-full&sslrootcert=/run/secrets/root-ca.crt
~~~

Đường dẫn certificate phải tồn tại trong môi trường chạy và file phải có quyền đọc phù hợp. Hostname trong URL phải khớp SAN của certificate. Nếu URL dùng IP nhưng certificate chỉ có DNS SAN, xác minh hostname có thể thất bại; nên dùng endpoint DNS được cấp certificate đúng.

Các tùy chọn cụ thể và hỗ trợ certificate client phụ thuộc phiên bản pgJDBC. Kiểm tra tài liệu driver đang đóng gói.

### 10.2. MySQL Connector/J

MySQL Connector/J có thuộc tính **sslMode** với những chế độ khác nhau. Chế độ **VERIFY_IDENTITY** xác minh certificate và danh tính hostname của server; chỉ yêu cầu TLS mà không xác minh identity chưa đủ để chống giả mạo server.

Ví dụ dạng cấu hình khái niệm:

~~~text
jdbc:mysql://db.example.internal:3306/appdb?sslMode=VERIFY_IDENTITY
~~~

Cấu hình truststore/CA, client certificate và private key phụ thuộc Connector/J version và cách triển khai. Hãy xác nhận driver thật sự nạp CA mong muốn và không rơi về cấu hình không xác minh khi truststore thiếu.

### 10.3. Microsoft SQL Server JDBC

Microsoft JDBC Driver hỗ trợ các thuộc tính TLS như **encrypt** và **trustServerCertificate**. Trong môi trường production, nên bật mã hóa và để driver xác minh certificate theo trust chain/hostname, thay vì bật trustServerCertificate để bỏ qua xác minh.

Ví dụ minh họa:

~~~text
jdbc:sqlserver://db.example.internal:1433;databaseName=appdb;encrypt=true;trustServerCertificate=false
~~~

Certificate server cần được cấp bởi CA được client tin cậy và tên máy chủ phải phù hợp. Cấu hình truststore và các tùy chọn driver khác cần theo đúng phiên bản JDBC driver.

**Các ví dụ trên là theo từng driver, không thể thay thế lẫn nhau.** Trước khi phát hành, chạy kiểm thử kết nối từ đúng runtime image/host và xác minh handshake, hostname, CA, ngày hết hạn. Không chỉ kiểm tra bằng một công cụ client khác với driver mà ứng dụng sẽ sử dụng.

## 11. Mutual TLS và chứng thư client

Trong một số kiến trúc, database yêu cầu client certificate ngoài username/password. Đây là **mutual TLS (mTLS)**: server trình certificate để client xác minh, và client cũng trình certificate để server xác minh.

Luồng khái quát:

1. Client kết nối tới database endpoint.
2. Server gửi certificate và chain.
3. Client xác minh server.
4. Server yêu cầu client certificate nếu cấu hình mTLS.
5. Client trình certificate và chứng minh sở hữu private key tương ứng.
6. Server xác minh client certificate theo trust policy.
7. Hai bên thiết lập phiên TLS mã hóa.

mTLS không tự thay thế authorization ở database. Certificate xác định danh tính ở lớp kết nối; DBMS vẫn cần ánh xạ danh tính hoặc yêu cầu username/role và áp dụng quyền phù hợp.

Khi dùng mTLS:

- Cấp certificate riêng cho từng workload hoặc nhóm workload có cùng chính sách.
- Không chia sẻ một private key cho tất cả ứng dụng.
- Giới hạn SAN/subject và thời hạn theo chính sách.
- Bảo vệ private key trong keystore hoặc secret mount.
- Theo dõi CA chain và trạng thái thu hồi.
- Có quy trình cấp lại, đổi certificate và thu hồi.
- Kiểm tra driver hỗ trợ certificate format và handshake cần thiết.

## 12. Luân chuyển mật khẩu không gây gián đoạn

Password rotation là thay đổi có kế hoạch, không chỉ là đổi chuỗi trong secret store. Ứng dụng có connection pool; các kết nối hiện tại có thể vẫn dùng credential cũ cho đến khi bị đóng. Liquibase migration job có thể chạy vào thời điểm khác với ứng dụng.

Một quy trình luân chuyển an toàn khi DBMS hỗ trợ credential song song:

1. Tạo credential mới với quyền tương đương và phạm vi đúng.
2. Cập nhật secret store cho một workload thử nghiệm.
3. Mở kết nối mới và xác minh quyền đọc/ghi hoặc DDL theo vai trò.
4. Triển khai secret mới cho từng workload; khởi động lại hoặc refresh connection pool theo kế hoạch.
5. Xác nhận không còn kết nối mới dùng credential cũ.
6. Thu hồi credential cũ.
7. Theo dõi lỗi xác thực và audit log sau rotation.

Nếu DBMS chỉ cho phép một password trên một user, có thể tạo user/role thay thế, chuyển workload sang user mới rồi thu hồi user cũ. Phải đánh giá grant, ownership, default privileges và connection pool trước khi làm.

### 12.1. Rotation cho tài khoản Liquibase

Tài khoản migration thường chỉ hoạt động trong deployment job. Có thể cấp secret ngay trước job, chạy migration, rồi thu hồi token tạm hoặc để secret hết hạn theo chính sách. Với credential tĩnh, phải luân chuyển định kỳ và cập nhật pipeline trước khi chạy release.

Không đổi password giữa lúc một migration đang thực thi nếu điều đó có thể làm gián đoạn session hoặc retry. Nếu nghi ngờ credential bị lộ, ưu tiên containment/thu hồi theo quy trình sự cố; sau đó đánh giá migration đã chạy một phần và lịch sử DATABASECHANGELOG trước khi chạy lại.

## 13. Rotation và quản lý vòng đời chứng thư

Chứng thư có thời hạn và chuỗi tin cậy. Việc đổi server certificate hoặc CA cần phối hợp cả database server và client.

Một quy trình đổi CA thường có thể thực hiện theo hai giai đoạn:

~~~text
Giai đoạn 1:
  Client truststore tin CA cũ + CA mới
              |
              v
  Server vẫn dùng certificate do CA cũ cấp

Giai đoạn 2:
  Server chuyển sang certificate do CA mới cấp
              |
              v
  Client xác minh thành công bằng CA mới
              |
              v
  Gỡ CA cũ khỏi truststore sau khi mọi endpoint đã chuyển
~~~

Không xóa CA cũ khỏi truststore trước khi các endpoint còn dùng certificate cũ đã được chuyển, nếu không kết nối sẽ thất bại. Ngược lại, không giữ CA cũ vô thời hạn khi không còn cần tin cậy.

Checklist chứng thư:

- Subject Alternative Name có hostname mà client sử dụng.
- Certificate chain đầy đủ và được CA tin cậy ký.
- Not Before/Not After phù hợp thời gian hiện tại.
- Đồng hồ hệ thống được đồng bộ.
- Key usage/extended key usage đúng vai trò server/client.
- Private key khớp public key trong certificate.
- Driver/Java runtime hỗ trợ thuật toán và định dạng.
- Certificate cũ có quy trình thu hồi nếu bị lộ.
- Có cảnh báo trước ngày hết hạn.

Cần phân biệt lỗi hết hạn certificate với lỗi trust chain hoặc hostname mismatch. Không giải quyết tất cả bằng cách tắt xác minh certificate.

## 14. Không để secret xuất hiện trong log và telemetry

Thông tin kết nối có thể bị lộ qua:

- Log startup của Spring Boot.
- Exception do JDBC driver hoặc connection pool phát ra.
- Liquibase command log và SQL output.
- Debug log của datasource/driver.
- CI job output, shell trace và artifact.
- APM/tracing tags, metrics labels và support bundle.
- Actuator/configuration endpoint.
- Crash dump hoặc heap dump.

Nên áp dụng:

1. Không log object cấu hình datasource đầy đủ.
2. Không log command có password hoặc secret argument.
3. Redact trường password, token, private key và thông tin xác thực khỏi exception/report.
4. Chỉ bật JDBC/SSL debug trong thời gian điều tra có kiểm soát; kiểm tra nội dung trước khi chia sẻ.
5. Hạn chế người có quyền đọc log production.
6. Đặt retention và xóa an toàn theo chính sách.
7. Không đưa JDBC URL đầy đủ vào metric label nếu có thể chứa thông tin nhạy cảm.
8. Kiểm tra log trước khi đính kèm vào issue hoặc gửi nhà cung cấp.

Không phải mọi driver đều tự che password trong mọi log. Hãy thử trên runtime thực tế bằng một credential giả ở môi trường test và xác minh output không chứa giá trị nhạy cảm.

## 15. Changelog cũng là bề mặt bảo mật

Changelog là source code triển khai database. Không đưa secret vào SQL literal chứa password/token, comment hoặc description của changeset, loadData CSV có credential, file SQL được include, default value của cột nhạy cảm, test fixture có thông tin thật hoặc command/precondition message in ra credential.

Ví dụ không nên làm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "SEC-001-create-integration-user"
      author: "platform"
      changes:
        - sql:
            sql: |
              CREATE USER integration_user
              IDENTIFIED BY 'RealProductionPassword';
~~~

Nếu cần tạo database role/user qua migration, thiết kế theo khả năng của DBMS và quy trình quản lý identity/secret riêng. Không ghi password thực vào changelog bất biến trong Git. Có thể tạo role và grant quyền qua changeset, còn credential được provision bằng secret management hoặc hệ thống IAM/database authentication phù hợp.

**Checksum của Liquibase không phải mã hóa secret.** Nếu password nằm trong changeset, checksum chỉ là metadata kiểm tra thay đổi; không bảo vệ bí mật khỏi người đọc repository hoặc DATABASECHANGELOG/SQL log.

### 15.1. Không nhầm dữ liệu seed với secret

Dữ liệu tham chiếu như mã quốc gia hoặc trạng thái nghiệp vụ có thể được quản lý bằng changeset/loadData. Nhưng token API, mật khẩu mặc định, private key, recovery code và thông tin cá nhân thật không phải seed data. Dùng giá trị giả cho test; lấy bí mật runtime từ secret store.

## 16. Mã hóa dữ liệu lưu trữ và backup

TLS bảo vệ dữ liệu khi truyền. Nó không bảo vệ file database, snapshot hoặc backup bị sao chép trái phép. Cần đánh giá encryption at rest ở các lớp:

- Volume/disk database.
- Storage của backup và snapshot.
- File dump/export.
- File log chứa dữ liệu.
- File tạm hoặc cache.
- Truststore/keystore và secret bundle.
- Artifact CI có chứa dữ liệu kiểm thử.

Khóa mã hóa nên được quản lý tách khỏi dữ liệu được mã hóa, với quyền truy cập và rotation phù hợp. Nếu dùng KMS/HSM, workload chỉ nhận quyền sử dụng key cần thiết; không nhúng master encryption key vào source hoặc image.

Backup phải được kiểm thử khôi phục. Một bản backup mã hóa nhưng mất key hoặc quyền KMS có thể không phục hồi được. Ngược lại, key có quyền quá rộng có thể khiến người truy cập storage giải mã dữ liệu ngoài phạm vi.

Liquibase quản lý schema và migration, không thay thế chiến lược backup, encryption at rest, retention hoặc disaster recovery.

## 17. Network security và giới hạn kết nối database

Bảo mật kết nối còn phụ thuộc mạng:

- Chỉ cho phép workload cần thiết truy cập host/port database.
- Dùng private network hoặc private endpoint khi kiến trúc hỗ trợ.
- Firewall/security group chỉ mở từ subnet hoặc identity được phép.
- Không public database endpoint nếu không có nhu cầu được phê duyệt.
- Tách đường kết nối migration khỏi đường truy cập người dùng nếu phù hợp.
- Giới hạn số connection và timeout để giảm tác động của retry storm.
- Theo dõi nguồn kết nối bất thường và authentication failure.

TLS không thay thế network segmentation; network segmentation cũng không thay TLS. Hai lớp cùng giảm khả năng nghe lén, giả mạo và truy cập ngoài phạm vi.

## 18. Chẩn đoán lỗi mật khẩu, URL và chứng thư

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Authentication failed | Password sai, secret cũ, user bị khóa hoặc role thiếu | Kiểm tra secret version, user status và DB audit |
| Connection refused/timeout | Sai host/port, firewall, DNS hoặc DB chưa sẵn sàng | Xác minh endpoint và network route |
| Unknown host | DNS sai hoặc tên endpoint không được resolve | Kiểm tra DNS trong đúng runtime/container |
| Database/schema not found | JDBC URL hoặc default schema sai | Xác minh database, schema và quyền |
| PKIX path building failed | Client không tin CA chain hoặc thiếu intermediate | Kiểm tra truststore và certificate chain |
| Hostname verification failed | Hostname JDBC không khớp SAN certificate | Dùng endpoint đúng hoặc cấp certificate đúng SAN |
| Certificate expired/not yet valid | Hết hạn hoặc clock lệch | Kiểm tra thời gian, rotation và NTP |
| Keystore password incorrect | Sai password hoặc file keystore không đúng | Kiểm tra secret version, format và file mount |
| Client certificate rejected | Server không tin CA client hoặc certificate sai usage | Kiểm tra client chain, identity mapping và policy |
| Liquibase kết nối được, app không kết nối được | Hai datasource/credential/TLS config khác nhau | So sánh cấu hình không lộ secret và quyền từng role |
| App chạy được, migration thất bại | Tài khoản runtime không có DDL hoặc migration secret hết hạn | Dùng tài khoản migration riêng và kiểm tra grants |
| Lỗi chỉ xuất hiện trong container | Truststore/certificate path không được mount hoặc quyền file sai | Kiểm tra filesystem của container và driver runtime |

### 18.1. Trình tự điều tra an toàn

1. Xác định workload và môi trường đang lỗi.
2. Kiểm tra host, port, database và schema; không in password.
3. Xác nhận secret version và thời điểm rotation.
4. Kiểm tra tài khoản có đang hoạt động và đúng quyền.
5. Xác minh TLS mode, CA chain, SAN, thời hạn và truststore.
6. Kiểm tra quyền đọc certificate/keystore trong runtime.
7. Đọc log đã redact và DB audit.
8. Kiểm tra Liquibase DATABASECHANGELOG để xác định migration có chạy một phần hay không.
9. Khôi phục cấu hình đã biết là hợp lệ hoặc phát hành secret/certificate mới theo quy trình.
10. Sau khi kết nối lại, kiểm tra schema và ứng dụng trước khi tiếp tục release.

Không tắt TLS hoặc chuyển sang trust-all để phân loại lỗi trên production. Nếu cần so sánh, dùng môi trường thử nghiệm với certificate giả lập và cấu hình kiểm chứng.

## 19. Quy trình triển khai bảo mật theo môi trường

### Development

- Dùng database riêng hoặc container cục bộ.
- Dùng credential thử nghiệm không tái sử dụng production.
- Dùng CA/test certificate riêng nếu cần TLS.
- Không commit secret; dùng file local được ignore hoặc secret injection.
- Giữ dữ liệu test giả, không sao chép production nếu chưa được bảo vệ đúng chính sách.

### Staging

- Dùng secret và certificate riêng với production.
- Giữ TLS verification tương tự production.
- Kiểm thử rotation và quyền tài khoản.
- Chạy Liquibase bằng migration identity riêng.
- Kiểm tra log và audit để xác nhận không lộ secret.

### Production

- Lấy secret từ vault/secret manager hoặc workload identity.
- Giới hạn quyền theo role và schema.
- Dùng TLS với CA/hostname verification.
- Cấp secret chỉ cho workload/release được phê duyệt.
- Kiểm soát approval, audit, rotation và thu hồi.
- Không bật debug logging kéo dài.
- Xác minh backup, encryption at rest và quyền truy cập log.

Không dùng cùng password hoặc private key cho cả ba môi trường. Nếu staging bị xâm nhập, secret production không được tự động có mặt trong staging.

## 20. Checklist trước khi triển khai Liquibase an toàn

Trước một release:

- JDBC URL có trỏ đúng host, port, database và schema?
- URL có chứa username/password/token hoặc tham số bí mật không?
- Secret có được lưu ngoài repository và inject đúng lúc chạy?
- Không có password trong shell history, command arguments, log hoặc artifact?
- Secret production chỉ được cấp cho workflow/job được bảo vệ?
- Tài khoản ứng dụng và tài khoản Liquibase đã tách?
- Tài khoản migration có quyền vừa đủ trong schema cần quản lý?
- Tài khoản runtime không có DDL privilege nếu không cần?
- Liquibase và Hibernate có dùng đúng database đích?
- TLS có được bật và xác minh certificate chain?
- Hostname có khớp SAN của certificate?
- Truststore/keystore có đúng file, format, quyền đọc và secret password?
- Private key không nằm trong Git, image hoặc workspace được publish?
- Certificate còn hạn và có kế hoạch rotation?
- Có cảnh báo hết hạn và audit truy cập secret?
- CI/CD redact secret trong output và không cấp credential production cho mã chưa tin cậy?
- Changelog/SQL/seed data không chứa password, token hoặc dữ liệu thật nhạy cảm?
- Backup, dump, log và truststore được bảo vệ theo chính sách?
- Có quy trình rotation/thu hồi và kiểm tra kết nối sau rotation?
- Lỗi TLS được xử lý bằng sửa trust/hostname/certificate, không bằng tắt xác minh?

## 21. Bài thực hành: cấu hình Liquibase và Spring Boot với secret riêng

**Bối cảnh:** Một ứng dụng dùng PostgreSQL. Spring Boot đọc/ghi nghiệp vụ bằng tài khoản app_runtime; Liquibase chạy migration bằng tài khoản liquibase_migrator. Database yêu cầu TLS và certificate server được ký bởi CA nội bộ.

### Bước 1 — Tạo role database

DBA tạo hai role/user theo chính sách DBMS:

- **app_runtime**: quyền DML cần thiết trên bảng/view.
- **liquibase_migrator**: quyền tạo/sửa object trong schema ứng dụng và cập nhật bảng lịch sử Liquibase.

Không ghi password thật vào changelog. Credential được cấp qua secret manager.

### Bước 2 — Cấu hình kết nối

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/appdb?sslmode=verify-full&sslrootcert=/run/secrets/db-root-ca.crt
    username: app_runtime
  liquibase:
    url: jdbc:postgresql://db.example.internal:5432/appdb?sslmode=verify-full&sslrootcert=/run/secrets/db-root-ca.crt
    user: liquibase_migrator
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Password datasource ứng dụng và Liquibase được cấp riêng qua **SPRING_DATASOURCE_PASSWORD** và **SPRING_LIQUIBASE_PASSWORD**. Secret manager cấp giá trị cho process. CA certificate được mount read-only vào đúng đường dẫn; không đưa private key hoặc password vào image.

### Bước 3 — Kiểm tra TLS

- Dùng hostname khớp SAN trong certificate.
- Kiểm tra CA root/intermediate được tin cậy.
- Xác nhận certificate còn hạn.
- Kết nối từ đúng container/host chạy ứng dụng.
- Xác nhận driver không bỏ qua hostname verification.
- Không dùng sslmode=disable hoặc trust-all để sửa lỗi.

### Bước 4 — Chạy migration

- Pipeline lấy secret migration theo quyền được phê duyệt.
- Chạy Liquibase validate và SQL preview.
- Chạy update trên database thử nghiệm.
- Kiểm tra DATABASECHANGELOG và schema.
- Thu hồi hoặc kết thúc phiên credential theo chính sách.

### Bước 5 — Chạy ứng dụng

- Cấp secret app_runtime cho workload.
- Khởi tạo connection pool.
- Để Hibernate validate mapping.
- Chạy smoke test đọc/ghi dữ liệu.
- Kiểm tra database audit xác nhận user ứng dụng không thực hiện DDL ngoài ý định.

### Bước 6 — Thử rotation

- Tạo credential mới hoặc user thay thế.
- Cập nhật secret cho một instance test.
- Mở kết nối mới và xác minh.
- Rollout credential mới cho các instance còn lại.
- Xác nhận connection pool đã thay kết nối cũ.
- Thu hồi credential cũ và theo dõi lỗi xác thực.

### Bước 7 — Thử rotation certificate

- Đưa CA mới vào trust bundle trước khi server chuyển certificate.
- Cấp server certificate mới với SAN đúng.
- Chuyển endpoint và kiểm tra client.
- Sau khi mọi workload xác minh thành công, loại CA cũ theo kế hoạch.
- Ghi nhận thời gian, serial/fingerprint certificate và kết quả kiểm thử.

## 22. Ứng phó khi secret hoặc certificate bị lộ

Khi phát hiện secret bị lộ, ưu tiên vô hiệu hóa khả năng sử dụng nó và giới hạn tác động:

1. Xác định loại bí mật, môi trường, workload và phạm vi quyền.
2. Thu hồi token, đổi password hoặc revoke certificate theo quy trình.
3. Cấp secret/certificate thay thế qua kênh an toàn.
4. Cập nhật workload và xác minh kết nối.
5. Kiểm tra DB audit, CI logs, repository access và network logs.
6. Xác định có thay đổi schema/dữ liệu trái phép hay không.
7. Kiểm tra DATABASECHANGELOG và trạng thái database thực tế; không giả định log migration sạch chỉ vì credential đã đổi.
8. Xóa/rotate bản sao secret bị lộ trong secret store, file, artifact hoặc runner.
9. Làm sạch source/history theo chính sách và thông báo cho người có bản clone.
10. Ghi nhận sự cố, nguyên nhân và biện pháp ngăn tái diễn.

Nếu private key của server certificate bị lộ, cần revoke/thay certificate và đánh giá CA chain. Nếu private key client bị lộ, cần xác định những endpoint/role chấp nhận identity đó và thu hồi quyền tương ứng. Nếu password migration bị lộ, kiểm tra audit về DDL/DML bất thường, bởi tài khoản này có thể có quyền cao hơn tài khoản ứng dụng.

**Không chỉ xóa secret khỏi log hoặc Git rồi kết luận sự cố đã xử lý.** Secret cũ phải mất hiệu lực, workload phải dùng secret mới và phạm vi truy cập phải được xác minh.

**Kết luận:** Bảo vệ kết nối Liquibase và Spring Boot cần quản lý đồng thời **mật khẩu, JDBC URL, quyền database, TLS, truststore/keystore và private key**. Đưa secret ra khỏi source, cấp tài khoản riêng theo nguyên tắc quyền tối thiểu, xác minh certificate chain và hostname, luân chuyển credential/chứng thư có kiểm soát, đồng thời redact log và bảo vệ CI/CD. Liquibase tiếp tục quản lý schema bằng changeset và lịch sử; secret manager, DBMS, hệ thống CA và nền tảng vận hành chịu trách nhiệm bảo vệ danh tính và kênh kết nối. Khi các lớp này được kiểm chứng cùng nhau, migration mới có thể chạy đúng database mà không làm lộ thông tin truy cập.

