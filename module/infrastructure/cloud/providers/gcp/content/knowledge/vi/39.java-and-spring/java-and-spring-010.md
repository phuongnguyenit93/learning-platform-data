# JDBC, R2DBC và Cloud SQL Java Connector

Ứng dụng Java và Spring thường lưu dữ liệu nghiệp vụ trong PostgreSQL hoặc MySQL. Khi triển khai trên Google Cloud, Cloud SQL cung cấp cơ sở dữ liệu quan hệ được quản lý, còn ứng dụng phải chọn một cách truy cập phù hợp: **JDBC** cho mô hình đồng bộ, **R2DBC** cho pipeline reactive và **Cloud SQL Java Connector** để thiết lập kết nối tới Cloud SQL với xác thực Google Cloud và mã hóa an toàn.

Bài học này thuộc chương **Java và Spring trên GCP** của module **CLOUD_PROVIDERS_GCP**. Trong phạm vi module từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, kiến thức kết nối Cloud SQL giúp lựa chọn dịch vụ, bảo vệ tài nguyên, triển khai có kiểm soát, đồng thời giám sát độ tin cậy và chi phí.

Sau bài học, bạn có thể:

- Phân biệt JDBC, R2DBC, database driver, connection pool và Cloud SQL Java Connector.
- Chọn mô hình đồng bộ hoặc reactive theo luồng xử lý thực tế của Spring.
- Kết nối PostgreSQL trong Cloud SQL qua JDBC/HikariCP hoặc R2DBC/ConnectionPool.
- Cấu hình Application Default Credentials (ADC), Cloud SQL IAM và IAM database authentication.
- Hiểu vì sao connector không tự tạo đường mạng tới private IP.
- Thiết kế pool phù hợp khi Cloud Run hoặc GKE mở rộng số instance.
- Điều tra lỗi kết nối, lỗi quyền, pool exhaustion và độ trễ truy vấn.

## 1. JDBC, R2DBC và connector giải quyết ba vấn đề khác nhau

Ba thành phần thường xuất hiện cạnh nhau nhưng không thay thế chức năng của nhau:

| Thành phần | Câu hỏi nó giải quyết | Cách hoạt động |
|---|---|---|
| JDBC | Java gọi SQL như thế nào? | API kết nối và thực thi truy vấn theo mô hình blocking |
| R2DBC | Java xử lý SQL bằng luồng reactive như thế nào? | API truy cập cơ sở dữ liệu bất đồng bộ, non-blocking, tương tác với Publisher |
| Cloud SQL Java Connector | Ứng dụng xác thực và thiết lập đường kết nối an toàn với Cloud SQL ra sao? | Lấy metadata, xác thực bằng Google Cloud IAM, quản lý TLS và hỗ trợ IAM database authentication |
| JDBC/R2DBC database driver | Giao tiếp với giao thức PostgreSQL, MySQL hoặc SQL Server như thế nào? | Triển khai giao thức và ánh xạ API của Java sang cơ sở dữ liệu |
| Connection pool | Tái sử dụng kết nối, giới hạn số connection và tránh chi phí mở lại như thế nào? | Giữ các connection sẵn có và phân phối tới request |

~~~mermaid
flowchart LR
    APP["Spring service"]
    APP --> J["JDBC<br/>JdbcTemplate / JPA"]
    APP --> R["R2DBC<br/>DatabaseClient / repositories"]
    J --> H["HikariCP / JDBC DataSource"]
    R --> RP["R2DBC ConnectionPool"]
    H --> JC["Cloud SQL Java Connector<br/>JDBC socket factory"]
    RP --> RC["Cloud SQL Java Connector<br/>R2DBC provider"]
    JC --> NET["Đường mạng hiện có<br/>public / private / PSC"]
    RC --> NET
    NET --> SQL["Cloud SQL PostgreSQL / MySQL"]
~~~

JDBC và R2DBC quyết định cách ứng dụng xử lý I/O database. Connector xử lý đặc thù kết nối và xác thực Cloud SQL. Có thể dùng JDBC/R2DBC không cần connector nếu kết nối database trực tiếp qua IP/host với cơ chế xác thực và TLS khác. Ngược lại, cài connector không tự biến JDBC thành non-blocking hoặc R2DBC thành JPA.

### Khi nào chọn JDBC?

Chọn JDBC khi ứng dụng dùng Spring MVC, JdbcTemplate, Spring Data JDBC hoặc Hibernate/JPA; nghiệp vụ có transaction truyền thống và các thư viện đã trưởng thành. JDBC blocking không tự trở thành vấn đề trong mọi ứng dụng: với connection pool phù hợp, số request và thread được kiểm soát, đây thường là lựa chọn đơn giản, dễ quan sát.

### Khi nào chọn R2DBC?

Chọn R2DBC khi toàn bộ luồng ứng dụng thực sự reactive: Spring WebFlux, Project Reactor, các downstream non-blocking và nhu cầu xử lý đồng thời rất nhiều I/O mà không chiếm một thread cho mỗi thao tác chờ. R2DBC không làm SQL chạy nhanh hơn tự thân; nếu truy vấn chậm, locking hoặc thiếu index, việc đổi API cũng không giải quyết được.

