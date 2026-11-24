# Kết nối Azure Database for MySQL hoặc PostgreSQL qua JDBC

Spring Boot có thể kết nối tới **Azure Database for PostgreSQL Flexible Server** hoặc **Azure Database for MySQL Flexible Server** bằng JDBC giống như kết nối tới một relational database thông thường. Điểm cần cấu hình thêm nằm ở môi trường Azure: endpoint FQDN, network/firewall, TLS, danh tính Microsoft Entra, quyền ở cấp database, high availability và giới hạn connection. Spring Cloud Azure cung cấp starter JDBC để tích hợp Microsoft Entra passwordless authentication vào `DataSource`; Spring Boot tiếp tục quản lý `JdbcTemplate`, transaction và connection pool.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào hai dịch vụ relational database của Azure và cách kết nối chúng từ ứng dụng Java qua JDBC.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt Azure Database for PostgreSQL Flexible Server và Azure Database for MySQL Flexible Server.
- Thêm JDBC driver và Spring Cloud Azure JDBC starter theo BOM tương thích.
- Cấu hình `DataSource`, `JdbcTemplate`, HikariCP và `@Transactional`.
- Kết nối bằng tài khoản database/password hoặc Microsoft Entra passwordless authentication.
- Dùng Managed Identity và cấp quyền database theo nguyên tắc least privilege.
- Cấu hình TLS, FQDN, firewall, VNet/private access và kiểm tra đường mạng.
- Quản lý schema migration, connection pool, timeout, failover và retry an toàn.
- Kiểm thử bằng Testcontainers/local database và Azure test server.

## 2. Chọn đúng dịch vụ relational database

Hai dịch vụ đều là database engine managed, nhưng vẫn giữ các đặc điểm riêng của MySQL và PostgreSQL:

| Chủ đề | Azure Database for PostgreSQL Flexible Server | Azure Database for MySQL Flexible Server |
| --- | --- | --- |
| Engine | PostgreSQL | MySQL |
| JDBC driver | PostgreSQL JDBC Driver (`org.postgresql:postgresql`) | MySQL Connector/J (`com.mysql:mysql-connector-j`) |
| JDBC URL | `jdbc:postgresql://...` | `jdbc:mysql://...` |
| FQDN | `<server>.postgres.database.azure.com` | `<server>.mysql.database.azure.com` |
| Port mặc định | `5432` | `3306` |
| TLS | Bắt buộc với kết nối dịch vụ | TLS được bật/enforced mặc định |
| Microsoft Entra | Có | Có |
| Quyền dữ liệu | Role/user, schema/table/sequence privilege của PostgreSQL | User, database/table privilege của MySQL |
| HA | Primary + standby, có thể cấu hình theo zone | Primary + standby, có thể cấu hình theo zone |

Chọn engine dựa trên schema, SQL dialect, extension, workload và kỹ năng vận hành. Không nên coi việc đổi JDBC URL là đủ để chuyển từ MySQL sang PostgreSQL hoặc ngược lại. Các khác biệt về kiểu dữ liệu, generated key, JSON, collation, transaction isolation, SQL syntax và migration vẫn phải được xử lý.

### 2.1. Kiến trúc kết nối

~~~mermaid
flowchart LR
    A[Spring Boot application] --> D[Hikari DataSource]
    D --> J[JDBC driver]
    J --> T[TLS connection]
    T --> N[Azure network / DNS]
    N --> P[PostgreSQL Flexible Server]
    N --> M[MySQL Flexible Server]
    I[Microsoft Entra / Managed Identity] -. token .-> D
    K[Key Vault / secret provider] -. password nếu dùng .-> D
~~~

Ở runtime, `JdbcTemplate` lấy connection từ `DataSource`, thực thi SQL qua JDBC driver rồi trả connection về pool. Ứng dụng không nên tạo một `DriverManager.getConnection(...)` mới cho từng HTTP request. Với Spring Boot, `DataSource` và HikariCP giúp tái sử dụng connection, giới hạn số connection đồng thời và quản lý vòng đời.

## 3. Dependency và quản lý phiên bản

Spring Cloud Azure có starter riêng cho PostgreSQL và MySQL:

- `com.azure.spring:spring-cloud-azure-starter-jdbc-postgresql`
- `com.azure.spring:spring-cloud-azure-starter-jdbc-mysql`

Hai starter tích hợp xác thực Microsoft Entra passwordless vào Spring Boot JDBC. Chọn **một** starter phù hợp với engine ứng dụng sử dụng. Thêm Spring Boot JDBC starter và driver tương ứng; dùng BOM để đồng bộ các dependency Spring Cloud Azure.

Ví dụ Maven cho PostgreSQL:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-jdbc-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
    </dependency>
</dependencies>
~~~

