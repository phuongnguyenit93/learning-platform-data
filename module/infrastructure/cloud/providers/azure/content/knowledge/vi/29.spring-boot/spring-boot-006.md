# Truy cập Azure SQL và PostgreSQL bằng Spring Data

Một ứng dụng quản lý kho được phát triển bằng **Spring Boot** cần lưu danh mục sản phẩm, giá bán và lịch sử cập nhật. Đội phát triển có hai môi trường khách hàng: hệ thống A dùng **Azure SQL Database** vì đã chuẩn hóa SQL Server; hệ thống B dùng **Azure Database for PostgreSQL – Flexible Server** do tận dụng hệ sinh thái PostgreSQL. Họ muốn dùng cùng mô hình domain và repository của Spring Data, đồng thời triển khai lên **Azure App Service**, **Azure Container Apps** hoặc **AKS** mà không gắn mật khẩu database vào mã nguồn.

Vấn đề không chỉ là đổi JDBC URL. Hai hệ quản trị có **kiểu dữ liệu, cú pháp SQL, cơ chế tạo khóa, isolation/locking, driver, authentication, TLS, backup và mô hình mạng** khác nhau. Nếu chỉ thử với H2 rồi đổi profile ở production, ứng dụng có thể lỗi khi tạo schema, chạy migration hoặc xử lý transaction đồng thời.

Bài học **“Truy cập Azure SQL và PostgreSQL bằng Spring Data”** thuộc chương **Spring Boot trên Azure** của module **CLOUD_PROVIDERS_AZURE**. Nội dung kết nối kiến thức về subscription/resource group, Microsoft Entra ID, mạng ảo, tính toán, lưu trữ và dữ liệu với thực hành triển khai, giám sát, bảo vệ và kiểm soát chi phí một ứng dụng Spring Boot trên Azure.

Sau bài học, bạn sẽ:

- Phân biệt **Azure SQL Database** và **Azure Database for PostgreSQL Flexible Server**, chọn dịch vụ phù hợp.
- Hiểu chuỗi **Spring MVC → Service → Spring Data Repository → JPA/Hibernate/JDBC → HikariCP → Azure database**.
- Cấu hình **một ứng dụng** chạy với **hai Spring profiles**, không trộn dialect hoặc migrations.
- Thiết kế entity/repository/service/REST API với **Spring Data JPA**, validation và transaction.
- Quản lý schema bằng **Flyway**, với migration SQL Server và PostgreSQL riêng.
- Thiết kế kết nối an toàn bằng **TLS, database firewall, Private Endpoint/VNet và Microsoft Entra ID/managed identity**.
- Phân biệt Entra authentication của **JDBC SQL Server** với **token dưới dạng password JDBC cho PostgreSQL**.
- Tối ưu HikariCP, indexes, pagination, optimistic locking, retry và transactions.
- Kiểm thử tích hợp cho cả hai engine, phân tích lỗi, monitor và dự toán chi phí.

> **Phạm vi:** Ví dụ dùng Java 21, Spring Boot 3.x, Spring Data JPA/Hibernate và JDBC drivers phù hợp. Một số phiên bản đã được phát hành sau ví dụ có thể thay đổi API; khi áp dụng thực tế, chọn phiên bản Spring Boot/driver/Flyway còn được hỗ trợ, kiểm tra compatibility matrix và khóa dependency trong build. Không có tài nguyên Azure thật nào được tạo trong quá trình soạn bài.

## 1. Bức tranh tổng thể: Spring Data là gì và không phải gì?

**Spring Data** cung cấp các abstraction để truy cập dữ liệu: repository interfaces, method-name query derivation, paging/sorting và tích hợp transaction. Với quan hệ, hai hướng phổ biến là:

- **Spring Data JPA**: dùng Jakarta Persistence và Hibernate ORM, quản lý entities, relationships và unit of work.
- **Spring Data JDBC**: repository nhẹ, aggregate-centric, SQL rõ ràng hơn, không có JPA persistence context/lazy loading.

Cả hai đều chạy qua **JDBC DataSource** và driver đúng database. **Spring Data không biến hai hệ SQL Server và PostgreSQL thành cùng một engine**: native SQL, stored procedures, JSON types, locking hints và DDL vẫn có khác biệt.

~~~mermaid
flowchart LR
    CLIENT[Web / Mobile] --> API[Spring MVC REST Controller]
    API --> SERVICE[Transactional service]
    SERVICE --> REPO[Spring Data JPA repository]
    REPO --> ORM[Hibernate ORM]
    ORM --> POOL[HikariCP DataSource]
    POOL --> DRIVER{JDBC driver + Spring profile}
    DRIVER -->|sqlserver| MSSQL[(Azure SQL Database)]
    DRIVER -->|postgres| PG[(Azure PostgreSQL Flexible Server)]
    MI[Managed identity / Entra] -. Auth .-> DRIVER
    NET[VNet / Private DNS / TLS] -. Connection path .-> DRIVER
    MON[Azure Monitor / App Insights] -. Metrics and traces .-> SERVICE
~~~

### 1.1. Vai trò mỗi lớp

| Lớp | Trách nhiệm | Lỗi thường gặp |
|---|---|---|
| **Controller** | HTTP contract, validate input, map status/response | Trả entity chứa field nhạy cảm trực tiếp |
| **Service** | Business rules và transaction boundary | Gọi external API trong transaction dài |
| **Repository** | Query/paging/update aggregates | N+1, native SQL phụ thuộc vendor |
| **JPA/Hibernate** | Mapping entity ↔ table, dirty checking, optimistic lock | Để `ddl-auto=update` tự chỉnh schema production |
| **DataSource/HikariCP** | Quản lý JDBC connections và pool | Pool quá lớn, leaked connections |
| **JDBC Driver** | Protocol, TLS, auth, datatype conversions | Sai driver/port/certificate settings |
| **Azure database** | Persist/transactions/indexes/backup | Throttle, deadlock, network hoặc thiếu quyền |

### 1.2. Một codebase, hai cấu hình, không phải hai database cùng lúc

Bài này dùng **một active profile tại một thời điểm**:

~~~text
SPRING_PROFILES_ACTIVE=sqlserver  → Azure SQL Database
SPRING_PROFILES_ACTIVE=postgres   → Azure PostgreSQL Flexible Server
~~~

Điều đó khác hoàn toàn ứng dụng **multi-datasource** đồng thời kết nối cả hai DB. Multi-datasource cần hai DataSources, entity manager/repository packages, transaction managers và xử lý distributed consistency rõ ràng; **một `@Transactional` thông thường không tạo transaction ACID trải cả hai database**.

### 1.3. Source of truth

Azure SQL/PostgreSQL là nơi lưu dữ liệu nghiệp vụ có transaction. Nếu sau này thêm **Azure Managed Redis** làm cache, Redis phải giữ dữ liệu có thể dựng lại, có TTL/invalidation. Nếu thêm **Service Bus** để xử lý bất đồng bộ, commit DB và publish message cần outbox/idempotency khi yêu cầu nhất quán; không mặc định một HTTP request quản lý được atomic transaction giữa DB và broker.

## 2. Chọn Azure SQL Database hay Azure Database for PostgreSQL?

### 2.1. So sánh công nghệ

| Tiêu chí | Azure SQL Database | Azure Database for PostgreSQL Flexible Server |
|---|---|---|
| Engine | Microsoft SQL Server-compatible, T-SQL | PostgreSQL, SQL/PLpgSQL |
| JDBC driver | `com.microsoft.sqlserver:mssql-jdbc` | `org.postgresql:postgresql` |
| JDBC URL | `jdbc:sqlserver://...:1433;databaseName=...` | `jdbc:postgresql://...:5432/...` |
| ID auto increment | `IDENTITY(1,1)` | `GENERATED ... AS IDENTITY` |
| JSON features | SQL Server JSON functions/features theo engine/version | `json`/`jsonb`, operators/indexes |
| Upsert | T-SQL patterns, `MERGE` cần đánh giá concurrency | `INSERT ... ON CONFLICT` |
| Locking/isolation | SQL Server locking + row versioning theo cấu hình | PostgreSQL MVCC và isolation levels |
| Query tuning | Actual execution plan, Query Store, DMVs | `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements` |
| Authentication | SQL login hoặc Microsoft Entra via JDBC driver | PostgreSQL password hoặc Microsoft Entra token/role |
| Networking | Azure SQL logical server firewall/Private Endpoint | Flexible Server public/private networking models, DNS |
| Availability | Azure SQL HA/geo features theo tier | Flexible Server HA/backup/PITR theo configuration |

**Không coi “SQL Server” và “Azure SQL Database” là đồng nhất mọi tính năng**: Azure SQL Database là PaaS database với giới hạn service và compute tiers; không phải một Windows SQL Server instance cho phép mọi server-level operation.

### 2.2. Khi nào ưu tiên từng dịch vụ?

**Azure SQL Database** phù hợp khi tổ chức có T-SQL tooling, hệ thống Microsoft SQL hiện hữu, SQL Server-specific features được hỗ trợ trên Azure SQL và muốn dịch vụ managed có nhiều tùy chọn compute.

**PostgreSQL Flexible Server** phù hợp khi nhóm sử dụng PostgreSQL extensions/SQL, cần PostgreSQL compatibility hoặc ecosystem Java/PostgreSQL quen thuộc. Phải kiểm tra extension/version được Azure hỗ trợ thay vì giả định mọi Postgres extension đều có thể cài tùy ý.

Quyết định phải dựa trên **queries/indexes, transaction behavior, data model, SLA/backup, vùng hỗ trợ, network và tổng chi phí**, không chỉ tên database.

### 2.3. Hai cách kết nối mạng phổ biến

~~~mermaid
flowchart LR
    APP[App Service/AKS/Container Apps] --> VNET[Outbound VNet path]
    VNET --> DNS[Private DNS resolver]
    DNS --> PE[Private Endpoint or private VNet route]
    PE --> DB[(Azure managed database)]
    APP -. TLS + DB credentials .-> DB
    PUBLIC[Public Internet client] -. Blocked per policy .-> DB
~~~

Với Azure SQL Database, **Private Endpoint** đưa đường vào resource qua private IP, nhưng không tự có nghĩa `publicNetworkAccess` đã bị disable. Với PostgreSQL Flexible Server, cần phân biệt **Private access/VNet-injected server** và **Private Endpoint trong networking mode được hỗ trợ**: đây là hai kiến trúc, không tùy tiện chuyển đổi bằng một checkbox. Trong cả hai trường hợp, dùng **FQDN server chuẩn**, DNS phù hợp và TLS hostname verification; không hardcode private IP vào JDBC URL.

## 3. Điều kiện chuẩn bị và quyền Azure

### 3.1. Môi trường ứng dụng

- Java 21 hoặc Java LTS được Spring Boot version lựa chọn hỗ trợ.
- Maven 3.9+ hoặc Gradle phù hợp; source control và CI pipeline.
- Spring Boot + Spring Data JPA + JDBC drivers.
- Azure subscription/resource group **lab riêng có quyền**, không dùng DB production.
- Một database schema trống trên Azure SQL **hoặc** PostgreSQL Flexible Server, quyền chạy migrations.
- Kết nối mạng từ máy phát triển/runner **tới đúng Azure endpoint** (private hoặc public theo policy).
- Microsoft Entra identities/SQL/PG roles hoặc lab credentials **được cấp phép**.
- Azure Monitor/Application Insights/DB metrics nếu muốn đo hiệu năng thực.

**Nếu chưa được cấp Azure resources**, vẫn học entity, repository và query patterns trong bài; không tự tạo database bằng tài khoản ngoài quyền hoặc hạ firewall production để thử.

### 3.2. Quyền quản trị ≠ quyền dữ liệu

| Quyền | Tác dụng | Không mặc nhiên có |
|---|---|---|
| Azure RBAC Contributor | Tạo/chỉnh resource trong phạm vi được cấp | SQL `SELECT`/`INSERT` trên bảng |
| Azure SQL Entra admin | Bootstrap Entra principals/db authorization | Quyền mọi hệ thống ngoài scope DB |
| PostgreSQL server admin/Entra admin | Tạo roles/cấp grants theo mô hình | Azure subscription Owner |
| App database role | Truy vấn/mutate các bảng được grant | Tạo firewall/private endpoint |
| Migration role | Tạo/alter schema theo pipeline | Không nên là runtime app role |

Khuyến nghị tách **app runtime principal** và **migration/DBA principal**. App thường chỉ cần `SELECT/INSERT/UPDATE/DELETE` trên bảng nghiệp vụ, không cần `db_owner`/superuser hay quyền thay schema.

## 4. Spring Boot dependencies và tổ chức project

### 4.1. Maven `pom.xml` tham khảo

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>vn.demo.azure</groupId>
  <artifactId>spring-data-azure-demo</artifactId>
  <version>1.0.0</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>21</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-sqlserver</artifactId>
    </dependency>
    <dependency>
      <groupId>com.microsoft.sqlserver</groupId>
      <artifactId>mssql-jdbc</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Phiên bản `3.5.7` chỉ là baseline minh họa đã khóa** để biểu diễn cấu trúc Maven. Trước khi triển khai hãy kiểm tra Spring Boot, Flyway, PostgreSQL driver và Microsoft JDBC driver với dependency management/BOM và bản vá bảo mật mới nhất trong tổ chức. Một số phiên bản Flyway có thể đóng gói database support khác; xác minh artifact `flyway-sqlserver`/`flyway-database-postgresql` đúng version được quản lý. Không thêm cùng lúc Spring Data JDBC starter chỉ vì ứng dụng đã dùng Spring Data JPA; chúng là hai abstraction khác nhau và cần quyết định rõ.

### 4.2. Cấu trúc source minh họa

~~~text
spring-data-azure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/demo/azure/
    │   │   ├── Application.java
    │   │   ├── catalog/Product.java
    │   │   ├── catalog/ProductRepository.java
    │   │   ├── catalog/ProductService.java
    │   │   ├── catalog/ProductController.java
    │   │   └── catalog/ApiExceptionHandler.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-sqlserver.yml
    │       ├── application-postgres.yml
    │       └── db/migration/
    │           ├── sqlserver/V1__create_products.sql
    │           └── postgres/V1__create_products.sql
    └── test/
        └── java/vn/demo/azure/...
~~~

Đây là **cấu trúc để người học tạo trong project riêng**, không phải yêu cầu ghi thêm file trong workspace STEP 4. Bài này chỉ cập nhật Markdown được giao và field `status` trong YAML tương ứng.

### 4.3. Entry point

~~~java
package vn.demo.azure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Đặt entry point ở package gốc `vn.demo.azure` để Spring Boot scan `catalog` components/entities. Nếu đặt repositories ở ngoài cây package, cần cấu hình scan rõ ràng; không giải quyết bằng cách thêm `@ComponentScan("**")` rộng vô hạn.

## 5. Hai Spring profiles: SQL Server và PostgreSQL

### 5.1. Cấu hình dùng chung `application.yml`

~~~yaml
spring:
  application:
    name: spring-data-azure-demo
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
  flyway:
    enabled: true
    baseline-on-migrate: false
  datasource:
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 2000
      idle-timeout: 300000
      max-lifetime: 1200000

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      probes:
        enabled: true
~~~

**Ý nghĩa:** `ddl-auto=validate` yêu cầu entity mapping phù hợp schema đã tạo bằng Flyway; nó không tự tạo/sửa production tables. `open-in-view=false` buộc service layer xử lý lazy associations đúng transaction, tránh giữ DB session sang thời điểm serialize HTTP response.

