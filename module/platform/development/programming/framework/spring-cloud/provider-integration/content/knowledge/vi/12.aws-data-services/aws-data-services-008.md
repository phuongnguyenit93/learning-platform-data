# Xác thực RDS bằng IAM khi được hỗ trợ và làm mới kết nối

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud, SDK và driver tương ứng. Với **Amazon Relational Database Service (Amazon RDS)**, ứng dụng Java thường dùng JDBC để truy cập PostgreSQL, MySQL hoặc MariaDB. Khi triển khai production, ngoài việc cấu hình JDBC URL và network, cần chọn cách xác thực database phù hợp với danh tính workload và vòng đời connection pool.

RDS hỗ trợ **IAM database authentication** cho một số engine/phiên bản, cho phép workload dùng AWS Identity and Access Management (IAM) để xác thực khi mở database connection thay cho password database dài hạn. Ứng dụng tạo một **authentication token** có chữ ký SigV4, dùng token như password trong bước handshake của JDBC. Token có thời hạn **15 phút**; connection đã xác thực có thể tiếp tục hoạt động sau khi token hết hạn.

Thách thức nằm ở connection pool: HikariCP giữ connection vật lý trong thời gian dài và chỉ mở connection mới khi cần. Nếu ứng dụng tạo token một lần lúc khởi động rồi cấu hình nó như password tĩnh, những connection được mở sau khi token hết hạn sẽ thất bại. Cần tạo token mới **mỗi khi mở physical connection**, đồng thời giữ pool ổn định và xử lý failover/credential refresh.

Sau bài học, bạn có thể:

1. Xác định RDS engine/phiên bản hỗ trợ IAM database authentication và bật tính năng đúng cách.
2. Phân biệt IAM permission `rds-db:connect`, database user và SQL privilege.
3. Tạo authentication token bằng AWS SDK for Java v2 với đúng Region, hostname, port và username.
4. Bảo vệ kết nối bằng TLS và xác minh hostname; không dùng token làm password tĩnh trong cấu hình.
5. Tích hợp token provider với HikariCP để làm mới token khi tạo connection vật lý.
6. Kết hợp IAM database authentication với RDS Proxy khi phù hợp, theo dõi pool, failover và rotation.
7. Kiểm thử cơ chế cấp token và kết nối thực tế trong môi trường AWS staging.

> **Phạm vi:** IAM database authentication có hỗ trợ theo engine và phiên bản cụ thể, không phải tính năng chung của mọi database engine trên RDS. Bài dùng PostgreSQL làm ví dụ chính; MySQL/MariaDB có cấu hình user và TLS khác. Luôn đối chiếu ma trận engine/version và hướng dẫn của AWS trước khi bật trong production.

## 2. IAM database authentication hoạt động như thế nào?

### 2.1. Luồng xác thực

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant IAM as AWS SDK / IAM credentials
    participant RDS as RDS PostgreSQL
    App->>IAM: Lấy credentials từ provider chain
    App->>IAM: Ký token với Region, endpoint, port, DB user
    IAM-->>App: IAM authentication token
    App->>RDS: Mở TLS connection, gửi DB user + token
    RDS->>RDS: Kiểm tra chữ ký và quyền IAM
    RDS-->>App: Database session đã xác thực
    Note over App,RDS: Token chỉ dùng khi xác thực connection mới
~~~

Các bước cụ thể:

1. Workload có AWS credentials từ IAM role hoặc credential provider chain.
2. Ứng dụng tạo token cho đúng hostname endpoint, port, Region và DB username.
3. JDBC driver mở TLS connection đến RDS.
4. Driver gửi database username và token trong quy trình xác thực.
5. RDS kiểm tra token/IAM permission và database user đã được cấu hình cho IAM authentication.
6. Nếu hợp lệ, server cấp session database. Sau khi xác thực, session không phải gửi lại token cho mỗi câu SQL.

Token là một chuỗi được ký, không phải mật khẩu database truyền thống và không cần gọi một API RDS từ xa để sinh token. Tuy nhiên, token chứa thông tin xác thực có thời hạn; coi token là dữ liệu nhạy cảm, không ghi vào log, tracing hoặc exception message.

### 2.2. Token 15 phút không phải tuổi thọ connection

Đây là điểm quan trọng nhất khi dùng IAM auth với HikariCP:

- Token có hiệu lực **15 phút kể từ khi được tạo** để bắt đầu xác thực.
- Một connection đã xác thực thành công có thể tiếp tục dùng sau khi token hết hạn.
- Khi Hikari mở một physical connection mới (pool scale up, connection cũ bị retire, failover, idle eviction), ứng dụng phải tạo token mới.
- Không cần tạo token mới cho mỗi câu SQL hoặc mỗi lần mượn logical connection từ pool.
- Không đặt `maxLifetime` bằng 15 phút chỉ vì token sống 15 phút. Hai khoảng thời gian có ý nghĩa khác nhau.

~~~text
09:00  Tạo token T1
09:01  Mở physical connection C1 bằng T1
09:15  T1 hết hạn
09:20  C1 vẫn có thể tiếp tục thực hiện SQL
09:22  Hikari cần mở connection C2 -> tạo token T2 mới
~~~

