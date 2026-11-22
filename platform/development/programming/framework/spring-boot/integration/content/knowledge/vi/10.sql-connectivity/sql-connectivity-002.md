# spring.datasource.* và suy luận JDBC driver từ URL

## Mục tiêu và bối cảnh

Trong chương **Kết nối SQL** của module **SPRING_BOOT_INTEGRATION**, một ứng dụng Spring Boot có thể đọc dữ liệu từ PostgreSQL, MySQL, SQL Server hoặc một cơ sở dữ liệu khác để phối hợp với HTTP client, cache, message broker và các adapter của Spring Integration. Trước khi viết repository hay transaction, ứng dụng cần biết **kết nối tới cơ sở dữ liệu nào, lấy tài khoản ở đâu và sử dụng JDBC driver nào**.

Spring Boot giải quyết phần lớn công việc cấu hình thường gặp thông qua nhóm thuộc tính `spring.datasource.*`, bean `DataSource` và cơ chế auto-configuration. Đặc biệt, nếu đã khai báo JDBC URL thuộc một loại cơ sở dữ liệu mà Boot nhận diện, thông thường **không cần cấu hình `spring.datasource.driver-class-name`**: Boot suy ra tên lớp driver từ URL.

Bài học tập trung vào chính cơ chế này trong bối cảnh tích hợp hệ thống thực tế, bao gồm cấu hình theo môi trường, hợp đồng dữ liệu, kết nối pool, giao dịch, lỗi, kiểm thử và quan sát.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `spring.datasource.url`, JDBC driver, `DataSource`, connection pool và code truy cập SQL.
- Khai báo `spring.datasource.url`, `username`, `password` và các tùy chỉnh pool mà không đặt bí mật trong mã nguồn.
- Biết khi nào Boot suy ra được driver từ JDBC URL và khi nào cần cấu hình `driver-class-name`.
- Phân biệt lỗi **không tìm thấy driver**, **sai URL**, **không kết nối được**, **sai tài khoản** và **cạn connection pool**.
- Hiểu tác động của một hoặc nhiều `DataSource` đối với transaction, migration, test và observability.
- Sử dụng kết nối SQL như một adapter có trách nhiệm rõ ràng trong luồng tích hợp.

## 1. Các tầng trong một kết nối SQL của Spring Boot

Một lời gọi SQL không đi trực tiếp từ service tới database. Thông thường có các tầng:

~~~mermaid
flowchart TD
    A["application.yml + environment"] --> B["DataSourceProperties"]
    B --> C["DataSourceAutoConfiguration"]
    C --> D["DataSource / connection pool"]
    E["JDBC driver từ classpath"] --> D
    F["JdbcTemplate / Spring Data JPA"] --> D
    G["Business service / SQL adapter"] --> F
    D --> H["Database server"]
    I["Transaction manager"] --> D
    J["Actuator / Micrometer"] -.-> D
~~~

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `spring.datasource.*` | Cấu hình kết nối do người vận hành cung cấp | URL, username, password |
| `DataSourceProperties` | Bind cấu hình cơ bản và xác định thông tin kết nối | Kiểu properties của Boot |
| `DataSourceAutoConfiguration` | Đăng ký `DataSource` phù hợp nếu điều kiện thỏa mãn | Chọn implementation pooling |
| JDBC driver | Hiểu giao thức JDBC cụ thể của database | `org.postgresql.Driver` |
| `DataSource` | Cấp `Connection` cho code truy cập dữ liệu | `HikariDataSource` |
| Connection pool | Giữ và tái sử dụng kết nối để tránh mở mới mỗi lần | HikariCP |
| `JdbcTemplate` / JPA | Thực thi SQL hoặc ánh xạ đối tượng | `JdbcTemplate.queryForObject(...)` |
| `PlatformTransactionManager` | Điều phối transaction cục bộ phù hợp | `JdbcTransactionManager` / `JpaTransactionManager` |

**Phân biệt quan trọng:** JDBC URL không phải một kết nối đang mở. URL mô tả nơi kết nối và kiểu giao thức; driver thực hiện kết nối; `DataSource`/pool quản lý vòng đời kết nối; repository hay template sử dụng kết nối đó.

Trong một hệ thống nhận sự kiện từ broker, ghi vào database và gửi HTTP request, `@Transactional` thông thường chỉ bao phủ các resource tham gia transaction được cấu hình, **không tự mở rộng thành một transaction phân tán** tới message broker hoặc dịch vụ HTTP bên ngoài.

## 2. Tạo DataSource với Spring Boot

### 2.1. Dependency tối thiểu cho JDBC

Ví dụ Gradle Groovy DSL khi dùng PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

`spring-boot-starter-jdbc` đưa vào hạ tầng Spring JDBC và connection pool mặc định phù hợp (thường là HikariCP). `org.postgresql:postgresql` là **JDBC driver thực tế**, cần hiện diện ở runtime. Khi dùng plugin/BOM quản lý dependency của Spring Boot, không cần tự điền version cho những dependency đã được BOM quản lý.

Nếu ứng dụng dùng Spring Data JPA, starter JPA thường đã bao gồm hạ tầng JDBC/pooling liên quan; không cần cài trùng starter chỉ để có `DataSource`. Tuy nhiên **vẫn cần driver riêng** cho database đã chọn. Với database khác, thay driver PostgreSQL bằng driver tương ứng.

| Loại database | Dependency driver thường gặp | Lưu ý |
| --- | --- | --- |
| PostgreSQL | `org.postgresql:postgresql` | Runtime scope thường đủ |
| MySQL | `com.mysql:mysql-connector-j` | Không dùng tên driver `com.mysql.jdbc.Driver` cũ |
| MariaDB | `org.mariadb.jdbc:mariadb-java-client` | Khác driver MySQL |
| Microsoft SQL Server | `com.microsoft.sqlserver:mssql-jdbc` | Xem yêu cầu JDK và version phù hợp |
| Oracle Database | `com.oracle.database.jdbc:ojdbc11` hoặc artifact tương thích JDK | Chọn driver theo JDK/Boot đang dùng |
| H2 | `com.h2database:h2` | Thường dùng cho test/dev |