**Chú ý:** Hikari timeouts tính theo **milliseconds**. `maximum-pool-size=10` là baseline minh họa, không phải giá trị tối ưu cho mọi tier hoặc số replicas. Khi dùng Flyway trong cùng ứng dụng, runtime principal phải có quyền DDL migrations; production nên tách pipeline migration hoặc cấp quyền riêng có kiểm soát.

### 5.2. Profile Azure SQL `application-sqlserver.yml`

~~~yaml
spring:
  datasource:
    url: ${AZURE_SQL_JDBC_URL}
    username: ${AZURE_SQL_USER}
    password: ${AZURE_SQL_PASSWORD}
    driver-class-name: com.microsoft.sqlserver.jdbc.SQLServerDriver
  flyway:
    locations: classpath:db/migration/sqlserver
  jpa:
    database-platform: org.hibernate.dialect.SQLServerDialect
~~~

Ví dụ **JDBC URL** (không chứa credentials):

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;loginTimeout=30;
~~~

`encrypt=true` bảo vệ kênh truyền; `trustServerCertificate=false` yêu cầu kiểm tra certificate. Không đặt `encrypt=false` hoặc `trustServerCertificate=true` để chữa lỗi DNS/TLS trên production. Với Private Endpoint vẫn dùng **server FQDN chuẩn `*.database.windows.net`**, không dùng private IP.

### 5.3. Profile PostgreSQL `application-postgres.yml`

~~~yaml
spring:
  datasource:
    url: ${AZURE_PG_JDBC_URL}
    username: ${AZURE_PG_USER}
    password: ${AZURE_PG_PASSWORD}
    driver-class-name: org.postgresql.Driver
  flyway:
    locations: classpath:db/migration/postgres
  jpa:
    database-platform: org.hibernate.dialect.PostgreSQLDialect
~~~

Ví dụ URL với **TLS hostname validation**:

~~~text
jdbc:postgresql://my-pg-server.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory
~~~

`sslmode=verify-full` đòi certificate chain và hostname hợp lệ. `DefaultJavaSSLFactory` sử dụng Java trust configuration; cần bảo đảm đúng root/intermediate CA nằm trong JVM trust store phù hợp với PostgreSQL JDBC driver/version. Ở môi trường dùng `sslrootcert`/SSL factory khác, cấu hình theo hướng dẫn driver; **không dùng `sslmode=disable` hoặc `require` thay verify-full** nếu chính sách yêu cầu xác minh server identity.

PostgreSQL Flexible Server thường dùng username **database role** được cấp, không sao chép quy tắc `user@server` từ các hướng dẫn Azure Database for PostgreSQL Single Server cũ mà không kiểm chứng.

### 5.4. Biến môi trường cho lab

~~~bash
export SPRING_PROFILES_ACTIVE=postgres
export AZURE_PG_JDBC_URL="jdbc:postgresql://<pg-server>.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory"
export AZURE_PG_USER="<app-db-user>"

# Lấy mật khẩu từ secret store của lab, không commit vào Git.
# Dùng shell prompt hoặc secret injection của môi trường.

./mvnw spring-boot:run
~~~

**Đừng copy username/password/token vào shell history hoặc log build**. Ví dụ `./mvnw` chỉ hoạt động khi project người học đã có Maven wrapper; nếu không, dùng Maven đã cài từ nguồn tin cậy. Thông thường cần đặt `AZURE_PG_PASSWORD` qua secret injection có kiểm soát; để trống mà chưa có cơ chế Entra auth sẽ không kết nối được.

### 5.5. Không lẫn credentials giữa profiles

| Lỗi | Hậu quả |
|---|---|
| `SPRING_PROFILES_ACTIVE` không có | Không có `spring.datasource.url`, app fail startup |
| Chọn `sqlserver` nhưng JDBC URL PostgreSQL | Driver/dialect sai, connection fail |
| Dùng migration SQL Server cho PostgreSQL | `IDENTITY`/datatype/cú pháp DDL lỗi |
| Copy SQL password vào `application.yml` | Secret leak vào Git/image |
| Bật cả `sqlserver,postgres` | Properties đè nhau không dự đoán như mong muốn |
| Dùng `spring.jpa.hibernate.ddl-auto=update` trên production | Schema drift và mất kiểm soát migration |

**Nguyên tắc:** một deployment → một vendor profile → một DataSource/dialect → một tập migrations. Nếu cần hai DataSources đồng thời, đó là bài toán kiến trúc khác và phải cấu hình riêng.

## 6. Quản lý schema bằng Flyway: hai migrations, một domain

### 6.1. Vì sao không để Hibernate tự tạo bảng?

JPA/Hibernate có thể tạo schema trong lab, nhưng **production schema là hợp đồng lâu dài**: phải review trước khi đổi cột, index, constraint hoặc datatype. Với nhiều replicas, nếu mọi instance cố tự thay schema lúc startup có thể xảy ra race, drift và downtime.

Khuyến nghị:

1. Migration scripts nằm trong source control.
2. Có version cố định và code review.
3. Test trên **đúng database engine/version** (SQL Server và PostgreSQL).
4. Triển khai theo thứ tự **expand → migrate data → switch code → contract** cho thay đổi không tương thích.
5. App chạy với `ddl-auto=validate`, không phụ thuộc `update`/`create-drop`.
6. Migration principal có quyền DDL tách khỏi runtime principal.
7. Có backup/restore/rollback hoặc forward-fix plan trước DDL phá hủy.

### 6.2. Migration SQL Server

File `src/main/resources/db/migration/sqlserver/V1__create_products.sql`:

~~~sql
CREATE TABLE dbo.products (
    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name NVARCHAR(160) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    version BIGINT NOT NULL
        CONSTRAINT DF_products_version DEFAULT (0),
    updated_at_utc DATETIME2(6) NOT NULL
);

CREATE UNIQUE INDEX UX_products_sku ON dbo.products (sku);
~~~

Các điểm riêng của SQL Server:

- `IDENTITY(1,1)` tạo khóa số tăng dần.
- `NVARCHAR` lưu Unicode trong tên sản phẩm; các kiểu `VARCHAR` cần cân nhắc collation/UTF-8 support nếu chứa Unicode.
- `DATETIME2(6)` **không mang timezone**; ứng dụng quy ước lưu UTC.
- Index unique cho `sku` bảo đảm uniqueness ở **database**, không chỉ kiểm tra tại service.
- `dbo` là schema mặc định thường thấy; nếu database role có default schema khác, cần định nghĩa schema/mapping rõ.

### 6.3. Migration PostgreSQL

File `src/main/resources/db/migration/postgres/V1__create_products.sql`:

~~~sql
CREATE TABLE public.products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at_utc TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL,
    CONSTRAINT uq_products_sku UNIQUE (sku)
);
~~~

Các điểm riêng:

- `GENERATED BY DEFAULT AS IDENTITY` là identity column trong PostgreSQL hiện đại.
- PostgreSQL `VARCHAR` hỗ trợ Unicode theo encoding/collation của database (thường UTF-8).
- `NUMERIC(12,2)` là số thập phân chính xác tương ứng `BigDecimal`.
- `TIMESTAMP WITHOUT TIME ZONE` yêu cầu **quy ước UTC**; DB không gắn timezone vào giá trị.
- `public` là schema mặc định thường gặp; roles cần USAGE/GRANT thích hợp.

**Không chạy SQL Server migration trong PostgreSQL:** `IDENTITY(1,1)`, `NVARCHAR` và `DATETIME2` không có semantics DDL giống nhau. Ngược lại `GENERATED ... AS IDENTITY`/`public` không thay thế `dbo` trong SQL Server.

### 6.4. Hibernate mapping phải được kiểm chứng

Với SQL Server, entity sẽ dùng `@Nationalized` cho `name` để thể hiện ý định Unicode `NVARCHAR`. Với PostgreSQL, Hibernate dialect xử lý chuỗi Unicode theo kiểu hỗ trợ. Đây là ví dụ **cần integration test schema validation cho cả hai dialect**; không suy rằng mọi ORM version map nationalized string giống nhau.

Nếu Flyway báo lỗi khi driver/DB không nhận migration, kiểm tra:

- Active profile và `spring.flyway.locations`.
- Driver/Flyway database module version compatibility.
- Kết nối, role DDL, target schema (dbo/public), table tồn tại.
- Flyway schema history có migration cũ/chưa hoàn thành không.
- Cấu trúc tên `V1__...sql` có **hai dấu gạch dưới** theo convention.

**Không bật `baseline-on-migrate=true` bừa để bỏ qua lỗi trên database đã có bảng**. Một database production có dữ liệu cần kế hoạch baseline có kiểm soát và xác nhận migration history.

### 6.5. Schema change tương thích ngược

Ví dụ thêm cột `currency`:

~~~text
Phase 1 (expand):
  Add nullable column; keep old readers/writers working.

Phase 2 (migrate):
  Backfill existing rows in controlled batches.

Phase 3 (switch):
  Deploy code supporting both old/new field representation.

Phase 4 (contract):
  Add NOT NULL/constraints, remove deprecated fields after validation.
~~~

Đổi SQL Server và PostgreSQL theo **hai migration scripts** cùng version logic nhưng DDL riêng. Không phát hành code JPA đòi cột chưa được migrate trên production. Với app đa replicas, tương thích ngược giúp tránh lỗi trong rolling deployment.

## 7. Entity JPA: ánh xạ Product cho cả hai cơ sở dữ liệu

### 7.1. Class `Product.java`

~~~java
package vn.demo.azure.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.Nationalized;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 64, unique = true)
    private String sku;

    @Nationalized
    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @Column(name = "updated_at_utc", nullable = false)
    private LocalDateTime updatedAtUtc;

    protected Product() { } // Required by JPA.

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    @PrePersist
    @PreUpdate
    void touchUtc() {
        this.updatedAtUtc = LocalDateTime.now(ZoneOffset.UTC);
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Long getVersion() { return version; }
    public LocalDateTime getUpdatedAtUtc() { return updatedAtUtc; }
}
~~~

**Điểm thiết kế quan trọng:**

- `@Entity` dùng cùng model Java dù persistence là Azure SQL hay PostgreSQL.
- `GenerationType.IDENTITY` khớp SQL Server identity và PostgreSQL identity DDL, nhưng có thể giới hạn JDBC insert batching.
- `BigDecimal` cho tiền, **không dùng `double`** để cộng trừ giá trị tiền.
- `@Version` dùng **optimistic locking**: hai transactions sửa cùng row có thể khiến một transaction bị từ chối thay vì ghi đè không phát hiện.
- `@Nationalized` là annotation của **Hibernate**, không phải JPA thuần; portability giữa dialect cần test.
- `updatedAtUtc` là LocalDateTime **theo quy ước UTC** vì DDL dùng timestamp không timezone. Nếu business cần thời điểm tuyệt đối xuyên time zones, cân nhắc Java `Instant`/`OffsetDateTime` cùng SQL type/driver mapping thích hợp và test.
- `protected` no-args constructor để JPA instantiate entity. Service không tự set `id` hoặc `version`.

### 7.2. Đừng trả entity trực tiếp cho API

Entity có thể phát triển thêm relationships, internal audit columns hoặc fields nhạy cảm. Nên trả **DTO/record**:

~~~java
package vn.demo.azure.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record ProductView(
    Long id,
    String sku,
    String name,
    BigDecimal price,
    Long version,
    LocalDateTime updatedAtUtc
) {
    public static ProductView from(Product p) {
        return new ProductView(
            p.getId(), p.getSku(), p.getName(), p.getPrice(),
            p.getVersion(), p.getUpdatedAtUtc()
        );
    }
}
~~~

Trong ứng dụng thật, DTO nên chỉ chứa fields được client phép xem; `version` có thể hữu ích làm optimistic concurrency token (ví dụ HTTP ETag/If-Match), nhưng cần tự thiết kế enforcement ở API. **Chỉ có `@Version` không tự buộc HTTP client gửi expected version**; nó bảo vệ các changes xảy ra trong khoảng thời gian transaction tải entity đến khi ghi.

## 8. Spring Data JPA Repository: CRUD, query derivation và phân trang

File `ProductRepository.java`:

~~~java
package vn.demo.azure.catalog;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);

    boolean existsBySku(String sku);

    Page<Product> findByNameContainingIgnoreCase(String name, Pageable page);
}
~~~

Spring Data dựng query cho `findBySku` và `findByNameContainingIgnoreCase` theo metadata entity/dialect. Không cần tự viết SQL CRUD thông thường.

### 8.1. Spring Data repository methods phổ biến

| Method | Ý nghĩa | Lưu ý |
|---|---|---|
| `findById(id)` | Tìm theo khóa chính | Trả `Optional` |
| `findBySku(sku)` | Tra theo business key | Nên có unique index |
| `existsBySku(sku)` | Kiểm tra tồn tại | Không thay unique constraint trong race |
| `save(product)` | Insert/update theo entity state | SQL thực sự flush theo transaction |
| `saveAndFlush(product)` | Save và yêu cầu flush sớm | Không đồng nghĩa commit |
| `findAll(pageable)` | Paging/sorting | Offset pagination chậm ở page rất sâu |
| `deleteById(id)` | Xóa theo ID | Tôn trọng constraints/business deletion |

### 8.2. Query derivation ≠ truy vấn vendor-independent tuyệt đối

`findByNameContainingIgnoreCase` có thể dịch thành một biểu thức LIKE/lower/collation tương ứng. **SQL Server collation** và **PostgreSQL collation/`ILIKE` semantics** có thể khác nhau với Unicode, dấu tiếng Việt, case folding và wildcard. Test với các tên:

~~~text
"Cà phê"
"ca phe"
"CÀ PHÊ"
"Đèn LED"
"den led"
~~~

Không kết luận `IgnoreCase` mặc nhiên là **ignore accents** hoặc full-text search. Với tìm kiếm phức tạp, dùng index/collation/full-text capabilities phù hợp từng database; có thể cần repository adapter theo vendor.

### 8.3. JPQL và native SQL

Ví dụ **JPQL** portable (chỉ dùng khi thật sự cần):

~~~java
// Trong ProductRepository, ví dụ bổ sung có thể thêm:
@org.springframework.data.jpa.repository.Query(
    "select p from Product p where p.price between :minPrice and :maxPrice")
Page<Product> findWithinPriceRange(
    @org.springframework.data.repository.query.Param("minPrice")
    java.math.BigDecimal minPrice,
    @org.springframework.data.repository.query.Param("maxPrice")
    java.math.BigDecimal maxPrice,
    Pageable pageable
);
~~~

Đây là **đoạn code minh họa cần chèn vào interface repository**, không phải một file Java độc lập. Dùng bound parameters để tránh SQL injection; không nối chuỗi input thành SQL fragment. Với native SQL, phải xem riêng T-SQL vs PostgreSQL syntax, paging và type casting; **không tạo query `TOP 10` rồi kỳ vọng PostgreSQL hiểu**.

### 8.4. Pagination và sort có giới hạn

Với API:

~~~text
GET /products?name=phone&page=0&size=20
~~~

Spring Data có thể dùng `PageRequest.of(page, size, Sort.by("sku"))`. Cần:

- Giới hạn `size`, ví dụ tối đa 100.
- Chọn sort ổn định với khóa tie-break (ví dụ `sku` unique).
- Thêm index cho các patterns lọc/sort thường gặp.
- Với pagination cực sâu, cân nhắc **keyset/seek pagination** thay offset.
- Không trả raw SQL paging với interpolated user sort column; dùng whitelist.

