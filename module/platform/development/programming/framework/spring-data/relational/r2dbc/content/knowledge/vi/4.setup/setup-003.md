# Cấu hình kết nối tối thiểu trong application.yml

## 1. Cấu hình kết nối R2DBC gồm những gì?

Để ứng dụng Spring Data R2DBC truy cập được cơ sở dữ liệu, ứng dụng cần có driver R2DBC tương ứng và thông tin để tạo `ConnectionFactory`. Trong Spring Boot, phần lớn cấu hình kết nối thường được khai báo trong `application.yml` dưới namespace `spring.r2dbc`.

Một cấu hình tối thiểu cần xác định:

- **URL R2DBC:** loại driver, máy chủ, cổng và database cần kết nối.
- **Username:** tài khoản database mà ứng dụng sử dụng.
- **Password:** mật khẩu hoặc thông tin xác thực tương ứng.
- **Driver:** dependency của driver R2DBC phải có trong runtime classpath.

Ví dụ dưới đây dùng PostgreSQL. Tên database và tài khoản là ví dụ; cần thay bằng giá trị của môi trường thực tế.

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

Khi khởi động, Spring Boot đọc các thuộc tính này và cấu hình `ConnectionFactory` dựa trên driver có mặt trong ứng dụng. Các thành phần như Spring Data R2DBC, `R2dbcEntityTemplate` và `DatabaseClient` có thể sử dụng `ConnectionFactory` đó để thực hiện thao tác dữ liệu.

`application.yml` chỉ cung cấp thông tin cấu hình. Nó không tự cài đặt database server, tạo database, tạo tài khoản, mở cổng mạng hoặc cấp quyền cho tài khoản. Những điều kiện bên ngoài đó phải được chuẩn bị riêng.

## 2. Thêm dependency của Spring Data R2DBC và driver

Trước khi cấu hình URL, dự án phải có Spring Data R2DBC và driver của hệ quản trị đang dùng. Ví dụ với Gradle và PostgreSQL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Khi dùng Spring Boot dependency management, nên để BOM hoặc plugin của Spring Boot quản lý phiên bản tương thích thay vì tự chọn ngẫu nhiên phiên bản Spring Data, Spring Framework và Reactor. Driver cũng cần tương thích với phiên bản R2DBC SPI mà ứng dụng sử dụng.

Một vài driver thường gặp:

| Hệ quản trị | Dependency driver thường dùng | Scheme trong URL |
| --- | --- | --- |
| PostgreSQL | `org.postgresql:r2dbc-postgresql` | `r2dbc:postgresql:` |
| H2 | `io.r2dbc:r2dbc-h2` | `r2dbc:h2:` |
| Microsoft SQL Server | `io.r2dbc:r2dbc-mssql` | `r2dbc:mssql:` |
| MySQL | Driver R2DBC MySQL tương ứng, ví dụ `io.asyncer:r2dbc-mysql` | `r2dbc:mysql:` |

Tên artifact và các tùy chọn URL có thể thay đổi theo driver hoặc phiên bản. Cần sử dụng tài liệu của driver đang chọn để xác nhận dependency, scheme và các thuộc tính riêng.

**Lưu ý:** JDBC driver như `org.postgresql:postgresql` không thay thế cho R2DBC driver. URL JDBC như `jdbc:postgresql://...` cũng không phải URL R2DBC. Nếu ứng dụng truy cập database bằng Spring Data R2DBC, cần driver triển khai R2DBC SPI.

## 3. Hiểu các thuộc tính trong `spring.r2dbc`

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `spring.r2dbc.url` | URL kết nối theo định dạng của driver R2DBC | `r2dbc:postgresql://localhost:5432/customer_db` |
| `spring.r2dbc.username` | Tên tài khoản database | `app_user` |
| `spring.r2dbc.password` | Mật khẩu hoặc credential | `${DB_PASSWORD}` |
| `spring.r2dbc.properties.*` | Các tùy chọn bổ sung dành riêng cho driver | Tùy driver |
| `spring.r2dbc.pool.*` | Cấu hình connection pool khi sử dụng R2DBC Pool và phiên bản Boot hỗ trợ các thuộc tính này | `max-size: 10` |

Trong cấu hình thông thường, `url` là thuộc tính quan trọng nhất để Spring Boot nhận diện driver và đích kết nối. Username và password được cung cấp riêng để không phải nhúng thông tin xác thực vào URL.

