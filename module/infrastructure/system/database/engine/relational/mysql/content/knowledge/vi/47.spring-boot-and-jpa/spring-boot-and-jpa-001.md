# Cấu hình MySQL DataSource trong Spring Boot theo từng môi trường

## Mục tiêu

Spring Boot có thể tự tạo `DataSource` từ cấu hình `spring.datasource.*` và JDBC driver có trên classpath. Khi ứng dụng chạy ở máy phát triển, môi trường kiểm thử và production, mỗi nơi thường có endpoint, database, tài khoản, chứng thư TLS và giới hạn connection pool khác nhau. Nếu trộn các giá trị này vào mã nguồn hoặc dùng chung một cấu hình cho mọi môi trường, ứng dụng dễ kết nối nhầm database, lộ thông tin xác thực hoặc làm MySQL quá tải.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Bài này hướng dẫn cấu hình MySQL DataSource trong Spring Boot theo profile, biến môi trường và secret; thiết lập Connector/J, HikariCP và JPA; sau đó kiểm tra kết nối thực tế.

Sau bài học, bạn có thể:

- Giải thích cách Spring Boot tự cấu hình `DataSource` từ `spring.datasource.*`.
- Tách cấu hình dùng chung và cấu hình riêng cho `dev`, `test`, `prod` bằng profile.
- Ghi đè URL, username, password và pool settings bằng biến môi trường.
- Cấu hình MySQL Connector/J, TLS, timezone và HikariCP phù hợp.
- Chọn cách cấu hình JPA schema validation và kiểm tra kết nối trước khi triển khai.

## 1. DataSource trong Spring Boot

`DataSource` là abstraction JDBC dùng để cấp kết nối tới database. Thay vì tự mở socket hoặc gọi `DriverManager` trong từng repository, ứng dụng lấy connection từ `DataSource`. Trong ứng dụng Spring Boot thông thường, Spring Boot auto-configuration tạo `DataSource` nếu dependency JDBC/JPA và driver phù hợp có trên classpath, đồng thời ứng dụng chưa tự khai báo bean `DataSource` khác.

Với một MySQL database, cấu hình cơ bản gồm:

- JDBC URL: địa chỉ server, port và tên database.
- Username/password: account ứng dụng có quyền tối thiểu.
- JDBC driver: MySQL Connector/J.
- Connection pool: quản lý kết nối vật lý để tái sử dụng.

Spring Boot thường chọn HikariCP khi thư viện này có trên classpath. Các starter phổ biến như `spring-boot-starter-jdbc` và `spring-boot-starter-data-jpa` thường kéo theo pool phù hợp thông qua dependency management của Spring Boot. Nếu dự án dùng dependency riêng, hãy kiểm tra dependency tree thay vì thêm nhiều pool cùng lúc.

## 2. Thêm MySQL Connector/J

Với Maven, khai báo driver ở runtime:

```xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
```

Nếu dự án dùng Spring Boot parent hoặc Spring Boot dependency management, hãy để BOM quản lý phiên bản Connector/J tương thích. Chỉ pin phiên bản riêng khi có lý do tương thích hoặc chính sách nâng cấp rõ ràng.

Class driver hiện đại là `com.mysql.cj.jdbc.Driver`. Connector/J tự đăng ký qua JDBC service provider nên thường không cần khai báo `spring.datasource.driver-class-name`. Nếu dự án có classloader hoặc cấu hình đặc biệt, có thể khai báo tường minh:

```yaml
spring:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
```

Không dùng tên driver cũ `com.mysql.jdbc.Driver` trong dự án mới.

## 3. Cấu hình mặc định dùng chung

Đặt các thiết lập chung trong `src/main/resources/application.yml`. Ví dụ sau dùng biến môi trường để truyền thông tin kết nối, đồng thời cung cấp URL localhost chỉ dành cho môi trường phát triển:

```yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:mysql://localhost:3306/shop_dev}
    username: ${DB_USERNAME:shop_app}
    password: ${DB_PASSWORD:}
    hikari:
      pool-name: shop-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

Các con số HikariCP ở trên là ví dụ khởi đầu, không phải cấu hình tối ưu cho mọi tải. `connection-timeout` là thời gian tối đa chờ lấy connection từ pool; `max-lifetime` đặt tuổi thọ tối đa của connection vật lý; `idle-timeout` áp dụng cho connection idle khi pool có thể co lại. `max-lifetime` nên thấp hơn giới hạn tuổi thọ connection do proxy hoặc hạ tầng database áp đặt.

`minimum-idle` và `maximum-pool-size` quyết định quy mô pool. Nếu không cần duy trì số connection idle cố định, có thể chọn chính sách pool phù hợp với tải và hành vi scale của ứng dụng. Đặt `maximum-pool-size` lớn không tự làm truy vấn nhanh hơn.

`ddl-auto: validate` yêu cầu Hibernate kiểm tra schema khi khởi động mà không tự tạo hoặc sửa bảng. Production thường nên dùng Flyway hoặc Liquibase để quản lý migration có phiên bản, sau đó để Hibernate validate. Tránh `ddl-auto: update` như cơ chế triển khai schema production.

## 4. Tách cấu hình theo profile

Spring profile cho phép nạp cấu hình riêng theo môi trường. Một cách dễ quản lý là giữ các thuộc tính chung trong `application.yml`, rồi tạo:

- `application-dev.yml` cho máy phát triển.
- `application-test.yml` cho kiểm thử tích hợp.
- `application-prod.yml` cho production.

Ví dụ `application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop_dev?connectionTimeZone=UTC
    username: shop_dev
    password: dev-only-password
```

Ví dụ `application-test.yml` có thể trỏ tới database test riêng hoặc được ghi đè bởi Testcontainers trong lúc chạy test:

```yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:mysql://localhost:3306/shop_test}
    username: ${DB_USERNAME:shop_test}
    password: ${DB_PASSWORD:}
```

Ví dụ `application-prod.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
```

Trong production, placeholder không có giá trị mặc định sẽ làm ứng dụng báo lỗi cấu hình khi thiếu biến bắt buộc. Điều này giúp phát hiện thiếu secret hoặc endpoint ngay lúc khởi động thay vì vô tình kết nối tới database mặc định.

Kích hoạt profile bằng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Hoặc khi chạy JAR:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Không đặt `spring.profiles.active` bên trong file cấu hình dành riêng cho profile. Hãy chọn profile từ môi trường chạy, command line hoặc cấu hình triển khai để tránh vòng phụ thuộc khi Spring Boot nạp file.

## 5. Ghi đè cấu hình bằng biến môi trường

Spring Boot hỗ trợ relaxed binding: tên thuộc tính cấu hình có thể được biểu diễn bằng chữ hoa và dấu gạch dưới trong biến môi trường. Các biến thường dùng:

| Thuộc tính Spring | Biến môi trường |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `spring.datasource.hikari.maximum-pool-size` | `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` |
| `spring.datasource.hikari.connection-timeout` | `SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT` |

Ví dụ chạy trong container hoặc môi trường triển khai:

```bash
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL='jdbc:mysql://mysql-prod.internal:3306/shop?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC'
SPRING_DATASOURCE_USERNAME='shop_runtime'
SPRING_DATASOURCE_PASSWORD='injected-at-runtime'
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=20
```

Đây là cách minh họa truyền biến; giá trị password phải được inject bởi secret manager hoặc hệ thống quản lý secret của nền tảng, không ghi vào Dockerfile, file compose được commit, manifest công khai, log hay shell history dùng chung.

Không đặt endpoint production làm default trong `application.yml`. Nếu thiếu `DB_URL` hoặc secret ở môi trường production, ứng dụng nên dừng khởi động và báo lỗi cấu hình.

## 6. Cấu hình JDBC URL và Connector/J

JDBC URL MySQL có dạng:

```text
jdbc:mysql://host:port/database?property=value
```

Ví dụ production dùng TLS xác minh danh tính server và timezone UTC:

```text
jdbc:mysql://mysql-prod.internal:3306/shop?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC
```

`sslMode=VERIFY_IDENTITY` yêu cầu TLS và xác minh chứng thư server phù hợp với hostname. Hệ thống cần cài CA tin cậy và chứng thư có SAN phù hợp với hostname trong URL. Nếu môi trường dùng CA riêng, cấu hình trust store theo tài liệu Connector/J và cách triển khai Java tương ứng.

Không dùng `sslMode=DISABLED` trong production. `PREFERRED` có thể cho phép kết nối không mã hóa nếu server không hỗ trợ TLS; với môi trường cần bảo mật, chọn mode rõ ràng và kiểm thử xác minh chứng thư.

`connectionTimeZone=UTC` giúp Connector/J dùng timezone được chỉ định cho chuyển đổi thời gian. Cần thống nhất thêm timezone của MySQL session, kiểu `DATETIME`/`TIMESTAMP` và quy tắc lưu dữ liệu trong ứng dụng. Đừng xem việc đặt timezone trong URL là thay thế cho thiết kế dữ liệu thời gian.

Tránh thêm các tham số JDBC không hiểu rõ hoặc sao chép URL từ môi trường khác. Một số thuộc tính có thể thay đổi semantics, bảo mật, batching hoặc kiểu dữ liệu. Kiểm tra tài liệu Connector/J đúng phiên bản và xác minh bằng integration test.

## 7. Thiết kế connection pool HikariCP

HikariCP quản lý các kết nối vật lý và cấp logical connection cho code JDBC/JPA. Một số thiết lập quan trọng:

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `maximum-pool-size` | Tổng connection tối đa trong pool | Tính tổng trên mọi instance ứng dụng và các dịch vụ khác |
| `minimum-idle` | Số connection idle mục tiêu | Có thể duy trì sẵn connection để giảm độ trễ mở kết nối |
| `connection-timeout` | Thời gian chờ lấy connection từ pool | Hết hạn thường báo pool cạn hoặc database không đáp ứng |
| `validation-timeout` | Thời gian tối đa kiểm tra connection | Phải nhỏ hơn `connection-timeout` |
| `idle-timeout` | Thời gian connection idle có thể bị loại khi pool co lại | Có tác dụng khi pool cho phép idle thấp hơn maximum |
| `max-lifetime` | Tuổi thọ tối đa của connection vật lý | Đặt thấp hơn giới hạn phía MySQL/proxy/network |
| `leak-detection-threshold` | Ngưỡng log connection bị giữ quá lâu | Dùng chẩn đoán có kiểm soát; có thể gây cảnh báo giả khi tác vụ dài hợp lệ |

### Tính tổng connection

Pool size phải được tính trên toàn bộ hệ thống, không phải chỉ trên một JVM. Ví dụ, 4 replica ứng dụng với `maximum-pool-size=20` có thể mở tới 80 connection, chưa tính migration job, batch worker, monitoring, DBA và các service khác.

```text
Potential application connections
  = application replicas x maximumPoolSize per replica
