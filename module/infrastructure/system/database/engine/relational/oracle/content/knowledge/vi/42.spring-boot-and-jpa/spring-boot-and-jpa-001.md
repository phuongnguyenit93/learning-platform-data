# Cấu hình DataSource Oracle trong Spring Boot theo từng môi trường

## 1. Vai trò của DataSource trong Spring Boot

Trong ứng dụng Spring Boot dùng JDBC hoặc Spring Data JPA, DataSource là điểm vào để ứng dụng lấy kết nối tới database. Spring Boot có thể tự cấu hình DataSource khi có JDBC/JPA starter và thông tin kết nối phù hợp trong application configuration.

Với Oracle Database, DataSource thường dùng Oracle JDBC Thin Driver để kết nối tới một database service. Ứng dụng không nên tạo Connection mới bằng DriverManager trong từng repository hoặc service method. Thay vào đó, Spring quản lý một DataSource dùng chung; connection pool cấp connection cho mỗi đơn vị công việc rồi trả lại pool khi hoàn tất.

Các thành phần chính:

- **Oracle JDBC driver:** giao tiếp Oracle Net với listener và database.
- **DataSource:** factory tạo JDBC Connection.
- **Connection pool:** quản lý physical connection, giới hạn session, kiểm tra connection và tái sử dụng.
- **Spring transaction manager:** liên kết connection với transaction của Spring.
- **JPA EntityManager/Hibernate:** dùng DataSource để thực thi SQL khi ứng dụng chọn JPA.
- **Profiles và externalized configuration:** chọn endpoint, pool settings và secret theo môi trường.

Spring Boot thường chọn HikariCP khi Hikari có trên classpath và không có DataSource bean/type khác được chỉ định. Các starter JDBC/JPA thường kéo HikariCP theo dependency mặc định. OracleDataSource là JDBC DataSource factory; bản thân nó không phải connection pool. Nếu cần UCP, phải cấu hình UCP như pool implementation riêng.

## 2. Thêm Oracle JDBC dependency

### 2.1. Maven

Ví dụ dùng Oracle JDBC 11 driver cho ứng dụng chạy JDK 11 trở lên:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc11</artifactId>
        <version>${oracle.jdbc.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đặt oracle.jdbc.version trong dependency management hoặc property của project theo phiên bản driver đã được xác nhận:

~~~xml
<properties>
    <oracle.jdbc.version>23.6.0.24.10</oracle.jdbc.version>
</properties>
~~~

Phiên bản trên chỉ là ví dụ minh họa; chọn bản JDBC tương thích với JDK, Oracle Database release, Spring Boot và chính sách patch của tổ chức. Không mặc định version mới nhất luôn phù hợp với mọi database.

Nếu chỉ dùng JdbcTemplate/JDBC, dùng spring-boot-starter-jdbc thay cho spring-boot-starter-data-jpa. Không cần kéo Hibernate nếu ứng dụng không dùng ORM.

### 2.2. Gradle

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
}
~~~

Khai báo oracleJdbcVersion trong version catalog hoặc Gradle property để quản lý tập trung. Không khai báo nhiều version ojdbc đồng thời qua các module.

### 2.3. Chọn đúng JDBC artifact

| Artifact | Trường hợp sử dụng |
| --- | --- |
| ojdbc11 | Driver cho Java 11+ |
| ojdbc8 | Driver cho Java 8 và các môi trường phù hợp |
| ucp | Oracle Universal Connection Pool |
| ons | Oracle Notification Service client khi dùng các tính năng cần ONS |
| oraclepki, osdt_core, osdt_cert | Một số cấu hình wallet/TLS/TDE theo driver và hướng dẫn Oracle |

Không thêm toàn bộ artifact vào mọi ứng dụng. UCP, ONS và security artifact chỉ thêm khi tính năng và phiên bản driver yêu cầu.

### 2.4. Kiểm tra driver runtime

Spring Boot thường tự nhận diện driver từ JDBC URL và driver JAR. Với Oracle JDBC Thin, driver class là:

~~~text
oracle.jdbc.OracleDriver
~~~

Có thể cấu hình spring.datasource.driver-class-name, nhưng thường không cần nếu driver có trên classpath và URL hợp lệ.

Nếu gặp lỗi không tìm thấy driver, kiểm tra runtime dependency tree và artifact có được đóng gói trong executable JAR/container image hay không. Không giải quyết bằng cách thêm JAR thủ công vào máy production mà không cập nhật build.

## 3. JDBC URL cho Oracle

### 3.1. Ưu tiên SERVICE_NAME

Dạng URL phổ biến:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Ví dụ:

~~~text
jdbc:oracle:thin:@//db-dev.example.com:1521/devapp.example.com
~~~

SERVICE_NAME là dịch vụ database mà ứng dụng yêu cầu. Đây là cách kết nối phù hợp với PDB, RAC và service có thể relocate giữa các instance.

### 3.2. TNS alias

Nếu môi trường đã quản lý connect descriptor trong tnsnames.ora:

~~~text
jdbc:oracle:thin:@APPDB
~~~

Ví dụ entry:

~~~text
APPDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-prod.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = appsvc.example.com)
    )
  )
~~~

JDBC process phải đọc được đúng thư mục Oracle Net. Có thể cấu hình TNS_ADMIN bằng môi trường hoặc connection property oracle.net.tns_admin. Không mặc định rằng container Spring Boot có thể đọc tnsnames.ora trên máy DBA.

### 3.3. SID syntax