`Page<T>` thường chạy thêm **count query**, có thể tốn chi phí trên bảng lớn; nếu chỉ cần biết có trang tiếp, dùng `Slice<T>` hoặc query phù hợp. Hai engine có query planners khác nhau, phải đo thực tế.

## 9. Service layer và transaction boundary

### 9.1. Input DTO có validation

File `CreateProductRequest.java`:

~~~java
package vn.demo.azure.catalog;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank @Size(max = 64) String sku,
    @NotBlank @Size(max = 160) String name,
    @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2)
    BigDecimal price
) { }
~~~

File `ChangePriceRequest.java`:

~~~java
package vn.demo.azure.catalog;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public record ChangePriceRequest(
    @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2)
    BigDecimal price
) { }
~~~

**Validation tại API không thay database constraints.** Hai requests tạo cùng SKU đồng thời đều có thể qua `existsBySku`, nhưng unique index ở DB phải bảo vệ integrity cuối cùng.

### 9.2. ProductService

~~~java
package vn.demo.azure.catalog;

import jakarta.persistence.EntityNotFoundException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.BAD_REQUEST;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ProductView getBySku(String sku) {
        return repository.findBySku(sku)
            .map(ProductView::from)
            .orElseThrow(() ->
                new EntityNotFoundException("Product not found"));
    }

    @Transactional(readOnly = true)
    public Page<ProductView> search(String name, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                BAD_REQUEST, "page must be >= 0 and size in [1,100]");
        }
        var pageable = PageRequest.of(
            page, size, Sort.by("sku").ascending());
        if (name == null || name.isBlank()) {
            return repository.findAll(pageable).map(ProductView::from);
        }
        return repository.findByNameContainingIgnoreCase(name, pageable)
            .map(ProductView::from);
    }

    @Transactional
    public ProductView create(CreateProductRequest request) {
        var product = new Product(
            request.sku(), request.name(), request.price());
        return ProductView.from(repository.saveAndFlush(product));
    }

    @Transactional
    public ProductView updatePrice(String sku, ChangePriceRequest request) {
        var product = repository.findBySku(sku)
            .orElseThrow(() ->
                new EntityNotFoundException("Product not found"));
        product.changePrice(request.price());
        return ProductView.from(repository.saveAndFlush(product));
    }
}
~~~

**Tại sao dùng `@Transactional` ở service?**

- Đặt business operation và DB write trong một transaction rõ ràng.
- Với JPA, dirty checking xảy ra trong persistence context; `saveAndFlush` cho biết SQL đã được gửi sớm, nhưng **chưa commit**.
- `readOnly=true` có thể tối ưu flush mode/hints, **không phải DB access control**; nếu cần read-only chắc chắn, phải cấp database permissions/schema/transaction policy phù hợp.
- Spring mặc định rollback với unchecked exceptions; checked exceptions và transaction propagation cần thiết kế riêng.
- Method được gọi **nội bộ trong cùng object** có thể không đi qua Spring proxy; một `@Transactional` trên private method/self-invocation có thể không kích hoạt như dự kiến.

### 9.3. Optimistic locking thực tế

Giả sử hai transactions tải cùng một Product `version=3`:

~~~text
Transaction A: read price 100, version 3
Transaction B: read price 100, version 3
Transaction A: update price 120; version becomes 4; COMMIT
Transaction B: update price 130 with expected version 3
→ update affects 0 rows → optimistic locking failure
~~~

`@Version` ngăn một transaction ghi đè người khác **khi hai transactions đã tải entity trong trạng thái xung đột**. Tuy nhiên REST API trên chỉ đọc entity rồi cập nhật trong cùng request; nếu browser xem sản phẩm lúc 09:00 nhưng gửi PATCH lúc 09:10, server sẽ tải phiên bản mới ngay trước PATCH và có thể vẫn ghi đè thay đổi trước đó. Để chống **lost update xuyên HTTP requests**, truyền expected version/ETag và kiểm tra nó ở service trước khi sửa.

### 9.4. Transaction quá dài gây hại

Tránh:

~~~text
BEGIN TRANSACTION
  SELECT product
  Call external payment API (wait 30 seconds)
  Send Service Bus message
  UPDATE product
COMMIT
~~~

Kết nối và locks bị giữ lâu, external services không thuộc local DB transaction. Thiết kế phù hợp hơn là **transaction ngắn**, outbox/saga/idempotency khi workflow liên dịch vụ. `@Transactional` không tạo atomic commit giữa Azure SQL, PostgreSQL, HTTP APIs và Service Bus.

## 10. REST Controller và xử lý HTTP lỗi

### 10.1. ProductController

~~~java
package vn.demo.azure.catalog;

import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ProductView get(@PathVariable String sku) {
        return service.getBySku(sku);
    }

    @GetMapping
    public Page<ProductView> list(
        @RequestParam(required = false) String name,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        return service.search(name, page, size);
    }

    @PostMapping
    public ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProductRequest request,
        UriComponentsBuilder uriBuilder
    ) {
        var created = service.create(request);
        var location = uriBuilder.path("/products/{sku}")
            .buildAndExpand(created.sku()).toUri();
        return ResponseEntity.created(location).body(created);
    }

    @PatchMapping("/{sku}/price")
    public ProductView updatePrice(
        @PathVariable String sku,
        @Valid @RequestBody ChangePriceRequest request
    ) {
        return service.updatePrice(sku, request);
    }
}
~~~

HTTP API phục vụ mục đích học tập; production cần **authentication/authorization** ở Spring Security/API gateway, rate limits, request IDs, audit events và kiểm tra quyền sửa giá theo principal. Không expose một API thay giá công khai chỉ vì ví dụ chạy localhost.

### 10.2. Map exceptions thành response an toàn

File `ApiExceptionHandler.java`:

~~~java
package vn.demo.azure.catalog;

import jakarta.persistence.EntityNotFoundException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(EntityNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(EntityNotFoundException ex) {
        var problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Product not found");
        return ResponseEntity.status(404).body(problem);
    }

    @ExceptionHandler({
        DataIntegrityViolationException.class,
        OptimisticLockingFailureException.class
    })
    ResponseEntity<ProblemDetail> conflict(RuntimeException ex) {
        var problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT, "Conflicting product operation");
        return ResponseEntity.status(409).body(problem);
    }
}
~~~

**Không trả raw SQL errors** chứa database endpoint, SQL text, constraint metadata hoặc sensitive values cho client. Nội bộ có thể log exception class/trace ID với dữ liệu đã được redacted; riêng `DataIntegrityViolationException` có thể là vi phạm nhiều loại constraint, cần phân loại chi tiết nếu muốn API trả mã lỗi chính xác.

### 10.3. Ví dụ HTTP requests

~~~http
POST /products HTTP/1.1
Content-Type: application/json

{"sku":"SKU-001","name":"Tai nghe không dây","price":1200000.00}
~~~

~~~http
GET /products/SKU-001 HTTP/1.1
~~~

~~~http
PATCH /products/SKU-001/price HTTP/1.1
Content-Type: application/json

{"price":1150000.00}
~~~

~~~http
GET /products?name=Tai&page=0&size=20 HTTP/1.1
~~~

Khi đổi profile `sqlserver` → `postgres`, API contract **giữ nguyên** và code repository vẫn như trên nếu DDL/mapping được kiểm chứng. Chỉ thay JDBC profile, driver, schema migrations, database provisioning và quyền kết nối.

## 11. Kết nối an toàn: firewall, Private Endpoint, DNS và TLS

Ứng dụng Spring Boot có thể khởi động thành công trong local Docker nhưng timeout khi chạy trên Azure nếu đường mạng hoặc DNS khác nhau. **Connection string đúng chưa đủ**: cần đường outbound từ runtime đến database, phân giải đúng hostname, TCP/TLS hợp lệ và quyền database.

### 11.1. Azure SQL Database

Azure SQL Database chạy dưới **logical server** với FQDN dạng:

~~~text
<server>.database.windows.net
TCP 1433
~~~

Các lựa chọn mạng:

- **Public endpoint + firewall rules:** chỉ cho phép các nguồn IP được phê duyệt. Không mở `0.0.0.0/0`.
- **Private Endpoint:** đưa đường vào Azure SQL qua private IP trong VNet; **ứng dụng** cần outbound VNet path và DNS đúng.
- **Public network access disabled:** cần cấu hình riêng theo chính sách; Private Endpoint tồn tại **không tự chứng minh** public path đã bị khóa.
- **Connection policy:** tùy server/network, SQL client có thể dùng **proxy/redirect**; redirect có yêu cầu outbound ports/bộ quy tắc network riêng. Kiểm tra Azure SQL connection policy và NSG/firewall thay vì mở tất cả ports vô hạn.

### 11.2. Azure Database for PostgreSQL Flexible Server

Server FQDN dạng:

~~~text
<server>.postgres.database.azure.com
TCP 5432
~~~

Flexible Server có các kiến trúc kết nối riêng:

- **Public access theo network/firewall rules**, có thể kết hợp Private Endpoint ở những cấu hình/service modes hỗ trợ.
- **Private access/VNet integration** qua **delegated subnet** và private DNS theo model phù hợp.
- Quy định **networking mode** có thể ảnh hưởng khả năng chuyển đổi, Private Endpoint và địa chỉ IP. **Không xem “Private Endpoint” và “VNet-injected server” là hai tên của cùng một cấu hình.**

Hãy chọn mode khi provision và kiểm tra các tính năng vùng/phiên bản tại thời điểm triển khai. Không sao chép PostgreSQL **Single Server** networking guide cũ để cấu hình Flexible Server.

### 11.3. Đường truy cập từ từng hosting service

| Hosting Spring Boot | Điều phải cấu hình |
|---|---|
| **Azure App Service** | **VNet Integration cho outbound** tới private DB, DNS/routing phù hợp |
| **Azure Container Apps** | Environment VNet/egress, network restrictions và DNS |
| **AKS** | VNet/Pod egress, NetworkPolicy, Private DNS, NSG/UDR/Firewall |
| **Azure VM** | Subnet routes, DNS, NSG, managed identity |
| **On-premises** | VPN/ExpressRoute, route và private DNS forwarding |
| **Hosted CI runner** | Không tự nằm trong private VNet; dùng self-hosted/private runner hoặc cách migration được phê duyệt |

**Private Endpoint inbound của App Service** chỉ điều khiển người dùng vào App Service, không tự cấp app quyền outbound vào database Private Endpoint.

### 11.4. Luồng debug mạng đúng thứ tự

~~~mermaid
flowchart TD
    START[JDBC connection fails] --> NAME{Correct server FQDN?}
    NAME -->|No| FIXNAME[Fix hostname / profile]
    NAME -->|Yes| DNS{DNS resolves to intended IP?}
    DNS -->|No| FIXDNS[Private DNS / resolver / VNet links]
    DNS -->|Yes| TCP{TCP 1433 / 5432 reachable?}
    TCP -->|No| FIXX[Firewall / NSG / route / access mode]
    TCP -->|Yes| TLS{TLS verifies server identity?}
    TLS -->|No| FIXTLS[Trust store / CA / FQDN / driver]
    TLS -->|Yes| AUTH{Database login accepted?}
    AUTH -->|No| FIXAUTH[Entra token / SQL or PG user / role]
    AUTH -->|Yes| GRANT{SELECT/INSERT grants valid?}
    GRANT -->|No| FIXGRANT[Least-privilege DB grants]
    GRANT -->|Yes| QUERY[Inspect SQL / pool / transactions]
~~~

Từ **runtime đang lỗi**, dùng công cụ được phép:

~~~bash
nslookup "<sql-server>.database.windows.net"
nslookup "<pg-server>.postgres.database.azure.com"

# Nếu image/host có netcat; chỉ chứng minh TCP, không phải auth.
nc -vz "<sql-server>.database.windows.net" 1433
nc -vz "<pg-server>.postgres.database.azure.com" 5432
~~~

Không dùng private IP trực tiếp trong JDBC URL để “sửa nhanh” DNS: TLS hostname verification có thể thất bại và IP có thể thay đổi. **Không bật tùy chọn bỏ kiểm tra certificate** như một giải pháp network production.

### 11.5. Kiểm tra TLS cho từng driver

**Microsoft JDBC Driver for SQL Server:**

~~~text
encrypt=true
trustServerCertificate=false
~~~

**PostgreSQL JDBC Driver:**

~~~text
sslmode=verify-full
~~~

Trong PostgreSQL, `sslmode=require` có thể mã hóa đường truyền nhưng **không nên coi là thay thế chắc chắn cho verify-full** theo yêu cầu xác minh danh tính máy chủ. Với SQL Server, `trustServerCertificate=true` có thể bỏ kiểm tra chain/hostname; không dùng trong production.

TLS cần phiên bản JDBC driver/JDK truststore mới theo chính sách certificate của Azure. Cập nhật CA chain đúng, đồng thời kiểm tra JVM trust store trong **container image** chứ không chỉ laptop developer.

### 11.6. Không mở public firewall chỉ để migration

Nếu database đã private-only, dùng **private CI runner, migration job trong VNet hoặc bastion/admin host** được phê duyệt. Mở rộng firewall cho Internet rồi quên đóng là security regression phổ biến. Khi thay network, test **application runtime + migrations + DBA tools + scheduled jobs**, không chỉ một API GET.

## 12. Authentication: SQL password, Microsoft Entra và managed identity

### 12.1. Vì sao ưu tiên không có mật khẩu tĩnh?

Static database passwords có thể bị lộ qua source code, Git history, container env inspection, CI logs hoặc backups. Với workload chạy trên Azure, **managed identity** giúp ứng dụng nhận Entra token mà không lưu client secret, nhưng database phải hỗ trợ **authentication method và database principal mapping** tương ứng.

| Bài toán | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Lab mật khẩu | SQL authentication login/user | PostgreSQL user/password |
| Production passwordless | Entra authentication do Microsoft JDBC Driver hỗ trợ | Entra token được dùng với PostgreSQL login protocol/role |
| Token audience/scope | JDBC driver xử lý với auth mode được hỗ trợ | Thường `https://ossrdbms-aad.database.windows.net/.default` |
| Database authorization | Contained user/role `FROM EXTERNAL PROVIDER` và GRANT | Entra principal được ánh xạ thành PG role và GRANT |
| Refresh | JDBC driver/auth integration có logic nhận token theo mode | Pool cần cơ chế cung cấp token mới khi tạo connection |
| User-assigned identity | Cấu hình identity/client ID phù hợp driver version | DefaultAzureCredential/Workload Identity chọn identity phù hợp |

**Azure RBAC Contributor/Managed Identity trên VM không tự tạo quyền SELECT trên database.** Người quản trị database phải tạo principal/role và cấp grants đúng đối tượng.

### 12.2. Azure SQL Database với system-assigned managed identity

Đường đi:

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot app
    participant MI as Azure Managed Identity endpoint
    participant DRIVER as Microsoft SQL JDBC Driver
    participant ENTRA as Microsoft Entra ID
    participant SQL as Azure SQL Database
    APP->>DRIVER: Open JDBC connection
    DRIVER->>MI: Request managed identity token
    MI->>ENTRA: Token acquisition within Azure runtime
    ENTRA-->>DRIVER: Access token
    DRIVER->>SQL: TLS + Entra authentication
    SQL->>SQL: Validate contained user / DB grants
    SQL-->>APP: Authorized SQL session or login error
