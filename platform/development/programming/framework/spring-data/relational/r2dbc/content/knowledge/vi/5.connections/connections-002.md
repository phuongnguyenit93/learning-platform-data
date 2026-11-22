# Phân biệt URL R2DBC với URL JDBC

URL kết nối R2DBC và URL kết nối JDBC đều mô tả cách ứng dụng tìm đến một cơ sở dữ liệu, nhưng chúng thuộc hai SPI, hai hệ sinh thái driver và hai mô hình truy cập dữ liệu khác nhau. Với cùng một PostgreSQL server, JDBC thường dùng URL bắt đầu bằng `jdbc:postgresql:`, còn R2DBC dùng URL bắt đầu bằng `r2dbc:postgresql:`. Việc thay tiền tố trong chuỗi là chưa đủ để chuyển một ứng dụng từ JDBC sang R2DBC: ứng dụng còn phải dùng đúng driver, dependency, cấu hình Spring và API kết nối tương ứng.

## 1. URL kết nối dùng để làm gì?

Ứng dụng cần biết ít nhất các thông tin sau để kết nối database:

- Hệ quản trị hoặc driver cần sử dụng.
- Máy chủ và cổng kết nối, nếu database chạy qua mạng.
- Database hoặc catalog cần truy cập.
- Thông tin xác thực và các tùy chọn kết nối như SSL, timeout hoặc schema mặc định.

URL gom một phần hoặc toàn bộ những thông tin đó thành một chuỗi. Driver phân tích chuỗi và tạo kết nối theo giao thức mà nó hỗ trợ. Tuy nhiên, JDBC và R2DBC có cơ chế tìm driver, kiểu connection, cấu hình và quy ước URL riêng.

URL không phải là chính kết nối. Nó là thông tin đầu vào để tạo đối tượng kết nối thông qua API tương ứng:

| Hệ sinh thái | API tạo kết nối | Đối tượng kết nối |
|---|---|---|
| JDBC | `DriverManager` hoặc `DataSource` | `java.sql.Connection` |
| R2DBC | `ConnectionFactories` hoặc Spring `ConnectionFactory` | `io.r2dbc.spi.Connection` |

Vì vậy, một URL JDBC không thể được xem là URL R2DBC chỉ vì cả hai cùng trỏ đến một máy chủ database.

## 2. Cấu trúc tổng quát của URL JDBC

URL JDBC có dạng tổng quát:

```text
jdbc:<subprotocol>:<subname>
```

Trong đó:

- `jdbc:` là tiền tố xác định URL thuộc JDBC.
- `<subprotocol>` thường xác định hệ quản trị hoặc loại driver, ví dụ `postgresql`, `mysql`, `oracle`, `sqlserver`.
- `<subname>` chứa thông tin kết nối theo quy ước của driver, chẳng hạn host, port, database và tham số tùy chọn.

Ví dụ PostgreSQL:

```text
jdbc:postgresql://localhost:5432/orders
```

Có thể đọc URL này như sau:

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| Prefix | `jdbc:` | Dùng JDBC |
| Subprotocol | `postgresql` | Driver PostgreSQL JDBC |
| Host | `localhost` | Database chạy trên máy hiện tại |
| Port | `5432` | Cổng PostgreSQL thường dùng mặc định |
| Database | `orders` | Database cần truy cập |

Một số ví dụ khác:

```text
jdbc:mysql://localhost:3306/shop
jdbc:oracle:thin:@//localhost:1521/ORCLPDB1
jdbc:sqlserver://localhost:1433;databaseName=orders
jdbc:h2:mem:sample
```

Không có một cấu trúc `<subname>` duy nhất áp dụng cho tất cả JDBC driver. PostgreSQL, MySQL, Oracle, SQL Server và H2 có thể dùng cú pháp riêng. Một số driver dùng query parameter theo dạng `?key=value`, một số dùng dấu chấm phẩy hoặc cú pháp đặc thù.

JDBC driver thường được chọn thông qua `DriverManager` hoặc được đóng gói bên trong một `DataSource`/connection pool. Ví dụ dùng trực tiếp JDBC:

```java
String url = "jdbc:postgresql://localhost:5432/orders";

try (Connection connection = DriverManager.getConnection(
        url, "app", password)) {
    // Thực hiện công việc JDBC.
}
```

Trong ứng dụng Spring, `DataSource` thường là điểm cấu hình và cấp phát connection cho `JdbcTemplate`, JPA hoặc các thành phần JDBC khác.

## 3. Cấu trúc tổng quát của URL R2DBC

URL R2DBC thường có dạng:

```text
r2dbc:<driver>:[//<host>[:<port>]][/<database>][?<options>]
```

Trong đó:

- `r2dbc:` là tiền tố xác định URL thuộc R2DBC.
- `<driver>` là tên driver/provider R2DBC, ví dụ `postgresql`, `mysql`, `mariadb` hoặc `h2` tùy driver được cài đặt.
- Host, port và database xác định đích kết nối nếu driver dùng dạng kết nối mạng.
- Phần query options có thể chứa các tùy chọn do driver hỗ trợ.

Đây là hình thức tổng quát. Driver có thể mở rộng hoặc quy định chi tiết riêng, đặc biệt với database nhúng và các tùy chọn kết nối. Không nên giả định mọi driver đều chấp nhận cùng một tập tham số.

Ví dụ PostgreSQL:

```text
r2dbc:postgresql://localhost:5432/orders
```

Các thành phần tương ứng:

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| Prefix | `r2dbc:` | Dùng R2DBC SPI |
| Driver | `postgresql` | R2DBC PostgreSQL driver/provider |
| Host | `localhost` | Database server |
| Port | `5432` | Cổng PostgreSQL |
| Database | `orders` | Database cần truy cập |

Ví dụ một số driver khác:

```text
r2dbc:mysql://localhost:3306/shop
r2dbc:mariadb://localhost:3306/shop
r2dbc:h2:mem:///sample
```

Tên driver và cú pháp cụ thể phụ thuộc artifact R2DBC được dùng. Hãy kiểm tra tài liệu của đúng driver và phiên bản đang có trong dự án, thay vì suy ra tên driver từ tên JDBC connector.

R2DBC SPI có thể tạo `ConnectionFactory` từ URL thông qua `ConnectionFactories`:

```java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

ConnectionFactory connectionFactory = ConnectionFactories.get(
    "r2dbc:postgresql://localhost:5432/orders"
);
```

Trong ứng dụng Spring, thông thường `ConnectionFactory` được cấu hình và quản lý bởi Spring Boot hoặc cấu hình Spring riêng. `DatabaseClient`, `R2dbcEntityTemplate` và repository reactive sử dụng hạ tầng này để truy cập database.

## 4. So sánh trực tiếp với cùng một database

Với PostgreSQL ở `localhost:5432`, database `orders`, hai URL cơ bản là:

```text
JDBC:  jdbc:postgresql://localhost:5432/orders
R2DBC: r2dbc:postgresql://localhost:5432/orders
```

Phần thông tin host, port và database trông gần giống nhau, nhưng tiền tố quyết định hệ sinh thái kết nối. Hai chuỗi được xử lý bởi hai loại driver khác nhau.

| Tiêu chí | JDBC | R2DBC |
|---|---|---|
| Prefix | `jdbc:` | `r2dbc:` |
| SPI | JDBC | R2DBC SPI |
| Driver | JDBC driver | R2DBC driver |
| API tạo kết nối | `DriverManager` / `DataSource` | `ConnectionFactories` / `ConnectionFactory` |
| Kiểu connection | `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| Mô hình thao tác | Thông thường là đồng bộ và blocking | Reactive, hỗ trợ non-blocking I/O |
| Spring configuration phổ biến | `spring.datasource.*` | `spring.r2dbc.*` |
| Spring abstraction | `JdbcTemplate`, JPA/JDBC | `DatabaseClient`, `R2dbcEntityTemplate`, reactive repositories |
| Pool phổ biến | HikariCP qua `DataSource` | R2DBC Pool hoặc cơ chế pool tương ứng |

Điểm quan trọng: URL giống nhau ở phần host và database không làm cho driver có thể thay thế lẫn nhau. JDBC driver triển khai JDBC SPI; R2DBC driver triển khai R2DBC SPI. Muốn sử dụng R2DBC, ứng dụng phải có driver R2DBC tương ứng.

## 5. Dependency cũng phải tương ứng với URL

Một URL chỉ có ý nghĩa khi classpath có driver/provider hiểu URL đó.

Ví dụ với PostgreSQL và Gradle Kotlin DSL:

**Ứng dụng dùng R2DBC:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

**Ứng dụng dùng JDBC:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
```

