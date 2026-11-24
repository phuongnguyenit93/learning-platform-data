# Xác thực Microsoft Entra cho cơ sở dữ liệu khi được hỗ trợ

Một ứng dụng Spring Boot chạy trên Azure có thể dùng **Managed Identity** để lấy access token từ Microsoft Entra ID rồi kết nối tới cơ sở dữ liệu mà không lưu mật khẩu tĩnh. Tuy nhiên, cách tích hợp không giống nhau cho mọi database: PostgreSQL và MySQL Flexible Server dùng plugin JDBC của Spring Cloud Azure; Azure SQL dùng Microsoft JDBC Driver với chế độ xác thực Entra; Cosmos DB for NoSQL dùng Azure Identity và native data-plane RBAC. Mỗi dịch vụ còn cần một **database principal hoặc role assignment** riêng để cấp quyền dữ liệu.

Điểm quan trọng là tách ba bước: **workload lấy danh tính**, **database xác thực token**, rồi **database authorization kiểm tra quyền trên dữ liệu**. Có token hợp lệ không đồng nghĩa ứng dụng đã được quyền đọc hoặc ghi bảng/container. Cũng không có một cấu hình `spring.cloud.azure.*` duy nhất có thể thay thế mọi driver và cơ chế phân quyền.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này giới hạn vào những dịch vụ cơ sở dữ liệu Azure có tài liệu hỗ trợ Microsoft Entra authentication rõ ràng cho Java/Spring.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Giải thích luồng Microsoft Entra access token từ workload tới database.
- Phân biệt system-assigned Managed Identity, user-assigned Managed Identity, service principal và credential dành cho phát triển cục bộ.
- Xác định dịch vụ/driver có hỗ trợ Entra authentication và chọn đúng integration.
- Cấu hình passwordless JDBC cho Azure Database for PostgreSQL và MySQL Flexible Server bằng Spring Cloud Azure.
- Cấu hình Azure SQL bằng Microsoft JDBC Driver với `ActiveDirectoryManagedIdentity` hoặc `ActiveDirectoryDefault`.
- Kết nối Azure Cosmos DB for NoSQL bằng Java SDK và `DefaultAzureCredential`, sau đó cấp native data-plane role.
- Phân biệt authentication với database authorization và Azure control-plane RBAC.
- Quản lý token, connection pool, TLS, tenant, role scope và rotation an toàn.
- Kiểm thử quyền tối thiểu, token acquisition, token expiry, reconnect và các tình huống 401/403.

## 2. Microsoft Entra authentication hoạt động như thế nào?

Microsoft Entra ID là nhà cung cấp danh tính. Ứng dụng lấy token đại diện cho một user, service principal hoặc managed identity. Database chỉ chấp nhận token được phát hành cho đúng tài nguyên/audience, còn hiệu lực và thuộc tenant được cấu hình. Sau khi xác thực danh tính, database ánh xạ principal đó sang user/role hoặc role assignment để quyết định thao tác dữ liệu nào được phép.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot workload
    participant Entra as Microsoft Entra ID
    participant DB as Azure database
    participant Data as Database objects
    App->>Entra: Request token using Managed Identity / credential
    Entra-->>App: Access token for target database audience
    App->>DB: JDBC / SDK request with token
    DB->>DB: Validate signature, tenant, audience and expiry
    DB->>DB: Map principal to database user / data-plane role
    DB->>Data: Check database authorization
    Data-->>DB: Result
    DB-->>App: Query result or authorization error
~~~

Luồng này có ba điểm độc lập:

1. **Credential acquisition:** ứng dụng có lấy được token từ Entra không?
2. **Authentication:** database có chấp nhận token cho đúng server/database không?
3. **Authorization:** principal có quyền SELECT, INSERT, UPDATE, DELETE hoặc query container cần thiết không?

Một lỗi ở bước 1 thường liên quan đến Managed Identity endpoint, tenant, credential chain hoặc token audience. Lỗi ở bước 2 thường là Entra admin, principal mapping, token audience/expiry hoặc cấu hình server. Lỗi ở bước 3 thường là thiếu database grant, role assignment hoặc scope.

## 3. Ma trận hỗ trợ theo dịch vụ và Java integration

Không nên mặc định mọi dịch vụ có chữ “Azure Database” đều hỗ trợ cùng một cách xác thực. Hãy bắt đầu bằng việc chọn đúng API/engine và driver:

| Dịch vụ | Java/Spring integration | Cách Entra authentication | Phân quyền dữ liệu |
| --- | --- | --- | --- |
| **Azure Database for PostgreSQL Flexible Server** | PostgreSQL JDBC + Spring Cloud Azure PostgreSQL starter | `AzurePostgresqlAuthenticationPlugin` lấy token và chuyển cho JDBC driver | Entra principal được tạo thành PostgreSQL role; dùng GRANT |
| **Azure Database for MySQL Flexible Server** | MySQL Connector/J + Spring Cloud Azure MySQL starter | `AzureMysqlAuthenticationPlugin` chuyển token thành thông tin xác thực MySQL | Entra user/group/identity được tạo thành MySQL user; dùng GRANT |
| **Azure SQL Database** | Microsoft JDBC Driver for SQL Server; Spring Data JDBC/JdbcTemplate/JPA | `ActiveDirectoryManagedIdentity` hoặc `ActiveDirectoryDefault` | Contained database user mapped to Entra principal; database role/GRANT |
| **Azure SQL Managed Instance** | Microsoft JDBC Driver for SQL Server | Entra authentication modes của driver, tùy cấu hình instance | SQL login/database user và role theo mô hình SQL Managed Instance |
| **Azure Cosmos DB for NoSQL** | Azure Cosmos DB Java SDK; Spring Data Cosmos ở tầng repository | `DefaultAzureCredential`/TokenCredential qua Cosmos client | Native Cosmos DB data-plane RBAC |

Azure SQL JDBC driver còn có chế độ Entra cho Azure Synapse Analytics; cần xác minh khả năng cụ thể theo loại workspace, driver version và tính năng SQL đang dùng. Bài này không giả định API MongoDB/Cassandra/Gremlin/Table của Cosmos DB dùng cùng native NoSQL data-plane role. Với API khác hoặc dịch vụ không có tài liệu Java/Spring hỗ trợ, phải kiểm tra riêng trước khi triển khai.

## 4. Chọn credential cho từng môi trường

Azure Identity và Spring Cloud Azure hỗ trợ nhiều loại credential:

| Credential | Khi dùng | Lưu ý |
| --- | --- | --- |
| **System-assigned Managed Identity** | Workload chạy trên Azure resource có bật identity | Vòng đời gắn với resource; xóa resource thì identity bị xóa |
| **User-assigned Managed Identity** | Nhiều workload cần dùng chung một identity hoặc cần identity tồn tại độc lập | Phải chọn đúng client ID; quản lý role assignment riêng |
| **Service principal + certificate** | Workload không hỗ trợ Managed Identity hoặc chạy ngoài Azure | Ưu tiên certificate/federated credential thay cho secret tĩnh khi phù hợp |
| **Service principal + client secret** | Tích hợp legacy hoặc môi trường chưa hỗ trợ phương án khác | Secret phải lưu trong secret manager và có rotation |
| **DefaultAzureCredential** | Phát triển cục bộ và một số ứng dụng Java cần credential chain | Có thể dùng Azure CLI/IDE ở local và Managed Identity khi chạy trên Azure; kiểm soát rõ nguồn credential trong production |
| **Interactive/user credential** | Công cụ phát triển hoặc thao tác có người dùng | Không dùng flow tương tác trong backend headless |

### 4.1. Local development

Developer có thể đăng nhập bằng Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

Với Java SDK dùng `DefaultAzureCredential`, credential chain có thể tìm credential từ môi trường phát triển được hỗ trợ, chẳng hạn Azure CLI hoặc IDE. Database vẫn phải có principal đại diện cho user/developer và quyền phù hợp. Không dùng quyền admin cá nhân để chạy service thường xuyên.

### 4.2. Production

Khi ứng dụng chạy trên Azure App Service, Azure Spring Apps, VM, AKS hoặc một Azure resource hỗ trợ Managed Identity, ưu tiên cấp identity cho workload. Chỉ định user-assigned identity khi cần kiểm soát identity độc lập với vòng đời resource hoặc chia sẻ có chủ đích. Cấp quyền database cho identity đó ở scope nhỏ nhất.

Đối với AKS, có thể dùng Workload Identity Federation để ánh xạ Kubernetes service account sang Entra identity thay vì phát hành secret. Cấu hình issuer, subject và audience phải khớp với federation credential; đừng nhầm Kubernetes service account token với access token database.

### 4.3. Token audience phải đúng dịch vụ

Access token có audience/resource riêng. Không lấy token cho Azure Resource Manager rồi dùng cho SQL, PostgreSQL, MySQL hoặc Cosmos DB. Ví dụ các scope thường gặp:

| Dịch vụ | Token audience/scope thường dùng |
| --- | --- |
| Azure SQL | `https://database.windows.net/.default` |
| PostgreSQL/MySQL Flexible Server | Resource type `oss-rdbms`; scope thường là `https://ossrdbms-aad.database.windows.net/.default` |
| Cosmos DB for NoSQL | `https://cosmos.azure.com/.default` |

Với Spring Cloud Azure passwordless plugin, thư viện lấy token phù hợp theo tích hợp; không tự thay scope bằng một resource khác. Với Java SDK tự quản lý token, dùng đúng scope được tài liệu của dịch vụ chỉ định.

## 5. Azure Database for PostgreSQL Flexible Server

### 5.1. Bật Entra authentication và tạo database principal