~~~

Một JDBC URL cho **system-assigned identity** khi runtime/driver hỗ trợ:

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;
~~~

Nếu dùng profile riêng `sqlserver-mi`:

~~~yaml
spring:
  datasource:
    url: ${AZURE_SQL_MI_JDBC_URL}
    driver-class-name: com.microsoft.sqlserver.jdbc.SQLServerDriver
  flyway:
    locations: classpath:db/migration/sqlserver
  jpa:
    database-platform: org.hibernate.dialect.SQLServerDialect
~~~

Không cấu hình `spring.datasource.username/password` nếu driver thật sự nhận credentials từ managed identity. **Với user-assigned identity**, driver versions có cách chỉ định **client ID**/authentication properties khác nhau; kiểm tra tài liệu Microsoft JDBC Driver đang dùng thay vì tùy tiện coi object ID và client ID là một.

Để database chấp nhận principal, Entra admin được cấu hình ở Azure SQL logical server và DBA tạo user từ external provider (cú pháp minh họa trong **đúng database**):

~~~sql
CREATE USER [catalog-app-mi] FROM EXTERNAL PROVIDER;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON OBJECT::dbo.products TO [catalog-app-mi];
~~~

**Điều kiện:** tên `catalog-app-mi` phải resolve đúng Microsoft Entra principal trong tenant. Với tên trùng/ứng dụng cần phân biệt object IDs, có các cách tạo principal theo ID/`SID` phù hợp engine version; phải xem tài liệu Azure SQL và được DBA phê duyệt. App principal **không cần quyền CREATE TABLE** nếu migration được chạy bằng identity khác.

### 12.3. PostgreSQL Flexible Server với Microsoft Entra token

PostgreSQL JDBC protocol có **username/password**. Với Entra authentication:

1. Flexible Server được cấu hình hỗ trợ Microsoft Entra auth (và admin).
2. Entra principal/managed identity được ánh xạ thành **PostgreSQL database role** và có grants.
3. Ứng dụng lấy token cho scope phù hợp.
4. Khi mở JDBC connection, **username là DB role đã ánh xạ**, **password là access token ngắn hạn**, không phải secret cố định.
5. Connection pool/credential provider phải **lấy token mới cho các kết nối được tạo sau khi token cũ hết hạn**.

Ví dụ nhận token qua Azure Identity SDK:

~~~java
import com.azure.core.credential.AccessToken;
import com.azure.core.credential.TokenRequestContext;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

DefaultAzureCredential credential =
    new DefaultAzureCredentialBuilder().build();
AccessToken accessToken = credential.getToken(
    new TokenRequestContext().addScopes(
        "https://ossrdbms-aad.database.windows.net/.default"
    )
).block();

if (accessToken == null) {
    throw new IllegalStateException("Entra token unavailable");
}

// The token is short-lived. Do not log accessToken.getToken().
// A supported credential provider must refresh it for new JDBC sessions.
~~~

**Đây là đoạn minh họa cách lấy token**, cần thêm dependencies `com.azure:azure-identity` và `com.azure:azure-core` theo BOM phiên bản tương thích, đồng thời một **Hikari/DataSource passwordless integration** đã kiểm chứng. Không copy token lấy một lần vào `AZURE_PG_PASSWORD` của ứng dụng chạy 24/7: khi Hikari tạo kết nối mới sau khi token hết hạn, login có thể thất bại.

Có thể chọn **Spring Cloud Azure passwordless JDBC integration** tương ứng Spring Boot/Cloud Azure version, hoặc implement credential refresh tại lớp cấp **new connections** với token caching/expiry guards. Tên starter, thuộc tính và khả năng hỗ trợ Flexible Server có thể đổi giữa các bản; hãy xem compatibility guide, integration test và security approval trước dùng production.

Không tự ý dùng JDBC driver SQL Server `authentication=ActiveDirectoryManagedIdentity` trong PostgreSQL URL: đó là **driver-specific property**, không phải chuẩn JDBC chung.

### 12.4. PostgreSQL Entra role/GRANT

Trên PostgreSQL Flexible Server, DBA/Entra admin phải tạo hoặc ánh xạ principal Entra thành **PostgreSQL role** bằng quy trình Azure-supported tương ứng (ví dụ quản trị các hàm `pgaadauth` theo tính năng/version) và cấp:

~~~sql
-- Chỉ minh họa quyền cho DB role đã được tạo/ánh xạ hợp lệ.
GRANT USAGE ON SCHEMA public TO catalog_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.products TO catalog_app_role;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO catalog_app_role;
~~~

**`catalog_app_role` trong ví dụ là tên DB role giả định đã tồn tại**, không tự được tạo bằng Azure RBAC. Với PostgreSQL identity sequences, quyền sequence phụ thuộc cách identity/generated value được sử dụng và PostgreSQL version; chỉ cấp tối thiểu sau khi integration test. Không cấp `SUPERUSER` hoặc rộng toàn server cho app.

### 12.5. Rotation và kết nối đang mở

| Authentication | Khi thông tin hết hạn/rotate | Điều cần thiết kế |
|---|---|---|
| SQL/PG static password | New connections có thể fail sau rotation | Secret store + roll/overlap windows + pool recycling |
| Azure SQL Managed Identity | Driver lấy token phù hợp auth mode | Driver version, identity assignment, DB user và reconnect |
| PostgreSQL Entra access token | Token mới cần cho **new JDBC connection** | Passwordless provider/refresh logic, pool lifecycle |
| TLS CA/cert update | Client có thể không trust chain mới | Update JVM truststore/container base image |
| Database roles/GRANT | Auth thành công nhưng query bị deny | Audit permissions và least-privilege migration |

Token expiry của Entra **không đồng nghĩa** tất cả JDBC sessions đang mở bị đóng ngay; driver/service có behavior riêng. Nhưng mọi **new connection** phải xác thực hợp lệ; hãy test Hikari khi pool bị xoay vòng, scale-out và failover.

### 12.6. Không dùng secret manager như quyền SQL

Azure Key Vault chỉ giữ/trao credentials theo policy; nó không tự:

- tạo PostgreSQL database role;
- tạo contained SQL user;
- cấp SELECT/INSERT trên bảng;
- tạo route từ App Service tới Private Endpoint;
- sửa SSL certificate hostname mismatch.

Phân biệt **secret access**, **database authentication**, **database authorization** và **network reachability** khi chẩn đoán.

## 13. Connection pooling bằng HikariCP

HikariCP quản lý kết nối JDBC để tránh bắt tay TLS/authentication mỗi HTTP request. Tuy nhiên database connections là **tài nguyên hữu hạn**, đặc biệt trên Azure SQL compute tier nhỏ hoặc PostgreSQL Flexible Server số vCores thấp.

### 13.1. Quy mô pool theo số replicas

Giả sử:

~~~text
Azure Container Apps replicas (peak):  20
Hikari maximumPoolSize per replica:   10
Potential app connections:            200
Migration/DBA/monitoring headroom:    30
Peak total plan:                      ~230 connections
~~~

Nếu database tier hỗ trợ ít connections hơn, pool quá lớn gây login timeout/throttle. Còn nếu app chỉ dùng 3 connections đồng thời nhưng cấu hình 100/replica, nâng DB tier để chứa idle connections có thể tốn chi phí không cần thiết.

**Sizing phải dựa trên** đo concurrency, query latency, request queue, number of app replicas và DB connection limits; không dùng công thức “CPU cores × 10” như quy tắc tuyệt đối.

### 13.2. Các setting và tradeoff

| Hikari setting | Ý nghĩa | Điều kiện |
|---|---|---|
| `maximumPoolSize` | Số connections tối đa trong một app instance | Tổng replicas × pool không vượt budget |
| `minimumIdle` | Số idle connections mục tiêu | Quá cao làm tốn DB connections |
| `connectionTimeout` | Thời gian chờ borrow connection | Quá ngắn gây lỗi khi burst |
| `validationTimeout` | Timeout cho kiểm tra connection hợp lệ | Phải thấp hơn connection timeout |
| `maxLifetime` | Tuổi thọ tối đa connection trong pool | Thấp hơn network/service hard lifetime nếu có |
| `idleTimeout` | Ngưỡng trả bớt idle connection | Có tác dụng với pool dynamic |
| `keepaliveTime` | Ping idle connections khi phù hợp | Tránh ping quá dày trên hàng nghìn replicas |
| `leakDetectionThreshold` | Phát hiện giữ connection quá lâu (debug) | Không bật log verbose tràn trong production |

`maxLifetime` **không tự sửa PostgreSQL Entra token refresh** nếu credential provider vẫn trả token cũ khi tạo connection mới. Với user-assigned MI, kiểm tra client ID selection trên mỗi replica/AKS Workload Identity.

### 13.3. Pool exhaustion

Triệu chứng:

~~~text
HikariPool-1 - Connection is not available,
request timed out after 3000ms.
~~~

Không tự kết luận “SQL Server đã down”. Có thể:

- Transaction giữ connection vì query chậm hoặc external HTTP call trong transaction.
- Pool nhỏ hơn nhu cầu ứng dụng.
- DB tier throttle/CPU/IO quá tải.
- Connection leak do không trả về pool.
- Network/TLS/auth làm tạo connection mới chậm.
- Retry storm sau một outage làm mọi requests tranh pool.

Quan sát **active/idle/pending connections, query latency, database CPU/locks và error classes** trước khi tăng `maximumPoolSize`.

### 13.4. Retry đúng lớp, tránh nhân giao dịch

Một HTTP request tạo sản phẩm có thể:

~~~text
POST /products
  → INSERT succeeds, commit succeeds
  → connection drops before response
  → client retries POST
  → duplicate SKU / conflict
~~~

**Mọi connection error không có nghĩa transaction đã rollback.** Nếu thao tác có side effects, dùng **idempotency key/business unique constraint** và kiểm tra trạng thái authoritative trước khi retry. Chỉ retry các lỗi transient được phân loại, có exponential backoff/jitter và giới hạn nỗ lực; không retry vô hạn HTTP 400/403/invalid SQL.

## 14. Transactions, isolation và concurrency giữa hai engine

### 14.1. `@Transactional` làm gì?

Spring quản lý transaction scope của **DataSource/EntityManager đang hoạt động**:

~~~java
@Transactional
public void renameAndReprice(String sku, String newName, BigDecimal newPrice) {
    // Pseudocode: both changes occur on one managed entity/transaction.
    Product p = repository.findBySku(sku).orElseThrow();
    p.changePrice(newPrice);
    // A real entity setter for name would be required to rename it.
}
~~~

Đây là **đoạn minh họa transaction**, không phải method đầy đủ chạy được vì Product trong bài chưa có setter đổi tên. Không copy vào project mà chưa bổ sung domain method/validation.

Trong service `updatePrice` ở phần 9, dirty checking và `@Version` phối hợp để phát hiện một số lost updates. Tuy nhiên isolation và database-side locking khác nhau theo engine.

### 14.2. Read committed và MVCC

| Chủ đề | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Default transaction isolation | Thường READ COMMITTED; hành vi row-versioning có thể phụ thuộc DB settings | READ COMMITTED theo PostgreSQL |
| Dirty reads | Không trong cấu hình thông thường | Không |
| Readers vs writers | Cần biết row-versioning/locking configuration | MVCC snapshots theo isolation |
| Deadlock | Có, cần xử lý/retry transaction phù hợp | Có, SQLSTATE `40P01` |
| Serialization conflict | Theo isolation/data patterns | SQLSTATE `40001` khi Serializable |
| Update conflict | Có thể nhận qua JPA `@Version` | Có thể nhận qua JPA `@Version` |

**Không giả định READ COMMITTED của hai engines có tất cả semantics giống nhau**. SQL Server có khác biệt giữa lock-based read committed và READ_COMMITTED_SNAPSHOT; PostgreSQL MVCC snapshot được xác định ở cấp statement trong read committed. Phải test tình huống nghiệp vụ đọc–sửa đồng thời.

### 14.3. Pessimistic locking khi thật sự cần

Repository có thể định nghĩa:

~~~java
@org.springframework.data.jpa.repository.Lock(
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
)
@org.springframework.data.jpa.repository.Query(
    "select p from Product p where p.sku = :sku"
)
java.util.Optional<Product> findForUpdateBySku(
    @org.springframework.data.repository.query.Param("sku") String sku
);
~~~

**Đoạn này cần chèn vào interface `ProductRepository`**, không độc lập. Hibernate sinh SQL locking khác nhau ở SQL Server và PostgreSQL; bạn phải benchmark thực tế và xét risk deadlock/lock wait. Dùng optimistic locking khi conflicts hiếm; dùng pessimistic locking khi business flow cần khóa row sớm và có timeout/runbook phù hợp.

### 14.4. Một transaction không đi qua hai databases

~~~text
App transaction in Azure SQL: COMMIT
App transaction in PostgreSQL: ROLLBACK
Result: data differs if the process treats both as one operation.
~~~

Đây là lời nhắc về **distributed consistency**. Đừng dùng một `@Transactional` rồi tưởng vừa ghi Azure SQL vừa ghi PostgreSQL đã atomic. Cần phân vùng ownership, outbox, saga, compensation hoặc distributed transaction technology có support phù hợp và chi phí/rủi ro được đánh giá; tránh thiết kế cross-database write khi không cần.

### 14.5. Các nguyên tắc transaction

1. Transaction càng **ngắn** càng tốt.
2. Tránh HTTP calls/slow file I/O trong transaction.
3. Dùng database constraints bảo vệ uniqueness/integrity.
4. Optimistic version hoặc explicit locks khi có writes đồng thời.
5. Retry chỉ transient errors, đảm bảo idempotency.
6. Không expose entity/lazy loading qua HTTP sau transaction nếu `open-in-view=false`.
7. Audit trước khi thay isolation level vì throughput và locks có thể khác đáng kể.

## 15. Spring Data JDBC là lựa chọn khác khi không muốn ORM

Nếu application aggregate đơn giản, không cần JPA lazy loading/entity graph, **Spring Data JDBC** có thể giúp data access minh bạch hơn. Nhưng hãy chọn **một primary persistence paradigm** rõ ràng, không tự thêm hai starters vì tên đều có “Spring Data”.

### 15.1. Spring Data JPA vs JDBC

| Yếu tố | Spring Data JPA | Spring Data JDBC |
|---|---|---|
| Mô hình | Entity graph, persistence context, ORM | Aggregate-oriented repository |
| Lazy loading | Có theo mapping và transaction | Không có JPA lazy loading |
| Change tracking | Hibernate dirty checking | Save aggregate rõ ràng |
| Query language | JPQL/Criteria/SQL | SQL và generated repository queries |
| Vendor portability | Dựa trên dialect/ORM, vẫn có khác biệt | Cần chủ động quản SQL/dialect hơn |
| Khi phù hợp | Domain phức tạp, associations, ORM features | CRUD aggregates đơn giản và SQL control |

### 15.2. JdbcTemplate cho query chuyên biệt

Ngay cả khi dùng JPA, Spring Boot có thể autoconfigure `JdbcTemplate` từ cùng DataSource để thực hiện query đặc thù. Ví dụ dùng **SQL không phụ thuộc vendor**:

~~~java
package vn.demo.azure.catalog;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductReportDao {
    private final JdbcTemplate jdbc;

    public ProductReportDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<String> listSkus() {
        return jdbc.query(
            "SELECT sku FROM products ORDER BY sku",
            (rs, rowNum) -> rs.getString("sku")
        );
    }
}
~~~