```

Đảm bảo tổng connection tối đa vẫn nằm trong ngân sách của `max_connections` và để lại headroom cho quản trị, failover và tải đột biến. Pool quá lớn có thể tăng context switching, lock contention và tải database mà không tăng throughput.

### Kiểm tra connection timeout

Nếu request thường xuyên chờ `getConnection()`, hãy kiểm tra số connection active/idle, thời gian giữ connection, truy vấn chậm và lỗi database. Tăng `connection-timeout` chỉ làm request chờ lâu hơn; nó không giải quyết pool bị rò rỉ hoặc database quá tải.

Không giữ connection trong lúc gọi HTTP service, xử lý file hoặc thực hiện công việc CPU dài. Mở connection sát thời điểm cần truy vấn và trả về pool ngay sau khi hoàn tất.

## 8. Account MySQL dành riêng cho ứng dụng

Không cấu hình ứng dụng dùng `root` hoặc account DBA. Tạo account riêng cho runtime, giới hạn host nguồn và cấp quyền theo thao tác ứng dụng thực sự cần:

```sql
CREATE USER 'shop_runtime'@'10.20.30.40'
  IDENTIFIED BY '<secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON shop.*
  TO 'shop_runtime'@'10.20.30.40';
```

Địa chỉ host trong ví dụ phải thay bằng host hoặc network thực tế của ứng dụng. Nếu ứng dụng chỉ đọc, chỉ cấp `SELECT`; nếu cần gọi stored procedure, cấp `EXECUTE` đúng routine. Quyền DDL như `CREATE`, `ALTER` và `DROP` nên thuộc account migration riêng, không thuộc runtime account.

Lưu username/password qua secret manager, Kubernetes Secret, cloud secret service hoặc cơ chế được tổ chức phê duyệt. Xoay vòng secret cần có quy trình cập nhật cấu hình và connection pool; thay password ở MySQL trong khi pool vẫn giữ connection cũ không tự động cập nhật credential cho connection mới.

## 9. Cấu hình JPA và Hibernate

Nếu ứng dụng dùng `spring-boot-starter-data-jpa`, Spring Boot thường tự cấu hình `EntityManagerFactory` và transaction manager dựa trên `DataSource`. Với một database MySQL, không cần khai báo dialect thủ công trong trường hợp thông thường; Hibernate có thể nhận diện dialect từ JDBC metadata.

Cấu hình thường dùng:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

`open-in-view: false` đóng persistence context theo ranh giới service/transaction thay vì giữ nó mở xuyên suốt quá trình render web response. Ứng dụng cần tải dữ liệu cần thiết trong transaction hoặc dùng DTO/fetch plan rõ ràng để tránh lazy-loading ngoài transaction.

`ddl-auto: validate` kiểm tra mapping entity với schema hiện có. Dùng migration tool như Flyway hoặc Liquibase để tạo và thay đổi schema theo phiên bản. Trong môi trường phát triển có thể dùng chế độ tạo schema cho database dùng một lần, nhưng không mang cấu hình đó sang production.

Đặt `hibernate.jdbc.time_zone=UTC` giúp Hibernate chuẩn hóa cách bind/extract các giá trị thời gian hỗ trợ theo cấu hình này. Vẫn cần chọn kiểu SQL phù hợp và quy tắc timezone nhất quán ở domain model.

## 10. Kiểm tra DataSource khi ứng dụng khởi động

Trước khi mở traffic, xác minh ứng dụng kết nối được và dùng đúng database. Có thể kiểm tra bằng JDBC trong integration test hoặc một health indicator.

Ví dụ truy vấn kiểm tra:

```sql
SELECT DATABASE() AS current_database,
       CURRENT_USER() AS authenticated_account,
       @@hostname AS mysql_host,
       @@time_zone AS session_time_zone;
