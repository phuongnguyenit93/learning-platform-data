# Không tìm thấy trình điều khiển hoặc không tạo được ConnectionFactory

Khi khởi động ứng dụng Spring Data R2DBC, một lỗi thường gặp là Spring không tìm được driver phù hợp hoặc không tạo được bean ConnectionFactory. Một nhóm lỗi khác xuất hiện sau khi ứng dụng đã có ConnectionFactory nhưng không thể mở kết nối tới database. Hai nhóm lỗi này có biểu hiện gần giống nhau trong log, nhưng nguyên nhân và cách xử lý khác nhau.

**Hãy chẩn đoán theo thứ tự: dependency driver có trên runtime classpath không, driver có hỗ trợ scheme của URL không, cấu hình R2DBC có được Spring Boot đọc đúng không, ConnectionFactory có được tạo không, rồi mới kiểm tra kết nối thật và câu SQL.** Không nên bắt đầu bằng cách đổi username/password hoặc tăng pool size khi ứng dụng thậm chí chưa tìm được driver.

Spring Data R2DBC cần một implementation R2DBC tương thích với database đang dùng. JDBC driver và JDBC URL không thể thay thế R2DBC driver và R2DBC URL. ConnectionFactory là abstraction tạo connection reactive; DataSource là abstraction của JDBC. Một ứng dụng có thể dùng cả hai công nghệ, nhưng cấu hình và bean của chúng là hai đường riêng.

## 1. Phân biệt driver, ConnectionFactory và connection

Ba thành phần này nằm ở các giai đoạn khác nhau:

1. **R2DBC driver:** implementation giao thức R2DBC cho một hệ quản trị cụ thể, ví dụ PostgreSQL hoặc MySQL.
2. **ConnectionFactory:** object do driver tạo ra từ options/cấu hình; nó chịu trách nhiệm tạo các R2DBC Connection.
3. **Connection:** phiên kết nối thực tế tới database, được tạo khi ứng dụng yêu cầu ConnectionFactory cấp connection.

Luồng khởi tạo khái quát:

~~~text
Application configuration
        |
        v
R2DBC URL / ConnectionFactoryOptions
        |
        v
R2DBC ConnectionFactoryProvider discovery
        |
        v
Driver creates ConnectionFactory
        |
        v
ConnectionFactory.create()
        |
        v
Database connection
        |
        v
Execute SQL
~~~

Vì vậy, “không tìm thấy driver” thường là lỗi ở bước discovery hoặc classpath. “Không thể kết nối database” thường xảy ra sau khi đã có factory nhưng khi factory mở connection. “Query lỗi” xảy ra muộn hơn, khi statement được gửi hoặc kết quả được đọc.

### 1.1. Những thông báo lỗi thường gặp

Tên exception và câu chữ cụ thể phụ thuộc Spring Boot, Spring Framework, R2DBC SPI và driver. Một số dấu hiệu:

| Thông báo hoặc dấu hiệu | Lớp cần kiểm tra đầu tiên |
| --- | --- |
| No R2DBC ConnectionFactory available | Cấu hình hoặc auto-configuration không tạo được factory |
| No ConnectionFactoryProvider found for driver ... | Thiếu driver hoặc scheme không được driver hỗ trợ |
| Unable to create a ConnectionFactory from URL | URL sai, scheme không hợp lệ hoặc provider không tìm thấy |
| Failed to determine a suitable driver class | Thường là thông báo của JDBC auto-configuration; kiểm tra nhầm DataSource/JDBC config |
| Connection refused | Database không lắng nghe ở host/port hoặc network từ chối |
| UnknownHostException | DNS/hostname không phân giải được |
| Authentication failed / password authentication failed | Kết nối đã tới server nhưng xác thực thất bại |
| Database does not exist | Server có thể truy cập nhưng database name sai hoặc chưa được tạo |
| SSL handshake failed | TLS mode, certificate hoặc trust configuration không phù hợp |
| Connection reset / connection closed | Network, server, proxy, pool hoặc driver đóng connection |

Không phân loại lỗi chỉ bằng một dòng cuối của stack trace. Hãy đọc root cause và xem lỗi xuất hiện khi tạo bean, khi gọi create connection hay khi thực thi SQL.

## 2. Thêm đúng R2DBC driver vào runtime classpath

Spring Data R2DBC không chứa driver cho mọi database. Ứng dụng cần thêm implementation tương ứng với hệ quản trị đang sử dụng.

Ví dụ Gradle với PostgreSQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Ví dụ Maven:

~~~xml
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
~~~