Đối với MySQL, thay starter và JDBC driver:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-jdbc-mysql</artifactId>
</dependency>
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
</dependency>
~~~

Các version của Spring Boot, Spring Cloud Azure và JDBC driver phải tương thích. Không sao chép version driver cũ từ một quickstart rồi trộn với BOM khác. Hãy dùng [Spring Cloud Azure version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) để chọn BOM theo dòng Spring Boot đang dùng. Các starter JDBC của Azure hỗ trợ passwordless từ Spring Cloud Azure 4.5.0 trở lên; phiên bản cụ thể cần được kiểm tra trong version mapping.

## 4. Cấu hình PostgreSQL bằng JDBC

### 4.1. JDBC URL và TLS

JDBC URL cho PostgreSQL Flexible Server có dạng:

~~~text
jdbc:postgresql://<server>.postgres.database.azure.com:5432/<database>?sslmode=require
~~~

Ví dụ cấu hình cơ bản:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
~~~

`sslmode=require` bảo đảm kết nối được mã hóa bằng TLS. Trong production, nên cấu hình xác minh certificate và hostname bằng `sslmode=verify-full` cùng trusted root CA phù hợp. PostgreSQL JDBC mặc định không xác minh đầy đủ danh tính server nếu chỉ bật mã hóa; TLS encryption và TLS identity verification là hai việc khác nhau.

Luôn dùng FQDN do Azure cấp, không hard-code IP. Khi failover, endpoint có thể được DNS cập nhật để trỏ tới primary mới. Nếu dùng IP cũ, ứng dụng có thể không kết nối lại được.

### 4.2. Password authentication

Nếu dùng tài khoản PostgreSQL local:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Database user nên là tài khoản ứng dụng không có quyền quản trị server. Lưu password trong Azure Key Vault hoặc secret provider của môi trường deploy; inject qua environment/configuration an toàn. Không commit password vào `application.yml`, Docker image hoặc source control. Thiết kế rotation sao cho connection pool được tạo lại hoặc refresh theo quy trình đã kiểm thử.

### 4.3. Microsoft Entra passwordless với Spring Cloud Azure

Starter PostgreSQL hỗ trợ lấy Microsoft Entra token và dùng token làm thông tin xác thực cho JDBC driver. Cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

Khi chạy trên Azure với Managed Identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo nếu dùng user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

`DB_ENTRA_USERNAME` là tên database principal đã được cấu hình cho Microsoft Entra identity. Managed Identity chỉ giúp workload lấy token; nó không tự tạo user trong PostgreSQL và không tự cấp quyền SELECT/INSERT/UPDATE. Cần có Microsoft Entra administrator trên server, tạo database principal cho identity của ứng dụng, rồi cấp quyền ở database/schema/table.

Ví dụ luồng quyền:

1. Bật Microsoft Entra authentication trên PostgreSQL Flexible Server và cấu hình Entra administrator.
2. Đưa Managed Identity của ứng dụng vào cấu hình identity phù hợp.
3. Entra administrator tạo database principal tương ứng (ví dụ qua `pgaadauth_create_principal` theo tài liệu Microsoft).
4. Tạo role/privilege riêng cho runtime; chỉ cấp quyền trên database/schema/table cần thiết.
5. Cấu hình `passwordless-enabled: true`, username principal và URL TLS trong ứng dụng.
6. Xác minh token được lấy từ đúng identity và truy vấn chỉ thành công trong phạm vi quyền được cấp.

Ví dụ SQL quyền tối thiểu cần điều chỉnh theo schema:

~~~sql
GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT USAGE ON SCHEMA public TO app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO app_runtime;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO app_runtime;
~~~

Để các bảng/sequence tạo sau này cũng có quyền đúng, quản lý default privileges bằng migration hoặc role quản trị schema. Không dùng Entra administrator cho kết nối runtime của ứng dụng.

## 5. Cấu hình MySQL bằng JDBC

### 5.1. JDBC URL và TLS

JDBC URL MySQL Flexible Server có dạng:

~~~text
jdbc:mysql://<server>.mysql.database.azure.com:3306/<database>?sslMode=REQUIRED&serverTimezone=UTC
~~~

Ví dụ cấu hình password:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
~~~

`sslMode=REQUIRED` buộc sử dụng TLS. Trong production, nên cấu hình `sslMode=VERIFY_IDENTITY` với trust store chứa đầy đủ trusted root CA để xác minh certificate và hostname. Không dùng `DISABLED` hoặc tắt TLS để chữa lỗi kết nối. `serverTimezone=UTC` giúp thống nhất cách driver diễn giải thời gian; ứng dụng vẫn phải xác định rõ timezone ở domain và database.