**Không chỉ thêm starter JDBC rồi kỳ vọng Boot tự tải driver từ Internet theo URL.** Việc chọn tên class driver và việc có JAR driver ở classpath là hai bước khác nhau.

### 2.2. DataSourceAutoConfiguration kích hoạt khi nào?

Ở trường hợp thông thường, Spring Boot xem xét tạo `DataSource` khi:

- Các lớp JDBC/`DataSource` cần thiết có trên classpath.
- Không có bean `DataSource` do ứng dụng tự định nghĩa khiến auto-configuration mặc định phải nhường chỗ.
- Không có điều kiện loại trừ auto-configuration; đặc biệt, khi ứng dụng cung cấp bean R2DBC `ConnectionFactory`, auto-configuration JDBC thường nhường chỗ theo điều kiện của Boot.
- Có đủ thông tin để xây dựng `DataSource`: URL/driver phù hợp hoặc một embedded database được hỗ trợ.

Spring Boot cố gắng ưu tiên connection pool có sẵn; khi HikariCP nằm trên classpath cùng starter JDBC, Hikari thường được chọn. Ứng dụng có thể chỉ định implementation qua `spring.datasource.type` khi có nhu cầu đặc biệt.

Không cần tạo thủ công:

~~~java
// Thường KHÔNG cần trong ứng dụng Boot JDBC tiêu chuẩn:
@Bean
DataSource dataSource() {
    // Tự đọc URL, tài khoản và khởi tạo connection pool...
    return ...;
}
~~~

Khai báo bean `DataSource` riêng sẽ khiến một số auto-configuration mặc định **back off**; khi ấy ứng dụng phải chịu trách nhiệm cấu hình thuộc tính, pool, transaction và tác động đến các bean khác.

## 3. Cấu hình spring.datasource.* qua application.yml

Ví dụ ứng dụng xử lý đơn hàng và ghi vào PostgreSQL:

~~~yaml
# application.yml
spring:
  datasource:
    url: ${DB_JDBC_URL:jdbc:postgresql://localhost:5432/orders_db}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s
      validation-timeout: 1s
~~~

Địa chỉ `localhost`, tên database và tài khoản chỉ là **ví dụ cho môi trường phát triển**. Biến `DB_PASSWORD` phải được cấp từ môi trường/secret manager, không đưa giá trị thật vào repository hoặc ví dụ tài liệu.

| Property | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `spring.datasource.url` | JDBC URL tới DB | Thường đủ để Boot nhận diện driver |
| `spring.datasource.username` | Username kết nối | Quyền tối thiểu theo tác vụ |
| `spring.datasource.password` | Password kết nối | Lấy từ secret/config provider |
| `spring.datasource.driver-class-name` | Tên lớp JDBC driver (tùy chọn) | Chỉ đặt khi cần hoặc URL không suy luận được |
| `spring.datasource.type` | Implementation `DataSource` | Chỉ định khi không dùng lựa chọn mặc định |
| `spring.datasource.hikari.pool-name` | Tên pool Hikari | Dùng tên ổn định để quan sát |
| `spring.datasource.hikari.maximum-pool-size` | Số kết nối tối đa pool | Phải khớp năng lực DB và số replica |
| `spring.datasource.hikari.connection-timeout` | Thời gian tối đa chờ lấy connection từ pool | Không phải SQL query timeout |
| `spring.datasource.hikari.validation-timeout` | Giới hạn chờ kiểm tra connection hợp lệ | Phải hợp lý với connection timeout |

Boot bind cấu hình nhờ cơ chế **relaxed binding**. Ví dụ, khóa YAML `spring.datasource.url` cũng có thể được cấp qua biến môi trường chuẩn `SPRING_DATASOURCE_URL`; khóa `spring.datasource.hikari.maximum-pool-size` tương ứng `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE`. Các property source có thứ tự ưu tiên theo cơ chế externalized configuration của Spring Boot; vì vậy cần xác minh cấu hình thực sự được áp dụng tại runtime.

### 3.1. Vì sao tách nhóm datasource và hikari?

- `spring.datasource.*` chứa cấu hình kết nối cơ bản, được `DataSourceProperties` của Boot xử lý.
- `spring.datasource.hikari.*` chứa các thuộc tính riêng của HikariCP.
- Nếu Boot chọn pool khác Hikari, những khóa `spring.datasource.hikari.*` không phải cấu hình chung cho mọi implementation.
- Không nên tùy tiện đặt `spring.datasource.hikari.jdbc-url` thay cho `spring.datasource.url` trong cấu hình Boot tiêu chuẩn. Nhóm `spring.datasource.url` được Boot thiết kế để bind qua `DataSourceProperties` và xử lý khác biệt giữa tên URL của pool.

Một ví dụ cấu hình thay thế từ biến môi trường:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db.internal:5432/orders_db
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=<giá trị do secret manager cấp>
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=12
~~~

Dòng password ở đây là ký hiệu minh họa, không phải mật khẩu hợp lệ. Không in giá trị password vào log, trace hoặc output của lệnh kiểm tra cấu hình.

### 3.2. Cấu hình theo môi trường và profile

Có thể dùng file profile để đặt các thông số **không bí mật** theo môi trường:

~~~yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
  hikari:
    maximum-pool-size: 4
~~~

~~~yaml
# application-prod.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 2s
~~~

Ở ví dụ production, URL, username, password nên lấy từ biến môi trường hoặc secret store. Các giá trị profile chỉ áp dụng khi profile tương ứng được kích hoạt và có thể bị nguồn cấu hình ưu tiên cao hơn ghi đè.

Cần cân nhắc **tổng số kết nối = pool tối đa mỗi instance × số instance đang chạy**, cộng các kết nối của migration, job, monitoring và workload khác. Pool 20 connections ở 10 replicas có thể đòi đến 200 connections, không phải 20.

## 4. Boot suy luận JDBC driver từ URL như thế nào?

### 4.1. Quy tắc chung

Một JDBC URL có tiền tố `jdbc:` và phần định danh của driver, ví dụ `jdbc:postgresql:` hoặc `jdbc:mysql:`. Khi `spring.datasource.driver-class-name` không được khai báo, Spring Boot dùng thông tin từ URL để xác định loại database mà nó nhận biết rồi tìm tên class driver mặc định tương ứng.

Có thể hình dung logic quyết định ở mức khái niệm:

~~~text
Có spring.datasource.driver-class-name?
  |
  +-- Có  --> dùng tên driver được cấu hình, kiểm tra classpath
  |
  +-- Không
        |
        +-- Có JDBC URL Boot nhận diện?
        |      |
        |      +-- Có --> suy ra tên lớp driver từ URL
        |      +-- Không --> cần driver explicit hoặc cấu hình khác
        |
        +-- Không có URL nhưng có embedded DB hỗ trợ?
               |
               +-- Có --> Boot có thể tạo DataSource nhúng
               +-- Không --> không đủ thông tin kết nối
~~~

Đây là mô tả **hành vi**, không phải mã nguồn nguyên văn của Boot. Lớp `DataSourceProperties` có trách nhiệm xác định driver/URL cần dùng, trong đó Boot sử dụng danh mục driver nhận diện từ JDBC URL (như `DatabaseDriver`). Chỉ đọc URL để **suy luận tên class**, không chủ động hỏi database server đang chạy loại nào.

### 4.2. Bảng URL và driver phổ biến

| JDBC URL mẫu | JDBC driver được nhận diện thông thường |
| --- | --- |
| `jdbc:postgresql://db.example:5432/orders_db` | `org.postgresql.Driver` |
| `jdbc:mysql://db.example:3306/orders_db` | `com.mysql.cj.jdbc.Driver` |
| `jdbc:mariadb://db.example:3306/orders_db` | `org.mariadb.jdbc.Driver` |
| `jdbc:sqlserver://db.example:1433;databaseName=orders_db` | `com.microsoft.sqlserver.jdbc.SQLServerDriver` |
| `jdbc:oracle:thin:@//db.example:1521/ORCLPDB1` | `oracle.jdbc.OracleDriver` |
| `jdbc:h2:mem:orders_test` | `org.h2.Driver` |
| `jdbc:hsqldb:mem:orders_test` | `org.hsqldb.jdbc.JDBCDriver` |

Các tên class trên là ví dụ điển hình theo JDBC driver hiện đại. Boot phiên bản khác nhau có thể bổ sung hoặc thay đổi danh mục URL được nhận biết; với driver đặc thù, hãy tra hướng dẫn của vendor và chọn explicit class khi cần.

**Ba điều kiện để kết nối thành công:**

1. URL đúng cú pháp và đúng database endpoint.
2. JAR của JDBC driver phù hợp nằm trên runtime classpath.
3. Mạng, TLS, tài khoản, quyền truy cập và database server đều đáp ứng.

Boot suy ra đúng `org.postgresql.Driver` **không đồng nghĩa** đã có JAR PostgreSQL trong build. Ngược lại, có JAR đúng nhưng URL sai host/port hay password thì vẫn không kết nối được.

### 4.3. Không cần khai báo driver-class-name trong trường hợp phổ biến

Với:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_db
    username: orders_app
    password: ${DB_PASSWORD}
~~~

và dependency:

~~~groovy
runtimeOnly 'org.postgresql:postgresql'
~~~

Boot thường có đủ thông tin chọn `org.postgresql.Driver`. Đặt thêm:

~~~yaml
spring:
  datasource:
    driver-class-name: org.postgresql.Driver
~~~

là hợp lệ nhưng thường **dư thừa**. Việc khai báo chỉ để “cho chắc” có thể gây sai sót khi chuyển từ PostgreSQL sang MySQL hoặc khi driver được thay thế.

### 4.4. Khi nào cần driver-class-name?

Có những JDBC URL sử dụng tiền tố hoặc lớp driver mà danh mục mặc định của Boot chưa nhận biết:

- Database/driver ít phổ biến hoặc do vendor cung cấp.
- URL của một proxy/wrapper như JDBC instrumentation đặc thù.
- Driver JDBC dùng cú pháp URL riêng không được Boot ánh xạ.
- Ứng dụng cần chủ động chọn driver khác trong số những driver hỗ trợ URL tương ứng.

Khi đó có thể cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:vendorx://db.example:9999/orders_db
    driver-class-name: com.vendorx.jdbc.Driver
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

**Đây là ví dụ giả định**, không phải một driver/vendor có thật. Bạn vẫn phải thêm JAR đúng cho `com.vendorx.jdbc.Driver` và xác minh driver chấp nhận URL.

Nếu chỉ đặt `driver-class-name` mà **không có URL**, Boot không thể tự biết hostname, port và database name của một DB ngoài. Ngoại lệ khi ứng dụng sử dụng embedded database, JNDI datasource, hoặc cơ chế cấu hình đặc thù đã được triển khai.

### 4.5. Phân biệt suy luận của Boot và DriverManager

JDBC chuẩn có cơ chế đăng ký driver (SPI) để `DriverManager` tìm driver có thể xử lý URL. Spring Boot còn có cơ chế **suy luận một class driver được biết trước từ URL** để tạo `DataSource`.

Vì vậy:

- Có driver JAR trên classpath là điều kiện cần cho driver cụ thể.
- Danh mục URL của Boot không bao phủ mọi JDBC driver tồn tại trên thế giới.
- Nếu URL không được Boot hiểu, driver có thể vẫn hợp lệ theo JDBC, nhưng cấu hình Boot có thể yêu cầu `driver-class-name` hoặc bean `DataSource` chuyên biệt.
- Không dùng `driver-class-name` của JDBC để cấu hình kết nối R2DBC. R2DBC có `spring.r2dbc.url` và `ConnectionFactory` riêng.

## 5. Ví dụ thực tế: DataSource → JdbcTemplate → SQL adapter

Giả sử adapter cần lấy trạng thái đơn hàng khi có thông điệp từ broker. Dùng `spring-boot-starter-jdbc`, PostgreSQL driver và YAML ở phần 3, Boot tự tạo `DataSource` và cấu hình `JdbcTemplate` trong ngữ cảnh tiêu chuẩn.

Tạo bảng (quản lý bằng migration Flyway/Liquibase trong hệ thống thực):

~~~sql
CREATE TABLE integration_orders (
    order_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    last_event_id VARCHAR(100) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

DTO đại diện kết quả đọc:

~~~java
// OrderStatus.java
public record OrderStatus(String orderId, String status) {
}
~~~

Adapter SQL:

~~~java
// JdbcOrderStatusAdapter.java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStatusAdapter {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderStatusAdapter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public OrderStatus findById(String orderId) {
        return jdbcTemplate.queryForObject(
                """
                SELECT order_id, status
                FROM integration_orders
                WHERE order_id = ?
                """,
                (rs, rowNum) -> new OrderStatus(
                        rs.getString("order_id"),
                        rs.getString("status")),
                orderId);
    }
}
~~~