Không gọi JDBC blocking trực tiếp trên event-loop của WebFlux; tác vụ này có thể làm nghẽn event-loop. Nếu cần JDBC trong hệ reactive, tách sang scheduler thích hợp hoặc cân nhắc kiến trúc nhất quán. R2DBC không thay thế trực tiếp JPA/Hibernate: entity lifecycle, lazy loading và cơ chế transaction phải được thiết kế lại.

## 2. JDBC: API đồng bộ và nguyên tắc sử dụng

JDBC gồm DriverManager/DataSource, Connection, PreparedStatement và ResultSet. Thao tác gọi database thường chặn thread hiện tại cho đến khi có kết quả hoặc timeout. Spring Boot thường dùng DataSource với HikariCP, rồi dùng JdbcTemplate hoặc JPA ở lớp repository.

Ví dụ Java đọc trạng thái một đơn hàng với PreparedStatement:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderStatusRepository {
    private final DataSource dataSource;

    public OrderStatusRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findStatus(long orderId) throws SQLException {
        String sql = "SELECT status FROM orders WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next() ? rs.getString("status") : null;
            }
        }
    }
}
~~~

Điểm cần ghi nhớ:

- Dùng PreparedStatement và bind tham số; không nối dữ liệu đầu vào vào chuỗi SQL.
- Dùng try-with-resources để trả Connection về pool khi công việc kết thúc.
- Không giữ Connection trong singleton hoặc lưu vào HTTP session.
- Giao dịch nhiều câu lệnh phải được commit hoặc rollback đúng cách; trong Spring, ưu tiên @Transactional với transaction manager phù hợp.
- Đặt giới hạn thời gian chờ để một database outage không giữ vô hạn các thread xử lý request.

## 3. R2DBC: API truy cập cơ sở dữ liệu theo Reactive Streams

R2DBC (Reactive Relational Database Connectivity) định nghĩa ConnectionFactory, Connection, Statement và Result theo Reactive Streams. Thay vì trả ngay một giá trị hoặc blocking thread, API trả Publisher; ứng dụng thường thao tác với Mono và Flux của Project Reactor.

Ví dụ một repository dùng Spring DatabaseClient:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public final class ReactiveOrderRepository {
    private final DatabaseClient client;

    public ReactiveOrderRepository(DatabaseClient client) {
        this.client = client;
    }

    public Mono<String> findStatus(long orderId) {
        return client.sql("SELECT status FROM orders WHERE id = :id")
                .bind("id", orderId)
                .map((row, metadata) -> row.get("status", String.class))
                .one();
    }
}
~~~

Từ góc nhìn người gọi, Mono biểu thị kết quả bất đồng bộ có tối đa một phần tử; Flux dùng cho nhiều phần tử. Tác vụ chỉ được thực thi khi có subscription phù hợp.

Các giới hạn quan trọng:

- Tránh gọi block(), Thread.sleep hoặc JDBC blocking trong reactive path.
- Transaction của R2DBC dùng ReactiveTransactionManager và @Transactional trong ngữ cảnh reactive; không dùng JDBC transaction manager để quản lý R2DBC Connection.
- Không tạo subscription thủ công trong controller chỉ để “chạy cho xong”; trả Mono/Flux để framework quản lý request lifecycle.
- Backpressure hỗ trợ luồng dữ liệu, nhưng không loại bỏ giới hạn về số kết nối và năng lực xử lý truy vấn của Cloud SQL.
- Với nghiệp vụ cần JPA, JDBC thường đơn giản hơn một giải pháp reactive chắp vá.

## 4. Cloud SQL Java Connector hoạt động ra sao?

Cloud SQL Java Connector là thư viện kết nối cho các Cloud SQL instance. Thư viện dùng Google Cloud Application Default Credentials để gọi Cloud SQL Admin API, lấy thông tin instance và thông tin xác thực cần thiết, đồng thời thiết lập kết nối được mã hóa tới Cloud SQL. Nó hỗ trợ JDBC socket factory và provider cho R2DBC.

~~~mermaid
sequenceDiagram
    participant APP as Java / Spring
    participant CON as Cloud SQL Java Connector
    participant IAM as ADC / Google Cloud IAM
    participant API as Cloud SQL Admin API
    participant DB as Cloud SQL Database

    APP->>CON: Yêu cầu connection tới PROJECT:REGION:INSTANCE
    CON->>IAM: Lấy thông tin xác thực từ ADC
    CON->>API: Xác minh instance và lấy metadata/certificates
    API-->>CON: Thông tin kết nối đã xác thực
    CON->>DB: Kết nối mã hóa qua mạng sẵn có
    DB-->>CON: Phiên kết nối database
    CON-->>APP: JDBC Connection hoặc R2DBC Connection
~~~

**Connector không cấp đường mạng mới tới database.** Nếu chọn private IP, ứng dụng vẫn phải có đường đi hợp lệ tới VPC chứa Cloud SQL: ví dụ Compute Engine/GKE trong VPC, Cloud Run có Direct VPC egress hoặc Serverless VPC Access. Nếu chọn public IP, Cloud SQL instance phải có public IP và đường egress phù hợp. Với Private Service Connect (PSC), cần cấu hình PSC trước và chọn IP type tương ứng.

Connector là cơ chế xác thực/transport; ứng dụng vẫn phải xác thực ở tầng database bằng một trong hai cách:

1. **Built-in database authentication:** username/password của PostgreSQL hoặc MySQL.
2. **IAM database authentication:** user/service account Google Cloud được cấu hình làm database user; connector tự lấy và làm mới token ngắn hạn.