Không cần khai báo `driver-class-name` theo cách thường thấy ở JDBC. Driver R2DBC được tìm thấy từ runtime classpath và scheme của URL. Nếu thiếu driver hoặc scheme không được driver hỗ trợ, Spring không thể tạo connection factory phù hợp.

### 3.1. Cấu trúc URL PostgreSQL

URL PostgreSQL cơ bản có dạng:

```text
r2dbc:postgresql://<host>:<port>/<database>
```

Ví dụ:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

Trong đó:

- `r2dbc` cho biết đây là URL thuộc hệ sinh thái R2DBC.
- `postgresql` xác định driver PostgreSQL.
- `localhost` là máy chủ database trong ví dụ chạy cùng máy.
- `5432` là cổng PostgreSQL mặc định, nhưng có thể khác nếu server được cấu hình riêng.
- `customer_db` là tên database đã được tạo trên server.

Nếu database chạy trong Docker Compose hoặc một máy chủ khác, `localhost` có thể không phải địa chỉ cần dùng. Từ bên trong một container, `localhost` trỏ về chính container đó. Khi các container cùng một Docker network, ứng dụng thường kết nối bằng tên service database và cổng nội bộ của service.

### 3.2. Ví dụ với H2

Khi sử dụng H2 qua R2DBC, cần thêm driver H2 R2DBC và chọn URL theo chế độ database mong muốn. Một URL in-memory thường có dạng:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///testdb
```

Đây là ví dụ cấu hình cho môi trường phát triển hoặc kiểm thử. Vòng đời dữ liệu của database in-memory phụ thuộc vào cách driver và connection được cấu hình; khi ứng dụng dừng, dữ liệu có thể không còn. Không nên dùng database in-memory để thay thế kiểm thử tích hợp trên hệ quản trị đích nếu ứng dụng phụ thuộc vào cú pháp SQL, kiểu dữ liệu hoặc hành vi riêng của hệ quản trị đó.

## 4. Dùng biến môi trường để quản lý thông tin kết nối

Không nên commit mật khẩu thật, token hoặc credential của database vào Git. Spring Boot hỗ trợ placeholder trong YAML để lấy giá trị từ biến môi trường hoặc nguồn cấu hình bên ngoài.

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
```

Cú pháp `${TEN_BIEN:gia_tri_mac_dinh}` có nghĩa là dùng biến môi trường nếu biến đã được đặt; nếu không có thì dùng giá trị mặc định sau dấu `:`. Trong ví dụ, URL và username có mặc định thuận tiện cho môi trường local, còn password bắt buộc phải được cung cấp qua `R2DBC_PASSWORD`.

Trên PowerShell, có thể đặt biến cho phiên terminal hiện tại trước khi chạy ứng dụng:

```powershell
$env:R2DBC_PASSWORD = "local-development-password"
$env:R2DBC_URL = "r2dbc:postgresql://localhost:5432/customer_db"
$env:R2DBC_USERNAME = "app_user"
./gradlew bootRun
```

Trên Linux hoặc macOS:

```bash
export R2DBC_PASSWORD='local-development-password'
export R2DBC_URL='r2dbc:postgresql://localhost:5432/customer_db'
export R2DBC_USERNAME='app_user'
./gradlew bootRun
```

Giá trị ví dụ ở trên chỉ dành cho máy phát triển. Môi trường staging và production nên lấy credential từ secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai. Tránh ghi mật khẩu vào log, ảnh chụp màn hình, file cấu hình được commit hoặc tham số dòng lệnh có thể bị lưu lại.

Spring Boot cũng hỗ trợ biến môi trường theo tên thuộc tính, chẳng hạn `SPRING_R2DBC_URL`, `SPRING_R2DBC_USERNAME` và `SPRING_R2DBC_PASSWORD`. Cách này hữu ích khi nền tảng triển khai quản lý cấu hình trực tiếp qua environment variables.

## 5. Tách cấu hình theo môi trường

Một ứng dụng thường cần cấu hình khác nhau cho local, test, staging và production. Có thể dùng profile của Spring Boot để tách phần thay đổi theo môi trường.

Ví dụ `application.yml` giữ cấu hình chung và mặc định cho môi trường local:

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
```

Một file `application-test.yml` có thể trỏ tới database kiểm thử:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///customer_test
```

Kích hoạt profile `test` khi chạy kiểm thử hoặc khởi động ứng dụng:

```bash
SPRING_PROFILES_ACTIVE=test ./gradlew bootRun
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "test"
./gradlew bootRun
```

Với production, có thể giữ URL và username trong cấu hình triển khai, còn password được cấp qua secret store. Không cần tạo một file chứa mật khẩu production trong repository.

Spring Boot kết hợp cấu hình từ nhiều nguồn theo thứ tự ưu tiên. Biến môi trường và tham số triển khai có thể ghi đè giá trị trong YAML. Vì vậy, khi ứng dụng kết nối nhầm database, cần kiểm tra cả profile đang hoạt động và các biến môi trường đang được cấp cho tiến trình.

## 6. Cấu hình connection pool khi cần

Mỗi lần truy cập database đều cần một connection. Tạo kết nối mới liên tục có thể tốn thời gian và tài nguyên, vì vậy ứng dụng thường dùng connection pool để tái sử dụng các connection.

R2DBC Pool là thành phần riêng. Nếu muốn Spring Boot tạo pooled `ConnectionFactory`, cần có dependency `io.r2dbc:r2dbc-pool` tương thích và bật cấu hình pool được phiên bản Spring Boot đang dùng hỗ trợ.

Ví dụ Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
    runtimeOnly("io.r2dbc:r2dbc-pool")
}
```

Ví dụ cấu hình pool:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-idle-time: 30m
      max-acquire-time: 5s
```

Ý nghĩa các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `enabled` | Bật cấu hình pooled connection factory nếu dependency và phiên bản Boot hỗ trợ |
| `initial-size` | Số connection pool khởi tạo ban đầu |
| `max-size` | Số connection tối đa pool có thể cấp |
| `max-idle-time` | Thời gian một connection được phép ở trạng thái idle trước khi bị loại bỏ theo chính sách pool |
| `max-acquire-time` | Thời gian tối đa chờ lấy được connection trước khi thao tác acquire thất bại |

Các giá trị trên chỉ là ví dụ để minh họa cú pháp. `max-size: 10` không phải con số đúng cho mọi ứng dụng. Khi chọn kích thước pool, cần xét số instance ứng dụng, số request đồng thời, thời gian giữ connection, giới hạn connection của database và tải của các dịch vụ khác cùng dùng database.

Ví dụ, nếu có 4 instance ứng dụng và mỗi instance cho phép tối đa 20 connection, tổng số connection tối đa từ ứng dụng có thể lên tới 80. Cần tính cả kết nối của công cụ quản trị, job nền và các ứng dụng khác để tránh vượt giới hạn của database.

Không nên tăng `max-size` chỉ vì request chậm. Nếu truy vấn giữ connection lâu do SQL thiếu index hoặc transaction kéo dài, tăng pool có thể làm database chịu tải cao hơn mà không giải quyết nguyên nhân. Hãy theo dõi thời gian chờ acquire, số connection đang sử dụng, thời gian thực thi SQL và giới hạn phía database trước khi điều chỉnh.

Nếu ứng dụng không dùng pool, có thể bỏ toàn bộ phần `pool` và dependency `r2dbc-pool`. Không cần khai báo các thuộc tính pool khi dự án không có thành phần thực hiện pooling.

## 7. Thuộc tính riêng của driver

Ngoài URL, username và password, mỗi driver có thể hỗ trợ những tùy chọn riêng như SSL/TLS, application name, timeout hoặc các tham số giao thức. Spring Boot cho phép truyền thuộc tính driver qua `spring.r2dbc.properties` khi driver và phiên bản Boot hỗ trợ cách cấu hình đó.

Ví dụ minh họa về vị trí khai báo:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.example.internal:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
    properties:
      # Đặt các thuộc tính theo đúng tài liệu của driver đang sử dụng.
      # Tên và giá trị cụ thể phụ thuộc driver và phiên bản.
