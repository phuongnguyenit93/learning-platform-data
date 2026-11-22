# Cấu hình DataSource, thông tin kết nối và hồ sơ môi trường

## Mục tiêu và phạm vi

Trong một ứng dụng Spring Data JPA, `DataSource` cung cấp các kết nối JDBC tới cơ sở dữ liệu. Spring Boot có thể tự tạo `DataSource`, cấu hình Hibernate, `EntityManagerFactory` và transaction manager từ dependency cùng các thuộc tính cấu hình. Ta cần khai báo đúng thông tin kết nối, chọn cấu hình theo môi trường chạy và quản lý thông tin bí mật an toàn.

Sau bài này, bạn có thể:

- Giải thích luồng kết nối từ repository JPA tới cơ sở dữ liệu.
- Thêm JDBC driver và cấu hình URL, tài khoản, mật khẩu.
- Hiểu các thiết lập cơ bản của connection pool HikariCP.
- Tách cấu hình dùng chung, cấu hình phát triển và cấu hình production bằng Spring Profiles.
- Đưa thông tin nhạy cảm vào biến môi trường và kiểm tra lỗi kết nối.

Ví dụ sử dụng Spring Boot 3.x, Java 17+ và PostgreSQL. Cùng nguyên tắc có thể áp dụng cho MySQL, MariaDB, SQL Server hoặc H2 khi thay JDBC driver và URL tương ứng.

## 1. DataSource nằm ở đâu trong Spring Data JPA?

Một luồng thao tác dữ liệu điển hình:

1. Controller hoặc service gọi một Spring Data repository, ví dụ `CustomerRepository`.
2. Repository sử dụng JPA `EntityManager` để thực hiện truy vấn.
3. Hibernate (JPA provider mặc định thường được Spring Boot cấu hình) chuyển thao tác JPA thành SQL.
4. Hibernate lấy kết nối JDBC từ `DataSource`.
5. `DataSource` cấp một kết nối từ connection pool; câu lệnh được gửi tới database.
6. Kết quả được ánh xạ về entity và trả lại cho tầng gọi.

`DataSource` là abstraction của JDBC để lấy kết nối. Nó không phải database server và cũng không tự tạo database. Database, user và quyền truy cập phải được chuẩn bị ở phía hệ quản trị cơ sở dữ liệu.

Khi classpath có Spring Data JPA, có JDBC driver phù hợp và ứng dụng chưa tự khai báo một `DataSource` khác, Spring Boot thường tự cấu hình một `DataSource`. Với một nguồn dữ liệu, Boot cũng có thể tự cấu hình Hibernate, `EntityManagerFactory` và transaction manager. Vì vậy, ứng dụng thông thường không cần tự tạo các bean này.

## 2. Thêm dependency và JDBC driver

Ví dụ Maven dùng Spring Boot dependency management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-data-jpa` cung cấp Spring Data JPA, JPA và các thành phần JDBC cần thiết; Spring Boot thường dùng HikariCP làm connection pool mặc định khi thư viện này có trên classpath. Dependency `org.postgresql:postgresql` cung cấp driver để JDBC giao tiếp với PostgreSQL. Khi dùng MySQL hoặc hệ quản trị khác, hãy thêm driver tương ứng.

Nếu dùng Spring Boot parent hoặc BOM, không tự đặt version riêng cho driver và starter trừ khi có lý do tương thích cụ thể. Hãy để phiên bản Spring Boot quản lý các dependency đã được kiểm thử cùng nhau.

Lỗi thiếu driver thường xuất hiện khi ứng dụng không tìm thấy lớp JDBC driver hoặc không nhận diện được URL. Kiểm tra dependency đã được tải và driver phù hợp với loại database đang dùng.

## 3. Cấu hình thông tin kết nối

Spring Boot đọc cấu hình từ `application.properties` hoặc `application.yml`. Có thể dùng một trong hai định dạng. Ví dụ dưới đây dùng YAML.

### 3.1. Các thuộc tính DataSource cơ bản

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.datasource.url` | JDBC URL xác định loại database, máy chủ, cổng và database cần kết nối |
| `spring.datasource.username` | Tài khoản database của ứng dụng |
| `spring.datasource.password` | Mật khẩu của tài khoản |
| `spring.datasource.driver-class-name` | Tên lớp JDBC driver; thường có thể để Spring Boot tự suy ra từ URL và driver trên classpath |
| `spring.datasource.hikari.*` | Các thiết lập của connection pool HikariCP khi HikariCP được sử dụng |