Azure Database for MySQL Flexible Server dùng TLS 1.2 mặc định và hỗ trợ TLS 1.3 theo phiên bản/configuration của server. Kiểm tra server parameter, JDBC driver và trust store khi nâng cấp.

### 5.2. Microsoft Entra passwordless với Spring Cloud Azure

Starter MySQL dùng `AzureMysqlAuthenticationPlugin` qua tích hợp Spring Cloud Azure. Cấu hình cơ bản:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

Khi ứng dụng dùng Managed Identity, cấu hình credential chain:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo nếu dùng user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

Quy trình tạo user Entra và cấp quyền database khác PostgreSQL:

- Cấu hình Microsoft Entra administrator cho MySQL Flexible Server.
- Cấu hình Managed Identity và các quyền directory cần thiết theo tài liệu MySQL nếu server cần identity để tra cứu principal/group.
- Tạo Entra database user bằng cơ chế `CREATE AADUSER` phù hợp.
- Cấp quyền trên đúng database/table cho principal runtime.
- Dùng username Entra đã đăng ký trong JDBC configuration và bật `passwordless-enabled`.

Không copy cú pháp `CREATE AADUSER` của MySQL sang PostgreSQL; PostgreSQL dùng cơ chế tạo principal và grant riêng. Tương tự, không coi Azure Resource Manager Contributor là quyền đọc/ghi dữ liệu SQL.

## 6. Chọn password hay Microsoft Entra authentication?

| Tiêu chí | Database username/password | Microsoft Entra passwordless |
| --- | --- | --- |
| Credential | Secret trong database user | Token từ Entra identity |
| Rotation | Ứng dụng/vận hành phải quản lý password | Token ngắn hạn được credential integration làm mới |
| Workload trên Azure | Cần lấy secret an toàn | Managed Identity phù hợp |
| Local development | Dễ dùng với user test | Có thể dùng Azure CLI/IDE credential nếu được cấu hình |
| Database user/permission | Vẫn phải tạo và grant quyền | Vẫn phải tạo Entra database principal và grant quyền |
| Rủi ro chính | Secret leak, rotation sai, quyền quá rộng | Identity mapping, token acquisition, Entra/database principal chưa được cấp quyền |

Passwordless không có nghĩa database không cần username hoặc không cần database permission. Nó chỉ thay cách xác thực credential. Với production workload trên Azure, ưu tiên Managed Identity và role/database grant tối thiểu. Nếu buộc dùng password, lưu trong Key Vault hoặc secret manager và có quy trình rotation.

## 7. Spring Boot DataSource, JdbcTemplate và transaction

### 7.1. Dùng JdbcTemplate thay vì tự quản lý connection

Spring Boot tự cấu hình `DataSource` từ `spring.datasource.*`. Với JDBC starter, HikariCP thường là connection pool mặc định nếu có trong classpath. `JdbcTemplate` lấy connection, thực thi statement và trả connection về pool:

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

public record Customer(
    UUID id,
    String email,
    String displayName
) {}

@Repository
public class CustomerRepository {
    private final JdbcTemplate jdbc;

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer findById(UUID id) {
        return jdbc.queryForObject(
            """
            SELECT id, email, display_name
            FROM customers
            WHERE id = ?
            """,
            (rs, rowNum) -> new Customer(
                rs.getObject("id", UUID.class),
                rs.getString("email"),
                rs.getString("display_name")),
            id);
    }

    public List<Customer> findByEmailDomain(String domain) {
        return jdbc.query(
            """
            SELECT id, email, display_name
            FROM customers
            WHERE email LIKE ?
            ORDER BY email
            """,
            (rs, rowNum) -> new Customer(
                rs.getObject("id", UUID.class),
                rs.getString("email"),
                rs.getString("display_name")),
            "%@" + domain);
    }

    public int updateDisplayName(UUID id, String displayName) {
        return jdbc.update(
            "UPDATE customers SET display_name = ? WHERE id = ?",
            displayName,
            id);
    }
}
~~~

Các tham số `?` được bind qua PreparedStatement, tránh nối input vào SQL. Cần xử lý `EmptyResultDataAccessException` hoặc dùng query trả list/Optional nếu item không tồn tại là tình huống bình thường. Ví dụ dùng UUID phù hợp với PostgreSQL; nếu hỗ trợ MySQL, xác minh kiểu cột và JDBC mapping (ví dụ BINARY(16) hoặc CHAR(36)) theo schema đã chọn.

### 7.2. Transaction trong một relational database

Spring quản lý transaction JDBC thông qua transaction manager gắn với `DataSource`. Ví dụ:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository customers;
    private final AuditRepository audit;

    public CustomerService(
            CustomerRepository customers,
            AuditRepository audit) {
        this.customers = customers;
        this.audit = audit;
    }

    @Transactional
    public void changeDisplayName(
            UUID customerId, String newName) {
        customers.updateDisplayName(customerId, newName);
        audit.record("CUSTOMER_NAME_CHANGED", customerId.toString());
    }
}
~~~