IAM role Cloud SQL Client chỉ cho phép principal kết nối qua connector; nó không mặc nhiên cấp SELECT/INSERT/UPDATE trong PostgreSQL. Database GRANT vẫn cần được thực hiện.

## 5. Điều kiện chuẩn bị trên Google Cloud

### 5.1. Tài nguyên cần có

Ví dụ trong bài dùng Cloud SQL for PostgreSQL:

- Project ID: demo-gcp-prod.
- Region: asia-southeast1.
- Instance: orders-db.
- **Instance connection name**: demo-gcp-prod:asia-southeast1:orders-db.
- Database: orders.
- Workload runtime: service account orders-api@demo-gcp-prod.iam.gserviceaccount.com.
- Chọn đường mạng: PRIVATE để đi qua VPC; PUBLIC hoặc PSC tùy thiết kế.

Instance connection name gồm **project:region:instance**, khác với IP, DNS host và database name. Không nhầm instance name với tên database trong JDBC URL.

Bật Cloud SQL Admin API:

~~~bash
gcloud services enable sqladmin.googleapis.com --project=demo-gcp-prod
~~~

Tạo Cloud SQL instance, database và database user theo quy trình quản trị hiện có. Nên quản lý instance/network/bộ nhớ/backup qua IaC, tránh tạo thủ công mỗi lần ứng dụng deploy. Đối với production, cần xem HA, PITR, backups, maintenance window và alerting trước khi kết nối workload.

### 5.2. Cấp quyền IAM cho runtime

Grant Cloud SQL Client ở project chứa Cloud SQL instance:

~~~bash
gcloud projects add-iam-policy-binding demo-gcp-prod \
  --member="serviceAccount:orders-api@demo-gcp-prod.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
~~~

Nếu dùng automatic IAM database authentication, cấp thêm Cloud SQL Instance User:

~~~bash
gcloud projects add-iam-policy-binding demo-gcp-prod \
  --member="serviceAccount:orders-api@demo-gcp-prod.iam.gserviceaccount.com" \
  --role="roles/cloudsql.instanceUser"
~~~

Trong môi trường nhiều project, nếu workload service account thuộc project khác, Cloud SQL Admin API cần được bật trong những project liên quan và IAM phải được cấp trên project sở hữu Cloud SQL instance.

Trong local development, dùng ADC:

~~~bash
gcloud auth application-default login
~~~

Trong Cloud Run, Compute Engine hoặc GKE, gắn service account runtime thích hợp vào workload. Trên GKE, ưu tiên Workload Identity Federation for GKE; tránh mount service account key JSON dài hạn.

### 5.3. Kiểm tra network và firewall

Cloud SQL Connectors cần:

| Luồng | Cổng | Tại sao cần |
|---|---:|---|
| Workload → Cloud SQL Admin API qua HTTPS | TCP 443 | Lấy metadata, IAM/certificates, làm mới thông tin xác thực |
| Workload → Cloud SQL instance | TCP 3307 | Thiết lập kênh Cloud SQL Connector |
| Workload → Internet hoặc endpoint private tương ứng | Theo cấu hình | Chỉ cần nếu các dịch vụ phụ thuộc khác yêu cầu |

Domain sqladmin.googleapis.com không có địa chỉ IP cố định. Nếu dùng egress policy, hãy thiết kế cho HTTPS đến API Google Cloud, thay vì pin một IP tĩnh.

Khi dùng private IP, route và DNS tới dịch vụ Google APIs, Cloud NAT/Private Google Access hoặc Private Service Connect cho API có thể ảnh hưởng kết nối. Network phải được thiết kế dựa trên nơi workload chạy. Không mở public ingress rộng để “sửa nhanh” một lỗi private connection.

## 6. JDBC + HikariCP + Spring Boot kết nối Cloud SQL

### 6.1. Dependency

Với PostgreSQL, cần Spring JDBC, PostgreSQL JDBC driver và Cloud SQL PostgreSQL socket factory.

Ví dụ Gradle Groovy DSL (chọn version socket factory phù hợp với bản connector đã kiểm thử):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'com.google.cloud.sql:postgres-socket-factory:1.31.0'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Spring Boot quản lý phiên bản starter và driver qua dependency management; library socket factory cần phiên bản được kiểm soát riêng. Mẫu 1.31.0 minh họa artifact upstream đang tài liệu hóa; trước khi dùng production, hãy kiểm tra release và compatibility matrix mới nhất.

Mặc định Spring Boot JDBC starter thường cung cấp HikariCP. Không khởi tạo một DataSource mới cho mỗi request.

### 6.2. Cấu hình DataSource dạng Java Bean

Ví dụ này dùng built-in database user và password được đọc từ biến môi trường do nền tảng cấp. Trong production, hãy lấy DB_PASSWORD từ Secret Manager hoặc cơ chế quản lý secret tương đương.

~~~java
package example.orders.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import javax.sql.DataSource;

@Configuration
public class JdbcCloudSqlConfig {