Tại đây:

1. `JdbcOrderStatusAdapter` nhận `JdbcTemplate` từ Spring container.
2. `JdbcTemplate` lấy connection từ `DataSource` đã được Boot cấu hình.
3. Connection pool sử dụng JDBC driver PostgreSQL phù hợp URL để giao tiếp với DB.
4. Query dùng placeholder `?` thay vì ghép chuỗi SQL, giúp truyền giá trị tham số đúng cách.
5. `queryForObject(...)` cần đúng một hàng: nếu không tìm thấy, Spring có thể ném `EmptyResultDataAccessException`. Adapter nên chuyển thành kiểu kết quả nghiệp vụ phù hợp.

Trong ứng dụng lớn, nên định nghĩa **port** như `OrderStatusPort` ở tầng nghiệp vụ và để adapter JDBC triển khai port đó. Như vậy những phần xử lý HTTP, cache hay broker không phải phụ thuộc trực tiếp vào `JdbcTemplate`.

### 5.1. Lưu dữ liệu và dùng transaction đúng ranh giới

Một thao tác cập nhật có thể được đặt trong một application service được Spring quản lý:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderUpdateService {

    private final OrderStore orderStore;
    private final InboxStore inboxStore;

    public OrderUpdateService(
            OrderStore orderStore,
            InboxStore inboxStore) {
        this.orderStore = orderStore;
        this.inboxStore = inboxStore;
    }

    @Transactional
    public void apply(OrderEvent event) {
        boolean firstTime =
                inboxStore.insertIfAbsent(event.eventId());

        if (!firstTime) {
            return;
        }

        orderStore.applyBusinessChange(event);
    }
}
~~~