Ví dụ repository audit tối giản dùng cùng `JdbcTemplate`/`DataSource`:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void record(String eventType, String aggregateId) {
        jdbc.update(
            "INSERT INTO audit_events(event_type, aggregate_id) VALUES (?, ?)",
            eventType,
            aggregateId);
    }
}
~~~

Nếu hai repository cùng dùng một `DataSource` và cùng transaction manager, các lệnh SQL có thể commit/rollback cùng transaction database. `@Transactional` không tự bao gồm Azure Blob Storage, Service Bus hoặc một database khác; các side effect ngoài JDBC cần outbox/saga khi phải bảo đảm delivery.

Không mở connection bằng `DriverManager` bên trong repository hoặc giữ connection qua nhiều request. Với `JdbcTemplate`, Spring quản lý việc mượn/trả connection. Nếu dùng JDBC API trực tiếp, sử dụng try-with-resources cho `Connection`, `PreparedStatement` và `ResultSet`.

## 8. Connection pool HikariCP

Mỗi physical JDBC connection chiếm tài nguyên ở cả ứng dụng và database server. HikariCP giữ một tập connection đã mở để giảm chi phí TLS/authentication/handshake, nhưng pool quá lớn có thể làm database quá tải.

Ví dụ:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      keepalive-time: 300000
~~~

Các giá trị là điểm bắt đầu để đo, không phải cấu hình chuẩn cho mọi server. Hãy chọn theo:

- Số instance/pod chạy đồng thời.
- Số request thực sự giữ connection cùng lúc và thời gian query/transaction.
- Giới hạn connection của tier database và số connection dành cho migration/monitoring/admin.
- Thời gian idle timeout của network/firewall và giới hạn connection của môi trường.
- Tải read/write, query duration và failover behavior.

Ví dụ nếu 6 pod có `maximum-pool-size=10`, ứng dụng có thể mở tới 60 connection, chưa kể worker/migration. Không chỉ nhìn pool size trên từng pod; phải tính tổng trên toàn deployment và để lại headroom cho quản trị/replica.

### 8.1. Connection timeout và query timeout khác nhau

- **Connection timeout** giới hạn thời gian chờ lấy connection từ pool.
- **Login/socket timeout** giới hạn thời gian mở kết nối hoặc chờ network.
- **Statement/query timeout** giới hạn thời gian thực thi SQL.
- **Transaction timeout** giới hạn toàn bộ transaction nếu được cấu hình ở Spring/transaction manager.

Tăng một loại timeout không giải quyết loại khác. Ví dụ pool hết connection do transaction giữ quá lâu không được sửa bằng cách tăng socket timeout.

### 8.2. Tránh connection leak và pool exhaustion

Theo dõi Hikari metrics: active, idle, pending, acquisition time, usage time và timeout count. Nếu active luôn chạm maximum và pending tăng, kiểm tra:

- Transaction có giữ connection trong khi gọi HTTP/Blob/Service Bus không?
- Có query chậm hoặc thiếu index không?
- Có code JDBC thủ công quên đóng ResultSet/Statement/Connection không?
- Có batch job chạy song song không giới hạn?
- Pool tổng có vượt khả năng database không?

Giữ transaction ngắn; không thực hiện lời gọi network không liên quan khi đang giữ connection/row lock.

## 9. Networking và DNS

Azure Database for PostgreSQL Flexible Server và MySQL Flexible Server có lựa chọn public access và private network theo mô hình của từng dịch vụ.

| Cấu hình | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Public access + firewall | Có public FQDN; chỉ IP được allow mới vào được | Phát triển/test hoặc workload có egress IP cố định và policy cho phép |
| Private access / VNet integration | Database được tích hợp vào VNet/subnet riêng, không expose public endpoint | Production workload cần cô lập mạng |
| Private endpoint/Private Link | Kết nối private qua endpoint trong VNet theo khả năng dịch vụ | Kiến trúc private connectivity cần kiểm soát rõ |

Một số lựa chọn network là quyết định lúc tạo server hoặc có giới hạn chuyển đổi; kiểm tra tài liệu đúng dịch vụ trước khi provision. Không mở firewall tới toàn bộ Internet để chữa lỗi kết nối.

### 9.1. Port và FQDN

| Database | FQDN mẫu | Port |
| --- | --- | ---: |
| PostgreSQL | `pg-orders.postgres.database.azure.com` | 5432 |
| MySQL | `mysql-orders.mysql.database.azure.com` | 3306 |