URL legacy có thể dùng:

~~~text
jdbc:oracle:thin:@host:1521:ORCL
~~~

Đây là dạng SID. SID định danh instance; SERVICE_NAME định danh dịch vụ. Với RAC hoặc PDB, ưu tiên SERVICE_NAME để Oracle định tuyến tới instance phù hợp.

### 3.4. Không nhúng username/password vào URL

Không dùng:

~~~text
jdbc:oracle:thin:APP_USER/password@//dbhost:1521/appsvc
~~~

Credential có thể bị lộ trong log, exception, metrics, process diagnostics, file cấu hình hoặc thông tin triển khai. URL nên chỉ chứa endpoint/service; username/password lấy từ secret provider.

## 4. Cấu hình DataSource cơ bản

### 4.1. application.yml

Spring Boot có thể tự tạo DataSource từ các thuộc tính chuẩn:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//localhost:1521/XEPDB1
    username: APP_RUNTIME
    password: ${ORACLE_DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
~~~

ORACLE_DB_PASSWORD phải được cung cấp từ môi trường runtime hoặc secret store. Không ghi password thật vào file application.yml.

Với HikariCP, Spring Boot nhận biết pool trên classpath và cấu hình từ nhóm spring.datasource.hikari:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: app-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
~~~

Các giá trị trên chỉ minh họa. Chọn pool size và timeout theo tải, số instance ứng dụng, giới hạn session Oracle, thời gian request và timeout của load balancer/firewall.

### 4.2. Tối giản driver class

Nếu Oracle driver có trên runtime classpath, cấu hình tối thiểu có thể là:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
~~~

Spring Boot và JDBC driver có thể tự suy ra driver class từ URL. Khai báo rõ driver-class-name khi cần tránh ambiguity hoặc khi dùng DataSource type tùy chỉnh.

### 4.3. DataSourceProperties và Hikari

Spring Boot dùng DataSourceProperties để chuyển cấu hình chuẩn thành DataSource. Khi Hikari được chọn, property url được chuyển thành jdbcUrl theo API của Hikari.

Nếu tự tạo HikariDataSource bằng @ConfigurationProperties trực tiếp, cần nhớ Hikari dùng jdbcUrl chứ không dùng thuộc tính url. Cách phổ biến là bind DataSourceProperties rồi gọi initializeDataSourceBuilder(), để Spring thực hiện ánh xạ đúng.

## 5. Cấu hình theo từng môi trường bằng Profiles

Một ứng dụng thường chạy ở local/dev, test, staging và production. Mỗi môi trường có endpoint, account, pool size, TLS policy và secret khác nhau. Không nên đóng gói nhiều password vào một file rồi chọn bằng code.

### 5.1. Cấu trúc file

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

File application.yml chứa cấu hình dùng chung; file application-{profile}.yml chứa khác biệt theo môi trường. Spring Boot tự nạp file profile tương ứng khi profile được kích hoạt; không cần đặt spring.config.activate.on-profile bên trong file application-dev.yml hoặc application-prod.yml.

### 5.2. application.yml: cấu hình chung

~~~yaml
spring:
  application:
    name: orders-api

  datasource:
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: orders-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000

  jpa:
    open-in-view: false
    properties:
      hibernate:
        jdbc:
          time_zone: UTC

logging:
  level:
    com.zaxxer.hikari: INFO
~~~

Không đặt default production credential trong file chung. Mỗi profile/environment cung cấp URL và secret riêng.

### 5.3. application-dev.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//localhost:1521/XEPDB1
    username: ${ORACLE_DB_USERNAME:APP_DEV}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 1
      maximum-pool-size: 4

  jpa:
    hibernate:
      ddl-auto: update
    show-sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

DDL_AUTO update và show_sql chỉ phù hợp với môi trường phát triển có kiểm soát. Không mang cấu hình này sang production.

### 5.4. application-test.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//oracle-test.example.com:1521/testsvc
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 1
      maximum-pool-size: 3

  jpa:
    hibernate:
      ddl-auto: validate
~~~

Integration test cần một Oracle database/schema thật hoặc môi trường Oracle-compatible đã được tổ chức chấp thuận. Không mặc định H2 có thể mô phỏng đầy đủ Oracle SQL, sequence, PL/SQL, locking và datatype.

### 5.5. application-staging.yml

~~~yaml
spring:
  datasource:
    url: ${ORACLE_DB_URL}
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 2
      maximum-pool-size: 8

  jpa:
    hibernate:
      ddl-auto: validate
~~~

Staging nên mô phỏng production về database release, service routing, TLS, quyền runtime và pool policy càng sát càng tốt.

### 5.6. application-prod.yml

~~~yaml
spring:
  datasource:
    url: ${ORACLE_DB_URL}
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 5
      maximum-pool-size: 20
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000
      keepalive-time: 300000

  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false

logging:
  level:
    org.hibernate.SQL: WARN
    com.zaxxer.hikari: INFO
~~~

Các số liệu pool chỉ là điểm khởi đầu, không phải sizing recommendation cố định. Production nên quản lý schema bằng migration tool như Flyway/Liquibase hoặc quy trình DBA; Hibernate không nên tự tạo/thay đổi schema trong mỗi lần ứng dụng khởi động.

### 5.7. Kích hoạt profile

Có thể kích hoạt profile qua environment variable:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

Trong production:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Hoặc truyền argument khi chạy:

~~~text
java -jar orders-api.jar --spring.profiles.active=prod
~~~

Environment variable phù hợp với container/orchestrator. Không hardcode profile production trong source code vì cùng một artifact nên có thể được triển khai ở nhiều môi trường.

### 5.8. Thứ tự ưu tiên cấu hình

Spring Boot có nhiều nguồn externalized configuration. Các nguồn có độ ưu tiên cao hơn có thể override file application.yml, ví dụ:

- Command-line arguments.
- SPRING_APPLICATION_JSON.
- Java system properties.
- OS environment variables.
- Config data files.
- Default properties.

Chi tiết precedence phụ thuộc nguồn và cơ chế Config Data của phiên bản Spring Boot. Khi điều tra cấu hình sai, kiểm tra cả environment, command line, mounted config và profile đang active; không chỉ mở application.yml.

## 6. Inject secret theo môi trường

### 6.1. Environment variables

Spring Boot relaxed binding ánh xạ:

| Spring property | Environment variable |
| --- | --- |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.datasource.username | SPRING_DATASOURCE_USERNAME |
| spring.datasource.password | SPRING_DATASOURCE_PASSWORD |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.hikari.maximum-pool-size | SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE |

Ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:oracle:thin:@//db-prod.example.com:1521/ordersvc
SPRING_DATASOURCE_USERNAME=ORDERS_RUNTIME
SPRING_DATASOURCE_PASSWORD=<injected-secret>
~~~

Không ghi secret thực vào shell history, Dockerfile, compose file commit vào Git hoặc log pipeline.

### 6.2. Config tree cho secret mounted dưới dạng file

Spring Boot hỗ trợ config tree, phù hợp khi Kubernetes/secret manager mount từng key thành file.

Ví dụ cấu hình:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Thư mục có thể chứa:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
  spring.datasource.url
~~~

Tên file trở thành property key; nội dung file là giá trị. Nếu dùng config tree cho username/password, không đồng thời khai báo giá trị khác trong profile mà không hiểu precedence.

### 6.3. Secret manager

Trong cloud hoặc nền tảng enterprise, có thể dùng:

- HashiCorp Vault.
- AWS Secrets Manager.
- Azure Key Vault.
- Google Secret Manager.
- Secret store của Kubernetes/platform.
- Credential store của application server.

Spring Boot core không tự tích hợp mọi secret manager. Cần starter/provider phù hợp, identity/role được cấp quyền đọc secret và chính sách cache/rotation của provider.

### 6.4. Không log cấu hình chứa secret

Tránh:

~~~java
log.info("Datasource properties: {}", properties);
log.info("Database password: {}", password);
~~~

Không dump toàn bộ Environment hoặc DataSource bean nếu log có thể chứa password, token, wallet password hoặc URL nhạy cảm.

Chỉ log thông tin đã allowlist, ví dụ profile, service alias, pool name và database product version; không log secret.

### 6.5. Credential rotation

Một quy trình rotation nên gồm:

1. Tạo/đổi credential theo chính sách database.
2. Cập nhật secret store hoặc wallet.
3. Đảm bảo ứng dụng có thể đọc secret mới.
4. Refresh/restart/drain pool có kiểm soát để physical connection mới dùng credential mới.
5. Kiểm tra authentication và số connection mới.
6. Thu hồi credential cũ theo thời điểm đã thống nhất.
7. Theo dõi lỗi ORA-01017, ORA-28000 và login failures.

Thay password trong secret store không tự động thay credential đã được dùng để tạo physical connections đang nằm trong pool.

## 7. Pool configuration và sizing

### 7.1. HikariCP là mặc định phổ biến

HikariCP được Spring Boot ưu tiên khi có trên classpath. Cấu hình cơ bản:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      minimum-idle: 4
      maximum-pool-size: 20
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 300000
~~~

Ý nghĩa:

| Property | Ý nghĩa |
| --- | --- |
| pool-name | Tên pool dùng cho log/metrics |
| minimum-idle | Số connection nhàn rỗi tối thiểu |
| maximum-pool-size | Tổng connection tối đa trong pool |
| connection-timeout | Thời gian chờ mượn connection, milliseconds |
| validation-timeout | Thời gian chờ validation, milliseconds |
| idle-timeout | Thời gian connection nhàn rỗi trước khi có thể bị loại, milliseconds |
| max-lifetime | Tuổi tối đa physical connection, milliseconds |
| keepalive-time | Chu kỳ kiểm tra/giữ connection idle, milliseconds |
| leak-detection-threshold | Ngưỡng cảnh báo connection bị giữ quá lâu, milliseconds |

Hikari connectionTimeout không phải Oracle listener connect timeout. Nó là thời gian request chờ connection rảnh trong pool.

### 7.2. Tính tổng connection của toàn hệ thống

Giả sử:

- 4 pod ứng dụng.
- Mỗi pod maximumPoolSize = 20.
- 2 worker batch, mỗi worker có pool tối đa 5.

Tổng connection tiềm năng:

~~~text
4 × 20 + 2 × 5 = 90 connections
~~~

Database cần chịu được số connection này cùng DBA sessions, monitoring, scheduler, các ứng dụng khác và background processes. Với RAC, cần xem service distribution và giới hạn từng instance.

Không đặt maximumPoolSize thật lớn chỉ để tránh pool wait. Nếu database không xử lý được concurrency đó, queueing tại pool có thể bảo vệ database tốt hơn.

### 7.3. Timeout phải phối hợp

Một request có thể chịu nhiều timeout:

| Timeout | Đơn vị thường dùng | Ý nghĩa |
| --- | --- | --- |
| Hikari connectionTimeout | ms | Chờ mượn connection từ pool |
| Oracle Net CONNECT_TIMEOUT trong descriptor | giây | Thời gian kết nối tới endpoint |
| Oracle JDBC ReadTimeout | ms | Chờ dữ liệu đọc từ socket |
| JDBC Statement query timeout | giây | Thời gian thực thi statement theo JDBC |
| HTTP/load balancer timeout | Tùy nền tảng | Thời gian client/proxy chờ response |

Đơn vị và khả năng hỗ trợ của Oracle JDBC properties phụ thuộc driver/release. Kiểm tra tài liệu đúng phiên bản, không sao chép giá trị giữa các timeout khác đơn vị.

Ngân sách timeout nên có thứ tự hợp lý: pool wait không vượt SLA request; connect/read timeout không làm request treo vô hạn; timeout của upstream cần đủ lớn để service hoàn tất hoặc trả lỗi có kiểm soát.

### 7.4. maxLifetime và firewall/load balancer

Nếu firewall hoặc network appliance đóng connection idle sau một thời gian, maxLifetime/keepalive cần được đặt phù hợp với policy đó. Hikari nên retire connection trước khi hạ tầng tự đóng nó.

Không đặt maxLifetime giống nhau cho mọi môi trường nếu network policy khác nhau. Kiểm tra Hikari logs, Oracle listener logs và firewall idle timeout.

### 7.5. Validation

Hikari sử dụng JDBC4 Connection.isValid() khi driver hỗ trợ. Không cần cấu hình connectionTestQuery cho Oracle JDBC hiện đại nếu isValid hoạt động đúng.

Chỉ đặt connection-test-query khi driver/connection implementation yêu cầu hoặc đã xác nhận cần thiết:

~~~yaml
spring:
  datasource:
    hikari:
      connection-test-query: SELECT 1 FROM DUAL
~~~

Validation query tạo round trip và có thể tăng tải. Đo trước khi bật.

## 8. Oracle JDBC connection properties qua Hikari

Hikari cho phép truyền driver-specific properties:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        oracle.net.CONNECT_TIMEOUT: 10000
        oracle.net.OUTBOUND_CONNECT_TIMEOUT: 10000
        oracle.jdbc.ReadTimeout: 30000
~~~

Các giá trị minh họa cần xác minh đơn vị và behavior theo Oracle JDBC version. Có thể cấu hình timeout trong Oracle Net connect descriptor thay vì truyền property, ví dụ:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

Không đặt cùng một timeout ở nhiều tầng với giá trị mâu thuẫn. Khi điều tra connection chậm, tách thời gian chờ pool, DNS, TCP, listener, authentication và query execution.

### 8.1. TNS_ADMIN

Có thể đưa Oracle Net admin path qua driver property:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        oracle.net.tns_admin: /run/secrets/oracle-net
~~~

Path phải tồn tại trong container/pod và account chạy ứng dụng có quyền đọc. Nếu dùng tnsnames.ora, xác nhận alias có entry đúng và service được listener đăng ký.

## 9. TLS/TCPS và wallet theo môi trường

### 9.1. TCPS URL

Ví dụ connect descriptor:

~~~yaml
spring:
  datasource:
    url: >-
      jdbc:oracle:thin:@(DESCRIPTION=
      (ADDRESS=(PROTOCOL=TCPS)(HOST=db-prod.example.com)(PORT=2484))
      (CONNECT_DATA=(SERVICE_NAME=ordersvc.example.com))
      (SECURITY=(TLS_SERVER_DN_MATCH=TRUE)))
~~~

Port 2484 chỉ là ví dụ. Dùng listener TCPS port và certificate thực tế của môi trường.

### 9.2. Wallet/Oracle Net configuration

Wallet có thể cung cấp trust certificate cho TLS hoặc credential cho Secure External Password Store. Cần phân biệt:

- Truststore/PKI wallet xác minh certificate server.
- Client wallet chứa certificate/private key cho mutual TLS.
- Secure External Password Store chứa database username/password.

Các mục đích có thể dùng cùng hệ thống wallet tùy cách cấu hình, nhưng không đồng nghĩa một file wallet luôn có mọi credential/key cần thiết.

Ví dụ đưa Oracle Net admin directory qua environment:

~~~text
TNS_ADMIN=/run/secrets/oracle-net
~~~

Thư mục có thể chứa sqlnet.ora, tnsnames.ora và wallet file theo cấu hình. Không copy wallet vào image bất biến hoặc commit vào repository. Mount secret read-only và giới hạn quyền filesystem.

### 9.3. Server DN matching

TLS_SERVER_DN_MATCH giúp client xác nhận certificate thuộc đúng database endpoint. Không tắt DN matching hoặc certificate validation chỉ để vượt qua lỗi handshake.

Khi TLS lỗi, kiểm tra:

1. Listener đang phục vụ TCPS.
2. Certificate chain còn hiệu lực.
3. Hostname/DN khớp certificate.
4. Trust wallet đúng.
5. Đồng hồ máy client/server.
6. TLS protocol/cipher được hỗ trợ.
7. Wallet path và permission.

### 9.4. Secret wallet cho JDBC Thin

Oracle JDBC Thin có thể dùng Secure External Password Store. Khi cấu hình, driver lấy credential theo connect identifier từ wallet thay vì cần password trong application properties.

Với Spring Boot/Hikari, cấu hình wallet/Oracle Net property phải tương thích với cách Hikari tạo physical connection và driver version. Không đồng thời đặt username/password trực tiếp nếu muốn kiểm tra rõ việc lấy credential từ wallet. Thử trên đúng ojdbc JAR, wallet và container image trước khi triển khai.

## 10. Cấu hình JPA/Hibernate với Oracle

### 10.1. Dialect

Hibernate hiện đại có thể tự phát hiện Oracle dialect từ JDBC metadata. Thông thường không cần hardcode dialect nếu kết nối và metadata hoạt động.

Nếu cần cấu hình tường minh, chọn dialect phù hợp Hibernate version. Không sao chép Oracle12cDialect từ ví dụ Hibernate cũ sang Hibernate 6 mà không kiểm tra deprecation và dialect class.

### 10.2. DDL auto

Ví dụ production:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Các lựa chọn phổ biến:

| Giá trị | Hành vi |
| --- | --- |
| none | Hibernate không tự quản lý schema |
| validate | Kiểm tra mapping/schema tương thích |
| update | Cố gắng thay đổi schema theo mapping |
| create | Tạo schema mới khi khởi động |
| create-drop | Tạo schema khi start, drop khi shutdown |

Với production, thường dùng none hoặc validate và quản lý DDL qua Flyway/Liquibase/DBA migration. Không dùng create-drop trên database chứa dữ liệu nghiệp vụ.

### 10.3. Open Session in View

Với REST API, có thể tắt:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Điều này buộc application service xác định transaction/fetch boundary rõ ràng, tránh query bất ngờ khi serialize response.

### 10.4. Transaction management

Spring Boot tự cấu hình transaction manager tương ứng khi có JPA hoặc JDBC. Dùng @Transactional ở service layer để xác định transaction boundary.

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order create(Order order) {
        return repository.save(order);
    }
}
~~~