Spring Boot dependency management có thể quản lý phiên bản tương thích khi dự án sử dụng BOM hoặc plugin Spring Boot. Nếu dự án dùng phiên bản độc lập, cần khai báo phiên bản driver phù hợp với Spring Framework, Spring Data và database.

Hai artifact PostgreSQL trên có mục đích khác nhau:

- `org.postgresql:postgresql` là PostgreSQL JDBC driver.
- `org.postgresql:r2dbc-postgresql` là PostgreSQL R2DBC driver.

Chỉ thêm JDBC driver không làm xuất hiện một R2DBC `ConnectionFactory`. Tương tự, chỉ thêm R2DBC driver không cung cấp `java.sql.Driver` cho `DriverManager`.

Một ứng dụng có thể cần cả hai driver nếu thực sự sử dụng cả JDBC/JPA lẫn R2DBC. Trong trường hợp đó, hãy cấu hình hai connection stack riêng biệt và quản lý transaction, pool cũng như bean tương ứng cho từng stack.

## 6. Cấu hình URL trong Spring Boot

Spring Boot dùng các namespace cấu hình khác nhau cho JDBC và R2DBC. Đây là một trong những chỗ dễ nhầm nhất khi chuyển đổi dự án.

### 6.1. Cấu hình R2DBC

Ví dụ `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Các thuộc tính cơ bản:

- `spring.r2dbc.url`: URL của R2DBC driver.
- `spring.r2dbc.username`: tài khoản database.
- `spring.r2dbc.password`: mật khẩu database.

Spring Boot dùng cấu hình này để tạo `ConnectionFactory` khi có starter và driver phù hợp. Các bean reactive như `DatabaseClient` và repository R2DBC có thể sử dụng connection factory được cấu hình.

### 6.2. Cấu hình JDBC

Ví dụ `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Các thuộc tính cơ bản:

- `spring.datasource.url`: URL của JDBC driver.
- `spring.datasource.username`: tài khoản database.
- `spring.datasource.password`: mật khẩu database.

Spring Boot dùng cấu hình này để tạo `DataSource` cho `JdbcTemplate`, JPA và các thành phần JDBC khác.

### 6.3. Những nhầm lẫn cần tránh

| Cấu hình sai | Vì sao sai? | Cấu hình cần dùng |
|---|---|---|
| Đặt URL `jdbc:postgresql:...` vào `spring.r2dbc.url` | R2DBC provider không nhận URL JDBC | Dùng `r2dbc:postgresql:...` |
| Đặt URL `r2dbc:postgresql:...` vào `spring.datasource.url` | JDBC driver không xử lý URL R2DBC | Dùng `jdbc:postgresql:...` |
| Chỉ thêm `org.postgresql:postgresql` nhưng dùng `DatabaseClient` | Classpath thiếu R2DBC driver | Thêm `org.postgresql:r2dbc-postgresql` |
| Chỉ thêm `org.postgresql:r2dbc-postgresql` nhưng dùng `JdbcTemplate` | Classpath thiếu JDBC driver | Thêm `org.postgresql:postgresql` |
| Dùng `spring.datasource.*` nhưng mong đợi R2DBC repository kết nối | Đây là namespace cấu hình JDBC | Cấu hình `spring.r2dbc.*` |
| Dùng `spring.r2dbc.*` nhưng mong đợi JPA dùng connection đó | JPA/Hibernate dùng JDBC `DataSource` | Cấu hình JDBC riêng cho JPA |

Nếu ứng dụng cần cả hai công nghệ, có thể có cả hai cấu hình trong cùng file:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Việc khai báo hai cấu hình không làm hai loại connection dùng chung một pool hoặc một transaction. JDBC và R2DBC có connection factory, pool và transaction manager riêng. Cần kiểm tra auto-configuration và khai báo bean rõ ràng nếu ứng dụng có nhiều `DataSource`, `ConnectionFactory` hoặc transaction manager.