`JdbcTemplate` dùng **prepared statements/bound parameters** khi query có input:

~~~java
var names = jdbc.query(
    "SELECT name FROM products WHERE sku = ?",
    (rs, rowNum) -> rs.getString("name"),
    "SKU-001"
);
~~~

Các snippets này giả định cùng DataSource đã cấu hình. Nếu sử dụng **Spring Data JDBC repository** thay JPA, cần đổi starters, mapping annotations/aggregate model và repository configuration; không copy entity `jakarta.persistence.Entity` rồi coi là Spring Data JDBC entity.

### 15.3. Khi native SQL là cần thiết

Nếu query cần `jsonb`, GIN indexes hoặc `ON CONFLICT` của PostgreSQL, không cố ép thành portable JPQL. Tạo **vendor-specific DAO/query adapters** được chọn theo profile, kiểm thử và đo execution plan. Với Azure SQL, những kỹ thuật T-SQL/Query Store cũng phải được quản riêng; giữ business service interface chung.

## 16. Kiểm thử đúng database engine: Testcontainers và Azure staging

Một trong các lỗi nguy hiểm nhất là test mọi repository bằng **H2 in-memory** rồi giả định Azure SQL hoặc PostgreSQL sẽ giống. H2 có syntax, types, behavior locking, collation và migrations khác; “green unit tests” chưa đủ để chấp nhận database migration.

### 16.1. Kim tự tháp kiểm thử

| Test | Mục tiêu | Không kiểm chứng được |
|---|---|---|
| **Unit test service** | Business validation, DTO mapping, mock repository | SQL dialect, constraints, transactions thật |
| **Repository test với Testcontainers PostgreSQL** | PostgreSQL schema/Flyway/query/locking | Azure Flexible Server network/Entra/HA |
| **Repository test với Testcontainers SQL Server** | T-SQL, identity, unique constraints, Hibernate SQL dialect | Azure SQL Database firewall/Private Link/tiers |
| **Azure staging smoke test** | TLS, Entra/DB grants, Private DNS, host network, Flyway permissions | Full production peak throughput |
| **Load/resilience test** | Pool saturation, retries, failover và degradation | Mọi failure mode nếu không có kịch bản |

**Một container SQL Server không bằng Azure SQL Database** về mọi tính năng PaaS, nhưng rất hữu ích để phát hiện incompatibility DDL/ORM cơ bản trước deploy. Với production feature đặc thù (Query Store, elastic pools, Azure SQL authentication), vẫn cần staging thật trong Azure.

### 16.2. Thêm Testcontainers dependencies (chỉ test)

Trong Maven `dependencies`, bổ sung:

~~~xml
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>postgresql</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>mssqlserver</artifactId>
  <scope>test</scope>
</dependency>
~~~

Đây là **dependency snippets để chèn vào `pom.xml`**, dùng tên artifacts thường gặp với dòng Testcontainers 1.x được BOM Spring Boot 3.x quản lý. **Testcontainers 2.x đã có thay đổi module/artifact naming**, nên phải xác minh coordinates với dependency versions thực của project và image support trước khi áp dụng.

### 16.3. Integration test với PostgreSQL Testcontainers

~~~java
package vn.demo.azure.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
@ActiveProfiles("postgres")
class PostgresProductRepositoryIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", postgres::getJdbcUrl);
        r.add("spring.datasource.username", postgres::getUsername);
        r.add("spring.datasource.password", postgres::getPassword);
        r.add("spring.flyway.locations",
            () -> "classpath:db/migration/postgres");
    }

    @Autowired ProductRepository repository;

    @Test
    void persistsProductAndFindsBySku() {
        repository.saveAndFlush(
            new Product("TEST-PG-001", "Cà phê", new BigDecimal("12.50"))
        );
        var product = repository.findBySku("TEST-PG-001");
        assertThat(product).isPresent();
        assertThat(product.get().getPrice())
            .isEqualByComparingTo(new BigDecimal("12.50"));
    }
}
~~~

Ví dụ cần Docker/Testcontainers support và Flyway migration. PostgreSQL test container thường dùng connection **không TLS** nội bộ giữa test runner và Docker host; điều đó **không phủ nhận yêu cầu TLS verify-full khi chạy Azure**. Trong Azure staging kiểm tra TLS riêng.

### 16.4. Kiểm thử SQL Server tương đương

Tạo test class riêng với:

~~~java
@Container
static org.testcontainers.containers.MSSQLServerContainer<?> sql =
    new org.testcontainers.containers.MSSQLServerContainer<>(
        "mcr.microsoft.com/mssql/server:2022-latest"
    ).acceptLicense();

@DynamicPropertySource
static void props(DynamicPropertyRegistry r) {
    r.add("spring.datasource.url", sql::getJdbcUrl);
    r.add("spring.datasource.username", sql::getUsername);
    r.add("spring.datasource.password", sql::getPassword);
    r.add("spring.flyway.locations",
        () -> "classpath:db/migration/sqlserver");
}
~~~

**Đây là fragment để chèn vào một test class**, không phải file Java độc lập. Test class cần `@ActiveProfiles("sqlserver")`, `@SpringBootTest`, `@Testcontainers`, repository/test method tương đương. Cần chấp nhận license SQL Server **chỉ khi người thực hành có quyền và đồng ý điều khoản**, đủ CPU/RAM/disk, Docker hỗ trợ architecture/virtualization; image `2022-latest` nên được pin digest hoặc version phù hợp trong CI production.

### 16.5. Các ca kiểm thử tối thiểu cho cả hai DB

- [ ] Flyway V1 tạo `products` và Hibernate `ddl-auto=validate` thành công.
- [ ] Insert Product có SKU và tên **Unicode tiếng Việt**.
- [ ] PostgreSQL/SQL Server trả ID do DB sinh, giá `BigDecimal(12,2)` giữ chính xác.
- [ ] Read theo SKU với unique index.
- [ ] Insert trùng SKU bị database từ chối, map thành 409 an toàn.
- [ ] `findByNameContainingIgnoreCase` được kiểm tra với Unicode/collation phù hợp.
- [ ] Paging/sorting ổn định, size ngoài [1..100] bị từ chối.
- [ ] Concurrent updates dẫn tới optimistic locking conflict khi thực sự đụng version.
- [ ] Transaction rollback khi business validation/DB constraint lỗi.
- [ ] Native SQL vendor-specific (nếu có) được test riêng.
- [ ] Migrations chạy lại theo đúng Flyway history, không tạo/ghi đè dữ liệu.
- [ ] Azure staging dùng TLS/Entra/Private DNS/thực tế Azure DB roles thành công.

### 16.6. Unit test không thay authentication test

Mock `ProductRepository` không truy vấn JDBC; nó không phát hiện được:

~~~text
PKIX path building failed
SQL Server Error 18456: Login failed
PostgreSQL SQLSTATE 28P01: password authentication failed
Private endpoint DNS resolves to wrong IP
Flyway cannot CREATE TABLE due to insufficient grant
~~~

Những lỗi này đòi **integration/smoke tests từ network runtime thật**, không phải thêm Mockito mocks.

## 17. SQL portability và hiệu năng query

### 17.1. Chỉ portable ở mức abstraction phù hợp

Các thao tác JPA phổ biến có thể dùng chung. Nhưng khác biệt ở:

| Vấn đề | SQL Server | PostgreSQL | Quyết định |
|---|---|---|---|
| Auto ID | `IDENTITY` | `GENERATED AS IDENTITY` | Flyway vendor migrations |
| Unicode text | `NVARCHAR` hoặc VARCHAR theo collation | UTF-8 VARCHAR/TEXT | Hibernate mapping + DB tests |
| JSON | SQL Server JSON handling/features | `jsonb` với index/operator riêng | Vendor-specific repository |
| Upsert | T-SQL pattern/`MERGE` kèm concurrency review | `ON CONFLICT` | Không dùng chung native SQL |
| Case/accents | Collation ảnh hưởng so sánh | Collation/`ILIKE`, locale | Test search semantics |
| Time types | `DATETIME2`/`DATETIMEOFFSET` | `timestamp`/`timestamptz` | UTC mapping policy |
| Array types | Không có PG array semantics | Native arrays | Adapter riêng |
| Pagination native | `OFFSET...FETCH` | `LIMIT/OFFSET` | Dùng Pageable hoặc dialect-specific SQL |
| Indexing | SQL Server B-tree/columnstore/full-text features | B-tree/GIN/GiST/BRIN... | Query-plan-driven |
| Lock hints | T-SQL `UPDLOCK`... | `FOR UPDATE` | JPA lock hoặc adapter riêng |

### 17.2. Một query `findBySku` nhanh cần index

Repository:

~~~java
Optional<Product> findBySku(String sku);
~~~

Phải có unique index/constraint ở DB. Nếu table có hàng triệu rows nhưng không index `sku`, query có thể scan toàn bảng và giữ connection lâu.

**PostgreSQL query plan:** trên staging và SELECT an toàn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, name, price, version, updated_at_utc
FROM public.products
WHERE sku = 'SKU-001';
~~~

**Lưu ý:** `EXPLAIN ANALYZE` thực sự **thực thi statement**. Không chạy `EXPLAIN ANALYZE UPDATE/DELETE` trên dữ liệu thật nếu chưa có transaction/rollback plan.

**Azure SQL Database:** xem Query Store/Actual Execution Plan/DMVs được cấp phép, hoặc đo:

~~~sql
SET STATISTICS IO ON;

SELECT id, sku, name, price, version, updated_at_utc
FROM dbo.products
WHERE sku = 'SKU-001';

SET STATISTICS IO OFF;
~~~

Chỉ thực hành trên database lab/staging. Không phát tán SQL plans/parameter values chứa dữ liệu nhạy cảm vào bug report công khai.

### 17.3. Query chứa `%term%` có thể không dùng index B-tree

`findByNameContainingIgnoreCase` thường tìm substring:

~~~sql
WHERE LOWER(name) LIKE '%coffee%'
~~~

Đây là **mô hình tương đương**, không phải SQL Hibernate chắc chắn sinh y nguyên. B-tree index thông thường có thể không hiệu quả cho wildcard đầu chuỗi. Với quy mô lớn:

- PostgreSQL có thể dùng `pg_trgm` và GIN/GiST indexes **nếu extension/feature được Azure cho phép**.
- SQL Server có thể dùng **full-text indexes** hoặc mô hình tìm kiếm phù hợp.
- Nếu yêu cầu search đa trường/ranking phức tạp, cân nhắc Azure AI Search như hệ tìm kiếm chuyên dụng.

Không thêm index mới trong production chỉ dựa trên một ví dụ. Xem query plans/IO, selectivity, write overhead và chi phí lưu trữ.

### 17.4. N+1 query với JPA relationships

Giả sử sau này Product có nhiều `ProductCategory` records. Khi code chạy:

~~~java
for (Product p : repository.findAll()) {
    // Nếu truy cập một lazy relation cho từng product:
    // p.getCategories().size();
}
~~~

Hibernate có thể phát **1 query lấy products + N queries lấy categories**. Khắc phục có thể là:

- DTO projections.
- `@EntityGraph` hoặc JPQL join fetch có kiểm soát.
- Batch fetching phù hợp.
- Tránh `EAGER` mọi quan hệ và trả entity thẳng ra JSON.
- Đếm JDBC SQL statements/latency trong integration tests.

Đặc biệt chú ý **join fetch collections + pageable**: có thể gây in-memory pagination hoặc kết quả không như mong đợi. Thực hành query plan/ORM metrics trên cả hai engine.

### 17.5. Batch writes và IDENTITY

`GenerationType.IDENTITY` thường đòi DB sinh ID khi insert, có thể giảm hiệu quả JDBC batching trong một số Hibernate versions. Khi cần ingest hàng triệu rows, cân nhắc sequence strategies theo engine, bulk SQL, `JdbcTemplate.batchUpdate` hoặc pipeline staging; đây là **tối ưu vendor-specific** cần benchmark, không thay đổi ID strategy tùy tiện khi bảng production đã có dữ liệu.

### 17.6. Cursor/streaming và query timeout

Không gọi `findAll()` để nạp 10 triệu rows vào JVM:

- Dùng paging/batch queries hoặc streaming có transaction lifecycle rõ.
- Giới hạn `size` và sort ổn định.
- Đặt JDBC statement/query timeout khi phù hợp.
- Theo dõi memory và transaction duration.
- Với read reports lớn, cân nhắc analytics store hoặc read replicas theo sản phẩm/tier, không lạm dụng OLTP DB.

**Azure SQL và PostgreSQL đều có giới hạn tài nguyên riêng**. Nâng số app replicas mà không sizing database/pool có thể làm query throughput xấu hơn vì thừa concurrent connections.

## 18. Observability: đo ở Spring Boot và Azure database

### 18.1. Ba tầng cần tương quan

~~~mermaid
flowchart LR
    A[HTTP request / trace ID] --> B[Spring Data repository]
    B --> C[HikariCP connection borrow]
    C --> D[JDBC round trip]
    D --> E[Azure SQL or PostgreSQL]
    M[OpenTelemetry / App Insights] -. metrics .-> A
    M -. metrics .-> B
    M -. metrics .-> C
    P[Azure Monitor / DB insights] -. CPU/IO/locks .-> E
~~~

Một request API chậm có thể do:

- JVM/Garbage Collection/serialization.
- Hikari pool chờ connection.
- SQL query thiếu index.
- Transaction bị lock/deadlock.
- Network/TLS/login/retry.
- Database CPU/IO hoặc tier throttling.
- Dependency ngoài DB bị chậm.

Đo từng tầng thay vì chỉ đọc một `500 Internal Server Error`.

### 18.2. Spring Boot Actuator và Micrometer

Với `spring-boot-starter-actuator`, ứng dụng có thể expose health/metrics, và Hikari/Micrometer có metrics pool (nếu autoconfiguration hỗ trợ). Những chỉ số nên theo dõi:

| Metric intent | Cần nhìn |
|---|---|
| HTTP latency p50/p95/p99 | Các API chậm theo route/status |
| JDBC/Hikari active/idle/pending | Pool gần giới hạn hoặc requests bị xếp hàng |
| Hikari acquisition time | Chờ borrow connection |
| JDBC query duration | Query/SQL dependency latency |
| Transaction failures/rollbacks | Lỗi commit/constraint/optimistic locking |
| Database CPU/IO/storage | Resource saturation |
| Deadlocks/blocked sessions | Concurrency/transaction design |
| DB logins/new connections | Connection churn/token refresh |
| Flyway startup duration/errors | Migration lock/schema permission |

**Không mặc định mọi metric trên tự có ngay khi thêm Actuator**: một số cần JDBC/OpenTelemetry instrumentation/agent hoặc custom metrics. Bảo vệ Actuator endpoints; không public `env`/`configprops`/`heapdump` ra Internet.

### 18.3. Application Insights/OpenTelemetry

Trong App Service/AKS/Container Apps có thể dùng **Azure Monitor OpenTelemetry instrumentation** hoặc Application Insights Java agent theo support model. Trace ID nên đi qua controller → repository → SQL dependency, nhưng không gửi **raw SQL parameter values, access tokens hoặc PII** vào traces. Dùng sampling có kiểm soát; request thất bại cần đủ correlation evidence.

Phân biệt:

~~~text
HTTP latency:       1,200 ms
Hikari wait:          800 ms
SQL execution:        150 ms
Other app processing: 250 ms
~~~