Không mở Connection thủ công ngoài Spring transaction rồi kỳ vọng JPA transaction tự tham gia nếu không dùng đúng DataSource/transaction manager.

## 11. Nhiều Oracle DataSource trong một ứng dụng

Một ứng dụng đôi khi cần kết nối hai database, ví dụ OLTP và reporting. Mỗi DataSource cần cấu hình riêng, transaction manager riêng và persistence unit riêng nếu dùng JPA.

### 11.1. Hai nhóm cấu hình

~~~yaml
app:
  datasource:
    orders:
      url: ${ORDERS_DB_URL}
      username: ${ORDERS_DB_USERNAME}
      password: ${ORDERS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 20
    reporting:
      url: ${REPORTING_DB_URL}
      username: ${REPORTING_DB_USERNAME}
      password: ${REPORTING_DB_PASSWORD}
      configuration:
        maximum-pool-size: 8
~~~

Với cấu hình custom, dùng DataSourceProperties để ánh xạ url sang jdbcUrl:

~~~java
@Configuration
public class DataSourceConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    public DataSourceProperties ordersProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    public HikariDataSource ordersDataSource(
            @Qualifier("ordersProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting")
    public DataSourceProperties reportingProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting.configuration")
    public HikariDataSource reportingDataSource(
            @Qualifier("reportingProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }
}
~~~

Ví dụ cần import HikariDataSource, DataSourceProperties, ConfigurationProperties, Bean, Configuration, Primary và Qualifier. Trong project thật, kiểm tra binding prefix và bean naming; mỗi DataSource phải được inject bằng qualifier phù hợp.

### 11.2. Transaction manager

Nếu dùng JDBC transaction:

~~~java
@Bean
@Primary
public PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Nếu dùng JPA, mỗi datasource thường cần EntityManagerFactory và JpaTransactionManager riêng. Chọn repository package, persistence unit và transaction manager tương ứng; không trộn transaction của hai database như thể chúng là một local transaction.

### 11.3. Không có atomic transaction tự động giữa hai database

Hai local transaction manager trên hai DataSource không tự tạo distributed transaction. Nếu cần atomic commit qua nhiều database/resource, phải thiết kế JTA/XA hoặc mô hình saga/outbox. Không gọi hai repository rồi giả định cả hai database commit hoặc rollback đồng thời.

## 12. UCP thay cho HikariCP khi có yêu cầu Oracle-specific

### 12.1. Khi nào cân nhắc UCP?

UCP có thể phù hợp khi ứng dụng cần tích hợp sâu với Oracle Database HA:

- Fast Connection Failover/FAN.
- Runtime connection load balancing.
- Application Continuity/TAC integration theo driver/service support.
- Oracle-specific pool metrics và connection labeling.
- Các tính năng HA của Oracle client stack.

Nếu HikariCP đáp ứng nhu cầu, không cần thêm UCP chỉ vì database là Oracle.

### 12.2. Dependency

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>

<dependency>
    <groupId>com.oracle.database.ha</groupId>
    <artifactId>ucp</artifactId>
    <version>${oracle.jdbc.version}</version>
</dependency>
~~~

Đảm bảo UCP và JDBC driver version tương thích; không trộn UCP mới với driver cũ nếu Oracle không hỗ trợ.

### 12.3. Cấu hình UCP bằng DataSource bean

Khi dùng UCP, có thể khai báo pool tường minh để Spring Boot sử dụng DataSource bean đó:

~~~java
@Configuration
public class OracleUcpConfiguration {

    @Bean
    @Primary
    public PoolDataSource dataSource(Environment environment)
            throws SQLException {

        String url = environment.getRequiredProperty("spring.datasource.url");
        String username = environment.getRequiredProperty("spring.datasource.username");
        String password = environment.getRequiredProperty("spring.datasource.password");

        PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(url);
        pool.setUser(username);
        pool.setPassword(password);
        pool.setConnectionPoolName("orders-ucp");
        pool.setInitialPoolSize(2);
        pool.setMinPoolSize(2);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(10);
        pool.setValidateConnectionOnBorrow(true);

        return pool;
    }
}
~~~

Ví dụ cần import PoolDataSource, PoolDataSourceFactory, Environment, Bean, Configuration, Primary và SQLException. Với secret rotation, không chỉ đọc password một lần lúc startup rồi kỳ vọng pool tự cập nhật; cần quy trình refresh/drain.

### 12.4. Không cấu hình đồng thời hai pool

Nếu Hikari và UCP cùng có trên classpath, Spring Boot thường ưu tiên Hikari theo auto-configuration. Khi chủ động dùng UCP, khai báo DataSource bean/type rõ ràng và kiểm tra startup log để chắc chắn chỉ có pool mong muốn.

Không bọc một UCP pool trong Hikari pool hoặc ngược lại nếu không có thiết kế đặc biệt; nested pools gây khó hiểu về connection lifecycle và sizing.

## 13. Migration schema và startup ordering

### 13.1. Flyway/Liquibase

Database schema migration nên chạy có kiểm soát trước khi application nhận traffic. Với nhiều môi trường:

- Mỗi profile trỏ tới đúng database.
- Migration credentials có thể khác runtime credentials.
- Runtime account không cần CREATE TABLE/ALTER TABLE nếu không thực hiện migration.
- Migration history phải được backup/audit.
- Không cho nhiều replica cùng chạy migration không kiểm soát nếu tool/config không hỗ trợ locking đúng cách.

### 13.2. Tách migration và runtime account

Ví dụ:

- APP_MIGRATOR: được cấp quyền DDL cần thiết trong deployment window.
- APP_RUNTIME: chỉ có quyền DML/EXECUTE cần thiết.

Không dùng một account DBA cho cả migration và runtime.

### 13.3. Readiness và liveness

Readiness check nên phản ánh khả năng instance phục vụ request, có thể kiểm tra DataSource connection theo timeout ngắn và có giới hạn. Liveness check không nên liên tục mở connection nặng tới database theo cách khiến database outage làm toàn bộ pod restart loop.

Phân biệt:

- Liveness: process có còn sống và có thể tự phục hồi không?
- Readiness: instance có sẵn sàng nhận traffic không?
- Startup probe: ứng dụng đã hoàn tất khởi động chưa?

Không biến mọi lỗi database tạm thời thành liveness failure; có thể gây restart storm trong outage.

## 14. Quan sát và chẩn đoán

### 14.1. Spring Boot Actuator

Nếu dùng Actuator, DataSource và Hikari metrics có thể được expose qua Micrometer. Bảo vệ endpoint metrics/health bằng network policy và authentication phù hợp.

Theo dõi:

- Active connections.
- Idle connections.
- Pending threads.
- Max pool size.
- Min idle.
- Connection acquisition time.
- Connection usage duration.
- Timeout/failure count.

### 14.2. Hikari logs

Log pool có thể giúp chẩn đoán:

- Pool initialization.
- Connection creation failures.
- Pool starvation.
- Connection leak warnings.
- Pool shutdown/refresh.

Không bật DEBUG quá rộng trong production lâu dài; log có thể tăng mạnh và để lộ endpoint/configuration.

### 14.3. Kiểm tra database session

DBA có thể kiểm tra session từ database:

~~~sql
SELECT username,
       service_name,
       machine,
       program,
       status,
       COUNT(*) AS session_count
FROM v$session
WHERE username = 'APP_RUNTIME'
GROUP BY username, service_name, machine, program, status
ORDER BY machine, status;
~~~

Đối chiếu số session với tổng pool size của mọi pod/worker. Cần quyền truy cập V$SESSION hoặc view phù hợp.

### 14.4. Xác nhận service/PDB

Sau khi mở connection:

~~~sql
SELECT USER AS database_user,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Query này hữu ích khi local/staging/prod có nhiều service hoặc PDB.

### 14.5. Không log JDBC URL chứa thông tin nhạy cảm

URL có thể chứa host nội bộ, service, wallet path hoặc connect descriptor. Không nhất thiết mọi URL đều là secret, nhưng cần đánh giá thông tin topology trước khi đưa vào public logs/traces.

## 15. Kiểm thử cấu hình theo môi trường

### 15.1. Kiểm tra startup

Xác nhận:

1. Profile đang active đúng.
2. Oracle JDBC driver được load.
3. DataSource được tạo đúng type.
4. Pool khởi tạo đúng min/max.
5. Secret provider trả credential hợp lệ.
6. Service name resolve được.
7. TLS/wallet được load nếu bật.

### 15.2. Integration test

Một integration test nên:

- Mở connection từ Spring-managed DataSource.
- Kiểm tra database user/service/PDB.
- Thực hiện transaction insert/update rồi rollback.
- Kiểm tra sequence/identity và datatype Oracle quan trọng.
- Kiểm tra migration/schema version.
- Kiểm tra quyền runtime account.

Không chỉ test DataSource bằng một SELECT 1 FROM DUAL rồi kết luận toàn bộ JPA mapping và transaction hoạt động.

### 15.3. Test pool behavior

Kiểm tra khi:

- Tăng concurrency.
- Database tạm thời không truy cập được.
- Listener/service restart trong môi trường test.
- Credential được rotate.
- Connection idle bị firewall đóng.
- Pool đạt maximumPoolSize.
- Query chạy lâu hơn read/statement timeout.

Quan sát pending threads, borrow timeout, stale connection, pool refill và recovery time.

### 15.4. Không dùng H2 làm bằng chứng tương thích Oracle

H2 hữu ích cho test logic đơn giản, nhưng không thay thế Oracle integration test khi ứng dụng dùng:

- PL/SQL package.
- Oracle sequences.
- MERGE, hierarchical query, analytic SQL đặc thù.
- Oracle DATE/TIMESTAMP/TIMESTAMP WITH TIME ZONE.
- CLOB/BLOB và LOB streaming.
- Locking/isolation semantics.
- Oracle-specific function/index/constraint.

## 16. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Failed to determine a suitable driver class | Thiếu ojdbc runtime dependency hoặc URL sai | Kiểm tra dependency tree, driver JAR và URL |
| ORA-01017 | Username/password sai hoặc secret stale | Kiểm tra secret provider, rotation và wallet alias |
| ORA-28000 | Account bị khóa | Kiểm tra account status và DBA policy |
| ORA-28001 | Password hết hạn | Rotate credential theo quy trình |
| ORA-12154 | Không resolve TNS alias | Kiểm tra TNS_ADMIN và tnsnames.ora |
| ORA-12514 | Listener không biết SERVICE_NAME | Kiểm tra service registration và URL |
| ORA-12541 | Không có listener tại host/port | Kiểm tra listener, DNS và firewall |
| ORA-29024 | TLS certificate validation thất bại | Kiểm tra trust chain, DN matching và wallet |
| Hikari pool initialization fails | Database unreachable, secret sai hoặc pool config lỗi | Xem root SQLException và connection properties |
| Connection is not available, request timed out | Pool hết connection hoặc connection bị giữ lâu | Kiểm tra active/pending, leak, max pool và query time |
| Too many sessions | Tổng pool size vượt giới hạn database | Tính tổng pod/worker và giới hạn service |
| Connection reset/broken pipe | Firewall/network đóng socket hoặc DB failover | Kiểm tra timeout, keepalive, FAN và stale connection handling |
| Wrong database/PDB | URL/service profile sai | Kiểm tra SYS_CONTEXT và SPRING_PROFILES_ACTIVE |
| Schema validation failed | Hibernate mapping và schema lệch nhau | Chạy migration đúng phiên bản, kiểm tra datatype/sequence |
| DDL unexpectedly changes production | ddl-auto update/create | Dùng validate/none và migration tool |
| Password đổi nhưng login mới vẫn lỗi | Pool/secret provider vẫn dùng credential cũ | Refresh secret cache và drain/recreate pool |
| Hikari property ignored | Sai prefix hoặc property name | Kiểm tra spring.datasource.hikari và configuration metadata |
| UCP không được chọn | Hikari vẫn có ưu tiên auto-config | Chọn DataSource type/bean rõ ràng và kiểm tra startup log |

## 17. Quy trình triển khai theo môi trường

~~~text
Build một artifact
       |
       v
Chọn deployment environment
       |
       +---- dev
       |       - local Oracle/PDB
       |       - secret dev
       |       - pool nhỏ
       |       - log SQL khi cần
       |
       +---- test/staging
       |       - service test/staging
       |       - secret riêng
       |       - schema validate
       |       - TLS và pool gần production
       |
       +---- prod
               - Oracle service production
               - secret manager/wallet
               - TLS/TCPS theo policy
               - pool sizing theo tổng tải
               - schema migration riêng
               - monitoring/alert
       |
       v
Validate configuration and readiness
       |
       v
Route traffic
~~~

Một artifact có thể chạy ở nhiều môi trường; profile và secret được inject lúc deploy. Không build một JAR riêng chỉ để thay password hoặc database host.

## 18. Checklist cấu hình DataSource Oracle

1. **Đúng driver chưa?** ojdbc version phù hợp JDK, database và Spring Boot.
2. **URL dùng SERVICE_NAME chưa?** Tránh gắn cứng SID/instance khi dùng RAC/PDB.
3. **Profile có chọn đúng không?** Kiểm tra SPRING_PROFILES_ACTIVE.
4. **URL/user/password có đến từ đúng nguồn không?** Xem precedence giữa config file, environment và config tree.
5. **Không có secret trong Git/log chưa?** Password phải lấy từ secret store.
6. **Driver class có cần khai báo không?** Chỉ đặt khi auto-detection không đủ.
7. **Pool implementation đúng chưa?** Hikari mặc định hoặc UCP theo nhu cầu.
8. **Pool size đã tính tổng pod/worker chưa?** So với database session/process limits.
9. **Timeout đã phối hợp chưa?** Pool wait, connect, read, statement và HTTP.
10. **Network/TNS config đúng chưa?** TNS_ADMIN, DNS, listener, service.
11. **TLS/DN matching có bật khi cần không?** Không bỏ certificate validation.
12. **Wallet/keystore được mount an toàn chưa?** Read-only, ACL và rotation.
13. **Credential rotation có kiểm thử không?** Đảm bảo pool được refresh.
14. **JPA DDL policy đúng chưa?** Production thường validate/none.
15. **Migration account tách runtime account chưa?** Least privilege.
16. **Transaction boundary đúng chưa?** Dùng Spring @Transactional và transaction manager phù hợp.
17. **Health check có gây restart storm không?** Tách readiness/liveness.
18. **Actuator/metrics có bảo vệ không?** Không public endpoint quản trị.
19. **Đã kiểm tra service/PDB bằng SQL chưa?** Xác nhận đúng target.
20. **Đã integration test trên Oracle chưa?** H2 không thay thế Oracle compatibility.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** DataSource trong Spring Boot có vai trò gì?

**Câu 2.** Vì sao OracleDataSource không đồng nghĩa connection pool?

**Câu 3.** Spring Boot thường chọn HikariCP khi nào?

**Câu 4.** Artifact ojdbc11 phù hợp với runtime Java nào?

**Câu 5.** SERVICE_NAME khác SID như thế nào?

**Câu 6.** Vì sao một artifact nên được cấu hình bằng profile/external config thay vì build riêng theo môi trường?

**Câu 7.** SPRING_DATASOURCE_URL ánh xạ tới property nào?

**Câu 8.** Config tree dùng để giải quyết bài toán gì?

**Câu 9.** Vì sao không commit password trong application-prod.yml?

**Câu 10.** Hikari connectionTimeout khác Oracle CONNECT_TIMEOUT như thế nào?

**Câu 11.** Vì sao maximumPoolSize phải tính trên tất cả pod và worker?

**Câu 12.** maxLifetime cần liên hệ với timeout nào của hạ tầng?

**Câu 13.** Khi nào nên cân nhắc Oracle UCP?

**Câu 14.** Vì sao không nên bọc UCP trong Hikari?

**Câu 15.** Vì sao production thường không dùng ddl-auto update?

**Câu 16.** Vì sao nhiều DataSource cần transaction manager riêng?

**Câu 17.** Hai local transaction manager có tự tạo distributed transaction không?

**Câu 18.** Wallet có thể dùng cho credential và TLS như thế nào?

**Câu 19.** Vì sao readiness và liveness cần tách biệt?

**Câu 20.** Vì sao cần integration test trên Oracle thật hoặc môi trường Oracle được hỗ trợ?

<details>
<summary>Gợi ý đáp án</summary>

1. Cung cấp JDBC Connection cho JDBC/JPA và transaction manager.
2. OracleDataSource tạo physical connection; pool quản lý reuse, sizing và lifecycle.
3. Khi HikariCP có trên classpath và không có DataSource bean/type khác được chỉ định.
4. Java 11 trở lên theo artifact naming/support matrix; vẫn phải kiểm tra driver version.
5. SID định danh instance; SERVICE_NAME định danh database service.
6. Cùng artifact được deploy nhiều môi trường, giảm drift và không đóng gói secret/endpoint vào binary.
7. spring.datasource.url.
8. Nạp property từ file mounted, phù hợp secret/config injection.
9. Có nguy cơ lộ qua Git, backup, review và artifact.
10. Hikari chờ connection rảnh trong pool; Oracle CONNECT_TIMEOUT giới hạn kết nối network tới endpoint.
11. Database chịu tổng connection của mọi replica/worker, không chỉ một pod.
12. Firewall/load balancer idle timeout và connection lifecycle của database.
13. Khi cần Oracle-specific HA, FAN, FCF, RLB hoặc AC/TAC integration.
14. Nested pool gây hai lớp quản lý connection, khó sizing và lifecycle.
15. Có thể thay đổi schema ngoài kế hoạch; production nên dùng migration có kiểm soát.
16. Mỗi DataSource có connection/transaction resource riêng.
17. Không. Cần JTA/XA hoặc saga/outbox tùy yêu cầu.
18. Credential store giữ username/password; PKI wallet giữ trust/certificate/private key.
19. Database outage không nên khiến process restart liên tục; readiness ngừng nhận traffic, liveness chỉ kiểm tra process.
20. H2 không mô phỏng đầy đủ Oracle SQL, PL/SQL, datatype, locking và driver behavior.

</details>

## 20. Tài liệu chính thức

1. [Spring Boot Reference — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource auto-configuration, JDBC, connection pools và SQL initialization.
2. [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profiles, property sources, environment variables và config tree.
3. [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): cấu hình theo profile.
4. [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/index.html): JDBC/JPA và transaction integration.
5. [Oracle JDBC Developer's Guide — Data Sources and URLs](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): OracleDataSource, URL, service name và connection properties.
6. [Oracle JDBC Developer's Guide — JDBC Client-Side Security Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/client-side-security.html): wallet, credential store và TLS.
7. [Oracle Universal Connection Pool Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/): UCP configuration, pooling và connection lifecycle.
8. [HikariCP Configuration](https://github.com/brettwooldridge/HikariCP): pool sizing, timeout và connection lifecycle properties.
9. [Oracle Database Security Guide — Secure External Password Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-secure-external-password-store-password-credentials.html): wallet và credential management.

**Nguyên tắc cần nhớ:** Spring Boot nên quản lý một DataSource dùng chung và một connection pool phù hợp. Dùng JDBC Thin với SERVICE_NAME, tách cấu hình chung khỏi profile theo môi trường và inject password từ secret manager, config tree hoặc wallet. HikariCP là lựa chọn mặc định phổ biến; chọn UCP khi có nhu cầu Oracle HA cụ thể. Pool sizing phải tính tổng mọi replica/worker, timeout phải phân biệt theo tầng, và production cần schema migration có kiểm soát, TLS khi yêu cầu, least privilege, credential rotation và integration test trên Oracle.