Luôn dùng FQDN chính thức thay vì IP tĩnh. DNS có thể thay đổi khi failover hoặc thay đổi hạ tầng. Nếu dùng custom DNS, VNet peering hoặc hybrid network, kiểm tra private DNS zone/link và khả năng resolve từ đúng subnet của ứng dụng.

### 9.2. Chẩn đoán theo lớp

Khi ứng dụng không kết nối được, kiểm tra theo thứ tự:

1. **DNS:** FQDN có resolve về địa chỉ đúng từ pod/VM không?
2. **Route/network:** subnet, NSG, route table, firewall và private endpoint có cho TCP 5432/3306 không?
3. **Server firewall:** IP egress có nằm trong allowlist khi dùng public access không?
4. **TLS:** driver có hỗ trợ TLS version, certificate chain và hostname verification không?
5. **Authentication:** username, password/token, Managed Identity và Entra principal có đúng không?
6. **Authorization:** database user có quyền CONNECT/USAGE/SELECT/INSERT… cần thiết không?
7. **Pool/engine:** còn connection slot không, server có đang failover/restart/maintenance không?

Không suy ra lỗi firewall chỉ từ thông báo `connection refused`; kiểm tra DNS, route, TLS và trạng thái server.

## 10. TLS và certificate validation

TLS bảo vệ dữ liệu trên đường truyền giữa ứng dụng và database. Hai dịch vụ đều yêu cầu kết nối mã hóa theo cấu hình mặc định; không tắt TLS trong production.

| Driver | Tối thiểu để mã hóa | Cấu hình xác minh server nên đánh giá |
| --- | --- | --- |
| PostgreSQL JDBC | `sslmode=require` | `sslmode=verify-full` với trusted CA và hostname |
| MySQL Connector/J | `sslMode=REQUIRED` | `sslMode=VERIFY_IDENTITY` với trusted CA/system trust store |

`require`/`REQUIRED` bảo đảm TLS được sử dụng nhưng chưa nhất thiết xác minh hostname theo mức cao nhất. Với `verify-full`/`VERIFY_IDENTITY`, driver kiểm tra chain và danh tính server. Dùng trust store chứa các root CA được Azure công bố; tránh certificate pinning vào intermediate/server leaf certificate có thể bị xoay vòng.

Không đặt `trustServerCertificate=true`, `sslmode=disable` hoặc `sslMode=DISABLED` như một cách khắc phục nhanh trong production. Nếu handshake lỗi, kiểm tra driver version, JVM trust store, root CA và hostname.

## 11. Database user, role và least privilege

Azure Resource Manager role và database privilege là hai lớp khác nhau:

- Azure RBAC quản lý tài nguyên Azure như tạo server, thay đổi cấu hình hoặc quản lý network.
- Database authentication xác định principal kết nối.
- Database authorization quyết định principal được đọc/ghi schema/table/sequence nào.

Không cấp Contributor/Owner ở subscription cho ứng dụng chỉ để nó chạy câu SQL. Dùng Entra principal hoặc database user riêng cho runtime; tách migration user có quyền DDL khỏi runtime user chỉ cần DML khi phù hợp.

### 11.1. PostgreSQL

PostgreSQL dùng role và privilege. Runtime user thường cần CONNECT database, USAGE schema, SELECT/INSERT/UPDATE/DELETE trên các table liên quan và sequence privilege nếu schema dùng sequence. Quyền tạo/alter table nên dành cho migration identity.

### 11.2. MySQL

MySQL dùng user và grant theo database/table. Tài khoản runtime chỉ cần các quyền DML trên database/schema ứng dụng; không dùng root/admin trong connection string. Cú pháp user/host và role assignment của MySQL khác PostgreSQL.

Ví dụ với local database user đã được tạo:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
    ON appdb.* TO 'app_runtime'@'%';
~~~

Với Microsoft Entra user, tạo principal bằng cơ chế `CREATE AADUSER` và grant cho đúng tên user đã đăng ký. Không dùng `GRANT ALL PRIVILEGES` cho runtime nếu ứng dụng không cần DDL hoặc quyền quản trị.

### 11.3. Migration identity và runtime identity

Flyway/Liquibase có thể cần CREATE/ALTER/DROP hoặc quyền tạo history table; ứng dụng runtime thường không cần những quyền đó. Có thể chạy migration trong deployment pipeline bằng identity riêng, rồi chạy service bằng principal hạn chế. Điều này giảm tác động khi credential của service bị lộ.

## 12. Schema migration và khác biệt SQL dialect

Dùng Flyway hoặc Liquibase để quản lý schema theo phiên bản. Tránh phụ thuộc vào `spring.jpa.hibernate.ddl-auto=update` khi dùng relational database production; với JDBC/JdbcTemplate, quản lý schema bằng migration scripts rõ ràng.

