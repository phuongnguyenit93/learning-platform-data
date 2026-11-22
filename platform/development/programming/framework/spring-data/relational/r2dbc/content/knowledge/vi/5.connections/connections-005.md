# Khám phá trình điều khiển và tạo ConnectionFactory

Để ứng dụng Spring Data R2DBC truy cập cơ sở dữ liệu, trước hết phải có một **R2DBC driver** phù hợp và một **ConnectionFactory** được cấu hình đúng. Driver triển khai giao thức R2DBC cho một hệ quản trị cơ sở dữ liệu cụ thể; ConnectionFactory là điểm tạo kết nối theo chuẩn R2DBC SPI. Spring R2DBC và Spring Data R2DBC sử dụng ConnectionFactory này để thực thi SQL và thao tác entity.

Có thể hình dung chuỗi thành phần như sau:

~~~text
Ứng dụng Spring
    ↓
Spring Data R2DBC / Spring R2DBC
    ↓
ConnectionFactory
    ↓
R2DBC Driver
    ↓
Giao thức của hệ quản trị cơ sở dữ liệu
    ↓
Database
~~~

Bài học tập trung vào cách chọn driver, cách R2DBC SPI tìm driver, những cách tạo ConnectionFactory, cấu hình bằng Spring Boot, sử dụng connection pool và kiểm tra kết nối trong ứng dụng.

## 1. R2DBC driver là gì?

R2DBC (Reactive Relational Database Connectivity) là một đặc tả truy cập cơ sở dữ liệu quan hệ theo mô hình reactive. Đặc tả này định nghĩa SPI (Service Provider Interface) để các thư viện truy cập dữ liệu có thể làm việc với driver của nhiều hệ quản trị cơ sở dữ liệu theo một hợp đồng chung.

**R2DBC driver** là thư viện triển khai SPI đó cho một hệ quản trị cụ thể. Driver chịu trách nhiệm chuyển các lời gọi API thành giao tiếp mà database hiểu, gửi câu lệnh và tham số, nhận kết quả, chuyển dữ liệu thành các kiểu R2DBC và báo lỗi.

Ví dụ, ứng dụng kết nối PostgreSQL cần một driver R2DBC dành cho PostgreSQL. Ứng dụng kết nối H2 cần driver R2DBC dành cho H2. Cùng sử dụng SPI không có nghĩa là một driver có thể kết nối mọi hệ quản trị.

### 1.1. R2DBC driver và JDBC driver khác nhau

JDBC và R2DBC có mục tiêu tương tự ở mức nghiệp vụ: cho phép Java làm việc với cơ sở dữ liệu quan hệ. Tuy nhiên, chúng là hai API và hệ driver riêng biệt.

| Tiêu chí | JDBC | R2DBC |
|---|---|---|
| API chuẩn | JDBC API | R2DBC SPI |
| Driver | JDBC driver | R2DBC driver |
| Mô hình I/O | Thường blocking | Reactive, không blocking khi driver triển khai đúng |
| Kết quả truy cập | Các API đồng bộ như ResultSet | Publisher theo Reactive Streams |
| Kết nối | DataSource tạo JDBC Connection | ConnectionFactory tạo R2DBC Connection |
| Spring tích hợp | Spring JDBC | Spring R2DBC và Spring Data R2DBC |

Một JDBC URL có dạng như jdbc:postgresql://host:5432/database. R2DBC URL có scheme riêng, ví dụ r2dbc:postgresql://host:5432/database. Không thể đưa JDBC URL hoặc JDBC driver vào ConnectionFactory rồi kỳ vọng ứng dụng hoạt động reactive.

Cũng không nên kết luận rằng chỉ cần bọc lời gọi JDBC trong Mono hoặc Flux là đã chuyển thành R2DBC. Lời gọi JDBC vẫn blocking. Muốn dùng R2DBC, ứng dụng cần driver triển khai R2DBC SPI.

### 1.2. Chọn driver theo hệ quản trị và phiên bản

Khi chọn driver, cần xác định:

- Hệ quản trị cơ sở dữ liệu và phiên bản đang chạy.
- Phiên bản R2DBC SPI mà driver hỗ trợ.
- Phiên bản Spring Boot / Spring Framework / Spring Data tương thích với driver.
- Khả năng hỗ trợ kiểu dữ liệu, transaction, SSL/TLS, authentication và các tính năng SQL ứng dụng cần.
- Khả năng vận hành trong môi trường triển khai, bao gồm connection pooling, timeout và quan sát lỗi.