Nâng SQL vCores có thể không chữa Hikari pool exhaustion do số replicas/long transactions; cần kiểm tra **pool sizing và transaction lifetime**.

### 18.4. Azure SQL metrics và PostgreSQL metrics

**Azure SQL Database:** CPU/DTU hoặc vCore resource utilization, data IO/log IO, deadlocks, blocked sessions, Query Store, failed connections và alerts theo tier.

**PostgreSQL Flexible Server:** CPU, memory/storage, active connections, IOPS, query statistics/`pg_stat_statements` khi khả dụng, locks, replication/HA health và logs/diagnostics theo tính năng.

Đừng so trực tiếp “CPU 80% của Azure SQL” với “CPU 80% của PostgreSQL” như cùng một throughput. Query patterns, indexes, tiers và engine behavior khác nhau; benchmark trên workload thực.

### 18.5. Health check không được tạo outage

Spring Boot `/actuator/health` có thể kiểm tra DataSource và báo DOWN khi DB không kết nối. Để làm **readiness**, hành vi này có thể phù hợp; nhưng **liveness** không nên phụ thuộc trực tiếp một database đang tạm lỗi để container bị restart hàng loạt, gây reconnect storm.

Thiết kế:

- **Liveness:** tiến trình/JVM còn có thể vận hành.
- **Readiness:** instance có thể phục vụ requests theo dependencies/SLO.
- **Startup probe:** cho thời gian init/migrations/connection pool nếu cần.
- Database failure có thể dẫn đến giảm readiness/fallback tùy business.

Không mở readiness/liveness responses chứa database hostname/credentials.

## 19. Triển khai Spring Boot lên Azure mà không lộ secrets

### 19.1. Luồng kiến trúc tham khảo

~~~mermaid
flowchart TB
    USER[Web/mobile client] --> INGRESS[HTTPS ingress / API gateway]
    INGRESS --> APP[Spring Boot on App Service / Container Apps / AKS]
    APP -->|Outboard VNet egress| VNET[Private network and DNS]
    VNET --> SQL[(Azure SQL Database)]
    VNET --> PG[(PostgreSQL Flexible Server)]
    ID[Microsoft Entra / managed identity] -. auth token .-> APP
    KV[Key Vault if secrets required] -. scoped secret access .-> APP
    MIG[Approved migration job] -. Flyway + DDL principal .-> VNET
    MON[Azure Monitor / App Insights] -. observe .-> APP
    MON -. observe .-> SQL
    MON -. observe .-> PG
~~~

**Ứng dụng dùng một database theo profile**; hai mũi tên tới SQL và PG mô tả **hai môi trường lựa chọn**, không phải mọi request ghi đồng thời cả hai.

### 19.2. Azure App Service

Các bước chính:

1. Chọn App Service Plan/Java runtime hoặc container image phù hợp.
2. Gán **system-assigned/user-assigned managed identity** đúng application.
3. Cấu hình **VNet Integration outbound** nếu database private-only.
4. Thiết lập app settings: `SPRING_PROFILES_ACTIVE`, JDBC URL, non-secret settings.
5. Cấp Entra/database principal và DB grants riêng.
6. Nếu cần password lab, inject từ Key Vault References/secret manager, không đưa vào Docker image.
7. Tạo migration job/pipeline ở network được phép.
8. Triển khai app image, smoke-test GET/POST/PATCH và theo dõi logs/metrics.

**Đừng nhầm VNet Integration outbound với Private Endpoint inbound của App Service**. Một API có thể public HTTPS ingress nhưng database vẫn private-only; đó là hai luồng network độc lập cần review.

### 19.3. Azure Container Apps

- Container App environment có VNet/egress đúng topology.
- Gắn managed identity, inject configuration qua environment variables/secrets.
- Kiểm soát **maximum replicas × Hikari maximumPoolSize** để không vượt DB connection cap.
- Khi scale-to-zero/cold start, Entra token acquisition, DNS/TLS và database connection startup có thể ảnh hưởng latency.
- Không để mỗi replica chạy Flyway DDL khi nhận peak traffic nếu pipeline migration là thành phần riêng.
- Khi rolling release, chạy **backward-compatible schema migrations** trước khi rollout code.

### 19.4. AKS

- Dùng **Microsoft Entra Workload Identity** nếu được hỗ trợ cho app/SDK, tránh đặt secret dài hạn vào Kubernetes Secret không được quản lý đúng.
- Pod egress/NetworkPolicy, CoreDNS/Private DNS, NSG/UDR và firewall phải cho phép DB.
- HPA/cluster autoscaler cần đi kèm **database connection budget**; 50 pods × 30 connections dễ làm cạn DB.
- Readiness/liveness semantics phải rõ để DB downtime không gây restart toàn bộ Pod fleet.
- Migration có thể chạy như job riêng với identity/permission khác, có lock và retry policy.

### 19.5. Migration identity khác runtime identity

Thường thiết kế:

~~~text
ci-migration-principal:
  CREATE/ALTER/INDEX on approved schema
  executes Flyway once during controlled release

catalog-runtime-principal:
  SELECT/INSERT/UPDATE/DELETE only on required tables
  no CREATE/ALTER/DROP privileges
~~~

Nếu dùng Flyway **ngay startup** và runtime identity bị hạn chế DDL, app có thể fail khi migration cần thay schema. Giải pháp không phải cấp db_owner/superuser cho mọi app replicas; chạy migration trong pipeline có quyền/approval rồi cho application `ddl-auto=validate` và có thể tắt tự migrate ở runtime (`spring.flyway.enabled=false` khi dùng external migration job) theo quy trình đã định.

### 19.6. CI/CD theo hai profiles

~~~mermaid
flowchart LR
    PR[Git PR] --> UNIT[Unit tests]
    UNIT --> PGTEST[PostgreSQL Testcontainers]
    PGTEST --> SQLTEST[SQL Server Testcontainers]
    SQLTEST --> SCAN[Security/SBOM/secret scan]
    SCAN --> STAGING[Deploy app to Azure staging]
    STAGING --> STAGE_MIG[Apply migration with DDL principal]
    STAGE_MIG --> SMOKE[TLS/Entra/Private DNS CRUD tests]
    SMOKE --> APPROVE[Approval]
    APPROVE --> PROD_MIG[Backward-compatible prod migrations]
    PROD_MIG --> CANARY[Canary app rollout]
    CANARY --> OBS[Observe 5xx/latency/locks/pool]
~~~

Khi chia môi trường theo SQL Server/PostgreSQL, chạy test matrix riêng: ít nhất **cả hai vendor unit/integration suites** và staging smoke test của môi trường sẽ triển khai. Không phát hành migration SQL Server chỉ vì PostgreSQL tests xanh.

### 19.7. Production secret và config checklist

- App profiles/version/dialect đúng với DB.
- JDBC URL chỉ chứa host/database/options, không chứa password/token.
- TLS certificate validation bật và truststore cập nhật.
- Managed identity/DB role mapping được kiểm chứng.
- Runtime identity không có quyền DDL ngoài nhu cầu.
- Outbound private path hoạt động từ mỗi runtime/runner.
- Hikari pool sizing phù hợp số replicas và DB tier.
- Logs/Actuator/metrics không lộ credentials/SQL parameters nhạy cảm.
- Có connection and query timeout; không retry vô hạn.
- Có rollback plan cho cả app và schema changes.

## 20. Troubleshooting: xác định đúng lớp bị lỗi

### 20.1. Bảng triệu chứng thực tế

| Triệu chứng | Nguồn gốc có thể | Cách điều tra |
|---|---|---|
| `Failed to configure a DataSource` | Profile không bật/thiếu env URL/driver | Spring profiles, `application-*.yml`, effective config |
| `No suitable driver` | Sai driver dependency hoặc JDBC prefix | Maven dependency tree, driver class, JDBC URL |
| `PKIX path building failed` | CA chain/truststore JVM hoặc certificate | JDK truststore, TLS hostname, SSL options |
| SQL Server login failed `18456` | SQL/Entra principal không hợp lệ | Entra admin/db contained user, grants, auth mode |
| SQL firewall access denied / timeout | Public firewall/private endpoint/DNS | Network mode, DNS từ runtime, TCP 1433 |
| PostgreSQL `28P01` auth failed | Password/token expired, role map sai | DB user, token audience, managed identity |
| PostgreSQL `42501` insufficient privilege | Login được nhưng thiếu GRANT | Schema USAGE, table/sequence grants |
| SQL Server permission denied | SQL login được, thiếu quyền object | DB roles, object-level grants |
| PostgreSQL `42P01` relation does not exist | Flyway chưa tạo table hoặc sai schema | `spring.flyway.locations`, search_path/schema |
| SQL Server invalid object name | Wrong database/schema, migration chưa chạy | `databaseName`, `dbo`, schema history |
| `FlywayValidateException` | Migration sửa sau đã apply/checksum mismatch | History, immutable migration policy |
| `Schema-validation: missing table/column` | Entity/DDL lệch hoặc wrong DB profile | Inspect migrations, dialect, table schema |
| `HikariPool - connection not available` | Pool chờ/DB slow/login chậm | Active/idle/pending, long transactions |
| SQL Server deadlock victim `1205` | Hai transactions tranh locks | Query Store/deadlock graph, lock order |
| PostgreSQL `40P01` deadlock | Thứ tự lock/transaction dài | PostgreSQL logs/pg_stat_activity |
| PostgreSQL `40001` serialization failure | Isolation conflict | Retry whole transaction if idempotent |
| Unique constraint conflict | Trùng SKU/data race | DB index, 409 API mapping |
| JPA optimistic locking exception | Bản ghi đã đổi trong transaction khác | Client concurrency token/retry design |
| Hibernate LazyInitializationException | Quan hệ lazy bị truy cập ngoài transaction | DTO projection/transaction scope |
| 5xx tăng sau scale-out | Pool × replicas vượt DB budget | DB connection limits, HPA/Hikari sizing |
| p95 chậm sau migration | Missing index/query plan/collation | Explain/Query Store, compare query patterns |
| Works locally, fails in Azure | VNet/DNS/MI khác local | Test network/identity từ deployed runtime |

### 20.2. Chẩn đoán từ phía ứng dụng tới database

**Bước 1 — Scope:** đúng Spring profile, database service/region/server FQDN và deployment version?

**Bước 2 — Config:** có `spring.datasource.url` và driver đúng? Database name/schema đúng?

**Bước 3 — Network:** DNS trả private IP dự kiến; TCP port và route thông?

**Bước 4 — TLS:** chain/hostname/JVM truststore hợp lệ; không dùng `trustServerCertificate=true`/`sslmode=disable`?

**Bước 5 — Authentication:** SQL login/Entra token/PG role đúng? Token refresh khi connections mới?

**Bước 6 — Authorization:** có SELECT/INSERT trên bảng? App không cần DDL; migration job có DDL?

**Bước 7 — Schema:** Flyway history/version, SQL dialect, column datatype và Hibernate validation?

**Bước 8 — Runtime:** Hikari active/idle/pending, query durations, deadlocks, IO/CPU/throttle?

**Bước 9 — Business correctness:** optimistic lock, duplicate rows, idempotency và transaction outcome?

**Bước 10 — Recovery:** kiểm tra API test, database state, metrics, update runbook và remove temporary exceptions.

### 20.3. Lỗi TLS không phải lý do tắt bảo mật

Nếu PostgreSQL báo certificate verification failed:

~~~text
JDBC URL: jdbc:postgresql://10.0.0.12:5432/catalogdb?sslmode=verify-full
Observation: certificate issued for server FQDN, not private IP.
~~~

Sửa thành **FQDN chuẩn** với Private DNS trỏ IP có route, và cập nhật CA/truststore. Tương tự với SQL Server: dùng `*.database.windows.net` theo connection policy/certificates, không hạ `trustServerCertificate=false`.

### 20.4. Lỗi database credential không giống network

~~~text
TCP 5432 succeeded
TLS handshake verified
PostgreSQL login SQLSTATE 28P01
~~~

Mạng/TLS đã đi qua; điều tra database role/token/password, Entra configuration và application pool credential refresh. Tạo Private Endpoint thứ hai thường không chữa lỗi đăng nhập.

### 20.5. Lỗi optimistic lock khác unique conflict

- **Unique conflict** xảy ra khi hai requests tạo cùng SKU; database unique index bảo vệ.
- **Optimistic lock** xảy ra khi hai transactions sửa cùng entity version cũ; JPA version bảo vệ.
- **Database deadlock** có thể xảy ra khi lock resources theo thứ tự khác nhau; cần thay transaction/query và retry có kiểm soát.

Không trả tất cả thành HTTP 500. Mapping API phải có **409 conflict** khi đúng semantics; lỗi database unavailable có thể thành 503 với policy retry an toàn, nhưng không tiết lộ raw internals.

### 20.6. Cẩn trọng với các lệnh chẩn đoán có side effects

Tránh “test connection” bằng cách:

~~~sql
DROP TABLE products;
DELETE FROM products;
~~~

Chỉ kiểm tra health bằng **SELECT/metadata read** trong môi trường được phép; không dump table chứa PII hoặc reset migration history. Khi debug production, không tăng SQL logging để ghi mọi parameter có dữ liệu khách hàng.

## 21. FinOps: kết nối database đúng còn phải tiết kiệm chi phí

### 21.1. Tổng chi phí không chỉ là giá mỗi GB

| Thành phần | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Compute | vCore/DTU/tier/serverless/elastic pool theo lựa chọn | vCores/compute tier, scaling/HA |
| Storage | Data/log storage, backup/retention | Storage, backup, log/IO features |
| Networking | Private Endpoint, DNS, egress/Firewall | Private networking, DNS, egress |
| High availability | Geo/replication/availability theo tier | HA/standby/PITR/replicas theo cấu hình |
| Application | App Service/Container Apps/AKS, replicas, CPU/RAM | Tương tự |
| Observability | Query Store, logs, Azure Monitor/App Insights | Server logs/monitoring/pg stats |
| Operations | Schema migration, permissions, restore tests | Schema migration, extensions, restore tests |

Giá phụ thuộc **region, thời điểm, tier, storage/HA configuration và reservations/commitments**. Dùng Azure Pricing Calculator và Cost Management thay vì lấy một con số cố định từ ví dụ.

### 21.2. Chi phí ẩn của pool quá lớn

Giả sử 40 app replicas với `maximumPoolSize=20`:

\[
40\times20=800\ \text{potential DB connections}.
\]

Nếu DB tier chỉ có ngân sách connections thấp hơn và mỗi request tranh kết nối, team có thể tưởng cần nâng DB compute gấp đôi. Thử **pool sizing, transaction optimization, query indexing và scale limit** trước khi mua thêm capacity. Với PostgreSQL, có thể đánh giá connection pooling/proxy được dịch vụ hỗ trợ khi phù hợp, nhưng phải test transaction/session semantics, prepared statements và auth.

### 21.3. Query thiếu index làm tăng cả latency và bill

Khi `findBySku` không có index:

~~~text
Average query duration:       150 ms
DB CPU high under peak
Hikari active connections:    near max
API p95:                      >1 second
~~~

Sau khi tạo index đúng (và kiểm tra write tradeoff):

~~~text
Query duration may drop materially
Connections return to pool faster
Fewer vCores/replicas may be needed
~~~

Đây là **mô hình nhân quả**, không phải cam kết giảm 10× trên mọi dataset. Benchmark với **actual plan, data size, distribution và read/write mix**. Nhiều indexes cũng tăng write IO/maintenance cost.