Nếu ứng dụng dùng token T1 làm password tĩnh trong `spring.datasource.password`, Hikari có thể dùng lại token cũ khi cần mở physical connection mới và nhận lỗi xác thực. Cách đúng là đặt logic tạo token ở tầng tạo physical connection.

## 3. RDS engine, database user và điều kiện hỗ trợ

### 3.1. Kiểm tra engine trước khi thiết kế

IAM database authentication được hỗ trợ cho các dòng engine như:

- Amazon RDS for PostgreSQL.
- Amazon RDS for MySQL.
- Amazon RDS for MariaDB.
- Amazon Aurora PostgreSQL-Compatible Edition.
- Amazon Aurora MySQL-Compatible Edition.

Tính năng còn phụ thuộc engine version, Region, cấu hình cluster/instance và topology. Không áp dụng giả định này cho RDS for Oracle hoặc SQL Server. Trước khi triển khai, kiểm tra trang hỗ trợ IAM database authentication cho **đúng engine và version** đang chạy.

IAM DB authentication phải được bật trên DB instance hoặc Aurora cluster theo hướng dẫn của engine. Một số tính năng/quy trình thay đổi cấu hình có thể cần thời gian áp dụng hoặc thao tác reboot theo loại tài nguyên; kiểm tra trạng thái sau khi cập nhật.

### 3.2. Giới hạn vận hành cần tính trước

- **Bộ nhớ database:** IAM DB authentication dùng tài nguyên tính toán trên DB; AWS khuyến nghị dự phòng khoảng **300–1.000 MiB bộ nhớ bổ sung** để kết nối ổn định. Dùng Enhanced Monitoring để so sánh bộ nhớ tiến trình RDS trước/sau khi bật, đặc biệt trên burstable instance.
- **Kích thước token:** token thường tối thiểu khoảng **1 KB** và có thể lớn hơn tùy IAM tags, policy và độ dài ARN. JDBC driver, proxy client hoặc công cụ trung gian không được cắt ngắn password/token.
- **Temporary credentials:** nếu token được ký bằng credentials tạm thời, credentials đó phải còn hiệu lực tại thời điểm client dùng token để mở connection. Sinh token sát thời điểm kết nối và dùng credential provider có khả năng refresh.
- **Hostname:** không dùng custom Route 53 DNS record thay cho DB instance/cluster endpoint để ký token. Khi kết nối qua RDS Proxy, dùng chính proxy endpoint theo hướng dẫn của proxy.
- **Audit:** CloudWatch và CloudTrail không ghi lại từng lần IAM DB authentication hoặc thao tác tạo token. Có thể audit thay đổi IAM role/policy riêng, nhưng không dựa vào CloudTrail để thống kê từng lần login.
- **IAM condition keys:** IAM DB authentication không hỗ trợ mọi global condition context key; không giả định các điều kiện như `aws:SourceIp`, `aws:SourceVpc` hoặc `aws:SourceVpce` sẽ giới hạn được action `rds-db:connect`. Dùng resource ARN/user scope cùng VPC, subnet và security group để kiểm soát các lớp tương ứng.
- **Nền tảng:** IAM DB authentication không được hỗ trợ trên RDS on Outposts. Với PostgreSQL, một user không thể đồng thời dùng IAM (`rds_iam`) và Kerberos (`rds_ad`); `rds_iam` làm IAM auth được ưu tiên so với password auth.

### 3.3. Tạo database user cho PostgreSQL

IAM permission chỉ cho phép danh tính AWS kết nối với DB user được chỉ định. Nó **không tự tạo database user** và không cấp quyền SQL trên schema/table.

Ví dụ trên PostgreSQL RDS:

~~~sql
-- Kết nối bằng admin/database user có quyền quản trị.
CREATE USER reservation_app;

-- Cho phép user dùng IAM database authentication.
GRANT rds_iam TO reservation_app;

-- Cấp quyền SQL riêng theo least privilege.
GRANT CONNECT ON DATABASE reservationdb TO reservation_app;
GRANT USAGE ON SCHEMA public TO reservation_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO reservation_app;

-- Nếu sequence được dùng bởi identity/serial columns:
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO reservation_app;
~~~

Nếu bảng được tạo trong tương lai, cần thiết lập `ALTER DEFAULT PRIVILEGES` phù hợp cho role tạo object; quyền `ON ALL TABLES` chỉ áp dụng các table hiện có tại thời điểm chạy lệnh.

Với PostgreSQL RDS/Aurora PostgreSQL, role `rds_iam` là role tích hợp để bật IAM authentication cho database user. Một user PostgreSQL được cấp `rds_iam` sẽ dùng IAM authentication thay cho password authentication; không cấp đồng thời `rds_ad` cho cùng user.

### 3.4. MySQL và MariaDB có cú pháp riêng

Ví dụ minh họa cho MySQL/MariaDB engine có hỗ trợ:

~~~sql
CREATE USER 'reservation_app' IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS';

GRANT SELECT, INSERT, UPDATE, DELETE
    ON reservationdb.* TO 'reservation_app';
~~~

Cú pháp plugin và cách cấp quyền phải đối chiếu theo engine/version cụ thể. Không dùng câu lệnh `GRANT rds_iam` của PostgreSQL cho MySQL/MariaDB. Với Aurora MySQL, user được cấu hình IAM authentication không dùng password authentication; cần thống nhất một phương thức xác thực cho user đó.