Các ví dụ dựa trên dependency coordinates phổ biến; nên dùng phiên bản do Spring Boot dependency management/BOM quản lý nếu driver đó nằm trong dependency set được hỗ trợ. Không tự chọn một phiên bản driver cũ hoặc trộn nhiều phiên bản R2DBC SPI mà chưa kiểm tra compatibility.

### 2.1. Một số driver phổ biến

| Database | Artifact R2DBC thường dùng |
| --- | --- |
| PostgreSQL | org.postgresql:r2dbc-postgresql |
| MySQL | io.asyncer:r2dbc-mysql |
| MariaDB | org.mariadb:r2dbc-mariadb |
| H2 | io.r2dbc:r2dbc-h2 |
| Microsoft SQL Server | io.r2dbc:r2dbc-mssql |
| Oracle Database | com.oracle.database.r2dbc:oracle-r2dbc |

Artifact và phiên bản cần đối chiếu tài liệu chính thức của driver, Spring Boot version và R2DBC SPI compatibility. Một số driver đã thay đổi group/artifact hoặc được thay thế bởi implementation được duy trì mới hơn.

### 2.2. Driver phải có ở runtime, không chỉ compile/test

R2DBC tìm provider trong runtime classpath. Nếu driver được khai báo với scope chỉ dùng khi compile hoặc chỉ có trong test, ứng dụng có thể compile và test một phần nhưng chạy production lại không tìm được provider.

Với Gradle, kiểm tra:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Để xem dependency cụ thể được chọn:

~~~powershell
.\gradlew.bat dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
~~~

Với Maven:

~~~powershell
mvn dependency:tree -Dincludes=org.postgresql:r2dbc-postgresql
~~~

Kiểm tra output của runtime classpath và artifact cuối cùng được đóng gói. Đừng chỉ nhìn file build.gradle rồi giả định dependency đã có trong executable JAR/container.

### 2.3. Không dùng JDBC driver thay R2DBC driver

Hai dependency sau không tương đương:

~~~kotlin
runtimeOnly("org.postgresql:postgresql")       // JDBC driver
runtimeOnly("org.postgresql:r2dbc-postgresql") // R2DBC driver
~~~

JDBC driver triển khai API java.sql và tạo DataSource/Connection kiểu JDBC. R2DBC driver triển khai R2DBC SPI và tạo ConnectionFactory/Connection reactive.

Nếu ứng dụng dùng cả JDBC và R2DBC, có thể cần cả hai dependency. Nhưng thêm PostgreSQL JDBC driver không làm Spring Data R2DBC tự có PostgreSQL ConnectionFactory.

### 2.4. Kiểm tra dependency bị loại trừ hoặc xung đột

Driver có thể bị loại bởi:

- exclude trong Gradle/Maven.
- dependency conflict khiến phiên bản khác được chọn.
- cấu hình multi-module chỉ thêm driver vào module test.
- packaging/shading làm mất service metadata.
- image/container chạy một artifact khác với artifact đã kiểm thử.

Kiểm tra dependency tree và nội dung JAR được deploy. Nếu dùng custom classloader, plugin architecture hoặc native image, cần xác nhận cơ chế provider discovery vẫn hoạt động trong môi trường đó.

## 3. R2DBC URL phải dùng đúng scheme

URL R2DBC chứa scheme để provider biết driver nào cần xử lý.

Ví dụ PostgreSQL:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/appdb
spring.r2dbc.username=app_user
# Inject spring.r2dbc.password from a secret store
~~~

JDBC URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/appdb
~~~

Hai URL có mục đích khác nhau. Đưa jdbc:postgresql vào spring.r2dbc.url sẽ khiến R2DBC provider không nhận ra scheme.

### 3.1. Các phần của URL

Ví dụ:

~~~text
r2dbc:postgresql://db.example.internal:5432/orders
~~~

Có thể phân tích thành:

- Prefix R2DBC: r2dbc:
- Driver protocol: postgresql
- Host: db.example.internal
- Port: 5432
- Database: orders

Scheme driver phải khớp provider được thêm vào classpath. Ví dụ URL dùng postgresql nhưng runtime chỉ có MySQL driver thì không có provider phù hợp.

### 3.2. Không tự thêm tiền tố jdbc

Tránh:

~~~properties
spring.r2dbc.url=jdbc:postgresql://localhost:5432/appdb
~~~

Đúng:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/appdb
~~~

Tương tự, URL JDBC của MySQL hoặc SQL Server cũng không dùng trực tiếp cho R2DBC. Hãy xem URL format của đúng driver.

### 3.3. Credentials nên được cấu hình riêng

Spring Boot thường cho phép đặt username/password qua các thuộc tính spring.r2dbc.username và spring.r2dbc.password. Không commit password thật vào source control. Dùng environment variable hoặc secret manager. Nếu URL cũng chứa credentials, hãy tránh log toàn bộ URL vì có thể làm lộ thông tin xác thực.