PostgreSQL Flexible Server cho phép bật Microsoft Entra authentication trong lúc provision hoặc sau khi tạo server. Cần cấu hình Entra administrator. Administrator có quyền cao, nên chỉ dùng để tạo/quản lý principal; ứng dụng runtime cần principal riêng với quyền tối thiểu.

Một principal có thể là Entra user, group, service principal hoặc managed identity. Sau khi Entra admin đã được cấu hình, tạo PostgreSQL role tương ứng bằng extension `pgaadauth`. Ví dụ theo hướng dẫn Microsoft:

~~~sql
SELECT *
FROM pgaadauth_create_principal('orders_api', false, false);
~~~

Tên principal phải khớp với identity được cấu hình trên server. Sau đó cấp quyền database/schema/table:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_api;
GRANT USAGE ON SCHEMA public TO orders_api;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO orders_api;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO orders_api;
~~~

Ví dụ trên dùng tên role minh họa; xác minh tên role thực tế mà lệnh tạo principal trả về. Quản lý default privileges cho bảng/sequence tạo mới bằng migration hoặc role quản trị schema. Không cấp quyền superuser/CREATEDB cho service runtime.

### 5.2. Spring Cloud Azure starter

Thêm PostgreSQL starter và Spring Cloud Azure BOM tương thích với Spring Boot:

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
</dependencies>
~~~

Spring Cloud Azure PostgreSQL support tích hợp `AzurePostgresqlAuthenticationPlugin` và cung cấp property `spring.datasource.azure.passwordless-enabled`. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${PG_SERVER}.postgres.database.azure.com:5432/${PG_DATABASE}?sslmode=require
    username: ${PG_ENTRA_DATABASE_USER}
    azure:
      passwordless-enabled: true
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo cho user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

Đặt `PG_ENTRA_DATABASE_USER` là database principal đã được tạo cho Entra identity. Khi chạy local, có thể dùng credential source phù hợp như Azure CLI/IDE; khi deploy trên Azure, Managed Identity cung cấp token. Các property credential toàn cục phải theo đúng version Spring Cloud Azure đang dùng.

Passwordless PostgreSQL support có từ Spring Cloud Azure 4.5.0. Hãy chọn BOM tương thích với Spring Boot và kiểm tra version mapping trước khi nâng cấp; không tự nâng riêng starter mà bỏ qua các dependency Azure Identity liên quan.

### 5.3. Luồng kiểm tra

1. Xác minh FQDN, firewall/private network, port 5432 và TLS.
2. Xác minh Entra admin đã được cấu hình.
3. Xác minh database principal đại diện cho workload identity đã tồn tại.
4. Kiểm tra principal có quyền CONNECT, USAGE và quyền table/sequence cần thiết.
5. Xác minh Spring Cloud Azure lấy token cho resource `oss-rdbms`.
6. Thử SELECT/INSERT hợp lệ và một thao tác không được cấp quyền.

TLS vẫn cần bật. `sslmode=require` mã hóa kết nối; production nên đánh giá `verify-full` và CA/hostname verification theo cấu hình driver.

## 6. Azure Database for MySQL Flexible Server

### 6.1. Bật authentication và cấu hình identity phía server

MySQL Flexible Server hỗ trợ MySQL authentication, Microsoft Entra authentication hoặc cả hai tùy server setting. Khi bật Entra authentication, cấu hình Entra administrator và tạo database user ánh xạ tới Entra identity:

~~~sql
CREATE AADUSER 'orders-api-mi';
GRANT SELECT, INSERT, UPDATE, DELETE
    ON orders.* TO 'orders-api-mi'@'%';
FLUSH PRIVILEGES;
~~~

Tên Entra user/group/identity có quy tắc riêng của MySQL; cần dùng đúng spelling và kiểm tra mapping theo tài liệu dịch vụ. Việc xác thực thành công **không tự cấp quyền đọc/ghi**. Database user vẫn phải được GRANT quyền cần thiết.

**Lưu ý đặc biệt về user-assigned identity của MySQL server:** MySQL Flexible Server hiện dùng user-assigned managed identity gắn với chính server để đọc thông tin user/group/service principal từ Microsoft Graph. Identity phía server này cần các Graph permission được Microsoft yêu cầu (User.Read.All, GroupMember.Read.All, Application.Read.All hoặc Directory Readers theo hướng dẫn). Đây là identity phục vụ server lookup principal; nó **khác với Managed Identity của ứng dụng** dùng để lấy token kết nối database. Không cấp quyền Graph rộng cho workload chỉ vì database server cần quyền tra cứu.

### 6.2. Spring Cloud Azure MySQL starter

Dependency:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-jdbc-mysql</artifactId>
</dependency>
~~~

Kèm BOM `spring-cloud-azure-dependencies` tương thích. Starter dùng `AzureMysqlAuthenticationPlugin` để chuyển Entra token thành thông tin xác thực MySQL. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${MYSQL_SERVER}.mysql.database.azure.com:3306/${MYSQL_DATABASE}?sslMode=VERIFY_IDENTITY&serverTimezone=UTC
    username: ${MYSQL_ENTRA_DATABASE_USER}
    azure:
      passwordless-enabled: true
      credential:
        managed-identity-enabled: true
        # Chỉ khai báo nếu workload dùng user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