### 3.5. Phân biệt ba lớp quyền

| Lớp | Cơ chế | Câu hỏi được trả lời |
| --- | --- | --- |
| AWS workload identity | IAM role, OIDC/workload identity, credential provider | Ứng dụng đang chạy với danh tính AWS nào? |
| Cho phép đăng nhập DB | IAM policy action `rds-db:connect` gắn đúng DB resource/user | Danh tính AWS này có được xác thực vào DB user cụ thể không? |
| Quyền bên trong database | SQL `GRANT`, role và privilege của engine | DB user được SELECT/INSERT/UPDATE/DELETE object nào? |

Có `rds-db:connect` nhưng không có SQL privilege thì kết nối có thể thành công nhưng truy vấn bị `permission denied`. Có SQL privilege nhưng IAM policy sai thì bước handshake bị từ chối. Security group và TLS là các điều kiện mạng/bảo mật bổ sung, không thay thế hai lớp quyền này.

## 4. Cấp IAM permission `rds-db:connect`

### 4.1. Resource ARN có cấu trúc riêng

IAM database authentication dùng action **`rds-db:connect`**, không phải `rds:Connect`. Resource ARN có dạng:

~~~text
arn:aws:rds-db:<region>:<account-id>:dbuser:<db-resource-id>/<db-username>
~~~

Giá trị `<db-resource-id>` là resource ID của DB instance hoặc DB cluster theo loại tài nguyên, không phải DB identifier mà người quản trị thường đặt tên. Đối với RDS Proxy, dùng resource ID của proxy trong ARN theo hướng dẫn IAM DB authentication cho proxy.

Ví dụ policy cho một DB instance PostgreSQL:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "rds-db:connect",
      "Resource": "arn:aws:rds-db:ap-southeast-1:123456789012:dbuser:db-ABCDEFGHIJKLMNOP/reservation_app"
    }
  ]
}
~~~

Thay Region, account ID, resource ID và DB username bằng giá trị thật. Policy chỉ cho phép đăng nhập vào user `reservation_app` trên tài nguyên đã chỉ định; không dùng wildcard rộng nếu workload chỉ cần một user/database.

Với Aurora cluster, ARN dùng **DB cluster resource ID**. Với RDS Proxy, resource ID và cách cấp quyền khác với instance endpoint trực tiếp; không lấy DB identifier hoặc proxy DNS hostname thay cho resource ID.

### 4.2. Gắn role vào workload

Các cách cấp AWS credentials thường gặp:

- **Amazon ECS:** task role cho container ứng dụng.
- **Amazon EKS:** EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA) theo cấu hình cluster.
- **Amazon EC2:** instance profile role.
- **Môi trường phát triển:** AWS IAM Identity Center/profile hoặc credential provider được tổ chức cho phép.

AWS SDK for Java v2 có default credentials provider chain để tìm credential phù hợp. Ưu tiên credentials tạm thời do role cấp; tránh access key dài hạn trong `application.yml`, Docker image, biến môi trường commit vào pipeline hoặc source code.

Không cần cấp `rds:DescribeDBInstances` chỉ để ký token nếu ứng dụng đã biết endpoint, port và username. Chỉ cấp quyền quản trị/describe nếu chức năng thực sự cần.

## 5. Tạo token bằng AWS SDK for Java v2

### 5.1. Dependency

Thêm AWS SDK v2 RDS module, quản lý version đồng nhất bằng AWS SDK BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>rds</artifactId>
</dependency>
~~~

Ứng dụng vẫn cần JDBC driver của database, ví dụ PostgreSQL:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Spring Boot có thể dùng `spring-boot-starter-jdbc` để đưa vào JDBC, HikariCP và auto-configuration. AWSpring không bắt buộc phải có một starter RDS JDBC riêng; IAM token được tạo bằng AWS SDK, sau đó driver JDBC sử dụng token khi mở connection.

### 5.2. Sinh token cho PostgreSQL

Để có thể kiểm thử DataSource mà không gọi AWS, định nghĩa một interface nhỏ cho nguồn token:

~~~java
@FunctionalInterface
public interface IamTokenSupplier {
    String getToken();
}
~~~

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;
import software.amazon.awssdk.services.rds.model.GenerateAuthenticationTokenRequest;

public final class RdsIamTokenProvider implements IamTokenSupplier, AutoCloseable {
    private final RdsUtilities utilities;
    private final DefaultCredentialsProvider credentialsProvider;
    private final String hostname;
    private final int port;
    private final String username;

    public RdsIamTokenProvider(
            Region region, String hostname, int port, String username) {
        this.credentialsProvider = DefaultCredentialsProvider.create();
        this.utilities = RdsUtilities.builder()
                .region(region)
                .credentialsProvider(credentialsProvider)
                .build();
        this.hostname = hostname;
        this.port = port;
        this.username = username;
    }

    @Override
    public String getToken() {
        return utilities.generateAuthenticationToken(
                GenerateAuthenticationTokenRequest.builder()
                        .hostname(hostname)
                        .port(port)
                        .username(username)
                        .build());
    }

    @Override
    public void close() {
        credentialsProvider.close();
    }
}
~~~

Token được ký bằng AWS credentials hiện tại. SDK credential provider có thể lấy và làm mới credential tạm thời từ workload role theo provider chain. `RdsUtilities` cần đúng Region và endpoint; không dùng endpoint IP đã resolve thay cho DNS hostname.