    @Bean(destroyMethod = "close")
    DataSource dataSource() {
        HikariConfig config = new HikariConfig();

        String db = requireEnv("DB_NAME");
        config.setJdbcUrl("jdbc:postgresql:///" + db);
        config.setUsername(requireEnv("DB_USER"));
        config.setPassword(requireEnv("DB_PASSWORD"));

        config.addDataSourceProperty(
                "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        config.addDataSourceProperty(
                "cloudSqlInstance", requireEnv("INSTANCE_CONNECTION_NAME"));
        config.addDataSourceProperty("ipTypes", "PRIVATE");
        config.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        // TLS được Cloud SQL Java Connector xử lý.
        config.addDataSourceProperty("sslmode", "disable");

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000); // 10 giây
        config.setIdleTimeout(300000);      // 5 phút
        config.setMaxLifetime(1800000);     // 30 phút

        return new HikariDataSource(config);
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required configuration: " + name);
        }
        return value;
    }
}
~~~

Giải thích các tham số:

| Tham số | Ý nghĩa |
|---|---|
| socketFactory | Cài đặt Cloud SQL Connector cho PostgreSQL JDBC |
| cloudSqlInstance | Instance connection name theo project:region:instance |
| ipTypes=PRIVATE | Chọn private IP; cần đường kết nối VPC tới instance |
| cloudSqlRefreshStrategy=lazy | Chỉ làm mới dữ liệu cần thiết khi cần, phù hợp serverless có CPU bị throttling |
| sslmode=disable | Vô hiệu lớp SSL riêng của pgJDBC vì TLS đã do connector quản lý |
| maximumPoolSize | Số physical connections tối đa cho mỗi application instance |
| connectionTimeout | Thời gian tối đa chờ một connection từ pool |

Lưu ý: sslmode=disable trong cấu hình **JDBC dùng Cloud SQL Connector** không có nghĩa truyền plaintext giữa application và Cloud SQL. Connector đảm nhiệm TLS. Không sao chép lựa chọn đó sang JDBC kết nối IP trực tiếp khi chưa cấu hình TLS theo driver.

### 6.3. Spring repository bằng JdbcTemplate

Sau khi Spring có DataSource bean, có thể dùng JdbcTemplate:

~~~java
package example.orders.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String statusOf(long id) {
        return jdbc.query(
            "SELECT status FROM orders WHERE id = ?",
            rs -> rs.next() ? rs.getString("status") : null,
            id
        );
    }
}
~~~

Với Spring Data JPA, giữ datasource này làm nền cho Hibernate, nhưng phải xem xét entity mapping, transaction boundaries và lazy loading. Không đưa database password vào source code hoặc URL được ghi log.

## 7. Automatic IAM database authentication với JDBC

Nếu tổ chức không muốn quản lý mật khẩu DB_USER/DB_PASSWORD, Cloud SQL hỗ trợ automatic IAM database authentication cho PostgreSQL và MySQL. Connector tự tạo/làm mới OAuth token thay cho mật khẩu database.

Cần thực hiện trước:

1. Bật IAM database authentication trên Cloud SQL instance (PostgreSQL dùng database flag cloudsql.iam_authentication).
2. Tạo IAM database user/service account trong Cloud SQL.
3. Cấp roles/cloudsql.client và roles/cloudsql.instanceUser cho principal runtime.
4. Thực hiện PostgreSQL GRANT để user có quyền trên schema/table cần thiết.
5. Dùng **cùng IAM identity** để chạy connector và để đăng nhập database.

Tạo IAM database user cho service account:

~~~bash
gcloud sql users create orders-api@demo-gcp-prod.iam.gserviceaccount.com \
  --instance=orders-db \
  --type=CLOUD_IAM_SERVICE_ACCOUNT \
  --project=demo-gcp-prod
~~~

PostgreSQL biểu diễn tên IAM service account bằng cách bỏ hậu tố .gserviceaccount.com. Với service account ví dụ, database username trở thành:

~~~text
orders-api@demo-gcp-prod.iam
~~~

Cấp quyền dữ liệu tại PostgreSQL cho username đó theo nhu cầu thực tế, ví dụ:

~~~sql
GRANT CONNECT ON DATABASE orders
  TO "orders-api@demo-gcp-prod.iam";
GRANT USAGE ON SCHEMA public
  TO "orders-api@demo-gcp-prod.iam";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public
  TO "orders-api@demo-gcp-prod.iam";
~~~

Các lệnh GRANT này là ví dụ, cần áp dụng bởi database administrator có đủ quyền. Quyền trên bảng mới tạo sau này cần cấu hình default privileges hoặc role ownership phù hợp.

Với Hikari, thay phần username/password và thêm enableIamAuth:

~~~java
config.setUsername("orders-api@demo-gcp-prod.iam");
config.setPassword("unused-nonempty"); // Driver validation yêu cầu khác rỗng
config.addDataSourceProperty("enableIamAuth", "true");
~~~

Khi enableIamAuth=true, connector dùng token IAM để xác thực; chuỗi password placeholder được driver yêu cầu về mặt đầu vào và không được sử dụng làm credential database thực tế. Trong code production, giải thích rõ placeholder để người vận hành không nhầm với mật khẩu hợp lệ.

**Phân biệt hai lớp quyền:** Cloud SQL Client cho phép thiết lập kết nối qua connector; Cloud SQL Instance User cho đăng nhập database bằng IAM. PostgreSQL GRANT quyết định user được phép truy cập dữ liệu nào sau khi đã đăng nhập.

Với Cloud SQL SQL Server, tính năng IAM database authentication theo mô hình này không được Java connector hỗ trợ. Chọn phương án user/password và driver phù hợp.