```

Không nên sao chép tùy chọn của JDBC driver sang R2DBC driver theo phỏng đoán. Hai driver có thể dùng tên thuộc tính, kiểu giá trị hoặc cơ chế SSL khác nhau. Với kết nối qua mạng công cộng hoặc giữa các vùng hạ tầng, cần xem tài liệu driver và chính sách bảo mật để cấu hình TLS, xác minh chứng chỉ và hostname phù hợp.

## 8. `application.yml` không tạo schema từ Entity

Khai báo `@Table`, `@Id` và `@Column` giúp Spring Data R2DBC ánh xạ entity với bảng và cột. Các annotation đó không đồng nghĩa Spring Data R2DBC tự tạo hoặc cập nhật cấu trúc bảng theo entity như cơ chế DDL tự động thường thấy ở một số cấu hình JPA/Hibernate.

Database và schema cần được tạo bằng script khởi tạo, công cụ migration hoặc quy trình quản trị database. Spring Boot có thể hỗ trợ chạy các script SQL như `schema.sql` và `data.sql` khi cấu hình SQL initialization phù hợp; khả năng và thứ tự chạy phụ thuộc phiên bản Boot và loại connection factory.

Với ứng dụng thực tế, nên quản lý thay đổi schema bằng migration có phiên bản để các môi trường triển khai dùng cùng một lịch sử thay đổi. Cần xác định rõ công cụ migration đang dùng có kết nối qua JDBC hay R2DBC, vì một số công cụ migration truyền thống yêu cầu JDBC driver và datasource riêng. Việc thêm JDBC cho migration không làm JDBC driver trở thành R2DBC driver.

## 9. Kiểm tra cấu hình có hoạt động không

Khi ứng dụng khởi động thành công, Spring Boot thường tạo được `ConnectionFactory` nếu URL, driver và cấu hình cơ bản hợp lệ. Tuy nhiên, tạo bean không phải lúc nào cũng chứng minh database đã sẵn sàng nhận truy vấn; nhiều lỗi chỉ xuất hiện khi thao tác thực sự được subscribe và thực thi.

Có thể kiểm tra bằng một truy vấn đơn giản qua `DatabaseClient`:

```java
@Service
public class DatabaseHealthService {

    private final DatabaseClient databaseClient;

    public DatabaseHealthService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> ping() {
        return databaseClient.sql("SELECT 1 AS value")
                .map((row, metadata) -> row.get("value", Integer.class))
                .one();
    }
}
```

Phương thức `ping()` trả về `Mono<Integer>`. Nó mô tả thao tác kiểm tra; truy vấn chỉ được thực thi khi publisher được subscribe. Trong một ứng dụng WebFlux, tầng gọi có thể trả publisher này cho framework. Trong mã kiểm thử, có thể subscribe hoặc dùng cơ chế chờ kết quả phù hợp với test để xác nhận giá trị trả về là `1`.

Nếu dự án có Spring Boot Actuator và health indicator R2DBC tương ứng, endpoint health cũng có thể cung cấp tín hiệu về khả năng kết nối. Cần cấu hình exposure và bảo vệ endpoint phù hợp với môi trường triển khai.

Khi kiểm tra kết nối, hãy phân biệt ba việc:

1. Ứng dụng đọc được cấu hình YAML.
2. Spring tạo được `ConnectionFactory` từ driver và URL.
3. Ứng dụng thực sự lấy được connection, xác thực và chạy được truy vấn trên database.

Chỉ bước thứ ba mới xác nhận được toàn bộ đường kết nối đang hoạt động tại thời điểm kiểm tra.

## 10. Lỗi thường gặp khi cấu hình

| Triệu chứng | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo được `ConnectionFactory` | Thiếu driver R2DBC, URL sai scheme hoặc dependency không tương thích | Kiểm tra runtime dependency và phần đầu URL `r2dbc:<driver>:` |
| Không kết nối được host | Sai hostname, cổng, DNS, firewall hoặc database chưa chạy | Kiểm tra địa chỉ từ đúng môi trường chạy ứng dụng và trạng thái server |
| Authentication failed | Username/password sai, biến môi trường chưa được cấp hoặc tài khoản bị khóa | Kiểm tra tên biến, profile, credential và quyền đăng nhập |
| Database does not exist | URL trỏ tới database chưa được tạo hoặc sai tên | Kiểm tra tên database trên server và URL |
| Connection refused | Server không lắng nghe ở địa chỉ/cổng đã khai báo hoặc container chưa sẵn sàng | Kiểm tra cổng, bind address, container health và thứ tự khởi động |
| Pool acquire timeout | Pool hết connection, connection bị giữ quá lâu hoặc database không đáp ứng | Theo dõi active/idle/pending, thời gian truy vấn và transaction |
| SQL chạy được ở máy này nhưng lỗi ở máy khác | Khác hệ quản trị, dialect, schema hoặc phiên bản driver | So sánh môi trường, SQL thực tế, schema và driver |
| YAML không được đọc như mong muốn | Sai thụt lề, profile không hoạt động hoặc biến môi trường ghi đè giá trị | Kiểm tra cấu trúc YAML, profile active và nguồn cấu hình ưu tiên |

### 10.1. Dùng nhầm cấu hình JDBC

Một cấu hình JDBC thường có dạng:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

Cấu hình đó dành cho `DataSource` và JDBC. Với Spring Data R2DBC, cấu hình kết nối phải nằm dưới `spring.r2dbc` và URL phải dùng scheme R2DBC:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

Một dự án có thể chủ đích dùng cả JDBC và R2DBC, ví dụ một thành phần migration dùng JDBC trong khi luồng nghiệp vụ dùng R2DBC. Khi đó cần cấu hình hai stack rõ ràng và hiểu rằng chúng có thể dùng hai connection factory hoặc pool khác nhau. Không nên đặt thuộc tính JDBC rồi kỳ vọng repository reactive tự sử dụng nó.

### 10.2. Dùng `localhost` sai trong container

Nếu ứng dụng chạy trực tiếp trên máy và database cũng chạy trên máy, `localhost` có thể phù hợp. Nhưng nếu ứng dụng nằm trong container riêng, `localhost` trỏ tới container ứng dụng. Khi dùng Docker Compose, URL thường dùng tên service database, ví dụ:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://postgres:5432/customer_db
```