`OrderStore`, `InboxStore` và `OrderEvent` ở đây là các hợp đồng minh họa, không phải kiểu có sẵn của Spring. `insertIfAbsent` phải được hiện thực bằng thao tác **nguyên tử** với unique constraint tại database, ví dụ `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL. Hai thao tác DB phải tham gia **cùng transaction** và cùng resource manager để rollback dấu inbox khi cập nhật nghiệp vụ thất bại.

Những điểm cần nhớ:

- Connection được pool cấp phát không đồng nghĩa mỗi repository tự tạo transaction.
- `@Transactional` thường có hiệu lực khi lời gọi đi qua Spring proxy, không phải self-invocation thông thường.
- Transaction manager phải trỏ đúng `DataSource` mà adapter sử dụng, đặc biệt nếu hệ thống có nhiều DB.
- Một HTTP request ra đối tác hoặc một broker publish **không** tự rollback chỉ vì transaction SQL tại chỗ thất bại.
- Với cập nhật DB rồi phát sự kiện ra broker, cân nhắc **transactional outbox** để tránh mất sự kiện sau commit và idempotent consumer để chịu được redelivery.

## 6. HikariCP: cấu hình pool và hiểu ý nghĩa timeout

Khi dùng starter JDBC với HikariCP trên classpath, Boot thường chọn `HikariDataSource`. Pool hạn chế số kết nối thật cần mở và tái sử dụng chúng.

Các thông số phổ biến:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 3s
      idle-timeout: 10m
      max-lifetime: 30m
      validation-timeout: 1s
~~~

Giá trị chỉ minh họa; không có bộ thông số tối ưu cho mọi database hoặc workload. Tùy topology, số replica và độ trễ query, một pool nhỏ hoạt động ổn định có thể hiệu quả hơn pool rất lớn.

| Thuộc tính | Điều khiển | Không nên hiểu nhầm thành |
| --- | --- | --- |
| `maximum-pool-size` | Giới hạn connection đang nằm trong pool | Số SQL statement có thể chạy vô hạn |
| `minimum-idle` | Số connection nhàn rỗi tối thiểu Hikari cố gắng duy trì | Mức throughput tối thiểu |
| `connection-timeout` | Thời gian chờ pool cấp connection | Timeout mở TCP hoặc timeout toàn query |
| `idle-timeout` | Cách pool thu hẹp connection nhàn rỗi theo điều kiện | TTL dữ liệu hoặc TTL transaction |
| `max-lifetime` | Giới hạn vòng đời tối đa của connection trong pool | Timeout query đang thực thi |
| `validation-timeout` | Thời gian xác thực connection | Timeout nghiệp vụ end-to-end |

Pool được Hikari quản lý đồng thời với vòng đời application. Nếu database có timeout kết nối tại phía server/load balancer, `max-lifetime` nên được cân nhắc để giảm tái sử dụng connection đã chết. Không đặt giá trị tùy ý mà không đo độ trễ và hành vi của hệ thống.

**Ba loại timeout tách biệt:**

1. **Lấy connection từ pool:** `spring.datasource.hikari.connection-timeout`.
2. **Kết nối mạng/driver:** ví dụ connect/socket timeout do JDBC driver hỗ trợ, thường cấu hình bằng driver-specific properties.
3. **Thực thi SQL/transaction:** query timeout, transaction timeout, hoặc cơ chế hủy tác vụ SQL theo driver/database.

Tăng `maximum-pool-size` không sửa được một SQL query chậm do thiếu index. Ngược lại, connection pool bị cạn có thể là hệ quả của long-running transaction, quên đóng connection ở code JDBC thủ công hoặc lượng request vượt khả năng DB.

### 6.1. Driver-specific properties

Khi driver cần cấu hình chi tiết như application name, socket timeout hoặc SSL, có thể dùng JDBC URL hoặc nhóm property chuyển tiếp vào driver:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        ApplicationName: order-integration
~~~

`ApplicationName` ở ví dụ trên là thuộc tính PostgreSQL JDBC; **không phải** thuộc tính áp dụng cho mọi driver. Mỗi vendor có bộ tên, kiểu giá trị và đơn vị thời gian riêng. Trước khi cấu hình, kiểm tra tài liệu driver. Với SSL/TLS, không vô hiệu hóa kiểm tra chứng chỉ chỉ để né lỗi chứng chỉ trong production.

## 7. Điều gì xảy ra khi thiếu URL hoặc có embedded database?

Spring Boot hỗ trợ embedded database như H2, HSQLDB hoặc Derby khi dependency và cấu hình phù hợp. Trong một số trường hợp không có `spring.datasource.url`, Boot có thể tạo `DataSource` nhúng:

~~~groovy
// Ví dụ trong test hoặc demo
runtimeOnly 'com.h2database:h2'
~~~

Việc này thuận tiện cho học tập và test, nhưng có hai rủi ro:

1. Nếu quên cấu hình PostgreSQL URL trong môi trường không mong muốn, ứng dụng có thể khởi động với DB nhúng khi H2 nằm trên runtime classpath.
2. Cú pháp SQL, transaction isolation, kiểu dữ liệu, index và constraint của H2 **không hoàn toàn giống** PostgreSQL hay MySQL.

Vì vậy không coi test bằng H2 là đủ cho các truy vấn đặc thù PostgreSQL, cú pháp `ON CONFLICT`, transaction isolation hoặc behavior của driver. Với luồng quan trọng, dùng Testcontainers hoặc database test thực gần production.

Nếu **không** có URL và cũng không có embedded DB đủ điều kiện, lỗi cấu hình thường gặp là dạng:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.

Reason: Failed to determine a suitable driver class
~~~

Thông điệp cụ thể thay đổi theo Boot version. Đây là dấu hiệu cần kiểm tra **cấu hình URL, driver và classpath** trước khi sửa logic repository.

## 8. Lỗi khi suy luận driver và cách chẩn đoán

Không nên gộp mọi lỗi kết nối thành “database down”.

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `Failed to determine a suitable driver class` | Thiếu URL, URL không được Boot nhận diện, không có embedded DB | Xem `spring.datasource.url` và cần thiết thêm `driver-class-name` |
| `Cannot load driver class: org.postgresql.Driver` | Thiếu driver JAR tại runtime hoặc khai báo class sai | Xem runtime classpath/dependencies |
| `No suitable driver` | Driver không nhận URL, sai cú pháp URL hoặc chưa đăng ký driver phù hợp | So khớp URL với driver đang dùng |
| `Connection refused` | Server không mở cổng, host/port sai hoặc bị chặn mạng | Kiểm tra DNS, route, firewall, port, DB service |
| `Connection timed out` | Mạng/TLS/DB không đáp ứng đúng thời gian | Kiểm tra timeout từng lớp và log server |
| `password authentication failed` / `Access denied` | Tài khoản, secret hoặc quyền sai | Kiểm tra secret injection, chính sách DB và user |
| `database does not exist` | DB name sai hoặc chưa provisioning | Kiểm tra tên DB/schema và quyền tạo DB |
| `Connection is not available, request timed out` | Pool cạn, DB quá tải hoặc leak connection | Kiểm tra active/idle/pending pool và slow queries |
| `Table ... does not exist` | Chưa chạy migration hoặc sai schema | Kiểm tra Flyway/Liquibase và default schema |
| `Unknown property hikari...` hoặc cấu hình không hiệu lực | Sai prefix/kiểu property hoặc dùng pool khác | Kiểm tra metadata và implementation thực tế |
| App có R2DBC nhưng không tạo JDBC DataSource | `ConnectionFactory` làm JDBC auto-config back off theo điều kiện Boot | Cấu hình tường minh nếu cần cả hai stack |

**Thứ tự chẩn đoán hợp lý:**

1. Xác nhận profile và property source thực sự đang dùng, chỉ hiển thị thông tin **không bí mật**.
2. Kiểm tra URL có bắt đầu bằng `jdbc:` và dùng đúng định dạng vendor.
3. Kiểm tra driver JAR thuộc runtime classpath, không chỉ test classpath.
4. Xác minh tên lớp driver nếu cấu hình `driver-class-name`.
5. Thử kết nối mạng đến host/port database với công cụ được phép dùng tại môi trường.
6. Kiểm tra tài khoản, TLS, database name và permission.
7. Nếu pool khởi tạo được nhưng truy vấn lỗi, kiểm tra schema, migration, SQL và transaction.

Trong production, không in `spring.datasource.password`, raw JDBC URL chứa secret hoặc full connection properties vào log. Một số driver cho phép password trong URL/query parameters; nên tránh cách đó để giảm rủi ro lộ bí mật qua log và trace.

### 8.1. Một số sai sót phổ biến

**Sai 1: Driver URL khác với dependency.**

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example:3306/orders_db
    driver-class-name: org.postgresql.Driver
~~~

URL MySQL nhưng driver PostgreSQL là sự kết hợp sai. Bỏ cấu hình explicit nếu Boot nhận diện URL và thêm driver MySQL đúng, hoặc sửa cả URL và dependency theo database cần kết nối.

**Sai 2: Dùng URL không có tiền tố `jdbc:`.**

~~~yaml
spring:
  datasource:
    url: postgresql://db.example:5432/orders_db
~~~

Đây không phải URL JDBC thông dụng mà `DataSource` driver PostgreSQL mong đợi. Với PostgreSQL JDBC, cần `jdbc:postgresql://...`.

