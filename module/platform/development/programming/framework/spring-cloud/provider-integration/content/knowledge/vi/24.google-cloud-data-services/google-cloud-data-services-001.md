# Kết nối Cloud SQL bằng JDBC và Cloud SQL Connector

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud để truy cập storage, messaging, dữ liệu, danh tính và quyền. Trên Google Cloud, **Cloud SQL** cung cấp cơ sở dữ liệu quan hệ managed cho PostgreSQL, MySQL và SQL Server. Ứng dụng Java vẫn dùng JDBC và connection pool quen thuộc, nhưng cần thiết lập cách xác thực workload, đường mạng và bảo vệ kết nối đến instance.

Bài học tập trung vào **JDBC + Cloud SQL Java Connector**. Sau bài này, bạn có thể:

1. Phân biệt Cloud SQL project, instance, database, database user và instance connection name.
2. Kết nối Spring Boot bằng JDBC URL và JDBC Socket Factory cho PostgreSQL/MySQL.
3. Cấu hình Application Default Credentials (ADC), IAM role và IAM database authentication.
4. Phân biệt Public IP, Private IP và yêu cầu mạng VPC.
5. So sánh Java Connector với Cloud SQL Auth Proxy.
6. Cấu hình HikariCP, pool size, timeout, transaction và retry an toàn.
7. Kiểm thử kết nối, quyền, HA/failover và quan sát lỗi trên Google Cloud.

> **Phạm vi:** Ví dụ chính dùng PostgreSQL. Tên dependency/property cần đồng bộ theo phiên bản Cloud SQL Java Connector tương thích với Spring Boot. Project ID, instance connection name và database trong bài là dữ liệu minh họa.

## 1. Cloud SQL trong kiến trúc Spring Boot

Cloud SQL là dịch vụ cơ sở dữ liệu quan hệ managed. Google quản lý hạ tầng instance, backup, patching, monitoring và các lựa chọn HA; ứng dụng kết nối thông qua giao thức database quen thuộc.

Một instance có thể chứa nhiều database, mỗi database có các user/role riêng. Cần phân biệt:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Google Cloud project | `rental-platform-dev` | Phạm vi quản lý tài nguyên và IAM |
| Region | `asia-southeast1` | Khu vực đặt instance |
| Instance | `orders-db` | Tài nguyên Cloud SQL |
| Instance connection name | `rental-platform-dev:asia-southeast1:orders-db` | Định danh instance dùng cho connector/proxy |
| Database | `orders` | Cơ sở dữ liệu ứng dụng kết nối |
| Database user | `orders_app` | Danh tính ở tầng database |
| Workload identity | Service account của Cloud Run/GKE/Compute | Danh tính Google Cloud của ứng dụng |

**IAM principal của workload và database user là hai lớp danh tính khác nhau.** Service account có quyền kết nối Cloud SQL không mặc nhiên được phép truy vấn mọi bảng; database vẫn kiểm tra user, password hoặc IAM database authentication và quyền SQL.

~~~mermaid
flowchart LR
    APP["Spring Boot"] --> HIKARI["HikariCP / JDBC"]
    HIKARI --> CONN["Cloud SQL Java Connector"]
    CONN -->|"IAM + TLS"| SQL["Cloud SQL instance"]
    ID["Workload service account"] -->|"ADC"| CONN
    SQL --> DB["Database + DB roles"]
~~~

Java Connector giúp xác thực instance và thiết lập kết nối được mã hóa. JDBC driver thực hiện giao tiếp database; HikariCP quản lý pool connection. Connector **không thay thế JDBC driver, database user hoặc transaction manager**.

## 2. Chuẩn bị instance và IAM

### 2.1. Thông tin cần có

Trước khi cấu hình Spring Boot, xác định:

- Database engine: PostgreSQL, MySQL hoặc SQL Server.
- Region và instance connection name.
- Database name và database user.
- Public IP, Private IP hoặc Private Service Connect theo kiến trúc.
- HA, backup, maintenance window và giới hạn connection.
- Cơ chế database authentication: username/password hay IAM database authentication.

Ví dụ instance connection name:

~~~text
rental-platform-dev:asia-southeast1:orders-db
└──── project ID ────┘└── region ──┘└instance┘
~~~

Đây là **tên kết nối**, không phải JDBC hostname hoặc database name.

### 2.2. Bật API và cấp quyền

Project cần bật Cloud SQL Admin API (`sqladmin.googleapis.com`).

Workload service account thường cần:

- **Cloud SQL Client** (`roles/cloudsql.client`): quyền thiết lập kết nối tới Cloud SQL.
- **Cloud SQL Instance User** (`roles/cloudsql.instanceUser`): cần khi dùng IAM database authentication để đăng nhập database bằng IAM principal, ngoài quyền Cloud SQL Client.

Chỉ cấp role cần thiết cho service account chạy ứng dụng. Không gán Owner/Editor toàn project để giải quyết lỗi kết nối.

Với local development, người phát triển có thể dùng ADC từ tài khoản đã đăng nhập và được cấp quyền phù hợp. Với production, ưu tiên service account gắn trực tiếp với Cloud Run, GKE Workload Identity hoặc Compute Engine; tránh tải service account key JSON vào container hoặc source code.

### 2.3. Database user khác IAM principal

Với password-based database authentication:

- Ứng dụng có Google Cloud identity để connector xác thực quyền kết nối.
- Ứng dụng vẫn cung cấp database username/password.
- Database user phải được tạo trong Cloud SQL và được cấp quyền schema/table cần thiết.

Với **IAM database authentication**, Cloud SQL cho phép danh tính IAM đăng nhập database theo cấu hình engine và instance. Cần bật IAM database authentication, tạo user IAM phù hợp và cấp quyền SQL. Java Connector hỗ trợ tự động làm mới token khi cấu hình `enableIamAuth=true` ở các driver được hỗ trợ.

IAM database authentication **không thay thế quyền SQL**. Sau khi xác thực, user vẫn chỉ truy cập được những database/schema/table mà database grant cho phép.

## 3. Cloud SQL Java Connector và JDBC Socket Factory

### 3.1. Connector làm gì?

Cloud SQL Java Connector là thư viện chạy trong ứng dụng Java, hỗ trợ:

- Xác thực workload với Google Cloud bằng ADC.
- Kiểm tra quyền kết nối tới instance.
- Thiết lập kết nối TLS được quản lý.
- Làm mới thông tin kết nối/metadata theo vòng đời connector.
- Chọn loại IP phù hợp với cấu hình instance.

Connector không phải database engine và cũng không phải connection pool.

| Thành phần | Trách nhiệm |
| --- | --- |
| PostgreSQL JDBC driver | Giao tiếp giao thức PostgreSQL và thực hiện câu SQL |
| Cloud SQL Java Connector / Socket Factory | Xác thực instance, TLS và tạo đường kết nối |
| HikariCP | Giữ, cấp phát và thu hồi JDBC connections |
| Spring Data JPA/JdbcTemplate | Tương tác database ở tầng ứng dụng |
| Google Cloud IAM | Xác thực và phân quyền workload tới Cloud SQL |

### 3.2. Dependency PostgreSQL