Có thể tạo token bằng AWS CLI để kiểm tra thủ công:

~~~bash
aws rds generate-db-auth-token \
  --hostname mydb.abcdefghijkl.ap-southeast-1.rds.amazonaws.com \
  --port 5432 \
  --region ap-southeast-1 \
  --username reservation_app
~~~

Lệnh CLI cần AWS credentials có quyền `rds-db:connect` phù hợp. Token sinh ra là dữ liệu nhạy cảm; không đưa vào ticket, shell history chia sẻ, log CI hoặc chat công khai. Lệnh này giúp xác nhận khả năng tạo token, nhưng chưa chứng minh network, TLS, DB user và SQL grants đều đúng.

### 5.3. Token phải khớp chính xác endpoint đang kết nối

Các tham số phải thống nhất:

- `hostname`: RDS endpoint hoặc RDS Proxy endpoint mà JDBC client thật sự dùng.
- `port`: port database của endpoint.
- `region`: Region chứa DB/proxy.
- `username`: database username đã được cấu hình IAM authentication.

Khi dùng RDS Proxy, phải ký token với **hostname proxy endpoint** và dùng policy/resource ID của proxy theo tài liệu. Không tạo token cho DB instance rồi gửi đến proxy hostname. AWS không hỗ trợ custom Route 53 DNS record thay cho DB instance/cluster endpoint khi ký token; không tự thay hostname bằng alias hoặc IP đã resolve.

## 6. TLS là điều kiện bắt buộc trong IAM database authentication

IAM DB authentication yêu cầu kết nối được mã hóa bằng SSL/TLS. Với PostgreSQL JDBC, có thể dùng `sslmode=verify-full` và CA bundle phù hợp:

~~~yaml
app:
  rds:
    jdbc-url: jdbc:postgresql://db.example.ap-southeast-1.rds.amazonaws.com:5432/reservationdb
    host: db.example.ap-southeast-1.rds.amazonaws.com
    port: 5432
    username: reservation_app
    region: ap-southeast-1
    ca-file: /etc/ssl/certs/global-bundle.pem
~~~

Khi mở connection, truyền thuộc tính driver:

~~~java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", token);
properties.setProperty("sslmode", "verify-full");
properties.setProperty("sslrootcert", caBundlePath);
~~~

`verify-full` kiểm tra CA chain và hostname khớp certificate. Cập nhật CA bundle theo lịch AWS công bố và triển khai trước khi certificate cũ hết hạn. Không tắt TLS để "sửa nhanh" lỗi xác thực; IAM token không thay thế mã hóa đường truyền.

Với MySQL Connector/J, cấu hình TLS dùng `sslMode=VERIFY_IDENTITY` và trust material tương ứng với driver. Property của PostgreSQL và MySQL không giống nhau; kiểm tra đúng tài liệu JDBC driver đang dùng.

## 7. Làm mới token đúng cách với HikariCP

### 7.1. Tại sao password tĩnh không hoạt động lâu dài?

Cấu hình đơn giản như sau là không phù hợp cho IAM authentication:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example:5432/reservationdb
    username: reservation_app
    password: "<token-created-at-startup>"
~~~

Spring Boot khởi tạo DataSource một lần và HikariCP có thể dùng cùng password khi tạo physical connection mới sau nhiều phút. Token lúc startup hết hạn sau 15 phút; pool vẫn có thể đang hoạt động vì các connection đã xác thực, nhưng khi cần thêm hoặc thay connection, driver gửi token cũ và bị từ chối.

Không cần làm mới token cho mỗi lần `getConnection()` của ứng dụng nếu đó chỉ là logical borrow từ pool. Cần làm mới tại **lần tạo physical JDBC connection**.

### 7.2. Kiến trúc DataSource tạo token theo từng physical connection

Có thể bọc JDBC driver bằng một DataSource tùy chỉnh. HikariCP dùng DataSource này làm nguồn tạo physical connection; mỗi lần Hikari cần kết nối mới, DataSource sinh token mới rồi gọi driver.

~~~mermaid
flowchart TD
    A["Spring JdbcTemplate"] --> B["HikariCP pool"]
    B -->|"Borrow logical connection"| C["Connection đã có"]
    B -->|"Cần physical connection mới"| D["IAM-aware DataSource"]
    D --> E["RdsIamTokenProvider.getToken()"]
    E --> F["AWS SDK ký token mới"]
    F --> G["JDBC Driver + TLS"]
    G --> H["RDS / RDS Proxy"]
    H --> B
~~~

Ví dụ DataSource dành cho PostgreSQL:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

import org.springframework.jdbc.datasource.AbstractDataSource;

public final class IamPostgresDataSource extends AbstractDataSource {
    private final String jdbcUrl;
    private final String username;
    private final String caBundlePath;
    private final IamTokenSupplier tokenProvider;

    public IamPostgresDataSource(
            String jdbcUrl,
            String username,
            String caBundlePath,
            IamTokenSupplier tokenProvider) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.caBundlePath = caBundlePath;
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Connection getConnection() throws SQLException {
        final String token;
        try {
            token = tokenProvider.getToken();
        } catch (RuntimeException ex) {
            throw new SQLException("Unable to generate RDS IAM token", ex);
        }

        Properties properties = new Properties();
        properties.setProperty("user", username);
        properties.setProperty("password", token);
        properties.setProperty("sslmode", "verify-full");
        properties.setProperty("sslrootcert", caBundlePath);

        return DriverManager.getConnection(jdbcUrl, properties);
    }