### 3.4. Driver-specific options

Một số driver hỗ trợ query parameters hoặc options riêng cho SSL, schema, socket, timezone, application name và các tính năng khác. Cú pháp và tên option không giống nhau giữa các driver.

Không sao chép tham số từ JDBC URL sang R2DBC URL mà không kiểm tra tài liệu driver. Nếu option không được hỗ trợ, nó có thể bị từ chối hoặc không có tác dụng như mong đợi.

## 4. Cấu hình Spring Boot cho R2DBC

Trong ứng dụng Spring Boot, cấu hình tiêu chuẩn thường dùng prefix spring.r2dbc:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    # Inject password from environment or secret manager
~~~

Spring Boot có thể tự cấu hình ConnectionFactory khi:

- Có R2DBC infrastructure trên classpath.
- Có cấu hình URL/connection options phù hợp.
- Có provider tương ứng với driver protocol.
- Chưa có ConnectionFactory bean do ứng dụng tự khai báo khiến auto-configuration phải back off.

Chi tiết điều kiện và property phụ thuộc phiên bản Spring Boot.

### 4.1. Không nhầm spring.datasource với spring.r2dbc

Các thuộc tính JDBC:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: app_user
~~~

không tự cấu hình R2DBC ConnectionFactory.

Các thuộc tính R2DBC:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
~~~

không tự cấu hình JDBC DataSource. Nếu ứng dụng dùng cả hai, cấu hình cả hai theo đúng mục đích.

### 4.2. Profile có thể ghi đè cấu hình

Một ứng dụng có thể có application.yml, application-local.yml, application-test.yml và biến môi trường. Profile đang active hoặc biến môi trường có thể ghi đè URL mà developer đang xem.

Kiểm tra:

- Profile nào đang active?
- Config map/secret nào được mount trong container?
- Environment variable có override spring.r2dbc.url không?
- Có cấu hình URL khác trong test hoặc deployment manifest không?
- Log startup có hiển thị profile và nguồn cấu hình cần thiết không?

Khi debug, chỉ log host, port, database và driver protocol sau khi đã loại bỏ credentials/secret. Không in nguyên URL nếu URL có username/password.

### 4.3. Biến môi trường

Spring Boot relaxed binding thường ánh xạ biến môi trường:

~~~text
SPRING_R2DBC_URL
SPRING_R2DBC_USERNAME
SPRING_R2DBC_PASSWORD
~~~

Hãy kiểm tra tên biến trong môi trường deploy và cách platform inject secret. Một lỗi đánh máy trong tên biến có thể khiến ứng dụng dùng cấu hình mặc định hoặc không có URL.

## 5. Hiểu Spring Boot auto-configuration và bean ConnectionFactory

Spring Boot có thể tạo ConnectionFactory từ cấu hình nếu ứng dụng chưa cung cấp bean phù hợp. Nếu dự án khai báo ConnectionFactory thủ công, auto-configuration có thể back off và không còn sử dụng các thuộc tính mà developer mong đợi.

### 5.1. Kiểm tra có bean ConnectionFactory hay không

Một cách kiểm tra trong application context:

~~~java
@Component
public class ConnectionFactoryDiagnostics implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public ConnectionFactoryDiagnostics(
            ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("R2DBC ConnectionFactory metadata: {}",
                connectionFactory.getMetadata().getName());
    }
}
~~~

Nếu ứng dụng không khởi động được vì thiếu bean, constructor injection cũng không thể chạy. Khi đó cần xem condition evaluation report hoặc log auto-configuration để biết vì sao bean không được tạo.

Không log toàn bộ options nếu chúng có thể chứa password.

### 5.2. Bật condition evaluation report

Khi cần chẩn đoán auto-configuration, có thể khởi động với debug report theo cơ chế Spring Boot, ví dụ:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

Hoặc bật debug logging phù hợp. Condition evaluation report cho biết auto-configuration nào match hoặc không match và lý do. Đọc phần R2DBC/ConnectionFactory thay vì chỉ tìm dòng lỗi cuối cùng.

### 5.3. Kiểm tra bean bị định nghĩa thủ công

Tìm trong code:

- @Bean trả về ConnectionFactory.
- @Bean trả về ConnectionPool.
- AbstractR2dbcConfiguration.
- Custom R2dbcEntityOperations/DatabaseClient.
- Cấu hình multi-database hoặc routing ConnectionFactory.

Nếu có bean thủ công, xác nhận nó dùng đúng URL/options và không bị bean khác thay thế. Tránh tạo nhiều ConnectionFactory không cần thiết hoặc tạo pool lồng nhau.

### 5.4. Khi dùng nhiều database