Ví dụ Maven với PostgreSQL JDBC driver và Cloud SQL PostgreSQL Socket Factory:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.google.cloud.sql</groupId>
        <artifactId>postgres-socket-factory</artifactId>
        <version>${cloud-sql-java-connector.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

`cloud-sql-java-connector.version` là property dự án cần khai báo theo phiên bản connector được hỗ trợ. Spring Boot BOM thường quản lý phiên bản PostgreSQL JDBC driver; tránh override driver/connector bằng các bản không tương thích.

Nếu dùng JPA thay vì JdbcTemplate, có thể thay `spring-boot-starter-jdbc` bằng `spring-boot-starter-data-jpa`; nguyên tắc JDBC URL và connector vẫn tương tự.

### 3.3. JDBC URL PostgreSQL

Cloud SQL PostgreSQL Socket Factory được cấu hình qua JDBC URL:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
~~~

Các tham số:

- `jdbc:postgresql:///` dùng dạng URL không chỉ định host thông thường; socket factory xác định instance qua `cloudSqlInstance`.
- `cloudSqlInstance` có định dạng `project:region:instance`.
- `socketFactory` trỏ đến lớp PostgreSQL Socket Factory trong dependency.
- `ipTypes=PRIVATE` yêu cầu connector dùng đường kết nối private nếu instance có Private IP và workload có route mạng tới VPC tương ứng.
- `DB_NAME`, `DB_USER`, `DB_PASS` là thông tin database; không phải Google Cloud service account.

Nếu cần Public IP, có thể chọn `ipTypes=PUBLIC` hoặc cấu hình theo IP type provider hỗ trợ. Không đổi sang PRIVATE chỉ bằng cách sửa JDBC URL nếu workload chưa có kết nối mạng tới VPC chứa instance.

### 3.4. Cấu hình Spring Boot với HikariCP

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
    username: ${DB_USER}
    password: ${DB_PASS}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: orders-cloud-sql-pool
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Đây là cấu hình khởi đầu, không phải giá trị tối ưu cho mọi instance. Cần tính tổng connection của **mọi replica**:

~~~text
Tổng connection tối đa
  = số replica ứng dụng × maximum-pool-size
    + migration job
    + worker/background job
    + kết nối quản trị/giám sát
~~~

Ví dụ 6 replica × 8 connection = 48 connection từ API, chưa tính job và vận hành. Pool quá lớn có thể vượt giới hạn Cloud SQL hoặc làm database quá tải; pool quá nhỏ khiến request xếp hàng lâu. Hãy đo connection usage, query latency và throughput dưới tải thật.

### 3.5. Dùng MySQL

Với Cloud SQL MySQL, cần MySQL JDBC driver và MySQL Socket Factory:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>com.google.cloud.sql</groupId>
    <artifactId>mysql-socket-factory</artifactId>
    <version>${cloud-sql-java-connector.version}</version>
</dependency>
~~~

Ví dụ URL:

~~~properties
spring.datasource.url=jdbc:mysql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.mysql.SocketFactory&ipTypes=PRIVATE
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
~~~

Tên Socket Factory của PostgreSQL và MySQL **khác nhau**. Không sao chép nguyên class name từ engine này sang engine kia. SQL Server có driver/socket factory và tham số riêng; phải theo hướng dẫn tương ứng của phiên bản connector.

## 4. Application Default Credentials và workload identity

### 4.1. ADC hoạt động như thế nào?

Cloud SQL Java Connector lấy Google credentials thông qua **Application Default Credentials (ADC)**. ADC tìm danh tính theo môi trường thực thi:

- Local development: credentials được tạo qua Google Cloud CLI.
- Cloud Run: service account được gắn vào service.
- Compute Engine: service account gắn vào VM.
- GKE: Workload Identity Federation for GKE gắn Kubernetes service account với Google service account hoặc principal phù hợp.
- Môi trường ngoài Google Cloud: workload identity federation hoặc cơ chế credentials được tổ chức phê duyệt.

Không đưa service account key JSON vào `application.yml`. Tránh lưu file key trong Docker image, Git hoặc thư mục tạm dễ bị lộ.

### 4.2. Local development với ADC

Người phát triển có thể đăng nhập ADC bằng Google Cloud CLI:

~~~bash
gcloud auth application-default login
gcloud config set project rental-platform-dev
~~~

Lệnh đầu tạo credentials cho ứng dụng local. Tài khoản cần quyền IAM thích hợp trên project/instance. Lệnh chọn project của gcloud CLI không tự cấp quyền và không bảo đảm ADC luôn dùng đúng project trong mọi cấu hình; cần xác minh project và principal thực tế.

Khi chạy integration test local, không dùng tài khoản cá nhân có quyền quá rộng nếu có thể dùng service account test hoặc principal chuyên biệt.

### 4.3. Workload identity trong production

Một cấu hình triển khai tốt:

1. Tạo service account riêng cho service `orders-api`.
2. Cấp `roles/cloudsql.client` trên project hoặc instance theo phạm vi quản trị cho phép.
3. Nếu dùng IAM DB authentication, cấp thêm quyền instance user phù hợp và tạo database IAM user.
4. Gắn service account vào Cloud Run/GKE/Compute workload.
5. Để ADC tự lấy credentials từ môi trường; không mount key JSON.
6. Database user vẫn chỉ được cấp quyền SQL cần thiết.

IAM role cấp quyền kết nối đến Cloud SQL; quyền SQL quyết định ứng dụng được SELECT/INSERT/UPDATE bảng nào. Tách hai lớp này giúp giảm blast radius nếu service account hoặc ứng dụng bị lộ.

## 5. IAM database authentication

### 5.1. Phân biệt hai cách xác thực

| Cách | Xác thực kết nối instance | Đăng nhập database |
| --- | --- | --- |
| Password-based DB auth | Connector dùng ADC/IAM để xác thực tới Cloud SQL | DB username + password |
| IAM DB authentication | Connector dùng ADC/IAM; bật chế độ IAM auth | IAM principal được ánh xạ thành database user và token được cấp tự động |

Với IAM DB authentication, instance cần bật tính năng tương ứng và user IAM phải được tạo trong Cloud SQL. Tên database user có quy tắc khác nhau giữa PostgreSQL và MySQL; hãy dùng đúng định dạng do Cloud SQL quy định cho engine.

### 5.2. Cấu hình tự động IAM auth

Với PostgreSQL Socket Factory, có thể bổ sung tham số:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
~~~

Khi dùng `enableIamAuth=true`, connector quản lý token xác thực IAM cho database theo cơ chế được hỗ trợ. Không cấu hình password database tĩnh theo cùng cách của password-based authentication nếu engine/connector đang sử dụng IAM DB auth.

Để hoạt động:

- Cloud SQL instance phải bật IAM database authentication.
- Workload principal cần quyền kết nối Cloud SQL và quyền IAM DB authentication tương ứng.
- IAM database user phải được tạo trên instance.
- Database user phải có quyền SQL trong database.
- Connector, JDBC driver và engine version phải hỗ trợ cấu hình đang dùng.

**Không nhầm `roles/cloudsql.client` với quyền đăng nhập IAM database.** Hai role phục vụ hai mục đích khác nhau.

### 5.3. Khi nào dùng password và khi nào dùng IAM DB auth?

Password-based authentication dễ tích hợp với ứng dụng hiện hữu, nhưng cần lưu secret trong Secret Manager hoặc hệ thống quản lý secret được phê duyệt, có rotation và không log. IAM DB auth giảm nhu cầu quản lý password tĩnh, phù hợp workload có IAM identity rõ ràng, nhưng đòi hỏi cấu hình instance, IAM principal, database user và connector tương thích.

Dù chọn cách nào, database vẫn cần role/grant tối thiểu. Không dùng tài khoản database owner/superuser cho API runtime.

## 6. Public IP, Private IP và mạng VPC

### 6.1. Connector bảo vệ kết nối nhưng không tạo đường mạng

Cloud SQL Java Connector hỗ trợ xác thực và TLS, nhưng **không tự tạo route mạng** từ ứng dụng đến Private IP. Nếu chọn `ipTypes=PRIVATE`, workload phải có khả năng kết nối tới private address của instance thông qua VPC/network configuration.

~~~mermaid
flowchart TD
    APP["Cloud Run / GKE / Compute"] --> CHOICE{"Chọn IP type"}
    CHOICE -->|"PUBLIC"| PUB["Cloud SQL Public IP"]
    CHOICE -->|"PRIVATE"| VPC["VPC network route"]
    VPC --> SQL["Cloud SQL Private IP"]
    PUB --> SQL
    IAM["ADC + Cloud SQL IAM"] --> CONN["Java Connector"]
    CONN --> SQL
~~~

### 6.2. Public IP

Với Public IP, connector có thể xác thực và thiết lập TLS mà không cần quản lý SSL certificate thủ công. Connector không yêu cầu cấu hình authorized networks theo cách kết nối IP trực tiếp truyền thống. Tuy vậy:

- Workload vẫn phải có outbound network tới endpoint Cloud SQL.
- Egress/firewall/proxy của môi trường có thể chặn kết nối.
- Cần kiểm tra chính sách tổ chức, vùng mạng và yêu cầu compliance.
- Không biến database thành endpoint public cho mọi người dùng; IAM và cấu hình instance vẫn kiểm soát truy cập.

### 6.3. Private IP

Private IP phù hợp khi database chỉ được truy cập trong mạng riêng:

- Cloud SQL instance được cấu hình Private IP.
- Workload phải có đường kết nối đến VPC tương ứng.
- Cloud Run cần cấu hình Direct VPC egress hoặc Serverless VPC Access theo mô hình triển khai được hỗ trợ.
- GKE/Compute phải nằm trong mạng có route và firewall phù hợp.
- Java Connector chọn private IP bằng cấu hình IP type.

**Chỉ đặt `ipTypes=PRIVATE` không làm Cloud Run tự kết nối được VPC.** Nếu route chưa tồn tại, ứng dụng sẽ gặp lỗi timeout hoặc không kết nối được dù IAM role đã đúng.

### 6.4. Private Service Connect

Một số kiến trúc có thể sử dụng Private Service Connect để truy cập Cloud SQL theo mô hình endpoint riêng. PSC có cách thiết lập DNS/network và instance connectivity riêng. Connector cần được cấu hình phù hợp với lựa chọn IP/network; không suy PSC tương đương Private Service Access. Hãy theo tài liệu triển khai Cloud SQL của môi trường cụ thể.

## 7. Cloud SQL Java Connector và Cloud SQL Auth Proxy

Cả hai giúp workload kết nối Cloud SQL mà không phải tự quản lý certificate/authorized network theo cách cũ, nhưng cách triển khai khác nhau.

| Tiêu chí | Java Connector | Cloud SQL Auth Proxy |
| --- | --- | --- |
| Vị trí chạy | Trong process Java | Process/sidecar/container riêng |
| Tích hợp | JDBC Socket Factory | Mở local TCP hoặc Unix socket |
| JDBC URL | Chỉ rõ `cloudSqlInstance` và `socketFactory` | Kết nối tới `localhost:port` hoặc socket |
| Credentials | ADC trong ứng dụng | ADC của process proxy |
| TLS/auth | Connector quản lý | Proxy quản lý |
| Phụ thuộc ngôn ngữ | Tích hợp Java/JDBC | Có thể dùng cho nhiều loại ứng dụng |
| Vận hành | Dependency và cấu hình trong app | Quản lý process/sidecar, health và lifecycle riêng |

### 7.1. Khi nào chọn Java Connector?

- Ứng dụng Java/Spring Boot cần tích hợp gọn trong JDBC URL.
- Muốn quản lý connector cùng vòng đời ứng dụng.
- Muốn dùng trực tiếp HikariCP/JPA/JdbcTemplate.
- Workload có ADC và network path tới IP type đã chọn.

### 7.2. Khi nào chọn Auth Proxy?

- Nhiều ngôn ngữ hoặc ứng dụng cùng kết nối Cloud SQL.
- Muốn tách kết nối Cloud SQL khỏi process ứng dụng.
- Nền tảng triển khai hỗ trợ sidecar/companion process rõ ràng.
- Muốn ứng dụng tiếp tục dùng JDBC URL localhost mà proxy xử lý xác thực/TLS.

Không cần chạy **Java Connector và Auth Proxy chồng lên nhau** cho cùng một kết nối. Chọn một mô hình, cấu hình credentials/network phù hợp và kiểm thử đường đi thực tế.

### 7.3. Ví dụ JDBC khi dùng Auth Proxy

Giả sử proxy đã chạy và mở local TCP port `5432`:

~~~properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/${DB_NAME}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
~~~

Ở đây JDBC driver kết nối tới proxy trên localhost; proxy chuyển tiếp kết nối đến Cloud SQL. Ứng dụng vẫn cần database username/password hoặc IAM DB auth theo cách proxy và engine hỗ trợ. **Không cấu hình thêm Socket Factory của Java Connector vào URL này** nếu proxy đã là lớp kết nối.

## 8. HikariCP, connection pool và hiệu năng

### 8.1. Connector không phải connection pool

Cloud SQL Java Connector tạo đường kết nối an toàn, còn mỗi JDBC connection vẫn là một database connection. HikariCP tái sử dụng các connection để tránh tạo kết nối mới cho mọi HTTP request.

Để Spring quản lý singleton datasource và pool theo lifecycle ứng dụng. Tránh tự mở connection rồi không đóng, vì sẽ giữ slot database đến khi pool cạn.

### 8.2. Ước lượng pool size

Giả sử:

- 4 replica Spring Boot.
- Mỗi replica có `maximum-pool-size = 6`.
- 1 migration job có thể dùng tối đa 2 connection.
- Một số connection dành cho quản trị/monitoring.

~~~text
API pool = 4 × 6 = 24
Migration job = tối đa 2
Tổng ứng dụng dự kiến = 26 + quản trị/monitoring
~~~

Con số này phải nhỏ hơn giới hạn connection thực tế của instance với headroom. Tăng replica từ 4 lên 10 có thể làm tổng connection tăng gấp 2,5 dù cấu hình mỗi pod không đổi.

### 8.3. Timeout và lifetime

Các tham số Hikari thường cần cân nhắc:

- `connection-timeout`: thời gian chờ mượn connection từ pool.
- `validation-timeout`: thời gian kiểm tra connection.
- `idle-timeout`: thời gian connection nhàn rỗi có thể bị loại.
- `max-lifetime`: tuổi tối đa connection trước khi pool thay thế.
- `keepalive-time`: có thể dùng trong một số môi trường để giữ connection nhàn rỗi khỏi bị network đóng.

Không đặt `max-lifetime` quá thấp gây churn liên tục, hoặc quá dài nếu network/database có timeout ngắn hơn. Kiểm tra tài liệu HikariCP, Cloud SQL limits và cấu hình hạ tầng thực tế.

### 8.4. Query latency và pool saturation

Nếu request chậm, không mặc định lỗi do Cloud SQL Connector. Kiểm tra:

1. Thời gian chờ lấy connection từ HikariCP.
2. Thời gian thiết lập connection mới.
3. Query execution time và lock wait.
4. Số connection active/idle/pending.
5. CPU, memory, storage IOPS và connection count của Cloud SQL.
6. Network latency giữa workload và instance.

Pool đầy có thể là triệu chứng query chậm hoặc transaction giữ connection quá lâu, không nhất thiết là pool quá nhỏ. Tăng pool khi database đã quá tải có thể làm tình hình tệ hơn.

## 9. Transaction, retry và HA/failover

### 9.1. Transaction boundary

Spring Boot dùng transaction manager của JDBC/JPA như bình thường:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRepositoryService {
    private final JdbcTemplate jdbc;

    public OrderRepositoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(String orderId, long amount) {
        jdbc.update(
                "insert into orders(id, amount, status) values (?, ?, ?)",
                orderId, amount, "PENDING");

        jdbc.update(
                "insert into order_audit(order_id, action) values (?, ?)",
                orderId, "CREATED");
    }
}
~~~

Connector không thay đổi semantics transaction của PostgreSQL/MySQL. Các câu lệnh trong cùng transaction vẫn tuân thủ isolation level, lock và commit/rollback của database engine.

### 9.2. Retry phải xét tính idempotent

Lỗi mạng có thể xảy ra khi:

- Lấy connection từ pool.
- Đang chạy query.
- Đang commit transaction.
- Cloud SQL failover hoặc bảo trì.
- Connector refresh metadata/credentials.

Nếu lỗi xảy ra **sau khi server đã commit nhưng trước khi client nhận response**, client không biết transaction đã thành công hay chưa. Retry mù một lệnh INSERT/charge/payment có thể tạo duplicate.

Thiết kế an toàn:

- Dùng idempotency key/unique constraint cho thao tác nghiệp vụ.
- Retry ở ranh giới transaction với policy giới hạn và backoff.
- Chỉ retry lỗi transient được phân loại rõ.
- Không retry vô hạn hoặc retry mọi SQL exception.
- Với thao tác ghi tiền/đơn hàng, truy vấn trạng thái theo idempotency key trước khi thực hiện lại.

### 9.3. High Availability và failover

Cloud SQL HA có thể chuyển sang standby khi có sự cố theo cấu hình instance. Instance connection name thường vẫn là định danh kết nối logic, nhưng connection đang mở có thể bị ngắt trong quá trình failover.

Ứng dụng cần:

- Cho Hikari loại bỏ connection hỏng và tạo connection mới.
- Có timeout hợp lý để request không chờ vô hạn.
- Retry thao tác an toàn ở tầng nghiệp vụ.
- Theo dõi lỗi kết nối và thời gian phục hồi.
- Kiểm thử failover trong môi trường test/maintenance window phù hợp, không cố tình gây sự cố production.

Cloud SQL HA giảm downtime nhưng **không bảo đảm mọi transaction đang chạy đều được tiếp tục** hoặc client không bao giờ nhận exception.

## 10. Migration schema và quyền database

Dùng Flyway/Liquibase để quản lý schema theo phiên bản. Không chạy migration DDL nặng ở mọi replica khi ứng dụng khởi động nếu deployment có nhiều instance đồng thời; nên có migration job hoặc pipeline triển khai riêng.

Tách database principal:

- `orders_migrator`: quyền DDL cần cho migration.
- `orders_app`: quyền DML tối thiểu cho runtime.
- `orders_readonly`: chỉ đọc nếu có use case báo cáo.

Ví dụ PostgreSQL cấp quyền cơ bản (điều chỉnh schema/role theo môi trường):

~~~sql
CREATE ROLE orders_app LOGIN;
GRANT CONNECT ON DATABASE orders TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public TO orders_app;
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public TO orders_app;
~~~

Ví dụ này chưa cấu hình password và default privileges cho bảng tạo trong tương lai; cần quản lý credentials qua secret manager và cấp quyền phù hợp cho object mới. Không dùng superuser làm runtime account.

## 11. Kiểm thử Cloud SQL connection

### 11.1. Unit test và integration test

| Mức | Mục tiêu | Giới hạn |
| --- | --- | --- |
| Unit test | Test service/repository logic bằng mock hoặc Testcontainers DB cục bộ | Không xác minh IAM, Connector hay Cloud SQL network |
| Local integration | Test JDBC driver, SQL schema và transaction với PostgreSQL/MySQL local | Không kiểm tra quyền Google Cloud |
| Cloud integration | Test ADC, IAM, Java Connector, IP type, TLS và DB user trên instance sandbox | Cần project/instance test và cleanup |
| Resilience test | Test connection reset, restart/failover có kiểm soát, pool recovery | Không chạy destructive test trên production |

### 11.2. Kịch bản thực hành

1. Tạo Cloud SQL PostgreSQL instance trong project sandbox.
2. Bật Cloud SQL Admin API và xác định instance connection name.
3. Tạo database `orders` và user `orders_app`.
4. Cấp `roles/cloudsql.client` cho service account chạy ứng dụng.
5. Nếu chọn Private IP, cấu hình VPC connectivity cho workload trước khi đặt `ipTypes=PRIVATE`.
6. Thêm PostgreSQL JDBC driver và PostgreSQL Socket Factory dependency.
7. Cấu hình JDBC URL, ADC, username/password database và Hikari pool nhỏ.
8. Khởi chạy Spring Boot, thực hiện query đơn giản và transaction mẫu.
9. Kiểm tra log/metric khi sai instance name, thiếu IAM role, sai DB password, thiếu network route hoặc thiếu quyền SQL.
10. Thử IAM DB authentication trong sandbox nếu engine/instance đã bật và user IAM được tạo đúng.
11. Kiểm tra connection pool khi tải đồng thời và so sánh active/idle/pending.
12. Thử restart instance hoặc failover trong môi trường được phép, xác minh app phục hồi và thao tác ghi có idempotency.

### 11.3. Ví dụ kiểm tra kết nối bằng JdbcTemplate

~~~java
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class DatabaseHealthService {
    private final JdbcTemplate jdbc;

    public DatabaseHealthService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Map<String, Object> check() {
        return jdbc.queryForMap(
                "select current_database() as database_name, current_user as database_user");
    }
}
~~~

Health check không nên thực hiện query nặng hoặc gọi liên tục với tần suất cao. Có thể phân biệt liveness và readiness: liveness kiểm tra process còn hoạt động; readiness kiểm tra khả năng phục vụ request cần database theo chính sách ứng dụng.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `403 PERMISSION_DENIED` hoặc connector không được phép kết nối | Thiếu Cloud SQL Client role, API chưa bật, ADC sai principal | Kiểm tra project, API, IAM binding và credentials ADC |
| `could not connect` / timeout với Private IP | Workload không có route VPC hoặc firewall chặn | Kiểm VPC egress, Direct VPC egress/connector, IP type và route |
| Database authentication failed | DB user/password sai hoặc IAM DB auth chưa cấu hình | Kiểm database user, secret và `enableIamAuth` |
| `ClassNotFoundException` Socket Factory | Thiếu dependency hoặc class name sai engine | Kiểm `postgres-socket-factory`/`mysql-socket-factory` và URL |
| `No suitable driver` | Thiếu JDBC driver hoặc URL prefix sai | Kiểm `org.postgresql.Driver`/MySQL driver và JDBC URL |
| Instance connection name invalid | Sai project/region/instance hoặc typo | Kiểm định danh `project:region:instance` |
| Kết nối chập chờn sau idle | Network timeout, pool lifetime hoặc instance maintenance | Kiểm Hikari lifetime/keepalive và connector logs |
| Hikari pool timeout | Pool cạn, query chậm, transaction giữ connection lâu | Kiểm active/pending, query latency, lock và pool size |
| SQL query bị từ chối sau khi kết nối thành công | Database grants/schema privileges thiếu | Kiểm quyền SQL; IAM kết nối không cấp quyền bảng |
| Lỗi sau failover | Connection cũ bị ngắt, transaction không hoàn tất | Cho pool loại connection hỏng, retry an toàn và kiểm trạng thái |

Khi điều tra, ghi SQLState, mã lỗi, instance alias, request/correlation ID và thời gian; không ghi password, service account key, token hoặc toàn bộ connection string có secret.

## 13. So sánh với RDS/Azure Database và kiến trúc đa cloud

Các cloud provider đều cung cấp managed relational database nhưng cơ chế kết nối và identity khác nhau:

| Khía cạnh | Google Cloud SQL | AWS RDS/Aurora | Azure Database |
| --- | --- | --- | --- |
| JDBC driver | PostgreSQL/MySQL/SQL Server JDBC | Driver theo engine | Driver theo engine |
| Kết nối được quản lý | Cloud SQL Java Connector/Auth Proxy | RDS CA/TLS, IAM DB auth tùy engine, RDS Proxy | TLS, Azure identity/auth tùy dịch vụ/engine |
| Workload identity | Google service account/ADC | IAM role | Managed identity/service principal |
| Private networking | VPC, Private IP, PSC theo kiến trúc | VPC/subnet/security group | VNet/private endpoint |
| Connection pooling | HikariCP hoặc pool tương ứng | HikariCP/RDS Proxy | HikariCP hoặc proxy/service tương ứng |
| Database authorization | DB user/roles hoặc IAM DB auth | DB user/roles hoặc IAM DB auth khi hỗ trợ | DB user/roles hoặc Entra authentication khi hỗ trợ |

Tầng repository/service nghiệp vụ có thể dùng chung JDBC, Spring Data JPA, JdbcTemplate và transaction abstraction. Phần **connection bootstrap, identity, network, secret, failover và proxy** cần adapter/cấu hình theo provider.

Không nên tạo một JDBC URL đa cloud bằng cách ghép tham số AWS, Google và Azure vào cùng chuỗi. Tách profile/secret/configuration theo provider và dùng migration/query SQL tương thích với engine thực tế.

## 14. Bài tập thực hành

### Bài A — Kết nối Cloud SQL bằng password authentication

Tạo Cloud SQL PostgreSQL instance sandbox, database `orders`, DB user riêng. Thêm JDBC driver và Cloud SQL PostgreSQL Socket Factory, cấu hình ADC cùng `roles/cloudsql.client`, sau đó chạy Spring Boot và truy vấn `select current_database()`.

### Bài B — Chọn Private IP

Cấu hình Cloud SQL Private IP và workload có VPC connectivity. Đặt `ipTypes=PRIVATE`, chạy ứng dụng và kiểm tra route. Thử bỏ cấu hình VPC trong môi trường test để quan sát lỗi network, sau đó giải thích vì sao connector không tự tạo route.

### Bài C — IAM database authentication

Bật IAM database authentication trên instance test, tạo IAM database user và cấp role phù hợp cho service account. Bật `enableIamAuth=true`, kiểm tra kết nối và quyền SQL. Phân biệt lỗi IAM kết nối với lỗi database grant.

### Bài D — So sánh Java Connector và Auth Proxy

Chạy cùng một ứng dụng theo hai cấu hình: JDBC Socket Factory trong process và JDBC tới localhost thông qua Auth Proxy. So sánh cách cấp credentials, port, log, health check và vận hành sidecar.

### Bài E — Tính connection pool

Với 8 replica, mỗi replica tối đa 10 connection, 2 worker và 1 migration job, hãy tính tổng connection tối đa. So sánh với giới hạn Cloud SQL và đề xuất pool size có headroom.

### Bài F — Kiểm thử retry an toàn

Tạo một thao tác ghi có idempotency key. Giả lập mất kết nối quanh thời điểm commit và kiểm tra retry không tạo bản ghi trùng. Giải thích vì sao không thể retry mọi exception một cách mù quáng.

### Câu hỏi tự kiểm tra

1. Instance connection name có cấu trúc như thế nào và khác database name ra sao?
2. Cloud SQL Java Connector có thay thế JDBC driver hoặc HikariCP không?
3. `roles/cloudsql.client` cho phép điều gì? Có cấp quyền SELECT bảng không?
4. Vì sao IAM principal và database user là hai danh tính khác nhau?
5. JDBC URL PostgreSQL cần những tham số nào để dùng Socket Factory?
6. `ipTypes=PRIVATE` có tự tạo đường mạng VPC cho Cloud Run không?
7. Java Connector và Cloud SQL Auth Proxy khác nhau ở vị trí chạy và cách ứng dụng kết nối như thế nào?
8. Khi nào cần `roles/cloudsql.instanceUser` và `enableIamAuth=true`?
9. Vì sao connection pool size phải tính trên tổng số replica?
10. Điều gì có thể xảy ra nếu connection bị ngắt ngay sau khi database commit?
11. Vì sao không nên retry mọi thao tác ghi sau lỗi mạng?
12. Database user runtime nên được cấp quyền SQL như thế nào?
13. Khi Cloud SQL HA failover, connection đang mở có được bảo đảm không gián đoạn không?
14. Những thành phần nào trong Spring Boot có thể dùng chung giữa Cloud SQL, RDS và Azure Database, thành phần nào cần cấu hình riêng?

**Kết quả mong đợi:** người học cấu hình được Spring Boot kết nối Cloud SQL bằng JDBC và Cloud SQL Java Connector, phân biệt IAM của workload với quyền database, lựa chọn Public/Private IP đúng kiến trúc, vận hành HikariCP hợp lý, xử lý retry/failover an toàn và đánh giá cách tích hợp managed relational database giữa các cloud provider.