**Sai 3: Dùng R2DBC URL làm JDBC URL.**

~~~yaml
spring:
  datasource:
    url: r2dbc:postgresql://db.example:5432/orders_db
~~~

`r2dbc:` thuộc stack R2DBC; không phải `spring.datasource.url` cho JDBC. Nếu dùng R2DBC, phải cấu hình `spring.r2dbc.*` và dependency driver R2DBC tương ứng.

**Sai 4: Đọc `spring.datasource.hikari.jdbc-url` rồi bỏ qua `spring.datasource.url`.**

Trong cấu hình Boot tiêu chuẩn, nên đặt `spring.datasource.url` để Boot bind các thông số cơ bản và suy luận driver. Chỉ dùng cấu hình Hikari `jdbcUrl` trực tiếp khi có lý do rõ ràng, đặc biệt khi tự tạo `HikariDataSource`; trường hợp đó có quy tắc binding khác.

## 9. SQL schema, migration và thứ tự khởi tạo

**Kết nối thành công** không có nghĩa database đã có schema ứng dụng cần. Những trách nhiệm này tách biệt:

- Tạo database/user/permission: provisioning của hạ tầng.
- Định nghĩa bảng/index/constraint: migration và quản trị schema.
- Chọn DB URL + driver + pool: cấu hình kết nối.
- Thực hiện nghiệp vụ: repository, JdbcTemplate, JPA hoặc adapter.
- Giao dịch/khả năng phục hồi: transaction manager, outbox/inbox và retry.

Spring Boot có thể chạy các script `schema.sql` và `data.sql` khi được cấu hình phù hợp. Khóa `spring.sql.init.mode` điều khiển việc chạy SQL initialization, với hành vi mặc định và giới hạn phụ thuộc embedded database và các điều kiện của Boot.

Ví dụ chỉ minh họa cho môi trường demo:

~~~yaml
spring:
  sql:
    init:
      mode: always
~~~

**Không bật `always` trong production chỉ để tự tạo schema ở mỗi lần deploy.** Với hệ thống thực, ưu tiên Flyway hoặc Liquibase để có migration được version hóa, kiểm soát thứ tự và lịch sử thay đổi. Cần thiết lập rõ thứ tự chạy migration trước khi service bắt đầu đọc/ghi dữ liệu.

Nếu ứng dụng dùng JPA, các property như `spring.jpa.hibernate.ddl-auto` quản lý cơ chế schema của Hibernate, **không phải** thay thế cho `spring.datasource.*`. Tránh cấu hình nhiều cơ chế tự tạo/sửa bảng cạnh tranh nhau.

## 10. Cấu hình nhiều DataSource: giới hạn của trường hợp mặc định

`spring.datasource.*` được thiết kế thuận tiện cho **DataSource mặc định**. Nếu ứng dụng đọc dữ liệu từ database kế toán và ghi sang database đơn hàng, cần phân biệt rõ hai DataSource và transaction manager.

Ví dụ thuộc tính riêng của ứng dụng:

~~~yaml
app:
  datasource:
    orders:
      url: ${ORDERS_DB_URL}
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
    reporting:
      url: ${REPORTING_DB_URL}
      username: ${REPORTING_DB_USER}
      password: ${REPORTING_DB_PASSWORD}
~~~

`app.datasource.*` **không được Boot tự tạo thành hai DataSource** chỉ vì xuất hiện trong YAML. Phải tự định nghĩa bean với `@ConfigurationProperties`, `DataSourceProperties`/`DataSourceBuilder`, đặt `@Primary` cho default khi cần và cấu hình `JdbcTemplate`/transaction manager của từng nguồn một cách nhất quán.

Một lỗi thường gặp là bind trực tiếp thuộc tính `url` lên `HikariDataSource` tạo bằng tay. Hikari sử dụng property `jdbcUrl`, trong khi `DataSourceProperties` của Boot hiểu `url` và ánh xạ phù hợp khi dùng `initializeDataSourceBuilder()`. Vì vậy nên tái sử dụng cơ chế `DataSourceProperties` cho mỗi nhóm thuộc tính riêng.

Với nhiều database:

- Gắn `@Qualifier` cho DataSource, JdbcTemplate và transaction manager theo từng adapter.
- Nếu dùng `@Transactional`, xác định rõ transaction manager cho đúng resource.
- Phân biệt “hai DataSource cùng một PostgreSQL server” và “hai database độc lập” vì atomicity/commit khác nhau.
- Giao dịch giữa hai DB hoặc DB và broker không mặc định atomic; khi cần độ tin cậy xuyên hệ thống, cân nhắc outbox, saga hoặc cơ chế bù trừ.
- Quan sát riêng từng pool, giữ tên pool có cardinality thấp và không đưa tenant ID vào tên pool theo mỗi request.

Khi ứng dụng đồng thời có R2DBC `ConnectionFactory` và JDBC `DataSource`, có thể phải định nghĩa rõ thành phần JDBC thay vì dựa vào auto-configuration mặc định; không giả định thêm hai starter sẽ tự tạo đầy đủ cả hai kết nối.

## 11. Độ tin cậy của adapter SQL trong luồng tích hợp

### 11.1. Khi nhận sự kiện có thể gửi lại

Broker thường có khả năng redelivery. Một consumer có thể:

1. Nhận `OrderPaid(eventId=E-100)`.
2. Ghi trạng thái đơn hàng trong SQL.
3. Crash trước khi acknowledge broker.
4. Nhận lại cùng message sau khi khởi động.

Driver suy luận đúng từ URL và connection pool chạy khỏe **không ngăn được tác động trùng**. Để tránh ghi lặp, dùng idempotency key ổn định trong hợp đồng dữ liệu và unique constraint trong database.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Trong một transaction, consumer cố insert `event_id`; nếu sự kiện đã tồn tại thì không áp dụng lại tác động nghiệp vụ. Cách diễn giải lỗi unique constraint, retry và transaction rollback phụ thuộc database/driver. Đừng dùng chuỗi thao tác `SELECT exists` rồi `INSERT` không được bảo vệ nguyên tử trong hệ thống nhiều consumer.