    @Override
    public Connection getConnection(String requestedUser, String ignoredPassword)
            throws SQLException {
        if (!username.equals(requestedUser)) {
            throw new SQLException("Unexpected database username");
        }
        // Không sử dụng password tĩnh do caller truyền vào.
        return getConnection();
    }
}
~~~

DataSource tạo token **mỗi khi DriverManager mở một physical connection**. HikariCP giữ connection đó trong pool; khi connection được trả về, Hikari chỉ reset/đưa logical handle về trạng thái idle. Token không được tạo lại cho mỗi query.

Trong ví dụ, `AbstractDataSource` là lớp tiện ích của Spring JDBC. PostgreSQL JDBC driver phải có trên runtime classpath để `DriverManager` tìm thấy driver. Với MySQL, cần một DataSource/driver adapter dùng đúng thuộc tính TLS của Connector/J thay vì sao chép `sslmode`/`sslrootcert`.

### 7.3. Cấu hình HikariCP dùng custom DataSource

Tạo một bean `RdsUtilities` và custom DataSource, sau đó đưa custom DataSource vào Hikari:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;

import javax.sql.DataSource;

@Configuration
public class RdsIamDataSourceConfiguration {

    @Bean(destroyMethod = "close")
    RdsIamTokenProvider rdsIamTokenProvider(
            @Value("${app.rds.region}") String region,
            @Value("${app.rds.host}") String host,
            @Value("${app.rds.port}") int port,
            @Value("${app.rds.username}") String username) {
        return new RdsIamTokenProvider(
                Region.of(region), host, port, username);
    }