## 8. R2DBC + Cloud SQL Java Connector + Spring WebFlux

### 8.1. Dependency

Nếu chọn Spring WebFlux và R2DBC PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'com.google.cloud.sql:cloud-sql-connector-r2dbc-postgres:1.31.0'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
    implementation 'io.r2dbc:r2dbc-pool'
}
~~~

Spring Boot BOM quản lý các dependency Spring/R2DBC được hỗ trợ; Cloud SQL connector là dependency độc lập. Kiểm tra compatibility với Spring Boot, Java runtime, Netty và driver trước khi nâng cấp.

Đừng thêm JPA starter chỉ để truy cập cùng cơ sở dữ liệu trong ứng dụng R2DBC; JPA là blocking. Nếu hệ thống cần kết hợp, tách rõ ranh giới luồng xử lý và transaction.

### 8.2. Tạo ConnectionFactory

Đối với PostgreSQL, Cloud SQL R2DBC provider dùng DRIVER=gcp và PROTOCOL=postgresql. HOST được điền bằng instance connection name. Các giá trị khác như USER, DATABASE, PASSWORD đến từ cấu hình.

~~~java
package example.orders.config;

import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.Option;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

import static io.r2dbc.spi.ConnectionFactoryOptions.*;

@Configuration
public class ReactiveCloudSqlConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionPool connectionFactory() {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
            .option(DRIVER, "gcp")
            .option(PROTOCOL, "postgresql")
            .option(HOST, requireEnv("INSTANCE_CONNECTION_NAME"))
            .option(DATABASE, requireEnv("DB_NAME"))
            .option(USER, requireEnv("DB_USER"))
            .option(PASSWORD, requireEnv("DB_PASSWORD"))
            .option(Option.valueOf("ipTypes"), "PRIVATE")
            .build();

        ConnectionFactory delegate = ConnectionFactories.get(options);

        ConnectionPoolConfiguration poolConfig =
            ConnectionPoolConfiguration.builder(delegate)
                .initialSize(0)
                .maxSize(5)
                .maxIdleTime(Duration.ofMinutes(5))
                .maxAcquireTime(Duration.ofSeconds(10))
                .build();

        return new ConnectionPool(poolConfig);
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required configuration: " + name);
        }
        return value;
    }
}
~~~

Đây là R2DBC ConnectionPool, khác HikariCP. Spring có thể dùng bean này cho DatabaseClient và Spring Data R2DBC repositories. Các thuộc tính pool và giá trị cụ thể cần được tune theo instance database và số replica ứng dụng; không tự tăng pool vô hạn khi thấy timeout.

R2DBC cũng hỗ trợ URL dạng:

~~~text
r2dbc:gcp:postgres://DB_USER:DB_PASS@PROJECT:REGION:INSTANCE/DB_NAME
~~~

Trong production, tránh đặt secret trực tiếp trong URL vì URL có thể xuất hiện trong log cấu hình, exception và diagnostic. Dùng ConnectionFactoryOptions hoặc cơ chế secrets của Spring.

### 8.3. Automatic IAM auth cho R2DBC

Cloud SQL R2DBC provider hỗ trợ IAM database auth cho PostgreSQL và MySQL theo nguyên tắc giống JDBC. Thay password bằng một chuỗi placeholder khác rỗng, điền database username rút gọn rồi thêm option enableIamAuth:

~~~java
.option(USER, "orders-api@demo-gcp-prod.iam")
.option(PASSWORD, "unused-nonempty")
.option(Option.valueOf("enableIamAuth"), true)
~~~

Đoạn trên là các dòng thay thế tương ứng trong ConnectionFactoryOptions builder, không phải lời gọi độc lập sau build(). IAM database user, role và PostgreSQL GRANT phải được cấu hình trước. Không dùng tính năng này khi chưa đánh giá yêu cầu IAM/database của tổ chức.

### 8.4. Repository reactive và transaction

Spring Data R2DBC cho phép truy vấn theo Mono/Flux. Transaction cần ReactiveTransactionManager thay cho JpaTransactionManager/DataSourceTransactionManager.

Ví dụ controller trả Mono mà không block:

~~~java
package example.orders.api;

import example.orders.repository.ReactiveOrderRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final ReactiveOrderRepository repository;

    public OrderController(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/{id}/status")
    public Mono<String> status(@PathVariable long id) {
        return repository.findStatus(id)
                .defaultIfEmpty("NOT_FOUND");
    }
}
~~~

Controller và repository ở phần này phải tồn tại trong cùng dự án; class ReactiveOrderRepository ở mục 3 là ví dụ kiến trúc có thể dùng để xây triển khai hoàn chỉnh.

## 9. Kết nối qua public IP, private IP và PSC

Connector không tự cung cấp VPC peering, VPC route hoặc Private Service Connect. Chọn IP type phù hợp với topology:

| IP type | Khi nào phù hợp | Điều kiện mạng |
|---|---|---|
| PUBLIC | Workload có egress tới public IP Cloud SQL | Cloud SQL có public IP, egress TCP 3307/443; connector xử lý auth/TLS |
| PRIVATE | Workload nằm trong hoặc có đường tới VPC chứa Cloud SQL | Cloud SQL có private IP; VPC/Direct VPC egress/peering và route phù hợp |
| PSC | Cloud SQL được kết nối bằng Private Service Connect | PSC endpoint/network/DNS được cấu hình đúng |