Một số driver thường gặp:

| Hệ quản trị | Driver R2DBC thường dùng |
|---|---|
| PostgreSQL | r2dbc-postgresql |
| H2 | r2dbc-h2 |
| MySQL | r2dbc-mysql |
| MariaDB | r2dbc-mariadb |
| Microsoft SQL Server | r2dbc-mssql |
| Oracle Database | oracle-r2dbc |

Tên artifact và cách cấu hình chi tiết có thể thay đổi theo nhà phát hành và phiên bản. Hãy dùng tài liệu của driver tương ứng và để Spring Boot dependency management quản lý phiên bản khi dự án sử dụng Spring Boot.

## 2. R2DBC SPI và vai trò của ConnectionFactory

R2DBC SPI định nghĩa một số abstraction để các thư viện phía trên không phải phụ thuộc trực tiếp vào cách một database cụ thể tạo kết nối.

Các thành phần quan trọng gồm:

- **ConnectionFactoryOptions**: tập hợp tùy chọn để mô tả driver, host, port, database, user, password và các thuộc tính kết nối khác.
- **ConnectionFactoryProvider**: provider do driver cung cấp, có khả năng nhận biết những options mà driver hỗ trợ và tạo ConnectionFactory tương ứng.
- **ConnectionFactories**: tiện ích tra cứu provider đã đăng ký và tạo ConnectionFactory.
- **ConnectionFactory**: abstraction tạo kết nối R2DBC.
- **Connection**: một phiên kết nối dùng để tạo statement, thực thi SQL, quản lý transaction và đóng kết nối.
- **Result** và **Row**: biểu diễn kết quả thực thi và một dòng dữ liệu trả về.

### 2.1. ConnectionFactory không phải là một Connection

Cần phân biệt hai đối tượng:

- ConnectionFactory là đối tượng tạo hoặc cấp phát kết nối. Ứng dụng thường giữ một instance dùng chung trong suốt vòng đời.
- Connection là một kết nối cụ thể được cấp phát cho một thao tác hoặc một đơn vị công việc. Kết nối cần được giải phóng đúng cách sau khi hoàn tất.

Phương thức create() của ConnectionFactory trả về một Publisher chứa Connection. Kết nối được lấy khi publisher được subscribe theo mô hình reactive. Việc gọi create() không giống như giữ một connection dùng chung cho toàn ứng dụng.

~~~java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

ConnectionFactory connectionFactory = /* cấu hình ở các phần sau */;

Mono<Connection> connectionPublisher =
    Mono.from(connectionFactory.create());
~~~

Publisher trên mô tả yêu cầu lấy kết nối. Khi đã lấy được connection, mã gọi trực tiếp R2DBC SPI phải chịu trách nhiệm giải phóng nó sau khi thao tác kết thúc. Khi sử dụng Spring DatabaseClient hoặc Spring Data R2DBC, framework quản lý vòng đời connection cho các thao tác do nó thực hiện.

### 2.2. ConnectionFactory cung cấp metadata

ConnectionFactory còn cung cấp metadata về driver:

~~~java
String driverName = connectionFactory.getMetadata().getName();
System.out.println("R2DBC driver: " + driverName);
~~~

Metadata hữu ích khi ghi log khởi động hoặc chẩn đoán cấu hình. Nó không thay thế việc kiểm tra kết nối thực tế: tạo được ConnectionFactory chưa chứng minh database đang truy cập được, thông tin đăng nhập hợp lệ hoặc mạng đã thông suốt.

## 3. Driver discovery: R2DBC tìm driver như thế nào?

Một R2DBC driver thường đăng ký provider theo cơ chế Java Service Provider. Khi ứng dụng thêm artifact driver vào runtime classpath, provider của driver được đăng ký để R2DBC SPI có thể tìm thấy.

Quá trình tổng quát:

1. Ứng dụng cung cấp ConnectionFactoryOptions hoặc R2DBC URL.
2. R2DBC SPI tìm các ConnectionFactoryProvider đã được đăng ký.
3. Provider kiểm tra xem có hỗ trợ driver/protocol và options đã cung cấp hay không.
4. Provider phù hợp tạo ConnectionFactory.
5. ConnectionFactory sử dụng driver để cấp phát connection khi có thao tác truy cập dữ liệu.

~~~mermaid
flowchart TB
    A["R2DBC URL / ConnectionFactoryOptions"]
    B["ConnectionFactories"]
    C["Service Provider discovery"]
    D["ConnectionFactoryProvider của driver"]
    E["ConnectionFactory"]
    F["R2DBC Connection"]
    G[("Database")]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
~~~

Nếu driver không có trong runtime classpath, SPI không thể tìm thấy provider phù hợp. Lỗi thường gặp là không tìm được driver phù hợp với URL hoặc options.

Đây là lý do dependency driver phải có ở runtime. Chỉ khai báo Spring Data R2DBC hoặc Spring R2DBC là chưa đủ để kết nối một database cụ thể.

## 4. Tạo ConnectionFactory bằng R2DBC URL

Cách ngắn gọn nhất là dùng R2DBC URL với tiện ích ConnectionFactories.

Ví dụ URL PostgreSQL:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;

ConnectionFactory connectionFactory =
    ConnectionFactories.get("r2dbc:postgresql://localhost:5432/orders");
~~~

Cấu trúc URL phổ biến có dạng:

~~~text
r2dbc:<driver>://[user:password@]host[:port]/database
~~~

Trong đó:

- r2dbc là scheme chỉ định đây là URL của R2DBC.
- driver xác định driver/provider cần sử dụng, ví dụ postgresql.
- user và password là thông tin xác thực nếu được cung cấp trong URL.
- host và port xác định máy chủ và cổng.
- database xác định database cần kết nối.

Cú pháp URL và các tùy chọn được hỗ trợ phụ thuộc driver. Một số driver có thêm tham số query để cấu hình SSL, timeout, schema hoặc các thuộc tính riêng. Hãy đối chiếu tài liệu driver trước khi sử dụng các tham số đó.

Không nên đưa mật khẩu thật vào URL nằm trong source code, file cấu hình được commit hoặc log. URL có thể bị ghi lại trong log lỗi hoặc thông tin chẩn đoán. Trong môi trường ứng dụng, hãy đưa thông tin xác thực vào biến môi trường hoặc secret manager và truyền qua cấu hình phù hợp.

## 5. Tạo ConnectionFactory bằng ConnectionFactoryOptions

Khi cần kiểm soát từng thuộc tính hoặc không muốn nhúng thông tin đăng nhập vào URL, có thể tạo ConnectionFactoryOptions bằng builder.

Ví dụ với PostgreSQL:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactoryOptions;

import java.util.Objects;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

public class R2dbcConnectionFactoryConfig {

    public ConnectionFactory connectionFactory() {
        String username = Objects.requireNonNull(
            System.getenv("DB_USERNAME"),
            "DB_USERNAME is required"
        );

        String password = Objects.requireNonNull(
            System.getenv("DB_PASSWORD"),
            "DB_PASSWORD is required"
        );

        ConnectionFactoryOptions options =
            ConnectionFactoryOptions.builder()
                .option(DRIVER, "postgresql")
                .option(HOST, "localhost")
                .option(PORT, 5432)
                .option(USER, username)
                .option(PASSWORD, password)
                .option(DATABASE, "orders")
                .build();

        return ConnectionFactories.get(options);
    }
}
~~~

Các option trên là những option chuẩn thường dùng. Driver có thể hỗ trợ thêm option riêng. Không phải mọi driver đều hỗ trợ cùng một tập thuộc tính hoặc cùng một kiểu dữ liệu cho option.

### 5.1. DRIVER và các option chuẩn

| Option | Ý nghĩa |
|---|---|
| DRIVER | Tên driver/provider cần sử dụng |
| PROTOCOL | Protocol hoặc biến thể kết nối nếu driver định nghĩa |
| HOST | Máy chủ cơ sở dữ liệu |
| PORT | Cổng dịch vụ |
| DATABASE | Tên database |
| USER | Tên đăng nhập |
| PASSWORD | Mật khẩu |
| SSL | Tùy chọn SSL nếu driver hỗ trợ |