    @Bean
    @Primary
    DataSource dataSource(
            RdsIamTokenProvider tokenProvider,
            @Value("${app.rds.jdbc-url}") String jdbcUrl,
            @Value("${app.rds.username}") String username,
            @Value("${app.rds.ca-file}") String caBundlePath) {

        IamPostgresDataSource physicalDataSource =
                new IamPostgresDataSource(
                        jdbcUrl, username, caBundlePath, tokenProvider);

        HikariConfig config = new HikariConfig();
        config.setPoolName("RdsIamPool");
        config.setDataSource(physicalDataSource);
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setMaxLifetime(1500000);

        // Không đặt config.setUsername()/setPassword():
        // IAM-aware DataSource tự tạo token cho mỗi physical connection.
        return new HikariDataSource(config);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Ví dụ dùng `@Primary` để Spring Boot/JdbcTemplate chọn DataSource này. Khi đã tự tạo DataSource, auto-configuration DataSource mặc định của Boot sẽ lùi lại. Không khai báo đồng thời một DataSource password-based khác rồi vô tình inject nhầm vào repository hoặc transaction manager.

`DataSourceTransactionManager` phù hợp cho JDBC transaction đơn DataSource. Nếu ứng dụng dùng JPA/JdbcTemplate chung một DataSource, dùng transaction manager tương ứng theo kiến trúc Spring Boot (ví dụ `JpaTransactionManager` có thể phối hợp JDBC access cùng DataSource); không tạo nhiều transaction manager không chủ ý.

Pool size và lifetime là giá trị minh họa; chọn theo DB connection budget, số replica, RDS Proxy và thời gian query. Token provider cần được gọi ở mỗi physical connect; không giữ token trong field như một giá trị dùng lại.

### 7.4. Vì sao không cần refresh mọi connection mỗi 15 phút?

Token hết hạn chỉ ngăn token cũ được dùng để **xác thực một kết nối mới**. Nó không phải session timeout của database. Nếu pool đang có 8 connection khỏe mạnh, cả 8 connection vẫn có thể phục vụ query sau phút thứ 15.

Không cần đóng toàn bộ pool theo chu kỳ token. Làm như vậy có thể gây connection storm: nhiều instance cùng mở lại connection, tạo tải xác thực và handshake lớn. Chỉ để HikariCP retire connection theo `maxLifetime`/validation policy phù hợp và tạo connection mới với token mới khi cần.

`maxLifetime` cần phối hợp với idle timeout của network, DB, proxy và thời gian bảo trì. Hikari không đóng một connection đang được mượn; nó đánh dấu connection để retire khi trả lại. `keepaliveTime` có thể giúp phát hiện/giữ connection idle theo cấu hình, nhưng không thay thế kiểm tra failover hoặc retry nghiệp vụ.

## 8. Dùng IAM database authentication qua RDS Proxy

### 8.1. Hai chặng xác thực cần phân biệt

RDS Proxy có thể nằm giữa ứng dụng và DB:

~~~text
Spring Boot -- IAM auth / TLS --> RDS Proxy -- backend auth --> RDS
~~~

RDS Proxy có hai mô hình cần phân biệt:

| Mô hình | Client → Proxy | Proxy → Database | Credential/permission chính |
| --- | --- | --- | --- |
| **Standard IAM authentication** | Ứng dụng dùng token IAM ký cho proxy endpoint | Proxy dùng database username/password lấy từ Secrets Manager | Role ứng dụng cần `rds-db:connect` trên proxy resource ID dạng `prx-...`; proxy role cần đọc secret và KMS key phù hợp. DB user backend tiếp tục dùng password auth; không cấu hình cùng DB user đó thành IAM-only user. |
| **End-to-end IAM authentication** | Ứng dụng dùng token IAM ký cho proxy endpoint | Proxy dùng IAM database authentication đến DB | Role ứng dụng cần `rds-db:connect` trên proxy resource ID; IAM role gắn với proxy cần `rds-db:connect` trên DB instance/cluster resource ID và DB user. Database user phải được cấu hình IAM auth. Không cần secret chứa DB password cho luồng end-to-end. |

Với end-to-end IAM, cấu hình proxy có `DefaultAuthScheme=IAM_AUTH`; xác nhận engine/version/Region nằm trong danh sách hỗ trợ hiện hành (AWS công bố cho MySQL và PostgreSQL). Bật IAM DB authentication trên DB target trước, tạo DB user tương ứng và cấp quyền IAM cho cả client role lẫn proxy role theo đúng tài nguyên. Standard IAM authentication vẫn hữu ích khi muốn client vào proxy bằng IAM nhưng giữ password authentication ở database backend. Với PostgreSQL, không grant `rds_iam` cho DB user trong mô hình standard nếu proxy cần đăng nhập backend bằng password.

Trong cả hai mô hình, token client phải được ký cho **RDS Proxy endpoint**, không phải endpoint DB đích. Không mặc định rằng client IAM auth đồng nghĩa proxy tự dùng IAM tới DB: chỉ end-to-end IAM mới áp dụng IAM cho cả hai chặng.

### 8.2. Khi nào proxy hữu ích?

RDS Proxy đáng cân nhắc khi:

- Workload scale nhanh hoặc có nhiều instance mở/đóng connection.
- Serverless/container có nhiều client sessions ngắn.
- Muốn quản lý backend connections và giảm tác động của connection churn.
- Muốn tách credential giữa client và database target theo cơ chế proxy hỗ trợ.

Proxy không loại bỏ HikariCP, không làm query nhanh hơn nếu DB đang nghẽn CPU/I/O, và không đảm bảo mọi session đều multiplex. Transaction dài hoặc session state có thể làm connection pinning. Theo dõi client connections, database connections, borrow latency và proxy target health.

## 9. IAM credential refresh, password rotation và failover

### 9.1. Làm mới AWS credentials khác làm mới DB token

Có hai vòng đời khác nhau:

1. **AWS credentials**: credentials tạm thời từ ECS task role, EC2 instance profile, EKS Pod Identity/IRSA hoặc AssumeRole có expiration riêng. AWS SDK credential provider chain có thể refresh credential theo provider.
2. **RDS IAM token**: được ký bằng AWS credentials tại thời điểm tạo, có thời hạn 15 phút và dùng khi mở DB connection mới.

Không cache AWS session credentials hoặc token trong static field lâu hơn expiration. Dùng SDK provider có khả năng refresh và tạo token mới ngay trước physical connect. Nếu role bị thu hồi quyền, connection mới có thể bị từ chối; các session đã xác thực không tự động bị ngắt ngay chỉ vì IAM policy đổi.

### 9.2. IAM auth khác password rotation

Secrets Manager rotation thay đổi database password/secret theo workflow của secret. IAM database authentication dùng token ngắn hạn được ký bằng IAM credentials; không phải password cố định được rotation mỗi tháng.

Nếu ứng dụng dùng **password-based JDBC** với Secrets Manager, cần refresh secret và thay connection khi mở mới. Nếu dùng **IAM DB auth**, cần refresh AWS credentials qua provider chain và sinh token mới mỗi lần physical connection. Hai cơ chế có thể kết hợp ở RDS Proxy trong cấu hình phù hợp, nhưng không nên trộn logic credential mà không xác định rõ client-auth và target-auth.

### 9.3. RDS failover và DNS endpoint

Khi RDS failover hoặc DB restart:

- Connection vật lý cũ có thể bị đóng hoặc mất hiệu lực.
- Hikari có thể phát hiện connection lỗi khi validation hoặc khi query sử dụng; request đang chạy có thể thất bại.
- Endpoint DNS chính thức tiếp tục là địa chỉ ứng dụng nên dùng; không pin IP đã resolve.
- Khi mở connection mới, IAM token phải được ký với hostname endpoint đang dùng và Region tương ứng.
- Transaction bị ngắt trong lúc commit có thể có kết quả không rõ với caller; dùng business key/idempotency để đối soát trước khi retry.

RDS Proxy có thể cải thiện quá trình failover ở tầng connection, nhưng không đảm bảo transaction đang thực thi không lỗi. Hãy thử failover trên môi trường staging, ghi nhận thời gian hồi phục, connection acquisition latency và số request cần retry.

## 10. Bảo mật và vận hành

### 10.1. Checklist bảo mật

- Gắn IAM role đúng workload; policy chỉ cấp `rds-db:connect` cho DB resource/user cần thiết.
- Cấp SQL privilege riêng theo least privilege; không dùng master/admin DB user cho ứng dụng.
- Bắt buộc TLS và hostname verification; quản lý CA bundle và thời hạn certificate.
- Không ghi token, AWS credentials, DB password hoặc connection string có secret vào log/trace.
- Không gửi token qua URL query string, message queue hoặc response HTTP.
- Dùng đúng hostname/Region/port khi ký token; endpoint proxy và DB instance có resource ARN riêng.
- Giới hạn network bằng VPC/subnet/security group; IAM authentication không thay thế network firewall.
- Tách IAM role dev/staging/prod và audit thay đổi policy/DB grants.
- Theo dõi số connection, lỗi authentication, pool timeout và failover.

### 10.2. Metric cần quan sát

| Nguồn | Metric hoặc sự kiện | Ý nghĩa |
| --- | --- | --- |
| HikariCP | active, idle, pending, max, acquisition time, timeout count | Pool có cạn hay request chờ lâu không? |
| Amazon RDS | `DatabaseConnections`, CPU, memory, IOPS, latency | DB có quá tải hoặc connection gần giới hạn không? |
| RDS Proxy | client connections, database connections, borrow latency, target health | Proxy có cấp backend connection kịp không? |
| Spring application | connection creation failures, IAM token generation latency, auth exceptions | Lỗi ở bước ký token, TLS hay DB authentication? |
| IAM/CloudTrail | thay đổi role/policy | Có thay đổi quyền hoặc cấu hình danh tính không? CloudWatch/CloudTrail không ghi từng lần IAM DB login hay token generation. |

Metric cụ thể phụ thuộc engine, loại RDS/Proxy, CloudWatch namespace và version. Hãy dùng dashboard theo cùng thời gian để phân biệt pool exhaustion, database max connections, IAM permission failure, TLS failure và network timeout. Nếu cần audit từng phiên database, cấu hình database audit/logging phù hợp với engine; đừng coi CloudTrail là nhật ký đăng nhập IAM DB.

## 11. Kiểm thử IAM authentication và connection refresh

### 11.1. Unit test cho token provider/DataSource

Interface `IamTokenSupplier` ở mục 5.2 cho phép test dùng supplier đếm số lần được gọi hoặc trả token khác nhau cho mỗi lần gọi. Khi gọi `IamPostgresDataSource.getConnection()`, kiểm tra supplier được gọi đúng một lần trước khi driver tạo connection. Để test không phụ thuộc AWS, có thể inject một supplier giả và mock JDBC driver/connection factory trong unit test.

Bài kiểm tra cần xác nhận:

1. Token không được lưu và tái sử dụng qua hai lần tạo physical connection.
2. Username và token được truyền qua JDBC properties, không nối token vào URL/log.
3. TLS properties (`verify-full`, CA bundle) được áp dụng.
4. Hikari logical borrow từ connection đã có không làm phát sinh token mới.
5. Khi Hikari tạo physical connection thay thế, supplier được gọi lại.
6. Lỗi sinh token hoặc xác thực driver được chuyển thành `SQLException` phù hợp và được log an toàn.

### 11.2. Integration test với PostgreSQL container

Testcontainers PostgreSQL có thể kiểm tra JDBC URL, Hikari lifecycle, transaction và DataSource wrapper với password authentication thông thường. Nó **không mô phỏng RDS IAM authentication plugin**, IAM policy, token validation, RDS Proxy hoặc VPC security group.

Vì vậy, chia kiểm thử thành hai lớp:

- **Local/CI:** PostgreSQL Testcontainers, kiểm tra DataSource wrapper với token supplier giả, Hikari pool lifecycle và transaction.
- **AWS staging:** dùng RDS PostgreSQL có bật IAM DB auth, workload role thật, IAM policy `rds-db:connect`, TLS CA bundle và endpoint chính thức. Kiểm tra token hết hạn rồi mở connection mới; xác nhận connection cũ vẫn hoạt động và connection mới dùng token vừa sinh.

### 11.3. Kịch bản staging cụ thể

1. Tạo DB user `reservation_app`, cấp `rds_iam` và SQL grants cần thiết.
2. Gắn IAM role vào ECS/EKS/EC2 staging, chỉ cấp `rds-db:connect` cho đúng resource/user.
3. Kết nối qua RDS endpoint với TLS `verify-full`; thực thi `SELECT current_user`.
4. Tạo Hikari pool nhỏ, giữ một connection đang mở qua mốc 15 phút; xác nhận session đã xác thực tiếp tục dùng được.
5. Yêu cầu Hikari mở physical connection mới sau khi token cũ hết hạn; xác nhận token mới được tạo và connection thành công.
6. Thu hồi `rds-db:connect` ở môi trường thử nghiệm, xác nhận connection mới bị từ chối; session đã mở có thể vẫn hoạt động, nên không coi thay đổi IAM là cơ chế kill session tức thời.
7. Khôi phục policy, thử failover/restart có kiểm soát; theo dõi thời gian pool phục hồi và transaction thất bại.
8. Nếu dùng RDS Proxy, kiểm tra riêng IAM client auth và target authentication, không suy ra từ kết quả direct DB connection.

Không chạy thử revoke policy/failover trên production nếu chưa có kế hoạch thay đổi được phê duyệt và khả năng khôi phục. Các bước trên là kịch bản cho staging có kiểm soát.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `FATAL: PAM authentication failed` hoặc thông báo IAM auth bị từ chối | User chưa được cấp role/plugin IAM, token sai hoặc role không có `rds-db:connect` | Kiểm tra DB user, policy ARN, Region, hostname, port và token |
| `Access denied for user` trên MySQL/MariaDB | User chưa dùng authentication plugin đúng hoặc SQL privilege thiếu | Kiểm tra plugin/user grants theo engine |
| Token tạo được nhưng JDBC connect thất bại | Security group, TLS, CA bundle, endpoint hoặc DB user sai | Kiểm tra từ đúng workload, bật TLS verify và đối chiếu hostname |
| Kết nối hoạt động lúc startup, sau 15 phút connection mới thất bại | Token được tạo một lần và cấu hình như password tĩnh | Sinh token mới trong DataSource mỗi physical connect |
| Pool đang chạy vẫn hoạt động sau 15 phút | Connection đã xác thực trước khi token hết hạn | Đây là hành vi bình thường; token không phải session expiry |
| Hikari không mở được connection mới | IAM credentials provider hết hạn/không refresh, policy đổi hoặc token không đúng endpoint | Kiểm tra provider chain và tạo token mới theo từng connect |
| Kết nối trực tiếp thành công, qua Proxy thất bại | Token/ARN dùng DB endpoint/resource thay cho proxy hoặc proxy target auth chưa cấu hình | Kiểm tra riêng client-auth và target-auth của proxy |
| Sau failover nhiều request lỗi | Physical connections cũ bị đóng, pool chưa tái tạo hoặc transaction bị ngắt | Validation, maxLifetime hợp lý, retry idempotent và test staging |
| SQL `permission denied` sau khi IAM login thành công | IAM chỉ cho phép đăng nhập, DB user thiếu SQL grants | Cấp quyền schema/table/sequence bằng SQL |
| `PKIX path building failed` hoặc hostname mismatch | CA bundle sai/cũ hoặc URL dùng alias/IP không khớp certificate | Cập nhật CA và dùng endpoint DNS chính thức với verify-full |

## 13. Bài tập tự luyện

1. Tạo IAM policy `rds-db:connect` chỉ cho phép DB user `reservation_app` trên một RDS PostgreSQL instance; giải thích vì sao DB identifier không thay thế resource ID trong ARN.
2. Tạo PostgreSQL user, cấp `rds_iam`, SQL grants riêng và xác minh user không có quyền truy cập schema ngoài phạm vi.
3. Viết `RdsIamTokenProvider` dùng AWS SDK v2, tạo hai token ở hai thời điểm khác nhau và giải thích tham số hostname/port/Region/username.
4. Bọc token provider trong custom DataSource và cấu hình HikariCP; chứng minh token chỉ tạo khi có physical connection mới, không phải mỗi logical borrow.
5. Giữ một connection qua 15 phút, sau đó mở connection mới; giải thích vì sao connection cũ có thể hoạt động trong khi token cũ không dùng được cho connection mới.
6. Thay RDS endpoint bằng RDS Proxy endpoint; sửa token hostname và IAM resource ARN; mô tả hai chặng xác thực client/proxy và proxy/database.
7. Tạo test giả lập lỗi token generation, lỗi TLS và `AccessDenied`; xác định lỗi nào retry được, lỗi nào cần sửa cấu hình/quyền.
8. Chạy test staging khi revoke rồi khôi phục IAM permission; đo thời gian ảnh hưởng tới connection mới và connection đã tồn tại.
9. So sánh IAM DB authentication của RDS với workload identity/connector của Azure Database và Google Cloud SQL; xác định interface ứng dụng có thể dùng chung và phần token/driver/connection factory phụ thuộc provider.

**Tiêu chí hoàn thành:** người học tạo được token IAM đúng endpoint, giải thích được quyền `rds-db:connect` và SQL grants, cấu hình TLS, tích hợp token provider với HikariCP, kiểm chứng token refresh khi mở physical connection mới và phân biệt token expiration với connection lifetime.

## Tài liệu tham khảo

- [Amazon RDS — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html): engine hỗ trợ, token, TLS và giới hạn.
- [Amazon RDS — Supported Regions and DB engines](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RDS_Fea_Regions_DB-eng.Feature.IamDatabaseAuthentication.html): ma trận engine/version/Region cho RDS.
- [Amazon Aurora — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/UsingWithRDS.IAMDBAuth.html): engine Aurora, token và các giới hạn riêng.
- [Amazon RDS — Setting up IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.Connecting.html): cấu hình DB user, IAM policy và kết nối.
- [Amazon RDS — IAM database authentication for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html): role `rds_iam` và SQL privilege.
- [Amazon RDS — IAM database authentication for MySQL and MariaDB](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html): authentication plugin và user.
- [AWS SDK for Java 2.x — Generate an IAM authentication token](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-rds.html): `RdsUtilities` và `GenerateAuthenticationTokenRequest`.
- [Amazon RDS Proxy — Setting up IAM authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html): xác thực IAM giữa client và proxy, cấu hình target.
- [Amazon RDS Proxy — Connecting using IAM authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connecting.html): standard IAM và end-to-end IAM, resource ARN và endpoint.
- [Amazon RDS Proxy — Concepts and terminology](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html): hai mô hình IAM auth và backend connection.
- [Amazon RDS — SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html): CA bundles và TLS theo engine.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): pool sizing, connection lifecycle và timeout.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC và HikariCP auto-configuration.