Ứng dụng nhiều database có thể có nhiều ConnectionFactory và transaction manager. Cần đặt tên bean và chỉ định đúng qualifier cho DatabaseClient, repository và transaction manager.

Nếu routing ConnectionFactory dùng tenant key, hãy bảo đảm target map có provider/factory hợp lệ và không có default factory vô tình route mọi tenant tới database sai.

## 6. Tự tạo ConnectionFactory để cô lập lỗi

R2DBC SPI cung cấp cơ chế parse options và tìm provider theo driver protocol. Ví dụ kiểm tra độc lập:

~~~java
ConnectionFactoryOptions options =
        ConnectionFactoryOptions.parse(
                "r2dbc:postgresql://localhost:5432/appdb");

ConnectionFactory connectionFactory =
        ConnectionFactories.get(options);
~~~

Nếu lỗi xảy ra ngay ở ConnectionFactories.get, hãy tập trung vào URL, provider discovery và runtime classpath. Nếu tạo factory thành công nhưng factory.create() lỗi, chuyển sang kiểm tra kết nối thật.

Không nhất thiết đưa đoạn code này vào production; đây là cách cô lập nguyên nhân khi debug.

### 6.1. Kiểm tra metadata không mở connection

Sau khi tạo factory:

~~~java
String driverName = connectionFactory.getMetadata().getName();
~~~

Metadata giúp xác nhận factory thuộc driver nào. Nó không chứng minh database đang chạy hoặc credentials hợp lệ.

### 6.2. Smoke test bằng ConnectionFactory

Có thể thử tạo rồi đóng một connection:

~~~java
Mono<Void> verifyConnection(ConnectionFactory factory) {
    return Mono.from(factory.create())
            .flatMap(connection -> Mono.from(connection.close()));
}
~~~

Trong test reactive:

~~~java
StepVerifier.create(verifyConnection(connectionFactory))
        .verifyComplete();
~~~

Nếu smoke test thất bại, kiểm tra root cause của driver, network, authentication, TLS và database. Không gọi block trong event loop hoặc trong đường xử lý request production.

## 7. Phân biệt lỗi tạo factory với lỗi mở connection

Đây là điểm quan trọng nhất khi đọc log.

### 7.1. Lỗi xảy ra lúc tạo ConnectionFactory

Ví dụ nguyên nhân:

- Thiếu driver dependency.
- Sai driver protocol trong URL.
- URL không parse được.
- Provider không đăng ký đúng.
- Driver version không tương thích với R2DBC SPI.
- Custom configuration truyền option không hợp lệ.
- Pool được yêu cầu nhưng dependency pool không có.

Ở giai đoạn này, chưa nhất thiết có kết nối tới database. Thay username/password thường không giải quyết được lỗi thiếu provider.

### 7.2. Factory tạo được nhưng create connection thất bại

Ví dụ nguyên nhân:

- Database chưa chạy.
- Host/port sai.
- DNS không phân giải.
- Firewall, security group hoặc container network chặn kết nối.
- Database chưa được tạo.
- Username/password sai.
- User không có quyền CONNECT hoặc quyền schema cần thiết.
- SSL/TLS mode hoặc certificate không đúng.
- Server giới hạn connection hoặc từ chối session.

Ở giai đoạn này, driver đã được tìm thấy và factory đã được tạo. Hãy kiểm tra kết nối từ chính môi trường chạy ứng dụng, không chỉ từ laptop developer.

### 7.3. Connection mở được nhưng SQL thất bại

Ví dụ:

- Table không tồn tại.
- Schema/search path sai.
- User thiếu SELECT/INSERT/UPDATE privilege.
- SQL dialect hoặc cú pháp không đúng.
- Bind parameter không tương thích kiểu cột.
- Constraint, transaction hoặc lock gây lỗi.

Đây không còn là lỗi discovery driver. Hãy kiểm tra migration, schema, SQL và quyền database.

## 8. Kiểm tra network và database từ môi trường chạy ứng dụng

Nếu factory được tạo nhưng connection không mở được, hãy kiểm tra theo đường mạng:

1. Hostname có phân giải trong container/pod không?
2. Port database có thể truy cập từ workload không?
3. Database có lắng nghe trên interface đó không?
4. Firewall/security group/network policy có cho phép không?
5. Database có chấp nhận thêm connection không?
6. TLS/certificate có đúng không?
7. Credentials và quyền database có hợp lệ không?

Không dùng kết quả kết nối từ máy developer để kết luận container production cũng kết nối được. DNS, route, secret và network policy có thể khác.

### 8.1. Host trong Docker Compose

Nếu ứng dụng và database chạy trong cùng Docker Compose network, hostname thường là service name, ví dụ postgres, không phải localhost.