## 7. Thông tin xác thực trong URL và cấu hình riêng

Một số driver cho phép đặt username và password trong URL. Ví dụ về hình thức:

```text
r2dbc:postgresql://app:secret@localhost:5432/orders
jdbc:postgresql://localhost:5432/orders
```

Với JDBC, username/password thường được truyền riêng qua `Properties`, `DriverManager` hoặc cấu hình `DataSource`. Với Spring Boot, cách dễ quản lý là dùng các thuộc tính `username` và `password` riêng như ví dụ ở trên.

Không nên đưa mật khẩu thật vào file cấu hình được commit hoặc URL xuất hiện trong log. URL có thể bị ghi lại trong log khởi động, báo lỗi, dashboard cấu hình hoặc thông tin chẩn đoán. Hãy dùng biến môi trường, secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai.

Nếu driver cho phép thông tin xác thực nằm trong URL, các ký tự đặc biệt như `@`, `:`, `/`, `?` và `#` có thể cần percent-encoding theo quy tắc parser của driver. Cách an toàn và dễ bảo trì hơn thường là tách username/password khỏi URL, trừ khi driver hoặc môi trường triển khai có yêu cầu khác.

## 8. Tham số tùy chọn và khác biệt giữa các driver

URL có thể chứa các tham số như SSL, timeout, schema, application name hoặc chế độ xác thực. Tuy nhiên, tên tham số, chữ hoa/chữ thường, giá trị hợp lệ và cách mã hóa phụ thuộc driver.

Ví dụ, JDBC PostgreSQL và R2DBC PostgreSQL có thể dùng những tên tùy chọn khác nhau hoặc diễn giải một tùy chọn theo cách khác nhau. Không nên sao chép toàn bộ phần query string của URL JDBC sang URL R2DBC mà không kiểm tra tài liệu driver.

Khi cần cấu hình SSL, hãy xác định:

1. Driver có hỗ trợ SSL/TLS hay không.
2. Tên option và các giá trị được driver chấp nhận.
3. Driver yêu cầu trust certificate, client certificate hoặc hostname verification như thế nào.
4. Cấu hình được truyền qua URL, `ConnectionFactoryOptions` hay thuộc tính riêng của Spring Boot.
5. Cách cấu hình hoạt động trong môi trường production và khi certificate được xoay vòng.

Không tắt kiểm tra certificate hoặc hostname chỉ để làm cho kết nối hoạt động trong production. Nếu kết nối TLS thất bại, hãy sửa trust chain, hostname hoặc cấu hình chứng thư theo yêu cầu của hệ thống.

Ngoài ra, URL R2DBC có thể được mở rộng bởi wrapper hoặc provider, ví dụ R2DBC Pool. Một cấu hình có thể có dạng:

```text
r2dbc:pool:postgresql://localhost:5432/orders
```

Tiền tố `r2dbc:pool:` yêu cầu provider pool tương ứng và driver cơ sở phải có mặt. Không phải mọi ứng dụng đều cần viết pool wrapper vào URL; Spring Boot có thể cấu hình pool qua các thuộc tính R2DBC khi dependency và phiên bản hỗ trợ. Hãy theo tài liệu của Spring Boot và R2DBC Pool đang sử dụng.

## 9. Khác biệt với database nhúng

Không phải mọi URL R2DBC đều có dạng `r2dbc:<driver>://host:port/database`. Với database nhúng hoặc in-memory, driver có thể dùng cú pháp riêng.

Ví dụ H2:

```text
JDBC:  jdbc:h2:mem:sample
R2DBC: r2dbc:h2:mem:///sample
```

Hai chuỗi cùng chỉ đến database in-memory có tên `sample`, nhưng cấu trúc URL khác nhau vì JDBC H2 driver và R2DBC H2 driver có quy ước riêng.

Khi chuyển database embedded từ JDBC sang R2DBC, cần xem lại:

- Cú pháp URL và cách đặt tên database.
- Database in-memory được chia sẻ giữa các connection như thế nào.
- Thời điểm database được tạo và đóng.
- Tùy chọn giữ database tồn tại khi connection cuối cùng đóng.
- Khả năng tương thích SQL và các tính năng của phiên bản H2.