Trong JDBC, dùng thuộc tính ipTypes như PRIVATE, PUBLIC hoặc PSC; trong R2DBC dùng option ipTypes. Giá trị mặc định khi không khai báo thường ưu tiên PUBLIC rồi PRIVATE. Vì vậy ở production cần cấu hình rõ IP type để tránh kết nối qua đường mạng khác kỳ vọng.

### Cloud Run

Nếu Cloud Run service dùng Cloud SQL connector với private IP, cấu hình Direct VPC egress tới VPC có route tới Cloud SQL, chọn subnet và kiểm tra firewall/egress. Đối với built-in Cloud SQL integration trên Cloud Run, Cloud Run có thể cung cấp connection qua socket; với thư viện Java Connector được ứng dụng khởi tạo trực tiếp, cách tích hợp socket built-in không bắt buộc.

### GKE

GKE workload có thể dùng Workload Identity Federation for GKE để cấp ADC cho service account Google Cloud. Đảm bảo pod/network policy và VPC/firewall cho egress 443/3307, sau đó dùng cùng cấu hình connector theo instance connection name.

### Compute Engine

VM chạy bằng service account đúng quyền Cloud SQL Client; OAuth access scope phải đủ để gọi APIs. Với private IP, VM cần nằm trong VPC hoặc đường kết nối hợp lệ đến Cloud SQL. Không đặt service account key trên đĩa VM.

## 10. Pooling, concurrency và giới hạn kết nối

Mở một kết nối database có chi phí xác thực, network handshake và tài nguyên trên PostgreSQL. Pool giúp tái sử dụng connection và đặt giới hạn số lượng.

Tổng số connection có thể tăng theo:

\[
\text{Số kết nối tối đa dự kiến}
\approx \text{Số instance ứng dụng} \times \text{Kích thước pool mỗi instance}
\]

Ví dụ, Cloud Run có 20 instance và HikariCP maximumPoolSize=5 thì có thể cần đến khoảng **100 physical connections**, chưa tính job, migration tool, console hay ứng dụng khác. Nếu autoscaling tăng nhanh, database có thể cạn connection trước khi CPU Cloud Run vượt ngưỡng.

### Khuyến nghị thiết kế pool

| Thiết lập | JDBC/HikariCP | R2DBC pool | Tác dụng |
|---|---|---|---|
| Maximum pool size | maximumPoolSize | maxSize | Chặn số connection mỗi app instance |
| Minimum/initial size | minimumIdle | initialSize | Tránh mở quá nhiều connection khi vừa scale |
| Acquire timeout | connectionTimeout | maxAcquireTime | Chặn request chờ pool quá lâu |
| Max idle time | idleTimeout | maxIdleTime | Giải phóng connection không dùng |
| Connection lifetime | maxLifetime | maxLifeTime nếu driver/pool hỗ trợ | Định kỳ thay connection |

Bắt đầu với pool nhỏ, quan sát Cloud SQL active connections, DB CPU, lock waits, query latency, connection acquire wait time và tỷ lệ 5xx/timeout. Chỉ tăng pool khi đã có dữ liệu chứng minh bottleneck, vì pool lớn không sửa được truy vấn kém hoặc thiếu index.

Trên Cloud Run, dùng lazy refresh để giảm hoạt động làm mới metadata không cần thiết khi CPU bị throttling. Khi Cloud SQL bảo trì hoặc failover, connection cũ có thể mất; ứng dụng cần retry có giới hạn, backoff và idempotency ở các thao tác phù hợp.

## 11. Transaction, timeout và retry

Một số lỗi khi kết nối database có thể do thiếu chiến lược transaction/timeout:

- Đặt timeout cho pool acquire, query và HTTP request tùy SLA.
- Dùng transaction ngắn, tránh chờ network call bên thứ ba trong một database transaction.
- Không retry mù mọi câu INSERT/UPDATE vì có nguy cơ ghi dữ liệu trùng khi commit đã thành công nhưng response thất bại.
- Với thao tác idempotent hoặc có idempotency key, retry exponential backoff có giới hạn.
- Phân biệt lỗi connection transient với lỗi cú pháp SQL, constraint violation hoặc permission: nhóm sau cần sửa logic/cấp quyền.
- Khi Cloud SQL failover, log và metric để xác định mất connection, recovery time, số request thất bại.

Trong Spring JDBC, @Transactional quản lý transaction trên DataSource. Trong Spring R2DBC, @Transactional với ReactiveTransactionManager dùng Reactor Context; không trộn thread-local JDBC transaction manager vào pipeline reactive.

## 12. Bảo mật credential và IAM

### 12.1. Chọn IAM database auth hay password?

| Tiêu chí | Built-in user/password | IAM database authentication |
|---|---|---|
| Credential ở tầng DB | Username + password | IAM user/service account + token ngắn hạn |
| Rotation | Tự quản lý, có thể lưu Secret Manager | Connector làm mới token |
| Quyền kết nối Cloud SQL | roles/cloudsql.client khi dùng connector | roles/cloudsql.client và roles/cloudsql.instanceUser |
| Quyền đọc/ghi dữ liệu | Database GRANT | Database GRANT |
| Phù hợp | Ứng dụng cũ, engine/công cụ cần password | Workload Google Cloud có IAM và muốn giảm password |
| Giới hạn | Phải quản lý và xoay vòng secret | Phải cấu hình IAM DB user, instance flag và bảo đảm principal nhất quán |