### 11.2. Lỗi không xác định kết quả

Nếu lệnh SQL ghi trả lỗi mạng sau khi gửi, client có thể **không biết chắc server đã commit hay chưa**. Điều này càng quan trọng nếu transaction đã đến ranh giới commit. Retry một thao tác tạo dữ liệu mà không có idempotency có thể tạo bản ghi mới hoặc tác động trùng.

Nên tách các loại lỗi:

| Lỗi | Tính chất | Cách xử lý gợi ý |
| --- | --- | --- |
| Sai SQL/schema | Không phải lỗi tạm thời của kết nối | Sửa migration/SQL, không retry liên tục |
| Vi phạm unique key | Có thể là duplicate nghiệp vụ hoặc dữ liệu sai | Kiểm tra hợp đồng trước khi quyết định bỏ qua |
| Deadlock/serialization conflict | Có thể retry transaction khi an toàn | Retry giới hạn, backoff, idempotency |
| Mất kết nối trước thao tác | Có thể retry khi xác định chưa có side effect | Cần giới hạn và quan sát |
| Lỗi ngay lúc commit/timeout | Có thể không xác định kết quả | Đối soát trạng thái bằng khóa nghiệp vụ |
| Pool cạn | Quá tải, connection leak hoặc query chậm | Đo pool và giới hạn concurrency |

Spring JDBC dịch `SQLException` thành các nhóm `DataAccessException` để code có thể phân loại tốt hơn. Nhưng không nên bắt `DataAccessException` rồi retry mọi trường hợp; phải dựa vào loại lỗi thực tế, driver và tính idempotent của thao tác.

### 11.3. Transaction, cache và outbox

Trong một luồng tích hợp:

~~~mermaid
flowchart LR
    A["Consume Order event"] --> B["SQL transaction"]
    B --> C["Upsert business row"]
    B --> D["Insert inbox key"]
    B --> E["Insert outbox event"]
    E --> F["Outbox relay / CDC"]
    F --> G["Message broker"]
    G --> H["Downstream consumer"]
    B -.-> I["Cache eviction after commit"]
~~~

Ghi business row + inbox + outbox trong **cùng một DB transaction** giúp tránh trạng thái “đã thay đổi nghiệp vụ nhưng quên lưu message cần phát”. Outbox relay vẫn có thể publish lặp khi crash trước khi đánh dấu gửi xong, nên consumer phía sau phải idempotent.

Evict cache trước khi transaction commit có thể khiến reader nạp lại dữ liệu cũ. Vì vậy nếu yêu cầu nhất quán, đặt invalidation sau commit hoặc dùng cơ chế transaction-aware đã được kiểm thử. Đây là chính sách của tầng tích hợp, không phải do `spring.datasource.url` tự quyết định.

## 12. Kiểm thử suy luận driver và kết nối SQL

Kiểm thử tốt không chỉ xác minh Spring context khởi động, mà còn kiểm tra **DB thật được dùng, driver đúng và lỗi được phân loại chính xác**.

### 12.1. Unit test cho nghiệp vụ

Logic phân loại message, tạo idempotency key hay map DTO nên được kiểm thử riêng với fake port. Unit test không cần khởi động database hoặc tạo `DataSource`.

### 12.2. JDBC slice test

Spring Boot hỗ trợ `@JdbcTest` để kiểm tra repository/JdbcTemplate trong một phần nhỏ context. Tùy dependency và cấu hình, test slice có thể thay DataSource bằng embedded database. Không suy luận rằng test JDBC dùng H2 chứng minh được URL PostgreSQL trong production.

Các test nên có:

| Kịch bản | Kỳ vọng |
| --- | --- |
| URL PostgreSQL hợp lệ và driver JAR có mặt | Context tạo DataSource và truy vấn thành công |
| Driver JAR thiếu | Startup/connection thất bại rõ nguyên nhân |
| JDBC URL sai định dạng | Lỗi được phát hiện và không chạy nhầm database |
| Password không đúng | Kết nối bị từ chối; không log secret |
| Migration chưa chạy | Lỗi schema được phát hiện |
| SQL unique key bị vi phạm | Adapter chuyển thành lỗi nghiệp vụ/duplicate phù hợp |
| Pool bị bão hòa | Có timeout/backpressure và metric cảnh báo |
| Giao dịch thất bại | Business update, inbox và outbox cùng rollback |
| Redelivery cùng eventId | Không tạo tác động nghiệp vụ trùng |

### 12.3. Integration test bằng PostgreSQL thật qua Testcontainers

Đối với driver inference và cú pháp PostgreSQL, ưu tiên container database trong test. Ví dụ skeleton với JUnit 5 và Testcontainers (dependency test tương ứng phải được cài):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class SqlConnectivityIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void applicationUsesTestDatabase() {
        // Assertion thực tế nên gọi repository và xác minh dữ liệu.
    }
}
~~~

Ví dụ chỉ minh họa **cách đưa URL, username, password của container vào Spring Boot**. Để test có ý nghĩa, cần chuẩn bị schema qua migration và assert repository/transaction thật; snippet này chưa là test hoàn chỉnh. Testcontainers cần Docker/compatible container runtime. Dependency artifacts có thể khác giữa dòng Testcontainers đang dùng, nên để dependency management của dự án quyết định version.

Trong test này **không khai báo `spring.datasource.driver-class-name`**: khi PostgreSQL driver tồn tại, ta kiểm tra chính khả năng suy luận từ `postgres.getJdbcUrl()`. Có thể assert một truy vấn `SELECT 1` hoặc truy vấn bảng đã migrate; không nên chỉ assert bean `DataSource` khác null.

## 13. Quan sát và vận hành kết nối

Thêm Actuator giúp kiểm tra các metric và health indicator được hỗ trợ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với HikariCP và Micrometer, Boot có thể xuất các chỉ số dạng `hikaricp.connections.*` và `jdbc.connections.*` (tên, nhãn và cách hiển thị tùy phiên bản, registry). Các chỉ số đặc biệt hữu ích:

| Chỉ số/tín hiệu | Câu hỏi vận hành |
| --- | --- |
| Active connections | Có đang sử dụng gần hết pool không? |
| Idle connections | Có kết nối nhàn rỗi sẵn để nhận request không? |
| Pending threads | Có caller đang chờ lấy connection không? |
| Connection acquisition time | Thời gian chờ cấp connection có tăng không? |
| Connection creation/timeout failures | DB/network/pool có đang gây lỗi không? |
| HTTP/broker backlog | SQL adapter chậm có gây tồn đọng ở upstream không? |
| Query/transaction latency (instrument riêng) | Pool khỏe nhưng SQL nào đang chậm? |

Một `DataSourceHealthIndicator` có thể kiểm tra kết nối database khi Actuator health hỗ trợ và được bật. Tuy vậy health check thành công chỉ cho thấy DB **có thể phản hồi phép kiểm tra tương ứng**, không chứng minh mọi query, migration hay quyền trên từng bảng đều chính xác.

Muốn quan sát từng câu SQL, có thể cần instrumentation riêng; **pool metrics không đồng nghĩa SQL tracing**. Không gắn `orderId`, `eventId`, raw SQL chứa dữ liệu người dùng hoặc URL có password vào metric tags/trace attributes.

Một sơ đồ chẩn đoán nhanh khi latency tăng:

~~~mermaid
flowchart TD
    A["Latency tăng"] --> B{"Pool pending cao?"}
    B -->|"Có"| C["Đo active, pool size, thời gian giữ connection"]
    C --> D["Kiểm tra slow query, long transaction, capacity"]
    B -->|"Không"| E{"DB query chậm?"}
    E -->|"Có"| F["Query plan / index / lock / IO"]
    E -->|"Không"| G["Kiểm tra HTTP, broker, cache và overhead xử lý"]
~~~

Chỉ tăng pool mà không kiểm tra năng lực DB có thể làm tình hình xấu hơn. Cần tính cả số instance, thời gian giữ connection, traffic burst và giới hạn kết nối của database.

## 14. Bảo mật và vận hành theo môi trường

Một cấu hình kết nối đáng tin cậy cần chú ý:

- **Secrets:** password lấy từ secret manager/biến môi trường; tránh in cả `DataSourceProperties` hoặc JDBC URL chứa secret.
- **Quyền hạn:** tạo user theo nhiệm vụ. User runtime thường không cần quyền DDL/DBA nếu migration chạy bằng tài khoản riêng.
- **TLS:** kiểm chứng server certificate theo tài liệu driver; không tắt xác thực SSL ở production.
- **Mạng:** DB ở private network; firewall cho phép đúng nguồn, không public database không cần thiết.
- **Credential rotation:** kiểm tra ảnh hưởng đến connection pool đang sống và thời điểm pool tạo connection mới.
- **Cấu hình:** xem lại profile, property override và secret injection trước deploy.
- **Capacity:** số replica × pool max nằm trong hạn mức của DB.
- **Recovery:** retry có giới hạn, backoff, idempotency, cảnh báo và circuit breaker khi ứng dụng xử lý cùng nhiều downstream.
- **Backup/migration:** không nhầm “kết nối được” với “có dữ liệu chính xác hoặc có thể khôi phục”.

Khi vận hành Kubernetes hoặc container, `localhost` bên trong ứng dụng chỉ trỏ tới **chính container/pod đó**. Địa chỉ database cần dùng hostname/service name mà container truy cập được. Một URL chạy trên laptop không mặc nhiên hợp lệ trong môi trường container.

## 15. Checklist trước khi đưa SQL adapter vào luồng tích hợp

- [ ] Đã thêm đúng starter JDBC/JPA và JDBC driver ở **runtime classpath**.
- [ ] `spring.datasource.url` dùng đúng `jdbc:<vendor>:...` và trỏ đúng database theo môi trường.
- [ ] Chỉ cấu hình `driver-class-name` khi cần; hiểu cơ chế Boot suy luận từ URL.
- [ ] Username/password lấy từ nguồn an toàn, không đặt bí mật trong mã nguồn/log/trace.
- [ ] Pool phù hợp với capacity DB và số instance; phân biệt pool timeout, network timeout và SQL timeout.
- [ ] Migration tạo schema trước khi adapter thực hiện query; không phụ thuộc H2 để kiểm chứng SQL đặc thù.
- [ ] Có kiểm thử URL→driver→DataSource bằng database thực hoặc Testcontainers.
- [ ] Đã định nghĩa transaction manager và ranh giới local transaction đúng resource.
- [ ] Có idempotency/inbox cho redelivery và outbox nếu cần đồng bộ DB→broker an toàn.
- [ ] Có cách phân loại lỗi driver, kết nối, xác thực, constraint và timeout.
- [ ] Đã bật các metric pool/health cần thiết và bảo vệ endpoint quản trị.
- [ ] Nếu có nhiều DataSource hoặc cả JDBC/R2DBC, đã cấu hình bean và qualifier tường minh.

**Kết luận kỹ thuật:** `spring.datasource.*` là điểm cấu hình kết nối SQL của Spring Boot; trong trường hợp phổ biến, Boot **suy ra lớp JDBC driver từ URL** và tạo `DataSource`/connection pool cho adapter sử dụng. Khả năng tự suy luận này giảm cấu hình lặp, nhưng không thay thế dependency driver, thiết lập database đúng, bảo mật, giới hạn pool, transaction, idempotency và kiểm thử luồng tích hợp.

## Tài liệu tham khảo

- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình `DataSource`, JDBC, JdbcTemplate, connection pooling và SQL initialization.
- [Spring Boot 3.5 — SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): đối chiếu các property và API với dòng Boot 3.x.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, placeholder, profile và relaxed binding.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, tham số SQL, exception translation và resource management.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, ranh giới transaction và phối hợp resource.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): thuộc tính pool, timeout và lifecycle.
- [PostgreSQL JDBC — Connecting to the Database](https://jdbc.postgresql.org/documentation/use/): cú pháp JDBC URL, driver và các connection properties của PostgreSQL.