Đừng suy luận rằng URL in-memory của JDBC có thể dùng nguyên trạng trong R2DBC chỉ vì tên database giống nhau.

## 10. URL không quyết định toàn bộ mô hình lập trình

Một URL bắt đầu bằng `r2dbc:` là dấu hiệu chọn R2DBC provider. Nó không tự động biến mọi phần của ứng dụng thành non-blocking.

Ví dụ:

```java
// R2DBC: trả về publisher reactive.
Mono<Customer> customer = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE id = :id
        """)
    .bind("id", 10L)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .one();
```

Trong khi đó, JDBC thường thực thi đồng bộ:

```java
// JDBC: gọi query và đọc ResultSet theo kiểu blocking.
Customer customer = jdbcTemplate.queryForObject(
    "SELECT id, name, email FROM customer WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getString("email")),
    10L
);
```

Nếu một ứng dụng WebFlux dùng JDBC trực tiếp trên event-loop thread, thao tác blocking vẫn có thể chặn thread dù endpoint trả về `Mono` hoặc `Flux`. Để dùng JDBC trong ứng dụng reactive, phải cô lập công việc blocking trên scheduler phù hợp và chấp nhận mô hình tài nguyên của JDBC. Nếu mục tiêu là truy cập database non-blocking theo reactive end-to-end, cần dùng R2DBC driver cùng các API reactive.

R2DBC không phải JDBC được đổi tên hoặc JDBC URL được bọc trong `Mono`. Đây là một SPI khác với driver và API connection riêng.

## 11. Quy trình chuyển cấu hình từ JDBC sang R2DBC

Khi chuyển một ứng dụng đang dùng JDBC sang Spring Data R2DBC, có thể thực hiện theo thứ tự sau:

### Bước 1: Xác định database và driver R2DBC

Kiểm tra hệ quản trị, phiên bản database, driver R2DBC được hỗ trợ và các tính năng ứng dụng cần dùng. Xác nhận driver có hỗ trợ kiểu dữ liệu, SSL, authentication, transaction và SQL dialect của dự án.

### Bước 2: Thay dependency phù hợp

Thêm starter R2DBC và driver R2DBC tương ứng. Chỉ giữ JDBC dependency nếu ứng dụng vẫn có thành phần dùng JDBC/JPA hoặc công cụ cần nó.

### Bước 3: Chuyển URL và namespace cấu hình

Ví dụ:

```properties
# Trước: JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}

# Sau: R2DBC
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/orders
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
```

Các dòng JDBC chỉ cần giữ nếu một phần khác của ứng dụng tiếp tục dùng JDBC. Không thay đổi prefix mà quên thay namespace và driver dependency.

### Bước 4: Kiểm tra option của driver

Đối chiếu các tùy chọn đang có trong URL JDBC với tài liệu R2DBC driver. Chuyển đổi từng tùy chọn một cách có chủ đích, đặc biệt là SSL, timeout, schema, authentication và pool.

### Bước 5: Thay API truy cập dữ liệu

Thay `DataSource`, `JdbcTemplate` hoặc JDBC repository bằng `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate` hoặc reactive repository phù hợp. Cập nhật kiểu trả về và cách xử lý lỗi sang `Mono`/`Flux`.

### Bước 6: Kiểm tra transaction và pooling

Kiểm tra transaction manager, giới hạn connection, timeout acquire và vòng đời subscription. JDBC transaction manager không quản lý transaction R2DBC; hai stack cần manager phù hợp với connection factory của chúng.

### Bước 7: Kiểm thử trên database mục tiêu

Chạy integration test với đúng database và driver sẽ triển khai. Kiểm tra truy vấn, mapping, generated key, transaction rollback, lỗi kết nối, timeout và hành vi khi publisher bị hủy.

## 12. Cách chẩn đoán lỗi URL và driver