Google Cloud khuyến nghị IAM database authentication khi ứng dụng tương thích. Với password, Secret Manager giúp lưu/rotate secret an toàn. Không đưa DB_PASSWORD vào source code, Dockerfile, Git, log lỗi hoặc output của pipeline.

### 12.2. Áp dụng quyền tối thiểu

Service account runtime chỉ cần quyền kết nối Cloud SQL và role API thực sự sử dụng. Trong PostgreSQL, dùng các role chỉ đọc/chỉ ghi theo nhu cầu và schema cần thiết. Không sử dụng user postgres/superuser cho ứng dụng nghiệp vụ.

Đối với CI/CD migration, dùng một danh tính có quyền DDL riêng với runtime. Không cấp CREATE/ALTER/DROP cho service đang phục vụ request nếu không cần.

## 13. Observability và kiểm soát chi phí

Ứng dụng Java và Cloud SQL cần được giám sát cùng nhau. Các tín hiệu hữu ích:

- **Từ ứng dụng:** latency của API, query duration, Hikari active/idle/pending connections, R2DBC pool acquire duration, exception rate, timeout rate.
- **Từ Cloud SQL:** CPU, memory, disk, connection count, transaction throughput, lock waits, deadlocks và slow query insights.
- **Từ connector:** lỗi IAM/API, lỗi refresh/certificate, network timeout và tổng số lần tạo connection.

Micrometer + Spring Boot Actuator có thể xuất metric HikariCP. Với R2DBC, metric và tracing cần phụ thuộc vào connector/pool và instrumentation cụ thể; xác minh có số liệu thật trước khi tạo dashboard.

Khi tối ưu chi phí, cân nhắc: số connection, sizing Cloud SQL instance, HA, storage tăng trưởng, network egress cross-region và tài nguyên Cloud Run/GKE. Một pool quá lớn làm tăng tải DB và memory dù request throughput không tăng.

## 14. Tình huống triển khai Orders API trên Cloud Run

Giả sử Orders API dùng Spring Boot và Cloud SQL PostgreSQL đặt trong cùng region. Nhóm muốn private networking, không lưu password dài hạn và có thể scale.

Quy trình đề xuất:

1. Chuẩn bị Cloud SQL instance có private IP, database orders và IAM database authentication.
2. Tạo service account orders-api và cấp Cloud SQL Client + Cloud SQL Instance User.
3. Thêm service account làm IAM database user, cấp SQL GRANT đúng các bảng nghiệp vụ.
4. Triển khai Cloud Run service cùng service account; bật Direct VPC egress tới network có đường tới Cloud SQL.
5. Nếu hệ dùng Spring MVC/JPA, thêm pgJDBC + JDBC socket factory + HikariCP; nếu WebFlux/R2DBC, dùng R2DBC provider + connection pool.
6. Cấu hình instance connection name và ipTypes=PRIVATE, bật IAM auth; không dùng DB_PASSWORD thực trong configuration.
7. Đặt pool max 5 connection cho mỗi instance lúc đầu, kiểm tra Cloud Run max instances so với Cloud SQL connection budget.
8. Chạy migration bằng danh tính riêng, sau đó kiểm tra API SELECT/INSERT dưới runtime identity.
9. Giám sát API p95 latency, pool waiting, Cloud SQL active connections, CPU, lock waits và 5xx errors.
10. Thử nghiệm DB failover/restart trong staging; điều chỉnh connection timeout, retry và graceful shutdown.

Nếu sau deploy xuất hiện 403, hãy kiểm tra principal của Cloud Run và role ở project sở hữu Cloud SQL. Nếu nhận “permission denied for table”, kết nối/IAM đã qua nhưng PostgreSQL GRANT còn thiếu. Nếu nhận timeout đến private IP, kiểm tra route/Direct VPC egress trước khi sửa credentials.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| 403 PERMISSION_DENIED từ Cloud SQL Admin API | Thiếu Cloud SQL Client, ADC sai hoặc API chưa bật | Xác minh service account runtime, sqladmin.googleapis.com và role đúng project |
| Timeout khi gọi Cloud SQL Admin API | Không đi được tới sqladmin.googleapis.com qua HTTPS | Kiểm tra DNS, egress TCP 443, proxy/Private Google Access/PSC |
| Timeout tới Cloud SQL | Private IP thiếu đường mạng hoặc egress TCP 3307 bị chặn | Kiểm tra VPC, Direct VPC egress, firewall và ipTypes |
| Instance not found | Sai project:region:instance hoặc instance thuộc project khác | Xem instance connection name trong Cloud SQL Console |
| Password authentication failed | Sai built-in password hoặc username | Kiểm tra Secret Manager, version và DB user thực tế |
| IAM login failed | Chưa bật flag, chưa thêm IAM database user hoặc thiếu Instance User | Kiểm tra Cloud SQL IAM auth setting, IAM roles và username rút gọn |
| Permission denied for table/schema | PostgreSQL GRANT thiếu | Kiểm tra CONNECT, USAGE, SELECT/INSERT/UPDATE và default privileges |
| Hikari connection timeout | Pool đầy, query giữ connection lâu hoặc DB chậm | Xem active/pending pool, slow queries, transaction và max connections |
| R2DBC provider not found | Thiếu connector hoặc R2DBC driver tương thích | Kiểm tra classpath, phiên bản Spring Boot, gcp provider và PostgreSQL driver |
| Reactive endpoint bị chậm đồng loạt | JDBC hoặc tác vụ blocking chạy trên event-loop | Kiểm tra block(), CPU profiling và tracing; dùng driver non-blocking hoặc scheduler phù hợp |
| Sau failover request lỗi ngắn hạn | Connection cũ mất trong quá trình chuyển primary | Retry idempotent có backoff, giới hạn pool wait và giám sát phục hồi |
| Service đang chạy nhưng database connection tăng vọt | Autoscaling nhân số pool lên quá nhiều | Tính instance × maxPool, giới hạn scale và đo connection count |