Một số khác biệt cần lưu ý:

| Chủ đề | PostgreSQL | MySQL |
| --- | --- | --- |
| Auto-generated ID | `GENERATED ... AS IDENTITY`, sequence | `AUTO_INCREMENT` |
| UUID | Kiểu `uuid` native | Thường lưu `BINARY(16)` hoặc `CHAR(36)` |
| JSON | `json`, `jsonb` | `JSON` |
| Time zone | `timestamp with time zone` (`timestamptz`) lưu instant theo UTC | `TIMESTAMP` chuyển đổi theo session time zone; `DATETIME` không tự mang timezone |
| Identifier | Quy tắc lower-case cho unquoted identifier | Phụ thuộc cấu hình/case sensitivity và filesystem cho tên database/table |
| Upsert | `INSERT ... ON CONFLICT` | `INSERT ... ON DUPLICATE KEY UPDATE` |
| Sequence | Có sequence object | `AUTO_INCREMENT` thường gắn với table |

Không dùng một migration SQL duy nhất cho cả hai engine nếu syntax khác nhau. Tách migration theo engine hoặc dùng Liquibase abstraction khi thực sự phù hợp. Test migration trên đúng major version của server mục tiêu.

## 13. High availability, failover và retry

Flexible Server có thể cấu hình HA với standby replica và automatic failover. Khi failover xảy ra, database server endpoint vẫn là FQDN mà ứng dụng sử dụng; DNS/traffic được chuyển tới primary mới theo kiến trúc dịch vụ. Tuy vậy, **các connection JDBC đang mở có thể bị ngắt**. Ứng dụng cần tạo lại connection từ pool và xử lý request đang chạy.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot / Hikari
    participant P as Current primary
    participant S as Standby
    A->>P: JDBC query / transaction
    P--xA: Connection lost during failover
    P--xS: Primary failure detected
    S->>S: Recovery / promotion
    Note over P,S: DNS or service routing switches to new primary
    A->>A: Discard broken connection
    A->>S: Reconnect through the same FQDN
    S-->>A: New connection ready
~~~

Không coi failover là trong suốt tuyệt đối. Ứng dụng nên:

- Dùng FQDN thay IP.
- Có pool timeout và connection lifetime hợp lý.
- Xử lý lỗi connection reset/broken pipe/SQLState tương ứng.
- Chỉ retry thao tác idempotent hoặc sau khi đã xác định transaction chưa commit.
- Đối chiếu trạng thái khi commit response bị mất; không replay mù quáng một lệnh thanh toán hoặc ghi trùng.
- Kiểm thử failover chủ động trên test server và quan sát thời gian reconnect.

HA không thay backup/PITR và không bảo vệ mọi lỗi do ứng dụng. Standby thường không phải read replica để ứng dụng tùy ý gửi truy vấn đọc; nếu cần read scaling, cấu hình read replica riêng và quản lý consistency/read-after-write.

## 14. Timeout, retry và transaction

Đặt timeout theo SLA của use case:

- Connection acquisition timeout: chờ lấy connection từ Hikari.
- Connect/socket timeout: thời gian mở kết nối và chờ I/O.
- Statement timeout: giới hạn query.
- Transaction timeout: giới hạn toàn bộ transaction.

Không đặt timeout dài vô hạn. Khi retry, phân loại lỗi:

| Lỗi | Hướng xử lý |
| --- | --- |
| DNS/firewall/TLS/authentication failure | Không retry vô hạn; sửa cấu hình/identity/network |
| Connection reset trong query read | Có thể retry có giới hạn nếu request read an toàn |
| Deadlock/serialization failure | Có thể retry toàn transaction nếu business operation idempotent và transaction được tạo lại từ đầu |
| Constraint violation | Xử lý như lỗi dữ liệu/conflict; không retry mù quáng |
| Timeout trong lúc commit | Kết quả có thể không rõ; đối chiếu trạng thái bằng operation/business key trước khi gửi lại |
| Failover/temporary unavailable | Backoff có jitter, giới hạn tổng deadline và số lần thử |

Retry chỉ một câu lệnh ở giữa transaction có thể phá logic nghiệp vụ. Nếu database báo lỗi khiến transaction aborted, phải rollback và bắt đầu transaction mới. Không gọi HTTP/Blob/Service Bus trong khi giữ transaction JDBC lâu; dùng outbox để phối hợp side effect ngoài database.

## 15. Quan sát và vận hành

Theo dõi cả phía ứng dụng và Azure database:

| Tầng | Chỉ số/diagnostic |
| --- | --- |
| HikariCP | Active/idle/pending connections, acquisition/usage time, timeout count |
| JDBC | Query duration, SQLState, connection errors, transaction rollback, deadlock |
| PostgreSQL | Active sessions, locks, slow query, CPU, memory, storage, IOPS, connection count |
| MySQL | Active connections, slow query, lock waits, CPU, storage, IOPS, connection count |
| Azure | Server health, HA state, failover event, CPU/storage/IO, connection metric, maintenance |