Khi ứng dụng không kết nối được, hãy phân loại lỗi trước khi thay đổi URL tùy tiện.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `No suitable driver` khi dùng JDBC | Thiếu JDBC driver hoặc URL không đúng prefix/subprotocol | Kiểm tra dependency JDBC và URL `jdbc:` |
| Không tìm thấy R2DBC `ConnectionFactory` | Thiếu R2DBC driver hoặc URL không có provider phù hợp | Kiểm tra dependency R2DBC, driver name và prefix `r2dbc:` |
| Lỗi parse URL khi khởi động | Cú pháp không được driver hỗ trợ hoặc ký tự URL chưa được encode | So sánh với tài liệu đúng phiên bản driver |
| `Connection refused` | Host/port sai, database chưa chạy hoặc firewall chặn | Kiểm tra service, DNS, port và network policy |
| Authentication failed | Username, password hoặc cơ chế xác thực không đúng | Kiểm tra secret và phương thức xác thực của server |
| JDBC kết nối được nhưng R2DBC không kết nối được | Hai driver có option, SSL hoặc authentication khác nhau | Kiểm tra cấu hình và khả năng của R2DBC driver |
| R2DBC repository không tìm thấy connection factory | Chỉ cấu hình `spring.datasource.*` hoặc thiếu R2DBC starter | Cấu hình `spring.r2dbc.*` và dependency tương ứng |
| JPA không tìm thấy `DataSource` | Chỉ cấu hình R2DBC | Cấu hình JDBC `spring.datasource.*` nếu ứng dụng cần JPA |
| Kết nối chạy được nhưng quá nhiều connection | Pool chưa được cấu hình hoặc giới hạn không phù hợp | Kiểm tra R2DBC pool và ngân sách connection của database |

Một cách kiểm tra nhanh là xác nhận bốn thành phần khớp nhau:

```text
URL prefix
    |
    v
Driver dependency
    |
    v
Spring configuration namespace
    |
    v
Connection API / data-access abstraction
```

Ví dụ, một cấu hình R2DBC PostgreSQL cần có URL `r2dbc:postgresql:...`, R2DBC PostgreSQL driver, cấu hình `spring.r2dbc.*` và API sử dụng `ConnectionFactory`, `DatabaseClient` hoặc reactive repository.

## 13. Checklist cấu hình trước khi chạy ứng dụng

Trước khi khởi động hoặc triển khai, hãy xác nhận:

- [ ] Đã xác định ứng dụng dùng JDBC, R2DBC hay cả hai.
- [ ] Prefix URL khớp với SPI: `jdbc:` cho JDBC, `r2dbc:` cho R2DBC.
- [ ] Tên driver/provider trong URL được driver đã cài đặt hỗ trợ.
- [ ] Dependency đúng loại đã có trong runtime classpath.
- [ ] Namespace cấu hình Spring Boot đúng với công nghệ đang dùng.
- [ ] Host, port và database name trỏ đến môi trường mong muốn.
- [ ] Username/password được lấy từ secret hoặc biến môi trường.
- [ ] Các option SSL, timeout, schema và pool được kiểm tra theo tài liệu driver.
- [ ] Connection pool và transaction manager thuộc đúng connection stack.
- [ ] Integration test chạy với database và driver thực tế.

## 14. Nguyên tắc cần nhớ

- URL JDBC bắt đầu bằng `jdbc:` và được JDBC driver xử lý.
- URL R2DBC bắt đầu bằng `r2dbc:` và được R2DBC provider xử lý.
- Cùng host, port và database không có nghĩa hai URL có thể thay thế cho nhau.
- JDBC driver và R2DBC driver là hai dependency riêng, triển khai hai SPI khác nhau.
- Spring Boot thường dùng `spring.datasource.*` cho JDBC và `spring.r2dbc.*` cho R2DBC.
- Tên option và cách viết URL phụ thuộc driver; không sao chép nguyên query string giữa hai hệ sinh thái.
- URL R2DBC không tự chuyển code JDBC thành reactive; ứng dụng phải dùng API R2DBC end-to-end nếu cần non-blocking.

Khi phân biệt đúng URL, driver, dependency và namespace cấu hình, việc kết nối Spring Data R2DBC trở nên rõ ràng hơn. Hãy xem URL là một phần của hợp đồng giữa ứng dụng và driver: chọn đúng prefix, đúng provider và đúng tùy chọn cho công nghệ đang dùng, sau đó kiểm chứng kết nối bằng integration test trên database mục tiêu.