Không ghi raw database password, IAM access token, connection URL có chứa credential hoặc SQL chứa dữ liệu nhạy cảm vào log khi debug. Nếu cần điều tra, ghi principal, instance connection name, error code và trace ID phù hợp.

## 16. Checklist production

- [ ] Database instance và engine/version tương thích với driver Java.
- [ ] Cloud SQL Admin API đã bật, service account runtime có quyền Cloud SQL Client.
- [ ] Nếu IAM auth, Cloud SQL Instance User role và IAM database user đã được cấu hình.
- [ ] PostgreSQL GRANT chỉ cấp quyền trên schema/table cần thiết.
- [ ] Workload có ADC hợp lệ, không lưu service account key JSON dài hạn.
- [ ] Đường mạng tới instance phù hợp với PUBLIC/PRIVATE/PSC và cổng 443/3307.
- [ ] JDBC dùng HikariCP/DataSource; R2DBC dùng reactive ConnectionFactory/ConnectionPool.
- [ ] Không chạy JDBC blocking trên WebFlux event-loop.
- [ ] Cấu hình thời gian chờ, pool size và retry phù hợp với SLA.
- [ ] Tổng giới hạn pool dự kiến không vượt connection budget của Cloud SQL.
- [ ] Secrets được quản lý bằng Secret Manager hoặc dùng automatic IAM DB authentication.
- [ ] Có migration workflow riêng với runtime identity.
- [ ] Đã kiểm thử failover, timeout và graceful shutdown.
- [ ] Có dashboard ứng dụng và Cloud SQL (connections, query latency, CPU, errors).
- [ ] Xác thực và quyền database đã được kiểm tra trên staging trước release.

## 17. Câu hỏi tự kiểm tra

**1. JDBC và R2DBC khác nhau ở đâu?**

JDBC là API truy cập cơ sở dữ liệu theo mô hình blocking, thường dùng với Spring MVC, JdbcTemplate và JPA. R2DBC dùng Reactive Streams để giao tiếp non-blocking, phù hợp Spring WebFlux và luồng reactive nhất quán.

**2. Cloud SQL Java Connector có tạo VPC route cho private IP không?**

Không. Connector hỗ trợ IAM, metadata và TLS. Workload vẫn phải có đường mạng thực tới private IP Cloud SQL thông qua VPC hoặc kết nối tương đương.

**3. Vì sao Cloud SQL Client chưa đủ để đọc bảng Orders?**

Cloud SQL Client cấp quyền kết nối qua connector. Đăng nhập ở tầng database và quyền SELECT/INSERT/UPDATE do database user và PostgreSQL GRANT quyết định.

**4. IAM database authentication cần những điều kiện gì?**

Bật IAM auth trên instance, thêm IAM database user/service account, cấp Cloud SQL Client và Cloud SQL Instance User, cấp quyền DB bằng GRANT, dùng cùng principal cho ADC và database user.

**5. Vì sao cần chú ý pool khi Cloud Run autoscaling?**

Mỗi Cloud Run instance có pool riêng. Tổng connection có thể tăng bằng số instance nhân kích thước pool; nếu vượt giới hạn Cloud SQL, kết nối mới có thể bị từ chối hoặc request bị timeout.

**6. Tại sao JDBC dùng Cloud SQL Connector có thể cấu hình sslmode=disable?**

Vì TLS giữa ứng dụng và Cloud SQL đã được Java Connector xử lý. Cách cấu hình này chỉ phù hợp khi đi qua socket factory của connector.

**7. Đổi sang R2DBC có làm truy vấn SQL chậm trở nên nhanh không?**

Không. Non-blocking cải thiện cách quản lý thread chờ I/O, không tự sửa thiếu index, lock contention, query plan kém hoặc database quá tải.

## 18. Tài liệu tham khảo

- [Cloud SQL: Connect using Cloud SQL language connectors](https://cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL Java Connector: repository và hướng dẫn chung](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory)
- [Cloud SQL Java Connector: JDBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md)
- [Cloud SQL Java Connector: R2DBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/r2dbc.md)
- [Cloud SQL Java Connector: configuration reference](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/configuration.md)
- [Cloud SQL for PostgreSQL: IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL for PostgreSQL: Log in with IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-logins)
- [Cloud SQL for PostgreSQL: Connection options](https://cloud.google.com/sql/docs/postgres/connection-options)
- [Cloud SQL for PostgreSQL: Manage connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL for PostgreSQL: Connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Spring Framework: R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [R2DBC Specification](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/)