Ví dụ URL PostgreSQL:

```text
jdbc:postgresql://localhost:5432/app_db
```

Trong URL trên:

- `jdbc:postgresql` chỉ ra JDBC driver cho PostgreSQL.
- `localhost` là hostname của database server.
- `5432` là cổng PostgreSQL mặc định.
- `app_db` là tên database đã được tạo trước.

Nếu database chạy trong Docker hoặc một máy chủ khác, hostname phải là địa chỉ mà tiến trình Spring Boot có thể truy cập. Khi ứng dụng cũng chạy trong Docker Compose, hostname thường là tên service database trên network của Compose, không nhất thiết là `localhost`.

### 3.2. Cấu hình dùng chung trong application.yml

Đặt các thuộc tính chung trong `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: spring-data-jpa-demo

  datasource:
    hikari:
      pool-name: app-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000

  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        jdbc:
          time_zone: UTC
```

Các thiết lập đáng chú ý:

- `pool-name` đặt tên pool để dễ nhận diện trong log và giám sát.
- `maximum-pool-size` giới hạn số kết nối tối đa trong pool của một instance ứng dụng.
- `minimum-idle` là số kết nối nhàn rỗi tối thiểu mà pool cố gắng duy trì.
- `connection-timeout` là thời gian tối đa (mili giây) chờ lấy một kết nối từ pool trước khi báo lỗi.
- `show-sql` bật/tắt việc hiển thị SQL do Hibernate sinh ra. Để false ở cấu hình chung giúp tránh log SQL ngoài ý muốn.
- `format_sql` định dạng SQL trong log khi logging SQL được bật.
- `jdbc.time_zone` đặt múi giờ JDBC cho các thao tác ngày giờ của Hibernate; hãy chọn quy ước thống nhất với ứng dụng và database.
- `open-in-view: false` tắt Open EntityManager in View. Service nên tải dữ liệu cần thiết trong transaction và trả DTO phù hợp; nếu tắt thuộc tính này, việc truy cập lazy relationship sau khi transaction/session đã đóng có thể gây lỗi.

Ở ví dụ này, URL, username và password được đặt trong file cấu hình riêng của từng profile ở phần tiếp theo. Nếu không có cấu hình kết nối hợp lệ từ profile đang hoạt động hoặc nguồn cấu hình bên ngoài, ứng dụng sẽ không thể tạo DataSource.

### 3.3. Cấu hình theo môi trường

Tạo các file nằm cạnh `application.yml`:

- `application-dev.yml`: cấu hình phát triển trên máy cá nhân.
- `application-test.yml`: cấu hình kiểm thử nếu cần.
- `application-prod.yml`: cấu hình production.

Ví dụ `application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app_db
    username: app_user
    password: ${DB_PASSWORD:local-dev-only}

  jpa:
    hibernate:
      ddl-auto: update
    show-sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Mật khẩu mặc định trong ví dụ chỉ nhằm giúp chạy thử trên máy cá nhân. Hãy thay bằng mật khẩu local riêng nếu cần. Log bind parameter ở mức TRACE có thể làm lộ dữ liệu nhạy cảm, vì vậy chỉ bật tạm thời trong môi trường phát triển và tắt khi không còn cần chẩn đoán.

Ví dụ `application-prod.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX:20}
      minimum-idle: ${DB_POOL_MIN:5}

  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false
```

Trong production, các biến `DB_URL`, `DB_USERNAME` và `DB_PASSWORD` phải được cấp từ môi trường triển khai hoặc hệ thống quản lý secret. Không đặt mật khẩu production thật trong source code, file YAML được commit hoặc log.

Profile `dev` dùng `ddl-auto: update` để tiện thử nghiệm schema. Production dùng `validate` để Hibernate kiểm tra schema hiện có tương thích với mapping entity. Phần quản lý schema được giải thích ở mục 6.

### 3.4. Chọn profile khi chạy ứng dụng

Spring Profile cho phép Spring Boot nạp thêm cấu hình phù hợp với môi trường đang chạy. Ví dụ:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DB_PASSWORD = "local-secret"
.mvnw.cmd spring-boot:run
```

Khi chạy JAR, có thể truyền profile qua tham số dòng lệnh:

```bash
java -jar target/spring-data-jpa-demo.jar --spring.profiles.active=prod
```

Các cách kích hoạt profile thường dùng:

- Biến môi trường `SPRING_PROFILES_ACTIVE=dev`.
- Tham số dòng lệnh `--spring.profiles.active=dev`.
- Thuộc tính `spring.profiles.active` trong cấu hình chung khi thật sự muốn đặt một profile mặc định cho ứng dụng.

Spring Boot nạp cấu hình chung rồi áp dụng các thuộc tính tương ứng của profile đang hoạt động. Giá trị từ biến môi trường và tham số dòng lệnh có thể ghi đè cấu hình đóng gói trong ứng dụng. Không đặt `spring.profiles.active` bên trong file `application-{profile}.yml` để kích hoạt chính file đó; hãy chọn profile từ cấu hình chung hoặc từ môi trường chạy.

Có thể kích hoạt nhiều profile cùng lúc, nhưng cần hiểu thứ tự ưu tiên khi các profile cùng khai báo một thuộc tính. Với ứng dụng đơn giản, nên chọn một profile rõ ràng cho mỗi lần chạy để tránh khó xác định cấu hình cuối cùng.

## 4. Quản lý biến môi trường và thông tin bí mật

Có hai cách thường gặp để cung cấp cấu hình:

1. Dùng trực tiếp tên thuộc tính Spring Boot, ví dụ `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME` và `SPRING_DATASOURCE_PASSWORD`.
2. Dùng placeholder trong YAML, ví dụ `${DB_URL}`; khi đó tiến trình phải có biến môi trường `DB_URL` tương ứng.

Ví dụ các biến môi trường cho production:

```text
SPRING_PROFILES_ACTIVE=prod
DB_URL=jdbc:postgresql://db.internal:5432/app_db
DB_USERNAME=app_runtime
DB_PASSWORD=<secret-from-deployment-platform>
DB_POOL_MAX=20
DB_POOL_MIN=5
```

Các nguyên tắc bảo vệ thông tin kết nối:

- Tạo tài khoản riêng cho ứng dụng với quyền tối thiểu cần thiết; không dùng tài khoản quản trị database để chạy ứng dụng.
- Cấp mật khẩu từ secret store, Kubernetes Secret, nền tảng triển khai hoặc cơ chế quản lý bí mật của tổ chức.
- Không commit mật khẩu thật vào Git. Nếu lỡ commit, đổi/thu hồi secret; xóa khỏi file hiện tại không làm mất lịch sử Git.
- Không in password, token hoặc toàn bộ JDBC URL có thông tin xác thực vào log.
- Với database qua mạng, cấu hình TLS/SSL theo yêu cầu của hệ thống và xác minh chứng chỉ theo hướng dẫn của nhà cung cấp.
- Phân tách tài khoản và database của dev, test, production để tránh ghi nhầm dữ liệu.

Placeholder dạng `${DB_URL}` không tự tạo biến môi trường. Nếu biến bắt buộc bị thiếu, Spring sẽ báo lỗi không phân giải được placeholder khi khởi động; đây là dấu hiệu cần kiểm tra cấu hình triển khai.

## 5. Connection pool HikariCP

Mở một kết nối TCP/JDBC mới cho từng thao tác rất tốn thời gian. Connection pool giữ một nhóm kết nối có thể tái sử dụng. Khi cần truy vấn, ứng dụng mượn kết nối từ pool và trả lại sau khi transaction hoặc thao tác hoàn tất.

Spring Boot thường chọn HikariCP khi thư viện này có trên classpath. Các thuộc tính phổ biến:

| Thuộc tính | Tác dụng |
|---|---|
| `maximum-pool-size` | Giới hạn tổng số kết nối trong pool |
| `minimum-idle` | Số kết nối nhàn rỗi mục tiêu tối thiểu |
| `connection-timeout` | Thời gian chờ lấy kết nối từ pool, tính bằng mili giây |
| `idle-timeout` | Thời gian một kết nối nhàn rỗi có thể ở trong pool trước khi được loại bỏ, tính bằng mili giây |
| `max-lifetime` | Tuổi thọ tối đa của kết nối trong pool, tính bằng mili giây |
| `pool-name` | Tên nhận diện pool |

Không nên tăng `maximum-pool-size` tùy tiện. Tổng kết nối có thể mở phải tính trên tất cả instance ứng dụng, ví dụ 4 instance với pool tối đa 20 có thể cần tới 80 kết nối, chưa tính tác vụ quản trị và các ứng dụng khác. Hãy đối chiếu giới hạn kết nối của database, số instance, mức tải thực tế và thời gian truy vấn.