Property `spring.datasource.azure.passwordless-enabled` bật token-based authentication. Với cấu hình đơn giản, credential có thể được lấy qua DefaultAzureCredential; production có thể chỉ định Managed Identity. Đảm bảo Connector/J hỗ trợ cleartext authentication plugin theo hướng dẫn MySQL và vẫn sử dụng TLS. Không hạ `sslMode` xuống DISABLED để khắc phục lỗi token.

### 6.3. Token audience và tên principal

MySQL Flexible Server dùng resource type `oss-rdbms` để lấy access token. Token phải dành cho đúng dịch vụ và tenant. Tên Entra principal có thể phân biệt chữ hoa/chữ thường; username trong JDBC URL phải khớp database user được tạo.

Microsoft đã thông báo sẽ áp dụng kiểm tra token audience chặt hơn từ tháng 1/2027; ứng dụng phải dùng audience được hỗ trợ là `ossrdbms`. Khi tự lấy token, dùng resource type/scope theo hướng dẫn mới nhất của MySQL Flexible Server, không tái sử dụng token cho Azure SQL hoặc PostgreSQL bằng cách đoán audience.

MySQL server identity và app identity có vai trò riêng:

| Identity | Dùng để | Cấu hình/quyền |
| --- | --- | --- |
| Server user-assigned identity | MySQL server tra cứu Entra users/groups/service principals | Gắn vào Flexible Server và cấp Graph permission theo tài liệu |
| Workload system/user-assigned identity | Spring Boot lấy token để đăng nhập database | Gắn vào App Service/VM/AKS/host; tạo MySQL AADUSER và GRANT quyền dữ liệu |
| Entra administrator | Quản lý Entra database users | Quyền quản trị cao; không dùng làm runtime identity |

## 7. Azure SQL Database và SQL Managed Instance

Azure SQL sử dụng Microsoft JDBC Driver for SQL Server. Không dùng PostgreSQL/MySQL authentication plugin. Driver có các mode Entra như:

- `ActiveDirectoryManagedIdentity`: workload chạy trên Azure resource có Managed Identity.
- `ActiveDirectoryDefault`: dùng Azure Identity `DefaultAzureCredential`; phù hợp cho credential chain được hỗ trợ, gồm local development và Azure hosting.
- `ActiveDirectoryInteractive`: luồng tương tác cho developer/user, không phù hợp backend headless.
- `ActiveDirectoryServicePrincipal` hoặc certificate mode: workload dùng service principal.

### 7.1. Thêm driver và cấu hình Managed Identity

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>com.microsoft.sqlserver</groupId>
    <artifactId>mssql-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Driver 12.2 trở lên hỗ trợ tên mode `ActiveDirectoryManagedIdentity` và `ActiveDirectoryDefault`. Các bản cũ hơn có alias như `ActiveDirectoryMSI`; hãy pin version theo ma trận tương thích và dùng tên mode đúng với driver.

Spring Cloud Azure cũng có thể cung cấp credential cho các tích hợp Spring khác, nhưng `ActiveDirectoryDefault` là chế độ của Microsoft JDBC Driver và dùng Azure Identity theo dependency/version của driver. Kiểm tra cấu hình credential mà driver thực sự đọc; không giả định mọi property của Spring Cloud Azure tự động truyền vào driver.

System-assigned Managed Identity:

~~~yaml
spring:
  datasource:
    url: jdbc:sqlserver://${SQL_SERVER}.database.windows.net:1433;databaseName=${SQL_DATABASE};encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=30;authentication=ActiveDirectoryManagedIdentity
~~~

User-assigned Managed Identity có thể chỉ định client ID bằng `msiClientId` theo version driver:

~~~text
jdbc:sqlserver://<server>.database.windows.net:1433;databaseName=<database>;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;msiClientId=<managed-identity-client-id>
~~~

Hoặc dùng `authentication=ActiveDirectoryDefault` để driver gọi DefaultAzureCredential:

~~~yaml
spring:
  datasource:
    url: jdbc:sqlserver://${SQL_SERVER}.database.windows.net:1433;databaseName=${SQL_DATABASE};encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;authentication=ActiveDirectoryDefault
~~~

Trong driver 12.1, Microsoft Learn mô tả tên `DefaultAzureCredential`; từ driver 12.2 tên chuẩn là `ActiveDirectoryDefault`. Không trộn property của PostgreSQL/MySQL starter với SQL Server JDBC driver nếu driver không đọc chúng.

### 7.2. Tạo database user cho Managed Identity

Trước hết cấu hình Microsoft Entra administrator trên logical SQL server/Managed Instance. Sau đó, Entra admin hoặc principal quản trị tạo contained database user đại diện cho workload:

~~~sql
CREATE USER [orders-api-mi] FROM EXTERNAL PROVIDER;
GO
ALTER ROLE db_datareader ADD MEMBER [orders-api-mi];
ALTER ROLE db_datawriter ADD MEMBER [orders-api-mi];
GO
~~~

Ví dụ dùng role dựng sẵn để minh họa. Production nên cân nhắc custom role hoặc GRANT chính xác theo schema/table thay vì cấp rộng `db_datawriter`/quyền CONTROL. Migration identity có thể cần DDL; runtime identity thường chỉ cần DML.

Azure SQL authentication có thể thành công nhưng truy vấn vẫn bị từ chối nếu database user chưa được tạo hoặc role/GRANT thiếu. Azure Resource Manager Contributor/SQL Server Contributor không tự cấp quyền SELECT/INSERT trên database.

### 7.3. Spring Data JDBC/JdbcTemplate

Khi `DataSource` được cấu hình đúng, Spring Data JDBC/JdbcTemplate hoạt động như với SQL Server thông thường:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int countOrders() {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM dbo.orders",
            Integer.class);
    }
}
~~~

Không tạo access token thủ công trong mỗi repository method. Để JDBC driver/credential integration quản lý token cho connection. HikariCP quản lý pool; connection mới cần xác thực hợp lệ, vì vậy kiểm tra credential refresh khi pool mở connection mới sau thời gian chạy dài.

## 8. Azure Cosmos DB for NoSQL

Cosmos DB for NoSQL dùng SDK/HTTP API, không phải JDBC. Java client nhận `TokenCredential` từ Azure Identity. Ví dụ:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Tạo client bằng `DefaultAzureCredential`:

~~~java
import com.azure.cosmos.CosmosAsyncClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

DefaultAzureCredential credential =
    new DefaultAzureCredentialBuilder().build();

CosmosAsyncClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("AZURE_COSMOS_ENDPOINT"))
    .credential(credential)
    .buildAsyncClient();
~~~

Trong Spring Data Cosmos, dùng credential này khi cấu hình `CosmosClientBuilder`/client bean mà `CosmosTemplate` hoặc repository sử dụng. Tên bean và điểm mở rộng phụ thuộc version Spring Data Cosmos; tránh tạo một client có key trong auto-configuration khác rồi vô tình tiếp tục dùng key.

### 8.1. Native data-plane RBAC

Cosmos DB for NoSQL có native data-plane role system riêng. Hai role dựng sẵn phổ biến:

- **Cosmos DB Built-in Data Reader:** đọc item, query và change feed theo phạm vi role.
- **Cosmos DB Built-in Data Contributor:** đọc/ghi item và thao tác dữ liệu theo phạm vi role.

Gán role cho principal ID của Managed Identity/service principal/user và giới hạn scope ở account, database hoặc container. Ví dụ scope container:

~~~text
/dbs/orders-db/colls/orders
~~~

Java SDK lấy token cho Cosmos DB for NoSQL bằng scope `https://cosmos.azure.com/.default`; SDK hỗ trợ token credential và tự gắn thông tin xác thực vào request.

Quyền quản lý account/database/container là control-plane RBAC. Quyền đọc/ghi item là native data-plane RBAC. Việc tạo role definition/assignment có thể cần control-plane permission riêng; workload runtime không nên được cấp quyền tự gán role cho chính nó.

Sau khi xác minh ứng dụng dùng Entra data-plane role, có thể cân nhắc tắt key-based authentication (`disableLocalAuth`) cho account mới hoặc trong migration bảo mật có kiểm soát. Làm việc này sau khi đã kiểm tra mọi workload, công cụ vận hành và backup/restore path; các client còn dùng account key sẽ bị ngắt.

### 8.2. Giới hạn theo API

Role `Cosmos DB Built-in Data Reader/Contributor` ở trên áp dụng cho **Cosmos DB for NoSQL**. Không áp dụng chúng một cách máy móc cho Cosmos DB API for MongoDB, Cassandra, Gremlin hoặc Table. Mỗi API có cơ chế auth/authorization riêng và phải tra tài liệu tương ứng.

## 9. Authentication khác authorization

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Azure resource identity | Workload là principal nào? | Managed Identity của App Service |
| Token authentication | Token có hợp lệ cho database không? | Audience SQL/oss-rdbms/Cosmos đúng, token chưa hết hạn |
| Database principal mapping | Database nhận diện principal thành user nào? | PostgreSQL role, MySQL AADUSER, SQL contained user |
| Database/data authorization | User được thao tác gì? | GRANT SELECT, db_datareader, Cosmos Data Reader |
| Azure control-plane authorization | Ai được quản lý resource/role assignment? | Azure RBAC trên server/account |

Một Managed Identity có thể có Azure role quản lý tài nguyên nhưng chưa có database user. Ngược lại, một database principal có GRANT trong database nhưng workload không lấy được token thì vẫn không kết nối được. Hãy kiểm tra từng lớp riêng biệt.

## 10. Token lifetime, connection pool và refresh