### 21.4. Serverless, scale-to-zero và connection storms

Nếu Azure SQL/serverless tier tạm dừng theo chính sách, lần kết nối đầu sau idle có thể chịu **cold resume latency**. Nếu hàng trăm app instances cùng startup/scale, chúng có thể tạo login storm. Thiết kế:

- Startup/readiness grace phù hợp.
- Retry connect với exponential backoff/jitter và giới hạn.
- Hikari minimumIdle không quá lớn khi có nhiều replicas.
- Workload warm-up đúng business SLO.
- Không tự enable auto-pause cho service không chấp nhận cold start.

Flexible Server có các compute/stop/start behaviors riêng theo tier; không sao chép SQL Database serverless semantics sang PostgreSQL như thể giống nhau.

### 21.5. Budget và governance

- Tag resources theo `application`, `environment`, `owner`, `costCenter`.
- Review chi phí database compute, storage, HA, backup và private network.
- Giám sát cost tăng khi deployment tăng replicas/pool/connections.
- Định nghĩa retention/backup theo RPO, không giảm bừa để tiết kiệm.
- Test restore có chi phí và cần scope được phê duyệt.
- Xóa **lab resources riêng** sau buổi học, không xóa shared database/schema.
- Budget alerts **không tự là hard cap**; cần owner và hành động.

**FinOps đúng:** tối ưu tổng chi phí để đạt **business correctness, p95 latency, availability và recovery objectives**, không chỉ chọn database tier rẻ nhất.

## 22. Case study: Product Catalog đa khách hàng, hai database engines

### 22.1. Yêu cầu

Một nhà cung cấp SaaS có **cùng Spring Boot codebase** phục vụ hai khách hàng doanh nghiệp:

| Thuộc tính | Khách hàng A | Khách hàng B |
|---|---|---|
| Database | Azure SQL Database | PostgreSQL Flexible Server |
| Hosting | Azure App Service | Azure Container Apps |
| Connectivity | Private Endpoint + App Service VNet Integration | Flexible Server private network + Container Apps VNet |
| Authentication | Managed identity/Entra | Managed identity/Entra, PG role + token |
| Data model | Product ID, SKU, name, price, version | Cùng domain |
| Schema migrations | Flyway SQL Server | Flyway PostgreSQL |
| Monitoring | App Insights + Azure SQL metrics | App Insights + PostgreSQL metrics |
| Target p95 | GET product dưới 200 ms | GET product dưới 200 ms |
| Availability | Product API quan trọng, DB failure phải lộ rõ health | Tương tự |

Yêu cầu nghiệp vụ:

- SKU unique trong từng database.
- Lưu giá bằng decimal chính xác.
- Người dùng A/B không nhìn dữ liệu của nhau.
- Hai requests sửa giá đồng thời không được âm thầm mất thay đổi.
- Migrations/backup/DR có owner và evidence.
- Không lưu mật khẩu DB trong Git, Docker image hoặc REST response.
- Có kế hoạch rollback release mà không phá schema trên production.

### 22.2. Thiết kế triển khai

~~~mermaid
flowchart LR
    subgraph TENANT_A[Customer A isolated environment]
      AAPP[App Service + sqlserver profile] --> ANET[VNet Integration]
      ANET --> ADB[(Azure SQL Database)]
      AID[Managed Identity A] -. JDBC Entra Auth .-> AAPP
    end
    subgraph TENANT_B[Customer B isolated environment]
      BAPP[Container Apps + postgres profile] --> BNET[Private VNet/DNS]
      BNET --> BDB[(PostgreSQL Flexible Server)]
      BID[Managed Identity B] -. PG token provider .-> BAPP
    end
    GIT[Single Java source + vendor Flyway migrations] --> AAPP
    GIT --> BAPP
~~~

**Cô lập môi trường có chủ đích**: mỗi khách hàng có runtime/DB principal/database phù hợp. Profile không phải ranh giới bảo mật nếu hai credentials được cấp quyền đọc chung một database; authorization và network isolation vẫn cần kiểm tra.

### 22.3. Release v1: tạo schema

1. Migrate SQL Server bằng `db/migration/sqlserver/V1__create_products.sql` trên database A.
2. Migrate PostgreSQL bằng `db/migration/postgres/V1__create_products.sql` trên database B.
3. Test table/unique index/permissions bằng đúng engine.
4. Deploy Spring Boot image **cùng source version** với hai profiles.
5. Validate Flyway history và JPA `ddl-auto=validate` không tự chỉnh schema.
6. Test CRUD/TLS/managed identity trên app runtime tương ứng.

**Không chạy cả hai migrations vào cùng database**. Khi A dùng Entra JDBC driver authentication, B dùng PG token integration, phải test hai auth flows riêng, kể cả token rotation theo giờ và pool scaling.

### 22.4. Sự cố 1: ứng dụng B chạy 1 giờ rồi không kết nối được

Triệu chứng:

~~~text
09:00 Container Apps starts; app creates pool with PostgreSQL Entra token.
09:05 GET /products succeeds.
10:10 DB connections are recycled after scale/failover.
10:10 New connections fail with authentication error.
~~~

Nguyên nhân: app B đã copy access token một lần vào `spring.datasource.password` khi startup; **token hết hạn** nhưng new Hikari connections tiếp tục dùng token cũ. Hướng xử lý:

1. Tách auth lỗi khỏi DNS/TLS bằng connection/SQLSTATE evidence.
2. Xác minh token audience, object identity, mapped PostgreSQL role.
3. Triển khai **supported passwordless credential provider** tạo token mới cho mỗi connection cần auth; cache/refresh trước expiry.
4. Load test qua ít nhất một token cycle và connection churn.
5. Không đổi toàn bộ DB sang static password như giải pháp lâu dài không review.

### 22.5. Sự cố 2: App Service A không truy cập Azure SQL sau chuyển private-only

Triệu chứng:

~~~text
Azure SQL has Private Endpoint.
Public access is disabled.
Developer laptop on VPN can connect.
App Service JDBC times out.
~~~

Nguyên nhân có thể: **App Service chưa có outbound VNet Integration**, VNet/Private DNS link sai hoặc route/NSG chặn. Kiểm tra từ runtime A, không kết luận vì laptop connect được. Sửa VNet Integration/Private DNS/TCP 1433 theo architecture. Không bật public access rộng để “test nhanh”.

### 22.6. Sự cố 3: hai người sửa giá

~~~text
User A reads SKU-001, price 1,200,000, version 8.
User B reads SKU-001, price 1,200,000, version 8.
User B updates to 1,150,000, version 9.
User A submits old UI form with price 1,180,000.
~~~

Với API demo hiện tại, server tải entity version 9 khi nhận PATCH; `@Version` không ngăn người A overwrite ý định của người B chỉ vì UI A xem dữ liệu cũ từ trước. Để bảo vệ **cross-request concurrency**, API phải nhận expected version (hoặc `If-Match` ETag) và kiểm tra:

~~~java
// Illustrative fragment inside a transactional service method.
Product p = repository.findBySku(sku).orElseThrow();
if (!java.util.Objects.equals(p.getVersion(), expectedVersion)) {
    throw new org.springframework.dao.OptimisticLockingFailureException(
        "Product changed since client read it");
}
p.changePrice(newPrice);
repository.saveAndFlush(p);
~~~

`expectedVersion`/`newPrice` phải được bổ sung vào API contract và validated, không mặc nhiên tồn tại trong `updatePrice` demo. Database-level `@Version` vẫn cần thiết để phát hiện race **sau khi kiểm tra expected version**, trước commit.

### 22.7. Sự cố 4: tìm kiếm Unicode khác nhau

Ở SQL Server, collation của DB có thể **case-insensitive/accent-insensitive**; ở PostgreSQL, `lower(name) like ...` có quy tắc khác. Search `"ca phe"` có thể trả kết quả khác cho `"Cà phê"`. Không sửa bằng cách xóa dấu trong toàn bộ nguồn dữ liệu; xác định business search semantics, lựa chọn collation/index/search engine và viết **contract tests** cho hai profiles.

### 22.8. Canary gate trước release v2

| Kiểm tra | Điều kiện pass |
|---|---|
| Flyway migrations | Không lỗi, history đúng, schema validate |
| Login và TLS | Entra/DB principal đúng, verify server cert |
| Private network | DNS/TCP từ đúng runtime, public denied theo policy |
| CRUD | Create/read/update, duplicate SKU 409 |
| Concurrency | Expected version + JPA optimistic lock test pass |
| Unicode | Product name/search theo semantics đã chấp thuận |
| Performance | p95 và DB CPU/IO đạt mục tiêu |
| Hikari | Active/pending và connection churn không có timeout |
| Reliability | DB failover/reconnect có bounded retry |
| Security | No secrets/PII logs, DDL identity khác app identity |

**Kết luận:** một codebase Spring Data có thể phục vụ Azure SQL và PostgreSQL, nhưng chỉ khi **database-specific DDL, identity/TLS/network, Unicode semantics và integration tests** được quản lý như những hợp đồng riêng.

## 23. Lab thực hành từ đầu tới cuối

Lab chỉ dành cho **subscription/DB dùng thử đã được phê duyệt**. Nếu không có quyền tạo tài nguyên Azure, người học vẫn có thể hoàn thành phần thiết kế SQL/JPA và Testcontainers trên máy cá nhân được phép; không mở firewall trên database người khác.

### 23.1. Lab A — PostgreSQL Flexible Server

1. Nhận server FQDN, database name và database role có quyền test.
2. Kiểm tra network mode (public firewall theo source IP cho lab hoặc private path) và TCP 5432.
3. Xác nhận `sslmode=verify-full` và truststore/certificate.
4. Tạo schema bằng Flyway với **migration principal**.
5. Đặt `SPRING_PROFILES_ACTIVE=postgres`, inject JDBC URL/user/password lab từ secret store.
6. Start Spring Boot và xem logs có kết nối/Flyway success mà không lộ secret.
7. Gọi REST CRUD API.
8. Kiểm tra SQL rows/index/constraints qua client DBA riêng.
9. Thử invalid credentials/blocked firewall trong lab; xác nhận lỗi phân tầng.
10. Nếu có Entra, đổi sang passwordless integration và test token refresh trên long-running app.

### 23.2. Lab B — Azure SQL Database

1. Nhận Azure SQL logical server, database name và network path.
2. Kiểm tra FQDN/port 1433, Private DNS và TLS `encrypt=true;trustServerCertificate=false`.
3. Tạo schema bằng Flyway migration `sqlserver/V1__...sql`.
4. Đặt `SPRING_PROFILES_ACTIVE=sqlserver`, inject credentials lab hoặc bật profile managed identity.
5. Test REST CRUD giống lab A.
6. Kiểm tra UTF-8/Unicode names, identity ID, version column.
7. Xác minh unique SKU index và HTTP 409 khi insert trùng.
8. Thực hành `SELECT`/Query Store hoặc execution plan bằng quyền đọc được phép.
9. Nếu dùng MI, kiểm tra Entra contained user/DB grants và credential-free startup.
10. Chỉ sau khi private path hoạt động, test disabled public access theo change policy.

### 23.3. Ví dụ kiểm thử HTTP

Với ứng dụng lab chạy ở `http://localhost:8080` và API đã được bảo vệ hoặc chạy local:

~~~bash
curl -i -X POST "http://localhost:8080/products" \
  -H "Content-Type: application/json" \
  -d '{"sku":"DEMO-001","name":"Cà phê Việt Nam","price":125000.00}'

curl -i "http://localhost:8080/products/DEMO-001"

curl -i "http://localhost:8080/products?name=C%C3%A0&page=0&size=20"

curl -i -X PATCH \
  "http://localhost:8080/products/DEMO-001/price" \
  -H "Content-Type: application/json" \
  -d '{"price":127500.00}'
~~~

**Những lệnh trên ghi dữ liệu vào database đang cấu hình**; chỉ dùng DB lab/synthetic data. Nếu lần đầu insert thành công, chạy lại POST cùng SKU sẽ nhận conflict; đó là expected unique constraint behavior, không phải fail ngẫu nhiên.

### 23.4. Câu hỏi tự kiểm tra lab

- Có đổi **code Java** giữa hai profiles không, hay chỉ đổi config/migrations?
- Nếu app dùng SQL Server URL với PostgreSQL driver, lỗi xảy ra trước hay sau authentication?
- Tại sao `ddl-auto=validate` và Flyway là hai cơ chế khác nhau?
- Tại sao username/password được SQL Server chấp nhận không đồng nghĩa token Entra user có quyền `SELECT`?
- Đâu là bằng chứng đã đạt TLS hostname verification thay vì chỉ TCP open?
- Nếu application đổi giá sau khi browser giữ dữ liệu cũ, `@Version` đã bảo vệ đủ chưa?
- Khi tăng từ 5 lên 50 replicas, tính lại Hikari pool như thế nào?
- Điều gì khiến 1 migration SQL Server không thể dùng y nguyên cho PostgreSQL?

### 23.5. Tiêu chí hoàn thành

| Điều kiện | Bằng chứng |
|---|---|
| `application-sqlserver.yml`/`application-postgres.yml` đúng | Profile chạy độc lập |
| Flyway migrations đúng engine | Schema history, tables/indexes, `ddl-auto=validate` |
| JPA mapping đúng | CRUD ID/decimal/Unicode/version |
| Unique SKU | Database từ chối duplicate |
| Paging | Max size 100, sort ổn định |
| TLS | Verify chain và hostname từ runtime |
| Identity | App principal có DML, migration principal có DDL |
| Private network | DNS/route/TCP đúng, policy public access |
| Monitoring | Hikari + API + DB metrics |
| Operational | Backups/rollback/cleanup plan |

## 24. Bài tập tổng hợp và đáp án định hướng

### 24.1. Đề bài

1. Giải thích **Spring Data JPA** khác **Spring Data JDBC** thế nào.
2. Vẽ chuỗi Controller → Service → Repository → Hibernate/JDBC → Hikari → Azure DB.
3. Phân biệt Azure SQL Database với SQL Server trên VM.
4. Phân biệt PostgreSQL Flexible Server public networking với private VNet-injected networking.
5. Viết JDBC URL cho Azure SQL có TLS hostname verification.
6. Viết JDBC URL PostgreSQL có `sslmode=verify-full` và Java truststore.
7. Giải thích `SPRING_PROFILES_ACTIVE` và rủi ro bật cả hai profiles.
8. Liệt kê Maven dependencies cho Spring Data JPA, drivers và Flyway.
9. Viết hai Flyway migrations tạo Product với ID auto increment và giá decimal.
10. Giải thích `@Id`, `@GeneratedValue(IDENTITY)`, `@Version`, `@Nationalized`.
11. Viết repository method tìm product theo SKU.
12. Viết pageable search và giới hạn size.
13. Tại sao `@Transactional(readOnly=true)` không thay database read-only role?
14. Viết trường hợp mất update mà `@Version` phát hiện được.
15. Giải thích tại sao `@Version` không đủ để chống stale UI editing xuyên HTTP.
16. Nêu cách SQL Server/Pg khác nhau khi search Unicode không phân biệt hoa/thường.
17. Giải thích nguyên nhân và cách tránh JPA N+1.
18. So sánh `BigDecimal` với `double` khi lưu tiền.
19. Tính total connections nếu 25 replicas × Hikari 12 connections.
20. Phân tích PG token hết hạn khi pool tạo new connections.
21. Giải thích Entra managed identity ở SQL Server khác Pg JDBC token-as-password.
22. Vì sao Azure Contributor không tự có `SELECT`?
23. Viết sequence check DNS → TCP → TLS → auth → grants.
24. Thiết kế CI/CD với migrations trước rollout và canary.
25. Nêu các metrics cho pool saturation vs slow SQL.
26. Viết retry policy cho serialization/deadlock mà không double-charge.
27. Giải thích khi nào cần Testcontainers và khi nào Azure staging.
28. Tính chi phí/risks khi mở rộng từ 5 lên 50 app replicas.
29. Thiết kế backup/restore test và data migration strategy khi đổi vendor.
30. Liệt kê những lệnh/thao tác không được chạy trên production chỉ để học.