Không phải kết nối nào cũng cần toàn bộ các option. Ví dụ, một số database nhúng không cần host hoặc port; một số driver dùng protocol hay thuộc tính riêng để chọn database hoặc schema.

### 5.2. Khi nào nên dùng URL, khi nào nên dùng Options?

| Cách tạo | Phù hợp khi |
|---|---|
| R2DBC URL | Cấu hình ngắn gọn, phù hợp với biến cấu hình môi trường hoặc Spring Boot |
| ConnectionFactoryOptions | Cần xây dựng options có điều kiện, đọc secrets riêng hoặc thêm option theo driver |
| Spring Boot properties | Ứng dụng Spring Boot muốn tận dụng auto-configuration và quản lý vòng đời bean |

Ba cách đều có thể tạo ra ConnectionFactory. Trong ứng dụng Spring Boot thông thường, nên ưu tiên cấu hình chuẩn của Boot để tránh tự tạo thêm một factory song song.

## 6. Khai báo dependency driver

Ứng dụng cần dependency của Spring Data R2DBC và driver tương ứng.

Ví dụ Gradle với Spring Boot và PostgreSQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Nếu dự án cần connection pool và phiên bản Spring Boot đang dùng không tự đưa pool dependency vào classpath, có thể thêm:

~~~kotlin
runtimeOnly("io.r2dbc:r2dbc-pool")
~~~

Khi sử dụng Spring Boot dependency management, nên bỏ version trực tiếp khỏi các dependency đã được BOM quản lý. Tránh tự chọn một phiên bản R2DBC SPI hoặc driver không tương thích với bộ phiên bản Spring Boot / Spring Data của dự án.

Cần phân biệt dependency của driver với dependency JDBC:

- PostgreSQL JDBC driver thường là org.postgresql:postgresql.
- PostgreSQL R2DBC driver là org.postgresql:r2dbc-postgresql.

Hai artifact phục vụ hai API khác nhau. Có mặt JDBC driver không đồng nghĩa có R2DBC driver.

## 7. Tạo ConnectionFactory bằng Spring Boot auto-configuration

Spring Boot có thể tạo và đăng ký ConnectionFactory từ cấu hình ứng dụng khi classpath có driver phù hợp. Spring Data R2DBC, Spring R2DBC và các thành phần liên quan sau đó có thể sử dụng bean này.

Ví dụ application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Trong cấu hình này:

- url xác định R2DBC driver và địa chỉ database.
- username và password lấy từ biến môi trường.
- Spring Boot tạo ConnectionFactory dựa trên URL, credentials và driver có trong runtime classpath.

Ứng dụng có thể inject ConnectionFactory hoặc sử dụng các abstraction cao hơn như DatabaseClient, R2dbcEntityTemplate và repository reactive.

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.stereotype.Component;

@Component
public class DatabaseConnectionInfo {

    private final ConnectionFactory connectionFactory;

    public DatabaseConnectionInfo(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String driverName() {
        return connectionFactory.getMetadata().getName();
    }
}
~~~

Không cần tự gọi ConnectionFactories.get() trong mỗi service. Một ConnectionFactory được quản lý bởi Spring container có thể được inject vào các thành phần cần truy cập dữ liệu.

### 7.1. Spring Boot auto-configuration cần những gì?

Thông thường cần đủ các điều kiện sau:

1. Có dependency Spring Boot R2DBC phù hợp.
2. Có R2DBC driver cho hệ quản trị đang dùng ở runtime classpath.
3. Có URL hoặc các thuộc tính kết nối hợp lệ.
4. Không có cấu hình tùy chỉnh xung đột làm auto-configuration bị thay thế.
5. Database có thể truy cập từ môi trường chạy ứng dụng và credentials hợp lệ.

Khi một bean ConnectionFactory do ứng dụng tự khai báo, auto-configuration có thể lùi lại theo điều kiện của Spring Boot. Vì vậy, nếu muốn Boot tự tạo factory, tránh khai báo thêm một factory không cần thiết.

### 7.2. Dùng profile cho môi trường khác nhau

Thông tin kết nối thường khác giữa local, test, staging và production. Có thể giữ cùng cấu trúc cấu hình nhưng thay giá trị bằng biến môi trường:

~~~yaml
spring:
  r2dbc:
    url: ${R2DBC_URL}
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
~~~

Ví dụ:

~~~text
Local:
R2DBC_URL=r2dbc:postgresql://localhost:5432/orders

Production:
R2DBC_URL=r2dbc:postgresql://db.internal:5432/orders
~~~

Không nên commit credentials vào repository. Trong môi trường production, sử dụng secret manager hoặc cơ chế cấp secrets của nền tảng triển khai. Chỉ cấp cho tài khoản ứng dụng những quyền database mà ứng dụng cần.

## 8. Connection pooling với r2dbc-pool

ConnectionFactory có thể tạo kết nối mới khi được yêu cầu. Trong ứng dụng phục vụ nhiều request, việc liên tục tạo và đóng kết nối vật lý có thể tốn tài nguyên và làm tăng độ trễ.

**Connection pool** quản lý một nhóm connection để các thao tác có thể mượn và trả lại connection. Trong hệ sinh thái R2DBC, thư viện r2dbc-pool cung cấp triển khai ConnectionFactory có khả năng pooling.

~~~mermaid
flowchart TB
    A["Repository / DatabaseClient"]
    B["Pooled ConnectionFactory"]
    C["Connection pool"]
    D["Connection 1"]
    E["Connection 2"]
    F["Connection N"]
    G[("Database")]