Không log password, access token, JDBC URL chứa secret, bind parameter nhạy cảm hoặc dữ liệu cá nhân. Dùng correlation ID/trace ID để nối request với query log và operation; không ghi full SQL parameter values nếu có PII.

Health check nên phân biệt:

- **Liveness:** JVM/app process còn hoạt động.
- **Readiness:** ứng dụng có thể phục vụ traffic; có thể cần kiểm tra DataSource tùy yêu cầu.
- **Database health:** kết nối tới database thành công, có timeout ngắn và không tạo tải quá lớn.

Không để liveness phụ thuộc trực tiếp vào database nếu database tạm thời lỗi sẽ khiến orchestrator restart toàn bộ pod liên tục. Readiness có thể đánh dấu instance không sẵn sàng khi database không thể phục vụ, theo chính sách deployment.

## 16. Kiểm thử JDBC với local database và Azure thật

### 16.1. Unit test

Mock repository/DAO hoặc dùng test slice phù hợp để kiểm tra business rule. Không cần Azure credentials hoặc network cho unit test.

### 16.2. Testcontainers

Testcontainers có thể khởi động PostgreSQL hoặc MySQL container để kiểm tra:

- JDBC mapping và PreparedStatement.
- SQL dialect và migration Flyway/Liquibase.
- Transaction commit/rollback, constraint và lock.
- Hikari DataSource lifecycle và repository behavior.

Local container xác minh engine tương thích, không chứng minh Azure Entra authentication, Managed Identity, private DNS, firewall, TLS certificate chain, HA failover hoặc server parameter của Azure.

### 16.3. Azure integration test

Tạo Flexible Server test riêng, dùng database/schema test và identity tối thiểu. Kiểm tra:

1. JDBC kết nối qua FQDN, đúng port và TLS verification.
2. Public firewall/private network chỉ mở cho workload cần thiết.
3. Password authentication hoặc Microsoft Entra Managed Identity hoạt động.
4. Runtime principal chỉ có quyền cần thiết; thử một thao tác bị cấm để xác minh least privilege.
5. Migration chạy đúng và ứng dụng đọc/ghi được.
6. Hikari pool hoạt động dưới tải đồng thời.
7. HA failover làm connection đứt rồi pool phục hồi; transaction không bị replay sai.
8. Metrics/diagnostics có thể truy vết nhưng không lộ secret.

Không dùng dữ liệu production hoặc identity quản trị trong integration test. Dọn tài nguyên test theo quy trình và tránh để test job tạo server/database không giới hạn.

## 17. Ví dụ luồng triển khai Spring Boot

~~~text
Build:
  - Chọn PostgreSQL hoặc MySQL driver
  - Import Spring Cloud Azure BOM tương thích
  - Thêm JDBC starter tương ứng

Provision:
  - Tạo Flexible Server và database
  - Chọn public firewall hoặc private network
  - Bật TLS và HA theo yêu cầu
  - Tạo Entra admin/database principal hoặc local runtime user
  - Cấp quyền database tối thiểu

Deploy:
  - Cấp Managed Identity cho workload
  - Cấu hình FQDN/database/username
  - Bật passwordless-enabled hoặc lấy password từ Key Vault
  - Cấu hình Hikari pool và timeouts
  - Chạy Flyway/Liquibase migration
  - Readiness check và metrics

Operate:
  - Theo dõi pool/database/HA
  - Kiểm thử failover định kỳ
  - Rotation identity/secret theo chính sách
  - Backup/PITR và restore drill
~~~

## 18. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Connection timed out` | Firewall, route, NSG, private DNS hoặc sai port | Kiểm tra FQDN resolve, TCP 5432/3306 và network path |
| TLS handshake failure | Driver/JVM trust store không phù hợp, root CA thiếu | Cập nhật driver, CA chain và TLS config |
| PostgreSQL/MySQL authentication failed | Username không đúng principal, password/token sai hoặc Entra user chưa được tạo | Xác minh identity và database principal |
| Entra token lấy được nhưng query bị permission denied | Có authentication nhưng chưa có database grant | Cấp quyền schema/table theo least privilege |
| Hikari pool timeout | Pool cạn, transaction dài, query chậm hoặc pool quá nhỏ | Xem active/pending, query duration và pool sizing |
| Sau failover ứng dụng không phục hồi | IP tĩnh, stale connection, DNS cache hoặc retry chưa đúng | Dùng FQDN, bỏ connection hỏng, reconnect và test failover |
| Query lỗi sau migration | SQL dialect hoặc major version khác | Tách migration theo engine, test trên đúng version |
| Duplicate data sau retry | Commit response bị mất và lệnh được replay | Dùng business key/idempotency, đối chiếu trước khi retry |
| App khởi động được nhưng DB không sẵn sàng | Kết nối chỉ được tạo khi request đầu tiên | Thêm readiness/connection validation phù hợp |