```

Trong Spring Boot Actuator, health endpoint có thể cung cấp trạng thái database khi health indicator phù hợp được bật. Không công khai chi tiết endpoint health hoặc thông tin nội bộ cho người dùng không được phép; giới hạn quyền truy cập management endpoint.

Với test tích hợp, ưu tiên MySQL thật trong Testcontainers thay vì chỉ dùng H2 nếu cần kiểm tra đặc tính MySQL như collation, JSON, locking, SQL mode, generated column hoặc Connector/J.

Ví dụ dùng `@DynamicPropertySource` để đưa URL container vào Spring context:

```java
@DynamicPropertySource
static void mysqlProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", mysql::getJdbcUrl);
    registry.add("spring.datasource.username", mysql::getUsername);
    registry.add("spring.datasource.password", mysql::getPassword);
}
```

Ví dụ giả định test đã khai báo và khởi động MySQL Testcontainer tên `mysql`. Cần thêm dependency Testcontainers MySQL tương thích với phiên bản dự án.

## 11. Nhiều DataSource trong một ứng dụng

Phần lớn ứng dụng chỉ cần một MySQL `DataSource`. Nếu ứng dụng có nhiều database, mỗi `DataSource` cần cấu hình và vòng đời riêng. Khi tự khai báo bean `DataSource`, Spring Boot có thể không còn áp dụng auto-configuration mặc định như trước; bạn phải cấu hình rõ bean chính, pool, transaction manager và persistence unit.

Với nhiều database JPA, cần chỉ định `@Primary` cho DataSource mặc định nếu phù hợp, dùng `@Qualifier` để inject đúng bean, cấu hình `EntityManagerFactory` và `PlatformTransactionManager` tương ứng. Repository cần được gắn với persistence unit đúng. Không dùng một transaction manager mặc định cho nhiều database và giả định transaction sẽ nguyên tử xuyên các database; distributed transaction cần kiến trúc riêng.

## 12. Cấu hình theo môi trường: ví dụ hoàn chỉnh

Một cấu trúc tài nguyên có thể như sau:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
```

Quy ước:

- `application.yml`: cấu hình chung, pool baseline và JPA.
- `application-dev.yml`: database local dành cho developer.
- `application-test.yml`: endpoint database test hoặc giá trị được Testcontainers ghi đè.
- `application-prod.yml`: placeholder bắt buộc cho URL và secret; pool sizing theo số replica thực tế.

Profile được chọn từ môi trường triển khai. Không commit mật khẩu production vào bất kỳ file profile nào. Nếu cần kiểm tra cấu hình đã bind, log tên profile và host/database đã được làm sạch; tuyệt đối không log password hoặc toàn bộ URL có thể chứa credential.

## 13. Lỗi thường gặp và cách xử lý

- **`Communications link failure`:** kiểm tra DNS, route, firewall, port 3306, TLS và trạng thái MySQL; xác minh endpoint từ đúng container/host ứng dụng.
- **`Access denied for user`:** kiểm tra account `user`/`host`, password được inject, plugin xác thực, quyền và yêu cầu TLS.
- **Không tìm thấy JDBC driver:** kiểm tra dependency `mysql-connector-j`, scope runtime và classpath khi đóng gói.
- **Kết nối nhầm database:** kiểm tra profile đang active, precedence cấu hình và `SELECT DATABASE()`.
- **Pool cạn:** kiểm tra connection leak, transaction kéo dài, truy vấn chậm và số replica ứng dụng; không chỉ tăng pool size.
- **Lỗi chứng thư TLS:** kiểm tra CA trust, SAN/hostname, thời hạn chứng thư và `sslMode`; không hạ xuống kết nối không xác minh để né lỗi production.
- **Sai thời gian:** thống nhất timezone ứng dụng, JDBC URL, Hibernate và MySQL session; phân biệt `DATETIME` với `TIMESTAMP`.
- **Schema validation thất bại:** chạy migration trước khi ứng dụng khởi động và đối chiếu kiểu cột, nullability, precision, index và tên constraint.
- **Secret thay đổi nhưng kết nối mới thất bại:** cập nhật secret trong runtime và recycle pool theo quy trình xoay vòng credential.

## 14. Bài tập thực hành

Tạo một ứng dụng Spring Boot dùng Spring Data JPA và MySQL:

1. Thêm `spring-boot-starter-data-jpa` và `mysql-connector-j` theo dependency management của Spring Boot.
2. Tạo `application.yml` chứa cấu hình chung, placeholder cho `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` và pool baseline.
3. Tạo `application-dev.yml` trỏ tới database local; tạo `application-prod.yml` yêu cầu các biến kết nối production.
4. Chạy ứng dụng với `SPRING_PROFILES_ACTIVE=dev`, xác minh profile và database bằng truy vấn `SELECT DATABASE(), CURRENT_USER()`.
5. Tạo account runtime riêng trong MySQL, cấp quyền DML cần thiết và xác nhận account không có quyền DDL.
6. Bật TLS xác minh hostname trong môi trường test có CA phù hợp; xác nhận kết nối thất bại khi chứng thư không hợp lệ.
7. Điều chỉnh HikariCP maximum pool size, chạy tải đồng thời và theo dõi active/idle connection cùng `max_connections`.
8. Dùng Flyway hoặc Liquibase tạo schema, đặt Hibernate `ddl-auto=validate` và xác minh ứng dụng khởi động đúng.
9. Viết integration test với MySQL Testcontainers để kiểm tra repository và transaction trên database thật.

**Tiêu chí hoàn thành:** mỗi môi trường dùng đúng database và credential, production không chứa secret trong mã nguồn, pool nằm trong ngân sách MySQL, TLS được xác minh, schema do migration quản lý và ứng dụng kiểm tra được DataSource khi khởi động.

## Kết luận

Cấu hình MySQL DataSource trong Spring Boot cần tách endpoint và secret theo môi trường, để Spring Boot quản lý DataSource/pool theo cấu hình rõ ràng và tính tổng connection trên toàn bộ ứng dụng. Dùng Connector/J tương thích, HikariCP có giới hạn phù hợp, account runtime quyền tối thiểu, TLS xác minh danh tính server và migration tool cho schema. Cuối cùng, kiểm tra bằng MySQL thật và theo dõi pool để bảo đảm cấu hình hoạt động đúng trong môi trường triển khai.