~~~yaml
services:
  app:
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://postgres:5432/appdb
  postgres:
    image: postgres:16
~~~

Trong container app, localhost trỏ tới chính container app. Chỉ dùng localhost nếu database thực sự chạy trong cùng network namespace hoặc port được forward phù hợp.

### 8.2. Kubernetes service DNS

Trong Kubernetes, host thường là Service DNS name trong cluster, chẳng hạn:

~~~text
postgres.database.svc.cluster.local
~~~

Hãy kiểm tra namespace, Service, Endpoint/EndpointSlice, NetworkPolicy và secret mount. Không đưa IP pod cố định vào cấu hình vì pod có thể thay đổi.

### 8.3. Database container có thể chưa sẵn sàng

Trong một số cấu hình Compose, thứ tự khởi tạo container không luôn bảo đảm database đã sẵn sàng nhận connection. Dùng health check/readiness và cơ chế retry startup có giới hạn. Không retry vô hạn khiến ứng dụng khởi động treo mà không có trạng thái rõ ràng.

## 9. Kiểm tra credentials, database và quyền

Sau khi xác nhận host/port truy cập được:

- Username có đúng với môi trường đang chạy không?
- Password secret có được mount và không rỗng không?
- Database name có tồn tại không?
- User có quyền kết nối database không?
- User có quyền trên schema/table cần dùng không?
- Có yêu cầu SSL hoặc certificate client không?
- Password có ký tự đặc biệt làm hỏng URL nếu nhúng trực tiếp không?

Nên đặt credentials ở thuộc tính riêng hoặc secret store thay vì nối vào URL. Nếu driver hỗ trợ nhiều cơ chế authentication, kiểm tra đúng cơ chế đang cấu hình.

### 9.1. Authentication thành công không đồng nghĩa query có quyền

Một user có thể kết nối database nhưng không có quyền SELECT trên table hoặc không có quyền dùng schema. Khi đó ConnectionFactory và connection đều hoạt động; lỗi chỉ xuất hiện khi chạy SQL.

### 9.2. Kiểm tra database name và schema

Một số driver kết nối được tới server nhưng báo lỗi khi database name sai. Một số hệ quản trị cho kết nối tới database mặc định nhưng query thất bại vì schema/search path không đúng. Hãy phân biệt lỗi ở handshake với lỗi khi truy vấn metadata hoặc bảng.

## 10. SSL/TLS và certificate

Trong môi trường production, database có thể bắt buộc TLS. Cấu hình SSL của R2DBC driver có thể khác JDBC driver. Các vấn đề thường gặp:

- Driver đang dùng SSL mode không đúng.
- Certificate CA chưa được trust.
- Hostname trong certificate không khớp.
- Client certificate/key không đúng định dạng hoặc quyền file.
- TLS protocol/cipher không tương thích.
- Container thiếu CA bundle cần thiết.

Không tắt xác minh certificate như một cách sửa production lâu dài. Nếu cần chẩn đoán, kiểm tra trust chain và hostname validation theo tài liệu driver, sau đó cấu hình CA/certificate đúng.

Không log private key, password hoặc nội dung secret khi bật debug.

## 11. Pool configuration và lỗi khởi tạo pool

Nếu ứng dụng dùng R2DBC connection pool, cần phân biệt:

- Driver factory gốc.
- Pool factory bọc factory gốc.
- Connection được lấy từ pool.

Một lỗi tạo pool có thể do thiếu dependency r2dbc-pool, cấu hình min/max size không hợp lệ hoặc target factory không được tạo. Một lỗi acquire timeout lại thường do pool không có connection khả dụng trong thời gian cho phép.

### 11.1. Kiểm tra pool dependency

Nếu tự cấu hình ConnectionPool, xác nhận dependency pool có trong runtime classpath. Nếu dựa vào Spring Boot auto-configuration, kiểm tra version Boot và property pool tương ứng. Không thêm pool dependency chỉ để chữa lỗi provider của database driver.

### 11.2. Kiểm tra pool size và acquire timeout

Các cấu hình như initial size, max size, max acquire time và max create connection time cần hợp lệ theo API/version đang dùng.

Pool max size quá nhỏ có thể gây acquire timeout dưới tải. Pool max size quá lớn có thể làm database cạn connection. Tính tổng pool qua tất cả replica:

~~~text
potential database connections
    = application replicas x pool max size
      + workers + migration + monitoring + administration
~~~

Không tăng max size trước khi kiểm tra connection hold time, query latency và giới hạn server.

### 11.3. Tránh tạo pool lồng nhau