Access token có thời hạn. Ứng dụng không nên lấy token một lần lúc startup rồi lưu vào `spring.datasource.password` lâu dài. Hãy để plugin/driver/credential integration lấy token khi tạo connection và quản lý cache/refresh theo cơ chế hỗ trợ.

Một số điểm vận hành:

- Connection JDBC đã xác thực thường có thể tiếp tục hoạt động sau khi token dùng lúc login hết hạn; token được kiểm tra khi thiết lập kết nối. Connection mới phải dùng token còn hạn.
- Khi HikariCP cần mở connection mới sau thời gian chạy dài, credential provider phải lấy token mới. Kiểm thử trường hợp pool mở connection sau khi token cũ hết hạn.
- Không log token, không lưu raw token trong config hoặc database.
- Đặt `maxLifetime`, `idleTimeout`, `keepaliveTime` theo giới hạn network/server; không đặt pool lifetime ngắn tùy tiện khiến Entra token request tăng quá mức.
- Khi identity bị xóa/role assignment bị thu hồi, connection đang mở có thể không bị ngắt ngay lập tức. Thu hồi quyền cần kế hoạch drain/recycle connection và xác minh lại quyền.
- Tránh khởi tạo một `DefaultAzureCredential` hoặc client SDK mới cho mỗi request; reuse credential/client thread-safe theo hướng dẫn SDK.

## 11. Bảo vệ Managed Identity và quyền Entra

Áp dụng nguyên tắc least privilege:

1. Mỗi workload hoặc nhóm workload có ranh giới tin cậy rõ ràng.
2. Ưu tiên system-assigned identity nếu vòng đời identity gắn với một Azure resource; dùng user-assigned khi cần quản lý độc lập.
3. Tạo database principal riêng cho runtime; tách admin và migration identity.
4. Chỉ cấp quyền database trên schema/table/container cần thiết.
5. Không cấp Azure subscription Owner/Contributor để thay database GRANT.
6. Với service principal, ưu tiên certificate hoặc workload federation; tránh client secret tĩnh nếu có phương án khác.
7. Audit role assignment và database grant; thu hồi quyền khi workload ngừng hoạt động.

**Lưu ý MySQL:** Graph permission được gắn với user-assigned identity của MySQL server phục vụ việc resolve principal; đây không phải lý do để cấp các quyền Graph đó cho application Managed Identity. Đánh giá phạm vi quyền của server identity riêng biệt.

## 12. Chẩn đoán lỗi theo dịch vụ

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Token acquisition failure | Managed Identity chưa bật, sai client ID, workload không có endpoint/credential hoặc tenant sai | Azure resource identity, credential chain, tenant và log Azure Identity |
| 401 / login failed | Token hết hạn, sai audience, principal không tồn tại hoặc Entra admin chưa cấu hình | Resource/scope, database principal, server Entra setting |
| PostgreSQL `password authentication failed` | Plugin không được nạp, username không khớp, token resource sai | Starter/plugin version, username, `oss-rdbms` token |
| MySQL access denied | AADUSER mapping sai, cleartext plugin/TLS chưa đúng hoặc GRANT thiếu | Entra user spelling, Connector/J options, database grant |
| SQL Server login failed | JDBC driver quá cũ, sai authentication mode hoặc identity chưa được map | Driver version, `ActiveDirectoryManagedIdentity/Default`, contained user |
| Cosmos 403 | Có token nhưng thiếu data-plane role hoặc scope không đúng | Principal ID, native role assignment và database/container scope |
| Local chạy được, Azure lỗi | Local dùng Azure CLI credential; production Managed Identity chưa được cấp role | Identity thực tế ở host, token claims, principal mapping |
| Pool hoạt động lúc đầu rồi lỗi khi reconnect | Token refresh/credential chain hoặc identity assignment có vấn đề | Hikari connection creation, Azure Identity diagnostics |
| Một service có quyền nhưng service khác không | Database principal/role là riêng cho từng database | Không giả định role Azure được chia sẻ giữa SQL/PostgreSQL/MySQL/Cosmos |

Không ghi access token hoặc connection string chứa secret vào log để chẩn đoán. Có thể ghi loại credential, principal ID đã được kiểm soát, database host, operation, error code và correlation/activity ID.

## 13. Kiểm thử Entra authentication

### 13.1. Unit test

Mock repository/DAO để kiểm tra business rule và xử lý lỗi. Unit test không chứng minh token có thể đăng nhập database hoặc role assignment đúng.

### 13.2. Local integration test

Với local development, dùng Azure CLI/IDE credential hoặc principal test được cấp quyền tối thiểu. Xác minh:

- Credential chain lấy được token cho đúng tenant/resource.
- Database principal đã được tạo.
- SELECT/INSERT hợp lệ thành công.
- Thao tác ngoài quyền bị từ chối.
- TLS hostname/certificate validation vẫn bật.

Không dùng Entra admin cá nhân làm user test cho service runtime.

### 13.3. Azure integration test