`connection-timeout` chỉ điều khiển thời gian chờ mượn kết nối từ pool; nó không phải timeout cho toàn bộ câu SQL. Timeout truy vấn, transaction và network là các thiết lập khác. Chỉ điều chỉnh `max-lifetime` hoặc `idle-timeout` khi có yêu cầu từ giới hạn của database/proxy và dữ liệu giám sát. Không giữ kết nối lâu hơn cần thiết; tránh thực hiện lời gọi mạng chậm trong transaction đang giữ kết nối.

Nếu pool cạn, ứng dụng thường phải chờ tới `connection-timeout` rồi báo lỗi. Nguyên nhân có thể là pool quá nhỏ, transaction kéo dài, truy vấn chậm, rò rỉ kết nối do code quản lý JDBC thủ công hoặc database không đáp ứng. Tăng pool mà không tìm nguyên nhân có thể làm database quá tải hơn.

## 6. Cấu hình JPA và quản lý schema

DataSource xác định cách kết nối tới database; các thuộc tính `spring.jpa.*` điều khiển hành vi JPA/Hibernate. Một số thuộc tính hay gặp:

- `spring.jpa.hibernate.ddl-auto`: hành động Hibernate thực hiện với schema.
- `spring.jpa.show-sql`: hiển thị SQL do Hibernate sinh.
- `spring.jpa.properties.hibernate.format_sql`: định dạng SQL trong log.
- `spring.jpa.open-in-view`: bật/tắt việc giữ EntityManager trong suốt request web.

Các giá trị `ddl-auto` phổ biến:

| Giá trị | Hành vi |
|---|---|
| `none` | Không tự động thay đổi schema |
| `validate` | Kiểm tra schema có phù hợp với mapping entity hay không |
| `update` | Cố gắng điều chỉnh schema theo entity; không thay thế công cụ migration có kiểm soát |
| `create` | Tạo schema khi khởi động; các đối tượng schema hiện có có thể bị tạo lại |
| `create-drop` | Tạo schema khi khởi động và xóa khi EntityManagerFactory đóng |

`update`, `create` và `create-drop` phù hợp cho thử nghiệm có kiểm soát, không nên dùng như quy trình triển khai schema production. Chúng có thể gây mất dữ liệu hoặc không biểu diễn đầy đủ các thay đổi phức tạp như đổi tên cột, chuyển đổi dữ liệu và thay đổi constraint.

Với production, hãy dùng công cụ migration như Flyway hoặc Liquibase để quản lý các thay đổi schema bằng phiên bản. Một quy trình thường gặp là chạy migration trước hoặc trong giai đoạn khởi động được kiểm soát, sau đó để Hibernate `validate` xác nhận mapping entity tương thích với schema.

Database phải tồn tại trước khi ứng dụng kết nối. Việc cấu hình JDBC URL không tự tạo database hoặc user. User runtime cần các quyền phù hợp để đọc/ghi dữ liệu; tài khoản migration có thể cần quyền DDL cao hơn và nên được quản lý riêng.

## 7. Kiểm tra cấu hình hoạt động

Thực hiện theo thứ tự sau khi cấu hình:

1. Xác nhận database server đang chạy và có thể truy cập từ máy/container chạy ứng dụng.
2. Xác nhận database đã được tạo, hostname và port đúng.
3. Xác nhận JDBC driver có trong dependency runtime.
4. Xác nhận profile đang hoạt động đúng và các biến môi trường đã được cấp.
5. Khởi động ứng dụng, đọc log để xác nhận DataSource/Hibernate khởi tạo thành công.
6. Gọi một repository từ service hoặc chạy một integration test để thực hiện truy vấn thực tế.
7. Nếu dùng `ddl-auto: validate`, xác nhận schema đã được migration trước khi khởi động.

Có thể kiểm tra profile qua log khởi động hoặc cấu hình Actuator nếu dự án đã thêm và bảo vệ endpoint phù hợp. Không bật endpoint hiển thị toàn bộ environment hoặc cấu hình nhạy cảm ra bên ngoài.

Ví dụ lệnh chạy profile dev:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