Không bọc một ConnectionPool đã tồn tại bằng một ConnectionPool khác nếu không có lý do rõ ràng. Pool lồng nhau có thể làm khó quản lý lifecycle, metrics và timeout; connection ở pool ngoài có thể giữ connection của pool trong quá lâu.

## 12. Version compatibility và dependency alignment

R2DBC gồm SPI và nhiều implementation. Nếu các dependency dùng phiên bản không tương thích, lỗi có thể xuất hiện khi load provider, tạo factory hoặc chạy query.

Kiểm tra:

- Spring Boot version.
- Spring Framework/Spring Data version do Boot quản lý.
- R2DBC SPI version.
- R2DBC driver version.
- R2DBC pool version nếu dùng.
- Java runtime version.

### 12.1. Ưu tiên dependency management của Spring Boot

Nếu dùng Spring Boot BOM/plugin, ưu tiên để Boot quản lý phiên bản các dependency được hỗ trợ. Tránh khai báo phiên bản thủ công cho mọi artifact nếu không cần thiết.

Nếu cần override driver, hãy xác nhận compatibility matrix của driver với R2DBC SPI và database version. Ghi nhận lý do override và test trong runtime giống production.

### 12.2. Không trộn API R2DBC cũ và mới tùy tiện

Một số ví dụ trên mạng dùng package hoặc API từ phiên bản cũ. Khi copy code, kiểm tra:

- Import package có tồn tại trong version dự án không?
- Interface/method có thay đổi không?
- Driver có hỗ trợ SPI mà ứng dụng đang dùng không?
- Có hai phiên bản cùng một artifact trên classpath không?

Lỗi compile và lỗi runtime provider discovery có thể đến từ dependency alignment khác nhau.

## 13. Tạo ConnectionFactory thủ công

Trong ứng dụng đơn giản, Spring Boot auto-configuration thường là đủ. Khi cần nhiều database, routing hoặc tùy chọn driver đặc biệt, có thể tạo factory thủ công.

Ví dụ khái quát:

~~~java
@Configuration
public class R2dbcConfiguration {

    @Bean
    ConnectionFactory connectionFactory() {
        ConnectionFactoryOptions options =
                ConnectionFactoryOptions.builder()
                        .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                        .option(ConnectionFactoryOptions.HOST, "localhost")
                        .option(ConnectionFactoryOptions.PORT, 5432)
                        .option(ConnectionFactoryOptions.DATABASE, "appdb")
                        .option(ConnectionFactoryOptions.USER, "app_user")
                        .option(ConnectionFactoryOptions.PASSWORD, "secret")
                        .build();

        return ConnectionFactories.get(options);
    }
}
~~~

Đây là cấu hình minh họa. Trong production, credentials phải lấy từ externalized configuration/secret store, không hardcode trong source.

### 13.1. Khi tự khai báo bean, kiểm tra auto-configuration backoff

Nếu ứng dụng có bean ConnectionFactory, Spring Boot có thể không tạo bean tự động nữa. Điều này có thể khiến thay đổi spring.r2dbc.url không có tác dụng như developer mong đợi.

Hãy kiểm tra bean thực tế được inject, metadata driver và nguồn options đã dùng. Không chỉ nhìn application.yml.

### 13.2. Đừng tạo ConnectionFactory mỗi request

ConnectionFactory là đối tượng hạ tầng có vòng đời ứng dụng. Không tạo factory hoặc pool mới cho từng HTTP request. Việc đó gây connection churn, resource leak và mất lợi ích pooling.

Với multi-tenant database routing, quản lý factory theo registry/lifecycle tenant; không tạo vô hạn pool cho tenant mà không có eviction và giới hạn tổng.

## 14. Kiểm tra bằng DatabaseClient sau khi factory hoạt động

Khi đã có ConnectionFactory và mở connection thành công, có thể chạy query nhẹ để xác nhận database session:

~~~java
DatabaseClient databaseClient =
        DatabaseClient.create(connectionFactory);

Mono<Integer> ping = databaseClient
        .sql("SELECT 1")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one();
~~~

Query này chỉ là smoke test; cú pháp và kiểu kết quả có thể cần điều chỉnh theo database. Nó không chứng minh toàn bộ schema, quyền table hoặc migration đã đúng.

### 14.1. Kiểm tra schema sau khi ping thành công

Tiếp theo kiểm tra:

- Database/schema hiện tại.
- Quyền SELECT trên bảng cần dùng.
- Table và column đã được migration tạo.
- Search path/schema mapping.
- Driver type mapping cho cột quan trọng.

Nếu SELECT 1 thành công nhưng repository query thất bại, vấn đề thường nằm ở schema, SQL, quyền hoặc mapping thay vì driver discovery.

## 15. Chẩn đoán theo môi trường

### 15.1. Local development