## 19. Bài tập thực hành

**Bài tập 1 — Kết nối PostgreSQL.** Tạo Azure Database for PostgreSQL Flexible Server, database `orders`, runtime user riêng. Cấu hình Spring Boot `spring.datasource.url`, TLS và Hikari; viết DAO dùng JdbcTemplate để tạo và đọc một order.

**Bài tập 2 — Kết nối MySQL.** Dùng MySQL Flexible Server và Connector/J. Cấu hình URL với FQDN, port 3306, TLS và UTC. Chạy migration tạo bảng, thêm/sửa/xóa dữ liệu bằng JdbcTemplate.

**Bài tập 3 — Passwordless.** Bật Microsoft Entra authentication, gán Managed Identity cho workload, tạo database principal và grant quyền. Cấu hình Spring Cloud Azure starter với `passwordless-enabled: true`; xác minh ứng dụng kết nối không cần password tĩnh.

**Bài tập 4 — Least privilege.** Tạo runtime principal chỉ có quyền SELECT/INSERT/UPDATE trên bảng ứng dụng. Thử CREATE TABLE hoặc DROP TABLE từ ứng dụng và xác minh bị từ chối; chạy migration bằng identity riêng có quyền DDL.

**Bài tập 5 — Hikari pool.** Chạy 5 pod giả lập với pool size 10. Tính tổng connection tối đa và so sánh với giới hạn database. Đo pending connection, acquisition time, query latency và tác động khi giảm/tăng pool.

**Bài tập 6 — TLS/network.** Thử kết nối khi thiếu firewall rule, sai DNS, thiếu root CA và dùng TLS verification. Phân biệt lỗi ở network, handshake và database authentication.

**Bài tập 7 — Failover.** Bật HA trên test server và kích hoạt planned failover. Quan sát connection bị ngắt, Hikari tạo connection mới, transaction đang chạy và request retry. Đề xuất idempotency cho thao tác ghi có kết quả không rõ.

**Bài tập 8 — Migration đa engine.** Dùng một schema nghiệp vụ trên PostgreSQL và MySQL. Tách migration cho UUID/generated key/JSON/timezone; chạy Testcontainers trên cả hai engine và so sánh kết quả.

## 20. Ghi nhớ

- **Azure Database for PostgreSQL/MySQL Flexible Server là relational database managed.** Spring Boot kết nối bằng JDBC driver tương ứng, `DataSource`, HikariCP và `JdbcTemplate`.
- Dùng starter `spring-cloud-azure-starter-jdbc-postgresql` hoặc `spring-cloud-azure-starter-jdbc-mysql` cùng BOM tương thích để tích hợp Microsoft Entra passwordless.
- **Managed Identity chỉ cung cấp danh tính/token.** Vẫn cần tạo database principal và cấp quyền SQL theo least privilege; Azure control-plane role không thay database grant.
- Luôn dùng **FQDN và TLS**. Production nên xác minh CA/hostname (`verify-full` cho PostgreSQL, `VERIFY_IDENTITY` cho MySQL) thay vì chỉ mã hóa mà không xác minh server.
- HikariCP phải được sizing theo tổng số instance và giới hạn database. Transaction dài, query chậm và pool quá lớn đều có thể gây cạn connection.
- `@Transactional` bảo vệ transaction của một relational DataSource; nó không bao gồm Blob, Service Bus hoặc database khác.
- HA failover có thể ngắt connection đang mở. Dùng FQDN, reconnect và retry có giới hạn; không replay mù quáng transaction có side effect.
- Testcontainers kiểm tra engine/JDBC/migration; Azure test server mới xác minh Entra, Managed Identity, network, TLS, quota và HA failover.

## 21. Tài liệu tham khảo

- [Spring Cloud Azure — PostgreSQL support và passwordless JDBC](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/postgresql-support)
- [Spring Cloud Azure — MySQL support và passwordless JDBC](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/mysql-support)
- [Spring Cloud Azure developer guide và version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Java JDBC quickstart — Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/connectivity/connect-java)
- [Java JDBC quickstart — Azure Database for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/connect-java)
- [Microsoft Entra authentication — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure)
- [Microsoft Entra authentication — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-how-to-entra)
- [TLS configuration — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect)
- [TLS configuration — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-tls)
- [Networking — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-networking)
- [Networking — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-networking)
- [High availability — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)
- [High availability — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-high-availability)