Khi cần kiểm tra SQL, bật logging trong dev:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 dùng logger `org.hibernate.orm.jdbc.bind` để ghi bind parameter. Log này có thể chứa dữ liệu người dùng; hãy tắt sau khi chẩn đoán và không dùng ở production nếu chưa đánh giá tác động bảo mật.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `Failed to determine a suitable driver class` | Thiếu JDBC driver hoặc chưa có JDBC URL | Kiểm tra dependency runtime, URL và profile đang hoạt động |
| `Connection refused` | Database chưa chạy, sai host/port hoặc network/firewall chặn | Kiểm tra service, cổng lắng nghe và kết nối từ đúng môi trường chạy ứng dụng |
| `password authentication failed` | Sai username/password hoặc user không được phép đăng nhập từ host đó | Xác nhận secret, user và chính sách xác thực của database |
| `database does not exist` | Tên database trong URL chưa được tạo hoặc sai chính tả | Tạo database và đối chiếu tên trong JDBC URL |
| Không phân giải được placeholder | Thiếu biến môi trường như `DB_URL` hoặc `DB_PASSWORD` | Kiểm tra biến được cấp cho đúng tiến trình/container |
| `Connection is not available, request timed out` | Pool hết kết nối hoặc database phản hồi chậm | Kiểm tra số kết nối, transaction dài, truy vấn chậm và giới hạn pool |
| `Schema-validation: missing table/column` | Schema chưa được migration hoặc không khớp entity | Kiểm tra migration, tên bảng/cột và profile đang chạy |
| Chạy được ở dev nhưng lỗi ở prod | Khác URL, quyền, secret, profile, SSL hoặc schema | So sánh cấu hình đã resolve mà không in secret; kiểm tra quyền và network của production |
| Sai lệch ngày giờ | Múi giờ JVM, JDBC, database hoặc kiểu dữ liệu không thống nhất | Chọn quy ước UTC hoặc quy ước của hệ thống và cấu hình đồng bộ |

Khi chẩn đoán, đọc nguyên nhân gốc trong stack trace, thường nằm ở phần `Caused by`. Các lỗi Hibernate như không lấy được JDBC connection có thể chỉ là lớp bọc; nguyên nhân thực tế thường nằm ở driver, network, xác thực hoặc database.

## 9. Lưu ý khi mở rộng cấu hình

- **Nhiều DataSource:** Khi ứng dụng kết nối nhiều database, cần khai báo từng DataSource, chỉ định bean chính nếu phù hợp, cấu hình EntityManagerFactory và transaction manager tương ứng, đồng thời liên kết repository với đúng nguồn dữ liệu. Không chỉ khai báo hai URL rồi mong Spring tự suy ra repository cần dùng database nào.
- **Tự tạo DataSource:** Khi khai báo bean `DataSource` riêng, một phần auto-configuration mặc định có thể nhường chỗ cho cấu hình tùy chỉnh. Hãy đảm bảo các bean JPA/transaction cần thiết vẫn được cấu hình đúng.
- **Kiểm thử repository:** `@DataJpaTest` tập trung vào lớp persistence và trong một số cấu hình có thể thay DataSource bằng embedded database. Nếu cần kiểm tra PostgreSQL thật, cấu hình test phù hợp hoặc dùng Testcontainers.
- **Tách quyền runtime và migration:** Tài khoản chạy ứng dụng chỉ nên có quyền cần thiết cho hoạt động thường ngày. Quyền tạo bảng, sửa schema nên thuộc quy trình migration.
- **Quan sát vận hành:** Theo dõi số kết nối đang hoạt động/nhàn rỗi, thời gian chờ lấy kết nối, lỗi kết nối và thời gian truy vấn. Điều chỉnh pool dựa trên số liệu thay vì phỏng đoán.

## 10. Checklist hoàn thành

- [ ] Đã thêm Spring Data JPA starter và JDBC driver đúng với database.
- [ ] JDBC URL trỏ tới đúng host, port và database.
- [ ] Username/password được cấp từ nguồn cấu hình phù hợp.
- [ ] Profile dev/test/prod được tách rõ và profile cần dùng đã được kích hoạt.
- [ ] Pool có giới hạn phù hợp với số instance và khả năng của database.
- [ ] Schema được quản lý bằng migration; production không dùng chế độ tự động tạo schema nguy hiểm.
- [ ] Ứng dụng khởi động, lấy được kết nối và thực hiện được một truy vấn repository.
- [ ] Log không làm lộ mật khẩu hoặc dữ liệu nhạy cảm.

## Kết luận

Cấu hình DataSource là điểm nối giữa Spring Data JPA và database. Spring Boot giúp tự động cấu hình phần lớn thành phần JDBC/JPA, còn ứng dụng cần cung cấp đúng driver, URL, thông tin xác thực và profile. Tách cấu hình theo môi trường, quản lý secret bên ngoài source code, giới hạn connection pool và dùng migration có kiểm soát sẽ giúp ứng dụng chạy ổn định từ máy phát triển tới production.