Kiểm tra database process/container, port mapping, profile local, URL scheme và credentials. Dùng log debug auto-configuration khi không có ConnectionFactory bean.

### 15.2. Automated test

Đảm bảo driver nằm trong test runtime classpath và Testcontainers đã khởi động trước khi application context tạo ConnectionFactory. Nếu test slice không load cấu hình production, import đúng R2DBC configuration.

Không dùng H2 R2DBC để giả lập PostgreSQL nếu test cần xác nhận PostgreSQL driver, native types hoặc SQL dialect.

### 15.3. Docker/Kubernetes

Kiểm tra DNS/service name, network policy, secret mount, active profile, port, readiness và database max connections từ bên trong workload.

Đảm bảo artifact được deploy có cùng dependency runtime như artifact đã kiểm thử.

### 15.4. Production

Không bật log chứa credentials hoặc toàn bộ connection URL. Thu thập root cause, driver metadata, host/database đã được che secret, profile, connection pool metrics và database health. Thực hiện thao tác kiểm tra bằng quyền tối thiểu.

## 16. Cây quyết định chẩn đoán

~~~text
Ứng dụng không có ConnectionFactory?
|
+-- Có
|   |
|   +-- R2DBC driver có trong runtimeClasspath?
|   |      |
|   |      +-- Không -> thêm đúng driver dependency
|   |      |
|   |      +-- Có
|   |           |
|   |           +-- URL dùng r2dbc:<driver>?
|   |           |      |
|   |           |      +-- Không -> sửa scheme/URL
|   |           |      |
|   |           |      +-- Có -> kiểm tra provider discovery,
|   |           |                version và auto-configuration
|   |
|   +-- Có bean ConnectionFactory thủ công?
|          |
|          +-- Có -> kiểm tra bean đó và auto-config backoff
|          +-- Không -> xem condition evaluation report
|
+-- Không, nhưng mở connection thất bại
    |
    +-- Kiểm tra host, port, DNS và network
    +-- Kiểm tra database name và trạng thái server
    +-- Kiểm tra credentials, quyền và SSL/TLS
    +-- Kiểm tra connection limit và pool
    |
    +-- Connection mở được nhưng SQL lỗi?
           |
           +-- Kiểm tra schema, migration, permission,
               query, bind parameter và type mapping
~~~

## 17. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| No ConnectionFactoryProvider found | Thiếu R2DBC driver hoặc URL scheme sai | Kiểm tra runtimeClasspath và protocol |
| Chỉ có PostgreSQL JDBC dependency | Nhầm JDBC với R2DBC | Thêm PostgreSQL R2DBC driver |
| Compile được nhưng production không có provider | Driver chỉ ở test/compile scope hoặc bị loại khi packaging | Kiểm tra runtime artifact |
| URL bắt đầu bằng jdbc: | Dùng JDBC URL trong spring.r2dbc.url | Đổi sang r2dbc:<driver> URL |
| Boot không tạo ConnectionFactory | Thiếu URL, driver hoặc auto-config không match | Xem condition report và config profile |
| Thay URL nhưng không có tác dụng | Bean ConnectionFactory thủ công khiến auto-config back off | Kiểm tra bean được inject và options |
| Connection refused | DB không chạy, sai port hoặc network từ chối | Kiểm tra từ container/pod |
| UnknownHostException | DNS/service name sai | Kiểm tra DNS và network |
| Authentication failed | Username/password hoặc auth mode sai | Kiểm tra secret và database user |
| Database not found | Database name sai/chưa tạo | Tạo database hoặc sửa URL |
| SSL handshake failure | CA, certificate, hostname hoặc SSL mode sai | Cấu hình TLS theo driver |
| Acquire timeout | Pool hết connection hoặc connection bị giữ lâu | Kiểm tra pending, hold time và DB capacity |
| Factory tạo được nhưng query lỗi | Schema, quyền, SQL hoặc type mapping | Chạy smoke query và kiểm tra migration |
| Chạy local được nhưng deploy lỗi | Profile, secret, DNS hoặc artifact khác | So sánh runtime config và dependency |
| Test pass với H2 nhưng PostgreSQL fail | Khác dialect, driver hoặc native type | Test với PostgreSQL thực qua Testcontainers |
| Lỗi sau nâng version | Driver/SPI/Spring dependency không tương thích | Kiểm tra dependency tree và BOM |

## 18. Kiểm thử cấu hình và kết nối

Nên có nhiều lớp kiểm thử:

### 18.1. Kiểm tra dependency/runtime artifact

CI có thể kiểm tra dependency tree hoặc khởi tạo application context với đúng runtime profile. Mục tiêu là phát hiện driver bị thiếu trước khi deploy.

### 18.2. Context test