Deploy ứng dụng lên Azure resource có Managed Identity hoặc Workload Identity. Kiểm tra:

1. Host cấp đúng system/user-assigned identity.
2. Principal ID/client ID khớp database user/role assignment.
3. Database authentication chấp nhận token đúng audience.
4. Least-privilege test: đọc/ghi cần thiết thành công, DDL hoặc truy cập schema khác bị từ chối.
5. Connection pool mở connection mới sau thời gian chạy dài vẫn lấy token hợp lệ.
6. Xóa/thu hồi role assignment trong môi trường test tạo lỗi quyền dự kiến.
7. Logs/metrics không chứa raw token hoặc secret.

### 13.4. Ma trận test tối thiểu

| Test | PostgreSQL | MySQL | Azure SQL | Cosmos NoSQL |
| --- | --- | --- | --- | --- |
| Local developer credential | Entra plugin | Entra plugin | ActiveDirectoryDefault | DefaultAzureCredential |
| Managed Identity | Starter credential | Starter credential + server identity setup | ActiveDirectoryManagedIdentity | TokenCredential |
| Principal mapping | PostgreSQL role | AADUSER | Contained database user | Native data-plane role |
| Least privilege | GRANT | GRANT | SQL role/GRANT | Reader/Contributor/custom role |
| Token audience | oss-rdbms | oss-rdbms | database.windows.net | cosmos.azure.com |
| Expiry/reconnect | JDBC pool new connection | JDBC pool new connection | JDBC pool new connection | SDK credential refresh |

## 14. Quy trình triển khai từ password sang Entra

Không tắt password authentication trước khi xác minh mọi workload đã chuyển:

1. **Inventory:** liệt kê ứng dụng, job, migration, reporting tool và operator đang dùng database password/key.
2. **Enable Entra:** cấu hình Entra administrator và server/account setting cần thiết.
3. **Create principal:** tạo database user hoặc native role cho workload identity.
4. **Grant least privilege:** cấp quyền tối thiểu và tách quyền migration/runtime.
5. **Update app:** cấu hình driver/starter/SDK đúng dịch vụ, endpoint, credential và TLS.
6. **Test:** chạy unit, integration và Azure smoke test; xác minh cả truy cập hợp lệ lẫn bị cấm.
7. **Deploy canary:** chuyển một workload/instance trước, theo dõi token acquisition, login error, 403 và connection pool.
8. **Rotate/revoke old secret:** sau khi tất cả workload chuyển thành công, thu hồi credential cũ theo change plan.
9. **Disable local auth nếu dịch vụ hỗ trợ và chính sách yêu cầu:** kiểm tra backup/restore, admin tools và integration còn lại.
10. **Audit:** lưu principal, role scope, owner, mục đích và quy trình thu hồi.

~~~mermaid
flowchart TD
    A[Inventory password/key users] --> B[Enable Entra on database]
    B --> C[Assign workload identity]
    C --> D[Create database principal / data role]
    D --> E[Grant least privilege]
    E --> F[Configure Spring driver / SDK]
    F --> G[Integration test + canary]
    G --> H{All workloads pass?}
    H -->|No| I[Fix identity, audience, role or network]
    I --> G
    H -->|Yes| J[Revoke old password/key]
    J --> K[Disable local auth where supported]
    K --> L[Audit and monitor]
~~~

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi Managed Identity là quyền database | Token hợp lệ nhưng SELECT bị từ chối | Tạo database principal/role assignment và GRANT |
| Dùng Azure Contributor thay database role | Có quyền quản lý resource nhưng không có quyền dữ liệu | Cấp database authorization riêng |
| Dùng token ARM cho database | Audience không hợp lệ | Lấy token đúng scope của dịch vụ |
| Dùng PostgreSQL/MySQL plugin cho Azure SQL | Driver không hiểu authentication mode | Dùng Microsoft JDBC Driver |
| Dùng Cosmos SDK key-based trong khi nghĩ đã chuyển Entra | Ứng dụng vẫn phụ thuộc key | Cấu hình TokenCredential và kiểm tra client bean thực tế |
| Cấp quyền admin cho runtime | Tăng blast radius khi credential bị lộ | Tạo principal riêng, GRANT tối thiểu |
| Nhầm MySQL server UAMI với app UAMI | Cấp Graph permission cho sai identity | Tách identity lookup phía server và identity kết nối phía app |
| Lưu access token trong application.yml | Token hết hạn, lộ credential | Dùng plugin/driver/SDK quản lý token |
| Chỉ test local bằng Azure CLI | Production Managed Identity có thể chưa được cấp quyền | Azure integration test với identity của workload |
| Tắt password/key auth quá sớm | Tool/job cũ mất kết nối | Inventory, canary và revoke theo từng bước |

## 16. Bài tập thực hành

**Bài tập 1 — PostgreSQL passwordless.** Tạo PostgreSQL Flexible Server, bật Entra admin, gắn Managed Identity cho Spring Boot workload, tạo principal bằng `pgaadauth_create_principal`, cấp quyền schema/table và kết nối qua `spring-cloud-azure-starter-jdbc-postgresql`.