Ở đây `postgres` phải là tên service hoặc hostname có thể phân giải từ container ứng dụng. Cổng nội bộ container có thể khác cổng được publish ra máy host.

### 10.3. Password chứa ký tự đặc biệt

Khi đặt password trực tiếp trong YAML, các ký tự như `#`, `:`, `{` hoặc dấu nháy có thể ảnh hưởng cách YAML phân tích giá trị nếu không được quote đúng. Dùng biến môi trường giúp tránh phải mã hóa credential trong file YAML. Nếu bắt buộc khai báo một chuỗi literal có ký tự đặc biệt, hãy đặt trong dấu nháy phù hợp và kiểm tra giá trị sau khi cấu hình được nạp.

## 11. Ví dụ cấu hình hoàn chỉnh cho local development

Ví dụ sau kết hợp URL, credential lấy từ biến môi trường và connection pool. Cần có dependency PostgreSQL R2DBC và `r2dbc-pool` như các phần trước.

```yaml
spring:
  application:
    name: customer-service

  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-idle-time: 30m
      max-acquire-time: 5s
```

Trước khi chạy, cần bảo đảm:

- PostgreSQL đang chạy và có thể truy cập từ máy chạy ứng dụng.
- Database `customer_db` đã tồn tại.
- Tài khoản `app_user` tồn tại và có quyền cần thiết trên database/schema.
- Biến `R2DBC_PASSWORD` đã được đặt.
- Dependency driver PostgreSQL R2DBC và R2DBC Pool có trong runtime classpath.
- Các giá trị pool phù hợp với giới hạn connection và tải của môi trường.

## 12. Trình tự cấu hình trong một dự án mới

Khi bắt đầu một ứng dụng Spring Data R2DBC, có thể triển khai theo thứ tự sau:

1. Chọn hệ quản trị cơ sở dữ liệu và driver R2DBC tương ứng.
2. Thêm `spring-boot-starter-data-r2dbc` cùng driver vào dependency của dự án.
3. Khai báo `spring.r2dbc.url`, `username` và `password` trong `application.yml` hoặc nguồn cấu hình bên ngoài.
4. Xác nhận database đã tồn tại, tài khoản có quyền truy cập và mạng cho phép kết nối.
5. Chỉ thêm R2DBC Pool khi dự án cần pooling; sau đó cấu hình giới hạn dựa trên tải và tài nguyên database.
6. Tạo hoặc áp dụng schema bằng script hay migration phù hợp.
7. Thực hiện truy vấn kiểm tra để xác nhận ứng dụng thực sự kết nối và đọc được dữ liệu.
8. Tách credential và địa chỉ kết nối theo profile hoặc biến môi trường cho từng môi trường triển khai.

Với Spring Data R2DBC, `application.yml` là nơi khai báo cách Spring Boot tạo kết nối reactive tới database. Dependency cung cấp driver thực hiện giao tiếp, URL xác định đích và loại driver, còn username/password cung cấp thông tin xác thực. Khi các phần này khớp với môi trường database, Spring Boot có thể tạo `ConnectionFactory` để repository, `R2dbcEntityTemplate` và `DatabaseClient` sử dụng trong các pipeline reactive.