### 24.2. Một số đáp án

**Câu 5 — Azure SQL URL:**

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;
~~~

**Câu 6 — PostgreSQL URL:**

~~~text
jdbc:postgresql://my-pg-server.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory
~~~

**Câu 11 — Spring Data Repository:**

~~~java
Optional<Product> findBySku(String sku);
~~~

**Câu 19 — pool:** 25 × 12 = **300 potential app connections**, chưa tính migration/DBA/monitoring. Nếu DB connection budget thấp hơn, cần giảm pool/review scale/tier.

**Câu 20 — PG Entra:** token ngắn hạn không được giữ cố định trong Hikari password. Cần credential provider/new-connection token refresh hoặc Spring Cloud Azure integration được kiểm chứng.

**Câu 21 — auth:** Microsoft SQL JDBC Driver có `authentication=ActiveDirectoryManagedIdentity` khi phù hợp; PG JDBC dùng DB username/role + token trong password field do integration cấp/refresh.

**Câu 24 — release:** chuẩn bị DDL expand migration tương thích, chạy bằng DDL principal trong private runner, smoke test, canary app rollout, đo SQL/PG performance, rollback image hoặc forward-fix migration đã có data.

**Câu 26 — retry:** chỉ retry whole transaction với backoff/jitter cho lỗi transient được phân loại, có idempotency key nếu nghiệp vụ có side effects. Không retry 400/unique conflict vô hạn.

### 24.3. Rubric

| Tiêu chí | Điều kiện đạt |
|---|---|
| **Spring Data** | Phân biệt JPA/JDBC, repository/transaction |
| **Database portability** | Vendor dialect/migrations/Unicode/locking được kiểm chứng |
| **Security** | TLS verify-full, Private DNS, Entra/DB grants tách RBAC |
| **Data integrity** | Unique constraints, decimal, optimistic lock/idempotency |
| **Reliability** | Pool sizing, retry, failover và backup/restore strategy |
| **Testing** | Testcontainers cả hai dialect + Azure staging smoke |
| **Observability** | HTTP/pool/query/DB metrics |
| **FinOps** | Sizing connections, compute, storage, HA và budget |

## 25. Checklist trước, trong và sau khi triển khai production

### 25.1. Kiến trúc và lựa chọn dịch vụ

- [ ] Xác định ứng dụng dùng **Azure SQL Database** hay **PostgreSQL Flexible Server** tại mỗi deployment.
- [ ] Chọn tier/region/HA/backup/compute theo SLO, RPO/RTO và budget.
- [ ] Có business/data owners và data classification.
- [ ] Có authoritative database, không sao chép cache hoặc event bus như bản ghi giao dịch duy nhất.
- [ ] Có kiến trúc private/public networking rõ, DNS và runtime egress.
- [ ] Không thiết kế một `@Transactional` cho hai database khác nhau mà chưa có distributed consistency strategy.

### 25.2. Application và schema

- [ ] Chốt Java/Spring Boot/driver/Flyway versions được hỗ trợ, kiểm tra security advisories.
- [ ] Có đúng một vendor profile active tại mỗi deployment.
- [ ] JDBC URL đúng driver/host/port/database/dialect.
- [ ] Flyway scripts riêng SQL Server/PostgreSQL, đã review và test.
- [ ] Hibernate `ddl-auto=validate`; không tự thay production schema.
- [ ] Entity mapping Unicode/numeric/UTC/timestamp/IDENTITY/version được test cho cả hai engines.
- [ ] Unique constraints/indexes đặt ở database, không chỉ trong service code.
- [ ] DTO/Bean Validation và REST errors an toàn; không expose entity/SQL exceptions.
- [ ] Paging có giới hạn và ổn định; query indexes được đo trên dữ liệu gần thật.
- [ ] Test concurrent writes/optimistic locking/HTTP stale version semantics.

### 25.3. Bảo mật và mạng

- [ ] Azure SQL `encrypt=true;trustServerCertificate=false`.
- [ ] PostgreSQL `sslmode=verify-full` với truststore/CA đúng.
- [ ] FQDN chuẩn và Private DNS resolve đúng từ **runtime**.
- [ ] App Service/Container Apps/AKS có outbound network path; CI migration runner cũng kết nối được.
- [ ] Public network access/firewall giới hạn theo policy, không có exception rộng còn sót.
- [ ] Microsoft Entra principal và **DB user/role/grants** được cấu hình đúng.
- [ ] Entra managed identity/token refresh đã được test qua pool connection churn.
- [ ] App principal chỉ có DML cần thiết; migration principal mới có DDL.
- [ ] No password/token/SQL parameters nhạy cảm trong Git, images, logs, dumps.
- [ ] Key Vault/secret store có least privilege và rotation plan nếu dùng mật khẩu.

### 25.4. Hiệu năng và vận hành

- [ ] Hikari pool × max app replicas nằm trong connection budget.
- [ ] Connection, query và request timeouts được thiết kế nhất quán.
- [ ] Retry transient lỗi có backoff/jitter/idempotency, không làm double-write.
- [ ] Long transactions, N+1 queries, missing indexes và offset paging sâu đã được đánh giá.
- [ ] Có readiness/liveness phù hợp, không restart storm khi DB outage.
- [ ] HTTP p95/p99, pool active/pending, DB CPU/IO/locks/deadlocks được monitor.
- [ ] App Insights/OpenTelemetry không ghi secrets/PII.
- [ ] Alerts có owner, runbook, SLO và suppress/threshold phù hợp.
- [ ] Test PITR/backup restore và failover của database theo business RPO/RTO.
- [ ] Có plan scale/HA/DR, không chỉ một instance mặc định.

### 25.5. Release

- [ ] Testcontainers/CI chạy migrations và repository tests cho **cả hai engines**.
- [ ] Staging Azure có thử TLS/Entra/Private DNS/permissions thật.
- [ ] Migration production được approved và chạy qua identity có DDL.
- [ ] Schema change tương thích ngược với app phiên bản cũ trong rolling deployment.
- [ ] Rollout canary, theo dõi lỗi 5xx, Hikari pending, query latency/DB throttling.
- [ ] Plan rollback ứng dụng và **forward-fix schema** khi migration đã có dữ liệu.
- [ ] Có người xác nhận dữ liệu sau deploy, tránh chỉ nhìn trạng thái container xanh.

### 25.6. Khi có incident

- [ ] Xác nhận đúng database engine/profile/subscription và resource IDs.
- [ ] Phân biệt DNS → TCP → TLS → authentication → authorization → SQL/schema.
- [ ] Xác nhận outage/pool starvation/slow SQL/tranh lock trước khi scale.
- [ ] Không mở public firewall rộng, cấp db_owner hay tắt TLS để “chữa nhanh”.
- [ ] Lưu evidence không chứa secret/PII, trace DB error theo correlation ID.
- [ ] Kiểm tra transaction outcome trước retry operation ghi dữ liệu.
- [ ] Xác minh backup/DR khi nghi ngờ mất dữ liệu.
- [ ] Sau recovery, test business correctness, đóng temporary exceptions và cập nhật runbook.

## 26. Dọn dẹp lab và tránh xóa nhầm database

Azure SQL và PostgreSQL Flexible Server có thể **tiếp tục tính phí** ngay cả khi Spring Boot đã dừng. Nhưng database production, private DNS zone, VNet hay resource group có thể là tài nguyên **dùng chung**, không được tự xóa chỉ vì muốn dọn lab.

### 26.1. Kiểm kê resource bằng lệnh chỉ đọc

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table

# Azure SQL server; thay các giá trị bằng resource lab được phép.
az sql server show \
  --resource-group "<approved-lab-resource-group>" \
  --name "<lab-sql-logical-server>" \
  --output json

# PostgreSQL Flexible Server; lệnh chỉ đọc.
az postgres flexible-server show \
  --resource-group "<approved-lab-resource-group>" \
  --name "<lab-pg-flexible-server>" \
  --output json
~~~

Các lệnh trên **không thay đổi tài nguyên** nhưng cần quyền đọc. Không coi một resource có tên `dev` hoặc `test` là chắc chắn disposable; kiểm tra owner/dependencies.

### 26.2. Quy trình cleanup

1. Xác nhận đúng **subscription/resource group/server/database** và owner.
2. Kiểm kê ứng dụng/CI/DBA/reporting có đang dùng database không.
3. Xác nhận retention/backup/export cần thiết trước khi xóa.
4. Thu hồi secrets, xóa **riêng principal/test data** theo change approval.
5. Đóng lab firewall exceptions/public access được tạo tạm.
6. Chỉ xóa **tài nguyên riêng lab** (database/server/Private Endpoint) khi chắc chắn không dùng chung.
7. Không xóa Private DNS zone/Resolver/VNet/Key Vault dùng chung với production.
8. Xem Cost Management để phát hiện DB compute, backups, Private Endpoints/logs còn tính phí.
9. Lưu lab findings/SQL migration version/lessons learned, không lưu password/token trong báo cáo.

Ví dụ lệnh xóa **được comment và không yêu cầu thực thi**:

~~~bash
# KHÔNG CHẠY trên production hay tài nguyên chưa có approval.
# az sql db delete --resource-group "<rg>" --server "<server>" \
#   --name "<lab-database>" --yes

# az postgres flexible-server delete \
#   --resource-group "<rg>" --name "<lab-server>" --yes

# Chỉ khi resource group 100% dành riêng cho lab và mọi owner đồng ý.
# az group delete --name "<approved-lab-resource-group>" --yes
~~~

**Không để Flyway test cleanup bằng `DROP SCHEMA` trên database thật**. Testcontainers tạo/làm sạch database ephemeral riêng; environment variables/profile sai có thể khiến test chạy migrations vào Azure production nếu không có guardrail.

### 26.3. Guardrails cho các lệnh SQL nguy hiểm

Những lệnh sau **không dùng để debug kết nối**:

~~~sql
DROP TABLE products;
TRUNCATE TABLE products;
DELETE FROM products;
~~~

Muốn kiểm tra kết nối, chọn bảng/DB lab và chạy `SELECT` không có side effects, ví dụ:

~~~sql
SELECT COUNT(*) FROM products;
~~~

Nếu một database được chia sẻ, query `COUNT(*)` trên bảng cực lớn cũng có thể tạo tải; ưu tiên health probe nhẹ và review quyền. Không xóa `flyway_schema_history` để “chạy lại V1” trên production.

## 27. Tài liệu tham khảo và ghi nhớ

### 27.1. Tài liệu kỹ thuật

Khi triển khai thật, tra cứu tài liệu **đúng phiên bản** Spring Boot, driver và dịch vụ Azure:

- [Spring Data JPA reference](https://docs.spring.io/spring-data/jpa/reference/) — repository methods, projections, paging, transaction integration.
- [Spring Boot data access reference](https://docs.spring.io/spring-boot/reference/data/sql.html) — DataSource/Hikari/JPA/Flyway.
- [Hibernate ORM documentation](https://hibernate.org/orm/documentation/) — dialect, mapping, optimistic locking.
- [Flyway documentation](https://documentation.red-gate.com/fd) — versioned migrations, database support, schema history.
- [Microsoft JDBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server) — driver, authentication, TLS và connection properties.
- [Microsoft Entra authentication with Microsoft JDBC Driver](https://learn.microsoft.com/sql/connect/jdbc/connecting-using-azure-active-directory-authentication) — managed identity/identity selection và prerequisites.
- [Azure SQL Database connectivity](https://learn.microsoft.com/azure/azure-sql/database/connectivity-architecture) — networking/connection policies.
- [Azure SQL Microsoft Entra authentication](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview) — principals/data-plane permissions.
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — connectivity/networking/HA.
- [PostgreSQL Flexible Server Microsoft Entra authentication](https://learn.microsoft.com/azure/postgresql/flexible-server/how-to-configure-sign-in-azure-ad-authentication) — Entra principals và token login.
- [PostgreSQL JDBC documentation](https://jdbc.postgresql.org/documentation/) — `sslmode`, SSL factory, parameters và type mapping.
- [Azure Spring and Java developer documentation](https://learn.microsoft.com/azure/developer/java/) — managed identity, deployment và SDK compatibility.
- [Spring Testcontainers documentation](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — realistic DB integration testing.

**Lưu ý:** URLs và feature availability có thể thay đổi. Trước khi dùng Maven version, Spring Cloud Azure passwordless starter, SQL Server managed identity authentication, PostgreSQL Entra role mapping hoặc networking mode trong production, hãy xem tài liệu Microsoft/Spring/driver release phù hợp và chạy kiểm thử thật. Không dùng ví dụ này thay chính sách bảo mật hay quyền DBA.

### 27.2. Mười hai nguyên tắc cốt lõi

1. **Spring Data là abstraction truy cập dữ liệu**, không xóa mọi khác biệt SQL Server/PostgreSQL.
2. **Một vendor profile tại một deployment:** JDBC driver, dialect, Flyway locations và database permissions phải nhất quán.
3. **DDL vendor-specific**: SQL Server `IDENTITY/NVARCHAR/DATETIME2` khác PostgreSQL `IDENTITY/VARCHAR/timestamp`.
4. **ORM có giới hạn portability**: Unicode/collation, JSON/native SQL, locking, paging và query plans cần tests.
5. **Schema quản bằng migrations**: Flyway versioned scripts, `ddl-auto=validate`, approval và backward compatibility.
6. **DB constraints bảo vệ dữ liệu cuối cùng**: unique index, decimal, optimistic version và transactions.
7. **`@Transactional` không biến nhiều database hay message broker thành một ACID transaction**.
8. **TLS là bắt buộc**: SQL Server `encrypt=true;trustServerCertificate=false`, PostgreSQL `sslmode=verify-full`, đúng CA/hostname.
9. **Private networking và DB auth là hai lớp**: App outbound VNet/Private DNS phải đúng; Azure RBAC không tự là SQL/PG GRANT.
10. **Managed identity khác nhau theo JDBC driver**: SQL Server driver có auth mode; PostgreSQL cần token-for-password/role và credential refresh đúng.
11. **Connection pool phải sizing theo tổng replicas**: pool quá lớn, retry storm và query chậm đều có thể làm outage.
12. **Kiểm thử/vận hành phải bám database thật**: Testcontainers cả hai engines, Azure staging smoke, tracing/metrics, backup/DR và FinOps.

### 27.3. Kết luận

Một ứng dụng Spring Boot dùng Spring Data để truy cập **Azure SQL Database hoặc Azure Database for PostgreSQL Flexible Server** chỉ được coi là triển khai tốt khi **entity và migrations khớp engine, JDBC kết nối TLS qua mạng được phê duyệt, danh tính có đúng database grants, transactions/constraints bảo vệ dữ liệu, connection pool và queries đạt SLO, cả hai profiles được kiểm thử và hệ thống có kế hoạch giám sát, rollback, phục hồi và kiểm soát chi phí**.