**Bài tập 2 — MySQL passwordless.** Bật Entra authentication cho MySQL Flexible Server. Phân biệt UAMI phía server dùng đọc Microsoft Graph với Managed Identity phía ứng dụng. Tạo AADUSER, GRANT SELECT/INSERT và xác minh Connector/J dùng TLS.

**Bài tập 3 — Azure SQL.** Cấu hình Microsoft JDBC Driver 12.2 với `ActiveDirectoryManagedIdentity` hoặc `ActiveDirectoryDefault`. Tạo contained database user từ external provider, cấp db_datareader và thử một lệnh DDL bị từ chối.

**Bài tập 4 — Cosmos DB.** Tạo `CosmosAsyncClient` với `DefaultAzureCredential`. Gán Cosmos DB Built-in Data Reader cho container cụ thể, thử query thành công và write thất bại; sau đó đổi sang Contributor và kiểm tra lại.

**Bài tập 5 — Authentication hay authorization?** Tạo bốn tình huống: không lấy được token, token sai audience, principal chưa tồn tại, principal tồn tại nhưng thiếu GRANT. Phân loại log/error và đề xuất nơi cần sửa.

**Bài tập 6 — Credential chain.** Chạy cùng một ứng dụng trên máy developer đã `az login` và trên Azure App Service có Managed Identity. Ghi nhận credential thực tế được chọn, tenant, principal và cách bảo đảm production không vô tình dùng credential developer.

**Bài tập 7 — Token refresh.** Dùng HikariCP, để ứng dụng chạy đủ lâu để token ban đầu hết hạn rồi tạo connection mới. Kiểm tra plugin/driver lấy token mới; theo dõi lỗi login và pool metrics mà không log token.

**Bài tập 8 — Migration.** Lập kế hoạch chuyển một ứng dụng từ database password sang Entra. Bao gồm inventory, principal/role, canary, secret revoke, tắt local auth nếu hỗ trợ và rollback plan.

## 17. Ghi nhớ

- **Microsoft Entra cung cấp danh tính và access token; database vẫn phải ánh xạ principal và cấp quyền dữ liệu.** Authentication thành công không đồng nghĩa authorization thành công.
- PostgreSQL/MySQL Flexible Server dùng Spring Cloud Azure JDBC starter và plugin riêng; Azure SQL dùng Microsoft JDBC Driver; Cosmos DB for NoSQL dùng Java SDK/TokenCredential và native data-plane RBAC.
- Dùng đúng **token audience/scope** cho SQL, OSS RDBMS hoặc Cosmos. Token ARM không thể thay token database.
- **Managed Identity không phải database user.** Tạo PostgreSQL role, MySQL AADUSER, SQL contained database user hoặc Cosmos data-plane role tương ứng.
- MySQL Flexible Server có **server-side user-assigned identity** để đọc Microsoft Graph; identity này khác Managed Identity của workload.
- Dùng system/user-assigned identity hoặc credential chain phù hợp; local developer có thể dùng Azure CLI/IDE, production ưu tiên Managed Identity/workload identity.
- Driver/starter/SDK quản lý token và reconnect; không lưu raw access token vào cấu hình hoặc log. Kiểm thử connection pool khi mở connection mới sau token expiry.
- Chuyển passwordless theo từng bước: inventory, enable Entra, principal, least privilege, canary, revoke secret rồi mới tắt local auth nếu dịch vụ hỗ trợ.

## 18. Tài liệu tham khảo

- [Passwordless authentication with Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/passwordless-authentication)
- [Spring Cloud Azure PostgreSQL support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/postgresql-support)
- [Spring Cloud Azure MySQL support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/mysql-support)
- [Use Spring Data JDBC with Azure SQL Database](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-jdbc-with-azure-sql-server)
- [Microsoft JDBC Driver — Entra authentication](https://learn.microsoft.com/en-us/sql/connect/jdbc/connecting-using-azure-active-directory-authentication)
- [Microsoft JDBC Driver — connection properties](https://learn.microsoft.com/en-us/sql/connect/jdbc/setting-the-connection-properties)
- [Configure and manage Microsoft Entra authentication with Azure SQL](https://learn.microsoft.com/en-us/azure/azure-sql/database/authentication-aad-configure)
- [Microsoft Entra authentication for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure)
- [Managed Identity connection for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity)
- [Microsoft Entra authentication for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/security/security-entra-authentication)
- [Set up Microsoft Entra authentication for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-how-to-entra)
- [Connect to Cosmos DB for NoSQL with Microsoft Entra ID and RBAC](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-connect-role-based-access-control)
- [Azure Identity client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/identity-readme?view=azure-java-stable)
- [Azure Cosmos DB Java client library](https://learn.microsoft.com/en-us/java/api/overview/azure/cosmos-readme?view=azure-java-stable)