Khởi động Spring context với cấu hình R2DBC và xác nhận bean ConnectionFactory tồn tại, metadata driver đúng. Context test này không nhất thiết chứng minh database đã sẵn sàng nếu connection được mở lazy.

### 18.3. Integration test với database đúng loại

Dùng Testcontainers hoặc database test cùng loại production. Kiểm tra:

1. Driver provider được discovery.
2. ConnectionFactory được tạo.
3. Connection mở thành công.
4. Smoke query thành công.
5. Migration/schema và quyền table đúng.
6. Repository save/find hoạt động.
7. Connection được đóng/trả pool sau test.

### 18.4. Kiểm tra lỗi cấu hình có chủ đích

Có thể có test cho URL sai scheme hoặc thiếu driver trong một module cấu hình riêng. Xác nhận lỗi có thông báo đủ rõ để phân biệt provider discovery với connection failure. Không làm hỏng runtime classpath chính chỉ để tạo negative test.

### 18.5. Không biến readiness thành query nặng

Readiness check có thể xác nhận ứng dụng sẵn sàng nhận traffic. Nếu mỗi lần probe chạy query phức tạp hoặc tạo connection mới, probe có thể làm tăng tải database. Dùng một truy vấn nhẹ và tần suất hợp lý; phân biệt liveness với readiness.

## 19. Checklist trước khi báo lỗi driver hoặc ConnectionFactory

- [ ] Có spring-boot-starter-data-r2dbc hoặc cấu hình Spring Data R2DBC tương ứng.
- [ ] Có đúng driver cho database đang dùng.
- [ ] Driver nằm trong runtime classpath và executable artifact.
- [ ] Không nhầm JDBC driver với R2DBC driver.
- [ ] URL dùng scheme r2dbc:<driver> đúng.
- [ ] Host, port và database name đúng.
- [ ] Profile và environment variable đang active được xác nhận.
- [ ] Không có custom ConnectionFactory bean cấu hình sai hoặc làm auto-config back off.
- [ ] R2DBC SPI, driver và Spring versions tương thích.
- [ ] Nếu dùng pool, dependency và pool options hợp lệ.
- [ ] Hostname/port truy cập được từ chính môi trường ứng dụng.
- [ ] Credentials, database permission và SSL/TLS đúng.
- [ ] Đã phân biệt lỗi factory creation, connection creation và SQL execution.
- [ ] Đã chạy smoke test bằng database/driver thật.
- [ ] Không log password, token hoặc URL chứa secret.

## 20. Quy trình khắc phục theo thứ tự

1. Đọc root cause và xác định lỗi xuất hiện ở startup, factory creation, connection creation hay SQL.
2. Kiểm tra runtime dependency tree và xác nhận driver đúng database.
3. Kiểm tra R2DBC URL scheme, host, port và database name.
4. Kiểm tra spring.r2dbc.* và profile/secret đang active.
5. Kiểm tra có ConnectionFactory bean thủ công hay routing factory không.
6. Xem condition evaluation report nếu Spring Boot không tạo bean.
7. Nếu factory đã có, kiểm tra DNS, network, server, credentials và TLS.
8. Nếu connection mở được, chạy SELECT 1 rồi kiểm tra schema/permission/migration.
9. Nếu dùng pool, kiểm tra acquire/create timeout và metrics.
10. Chạy integration test với database/driver cùng loại production.

Đổi từng biến một và ghi lại kết quả. Không đồng thời thay URL, driver version, pool size và SSL mode vì sẽ khó biết thay đổi nào giải quyết nguyên nhân.

## 21. Kết luận

Lỗi không tìm thấy R2DBC driver và lỗi không mở được database connection là hai giai đoạn khác nhau. Driver phải có trong runtime classpath và hỗ trợ scheme của R2DBC URL; Spring Boot phải đọc đúng spring.r2dbc.* hoặc ứng dụng phải tạo ConnectionFactory hợp lệ. JDBC driver, DataSource và jdbc: URL không thay thế được R2DBC driver, ConnectionFactory và r2dbc: URL.

Khi factory đã được tạo, chuyển sang kiểm tra host, port, DNS, network, database name, credentials, quyền và TLS. Nếu connection mở được nhưng SQL thất bại, kiểm tra schema, migration, query và mapping. Nếu có pool, phân biệt lỗi tạo pool/acquire connection với lỗi driver discovery.

Cuối cùng, hãy xác nhận từng lớp bằng dependency tree, condition evaluation report, ConnectionFactory metadata, smoke query và integration test trên database cùng loại production. Chẩn đoán theo giai đoạn giúp sửa đúng nguyên nhân, tránh thay đổi credentials hoặc pool một cách không liên quan và giữ thông tin bí mật khỏi log.