    A --> B
    B --> C
    C --> D
    C --> E
    C --> F
    D --> G
    E --> G
    F --> G
~~~

Ứng dụng vẫn làm việc với abstraction ConnectionFactory. Factory được bọc bởi pool sẽ quản lý việc cấp phát và tái sử dụng connection bên dưới.

### 8.1. Cấu hình pool trong Spring Boot

Khi có r2dbc-pool trên classpath, Spring Boot hỗ trợ cấu hình pool qua nhóm thuộc tính spring.r2dbc.pool.

Ví dụ:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 2h
      max-acquire-time: 5s
~~~

Ý nghĩa:

- enabled bật pool.
- initial-size là số connection ban đầu pool cố gắng khởi tạo theo cấu hình.
- max-size giới hạn số connection tối đa trong pool.
- max-idle-time giới hạn thời gian connection có thể nhàn rỗi.
- max-life-time giới hạn tuổi thọ connection.
- max-acquire-time giới hạn thời gian chờ lấy connection từ pool.

Tên thuộc tính và các tùy chọn khả dụng phụ thuộc phiên bản Spring Boot và r2dbc-pool. Hãy đối chiếu cấu hình của phiên bản dự án trước khi sao chép nguyên mẫu.

### 8.2. Tự tạo ConnectionPool bằng chương trình

Khi không dùng Spring Boot auto-configuration hoặc cần cấu hình thủ công, có thể bọc driver ConnectionFactory bằng ConnectionPool:

~~~java
import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.r2dbc.spi.ConnectionFactory;

import java.time.Duration;

ConnectionFactory driverFactory = /* factory tạo từ driver */;

ConnectionPoolConfiguration poolConfiguration =
    ConnectionPoolConfiguration.builder(driverFactory)
        .initialSize(5)
        .maxSize(20)
        .maxIdleTime(Duration.ofMinutes(30))
        .maxLifeTime(Duration.ofHours(2))
        .build();

ConnectionPool pooledFactory =
    new ConnectionPool(poolConfiguration);
~~~

ConnectionPool cũng triển khai ConnectionFactory, nên các thành phần Spring có thể dùng pooledFactory như một factory bình thường.

Nếu tự tạo pool trong Spring, hãy đăng ký bean và để Spring quản lý vòng đời, bao gồm việc dispose pool khi application context đóng. Không tạo pool mới cho mỗi request hoặc mỗi repository.

Không cấu hình đồng thời hai lớp pool cho cùng một đường kết nối. Nếu Boot đã tạo pooled ConnectionFactory, không bọc nó thêm một ConnectionPool khác trừ khi có lý do rõ ràng và hiểu được tác động.

### 8.3. Chọn kích thước pool

max-size không phải con số càng lớn càng tốt. Mỗi connection tiêu thụ tài nguyên ở database và ứng dụng. Cần cân nhắc:

- Giới hạn connection của database.
- Số instance ứng dụng chạy đồng thời.
- Số worker hoặc request thực sự truy cập database đồng thời.
- Thời gian trung bình một thao tác giữ connection.
- Connection dành cho migration, quản trị, batch job và các dịch vụ khác.

Ví dụ, nếu có 4 instance ứng dụng và mỗi instance cho phép tối đa 20 connection, riêng ứng dụng này có thể tạo tối đa 80 connection tới database. Con số đó phải nằm trong giới hạn mà database có thể phục vụ cùng với các client khác.

Pool quá nhỏ có thể khiến request phải chờ connection. Pool quá lớn có thể làm database quá tải và tăng tranh chấp. Hãy theo dõi thời gian acquire, số connection đang sử dụng, số connection nhàn rỗi và timeout trước khi điều chỉnh.

## 9. Vòng đời Connection và cách giải phóng tài nguyên

Khi sử dụng trực tiếp R2DBC SPI, connection phải được đóng sau khi thao tác hoàn tất. Trong reactive code, việc giải phóng cần diễn ra cả khi thao tác thành công, phát sinh lỗi hoặc bị hủy.

Spring cung cấp các abstraction như DatabaseClient để quản lý phần lớn vòng đời connection cho thao tác SQL. Khi làm việc trực tiếp với SPI, có thể dùng cơ chế quản lý tài nguyên reactive như Mono.usingWhen.

Ví dụ minh họa kiểm tra một truy vấn đơn giản:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

Mono<Integer> ping(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(connection.createStatement("SELECT 1").execute())
            .flatMap(result ->
                Mono.from(result.map((row, metadata) ->
                    row.get(0, Integer.class)
                ))
            ),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

Trong ví dụ, usingWhen quản lý việc đóng connection khi publisher hoàn tất bình thường, kết thúc do lỗi hoặc bị cancel. Kiểu dữ liệu của SELECT 1 trong ví dụ phụ thuộc database/driver; với hệ quản trị khác có thể cần điều chỉnh kiểu lấy từ Row.

Nếu connection được cấp từ pool, close() thường trả connection về pool để tái sử dụng. Nếu connection không thuộc pool, close() giải phóng kết nối theo triển khai driver.

Không nên lưu một Connection dùng chung trong singleton service để nhiều request cùng thao tác. Connection là tài nguyên có trạng thái, có transaction và vòng đời riêng; hãy để mỗi thao tác hoặc đơn vị công việc lấy và giải phóng connection theo cơ chế của framework.

## 10. Kiểm tra kết nối và chẩn đoán lỗi

Tạo được ConnectionFactory không đảm bảo kết nối thành công. Kết nối thực tế còn phụ thuộc DNS, mạng, firewall, host/port, trạng thái database, TLS, authentication, quyền truy cập và giới hạn connection.

Nên kiểm tra theo từng lớp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy provider/driver | Thiếu driver dependency hoặc sai DRIVER trong options | Kiểm tra runtime classpath và R2DBC URL |
| Không phân tích được URL | Sai scheme hoặc cú pháp URL | Dùng scheme r2dbc và cú pháp của driver |
| Connection refused / timeout | Host, port, firewall hoặc database chưa chạy | Kiểm tra DNS, route, port và trạng thái database |
| Authentication failed | Sai user/password hoặc cơ chế xác thực | Kiểm tra secrets và cấu hình auth |
| SSL handshake failed | TLS/certificate/protocol không tương thích | Kiểm tra SSL mode, trust store và chứng chỉ |
| Không lấy được connection từ pool | Pool cạn, thao tác giữ connection quá lâu hoặc database giới hạn | Theo dõi acquire timeout và pool metrics |
| Lỗi kiểu dữ liệu | Driver không hỗ trợ kiểu hoặc conversion chưa đúng | Kiểm tra driver codec và Spring Data custom conversions |

### 10.1. Kiểm tra cấu hình trước khi kiểm tra database

Có thể ghi lại tên driver từ metadata:

~~~java
System.out.println(connectionFactory.getMetadata().getName());
~~~

Không log password, URL có chứa password hoặc toàn bộ options nếu chúng có thông tin nhạy cảm. Log host, port, database và tên driver theo chính sách bảo mật của ứng dụng là đủ cho nhiều tình huống chẩn đoán.

### 10.2. Kiểm tra kết nối thật

Một health check nên thực hiện một thao tác database nhẹ qua đường kết nối mà ứng dụng đang dùng. Ví dụ, SELECT 1 có thể xác nhận rằng ứng dụng lấy được connection và database thực thi truy vấn.

Trong ứng dụng Spring Boot, có thể dùng cơ chế health indicator phù hợp với phiên bản và dependency đang cài. Nếu tự viết health check, hãy đặt timeout hợp lý và không tạo quá nhiều truy vấn kiểm tra liên tục.

Health check cần phân biệt trạng thái ứng dụng với trạng thái database. Nếu database tạm thời không sẵn sàng, hệ thống triển khai có thể cần đánh dấu readiness không đạt để ngừng nhận request mới; hành vi cụ thể phụ thuộc chính sách vận hành.

## 11. Những lưu ý bảo mật và vận hành

- Không hard-code username/password trong source code.
- Không commit file cấu hình chứa credentials thật.
- Dùng secret manager hoặc biến môi trường được bảo vệ trong runtime.
- Bật TLS/SSL khi môi trường và chính sách bảo mật yêu cầu; kiểm tra chứng chỉ thay vì tắt xác thực certificate để né lỗi.
- Dùng database account riêng cho ứng dụng với quyền tối thiểu cần thiết.
- Giới hạn pool theo tổng số instance và giới hạn connection của database.
- Đặt timeout cho việc acquire connection và các thao tác truy cập dữ liệu.
- Không log password, token hoặc URL có credentials.
- Theo dõi connection leak, pool exhaustion, timeout và lỗi driver.
- Đóng hoặc dispose pool khi ứng dụng dừng nếu ứng dụng tự tạo pool.

## 12. Chọn cách cấu hình nào trong dự án?

Có thể dùng các tiêu chí sau để chọn cách tạo ConnectionFactory:

| Bối cảnh | Cách nên dùng |
|---|---|
| Ứng dụng Spring Boot thông thường | Cấu hình spring.r2dbc.url, username, password và để Boot auto-configure |
| Muốn thay đổi địa chỉ database theo môi trường | Dùng biến môi trường hoặc profile cho các thuộc tính Spring Boot |
| Cần thêm option đặc thù của driver | Dùng URL có tham số driver hỗ trợ hoặc ConnectionFactoryOptions |
| Ứng dụng không dùng Spring Boot | Dùng ConnectionFactories.get(URL/options), sau đó đăng ký factory trong container DI |
| Cần tái sử dụng connection | Dùng r2dbc-pool hoặc pool được Boot cấu hình |
| Cần SQL/entity access trong Spring | Dùng ConnectionFactory làm nền cho DatabaseClient, R2dbcEntityTemplate hoặc repository |

Trong phần lớn ứng dụng Spring Boot, cách cấu hình qua application.yml là đủ. Tạo ConnectionFactory thủ công hữu ích khi ứng dụng cần cấu hình động, tích hợp nhiều database hoặc chạy ngoài Spring Boot. Pool nên được cấu hình ở một nơi duy nhất và được quản lý xuyên suốt vòng đời ứng dụng.

## 13. Ghi nhớ các khái niệm

- **R2DBC driver** triển khai R2DBC SPI cho một hệ quản trị cụ thể.
- **ConnectionFactoryOptions** mô tả thông tin để chọn driver và cấu hình kết nối.
- **ConnectionFactories** tìm provider đã đăng ký và tạo ConnectionFactory.
- **ConnectionFactory** tạo/cấp phát Connection theo mô hình reactive.
- **Connection** là tài nguyên cụ thể cần được giải phóng đúng cách.
- **Connection pool** tái sử dụng và giới hạn số connection đồng thời.
- **Spring Boot auto-configuration** có thể tạo ConnectionFactory từ cấu hình và driver trên classpath.
- **DatabaseClient / Spring Data R2DBC** sử dụng ConnectionFactory để thực hiện truy vấn và mapping ở tầng cao hơn.

Khi cấu hình R2DBC, hãy kiểm tra lần lượt driver artifact, URL/options, thông tin xác thực, khả năng truy cập database và pool. Phân biệt ConnectionFactory với Connection giúp tránh giữ kết nối sai vòng đời; hiểu driver discovery giúp xử lý lỗi thiếu provider; cấu hình pool đúng giới hạn giúp ứng dụng sử dụng tài nguyên database ổn định.

