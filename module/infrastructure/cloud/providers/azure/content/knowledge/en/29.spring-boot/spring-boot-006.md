# Accessing Azure SQL and PostgreSQL with Spring Data

An inventory management application built with **Spring Boot** needs to store a product catalog, selling prices, and update history. The development team has two customer environments: System A uses **Azure SQL Database** because it has standardized on SQL Server; System B uses **Azure Database for PostgreSQL – Flexible Server** to leverage the PostgreSQL ecosystem. They want to reuse the same Spring Data domain model and repository layer while deploying to **Azure App Service**, **Azure Container Apps**, or **AKS** without embedding database passwords in source code.

The challenge is not merely swapping the JDBC URL. The two database engines differ in **data types, SQL syntax, key-generation mechanisms, isolation/locking, drivers, authentication, TLS, backups, and networking models**. If you test only against H2 and flip a profile in production, the app can fail during schema creation, migration execution, or concurrent transaction handling.

The lesson **"Accessing Azure SQL and PostgreSQL with Spring Data"** belongs to the **Spring Boot on Azure** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects knowledge of subscriptions/resource groups, Microsoft Entra ID, virtual networking, compute, storage, and data with hands-on deployment, monitoring, security, and cost control for a Spring Boot application on Azure.

After this lesson, you will be able to:

- Distinguish **Azure SQL Database** and **Azure Database for PostgreSQL Flexible Server** and choose the right service.
- Trace the chain **Spring MVC → Service → Spring Data Repository → JPA/Hibernate/JDBC → HikariCP → Azure database**.
- Configure **one application** to run with **two Spring profiles** without mixing dialects or migrations.
- Design entities, repositories, services, and REST APIs with **Spring Data JPA**, validation, and transactions.
- Manage schemas with **Flyway** using separate SQL Server and PostgreSQL migrations.
- Design secure connectivity using **TLS, database firewalls, Private Endpoints/VNet, and Microsoft Entra ID/managed identity**.
- Contrast Entra authentication in **Microsoft JDBC Driver for SQL Server** with **token-as-JDBC-password for PostgreSQL**.
- Tune HikariCP, indexes, pagination, optimistic locking, retries, and transactions.
- Write integration tests for both engines, troubleshoot failures, monitor metrics, and estimate costs.

> **Scope:** Examples use Java 21, Spring Boot 3.x, Spring Data JPA/Hibernate, and matching JDBC drivers. Newer releases may change APIs; in practice, choose supported Spring Boot/driver/Flyway versions, check the compatibility matrix, and lock dependencies in your build. No real Azure resources were created while authoring this lesson.

## 1. Big Picture: What Spring Data Is and Is Not

**Spring Data** provides data-access abstractions: repository interfaces, query method derivation, paging/sorting, and transaction integration. For relational databases, two common options are:

- **Spring Data JPA**: built on Jakarta Persistence and Hibernate ORM, managing entities, relationships, and a unit of work.
- **Spring Data JDBC**: lightweight, aggregate-centric repositories with more explicit SQL and no JPA persistence context or lazy loading.

Both run over a **JDBC DataSource** and the database-specific driver. **Spring Data does not turn SQL Server and PostgreSQL into the same engine**: native SQL, stored procedures, JSON types, locking hints, and DDL still differ.

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

### 1.1. Role of Each Layer

| Layer | Responsibility | Common pitfalls |
|---|---|---|
| **Controller** | HTTP contract, input validation, status/response mapping | Returning entities containing sensitive fields directly |
| **Service** | Business rules and transaction boundaries | Calling external APIs inside long transactions |
| **Repository** | Querying/paging/updating aggregates | N+1 queries, vendor-locked native SQL |
| **JPA/Hibernate** | Entity ↔ table mapping, dirty checking, optimistic locking | Leaving `ddl-auto=update` to mutate production schemas |
| **DataSource/HikariCP** | Managing JDBC connections and pools | Oversized pools, leaked connections |
| **JDBC Driver** | Protocol, TLS, auth, data type conversions | Wrong driver/port/certificate settings |
| **Azure database** | Persistence, transactions, indexes, backups | Throttling, deadlocks, networking, or missing grants |

### 1.2. One Codebase, Two Configurations—Not Two Databases Simultaneously

This lesson activates **one profile at a time**:

~~~text
SPRING_PROFILES_ACTIVE=sqlserver  → Azure SQL Database
SPRING_PROFILES_ACTIVE=postgres   → Azure PostgreSQL Flexible Server
~~~

That is fundamentally different from a **multi-datasource** app connecting to both DBs at once. Multi-datasource requires separate `DataSource` beans, entity manager/repository packages, transaction managers, and explicit distributed consistency handling; **a standard `@Transactional` does not create an ACID transaction across both databases**.

### 1.3. Source of Truth

Azure SQL or PostgreSQL is the transactional system of record. If you later add **Azure Managed Redis** as a cache, Redis must hold rebuildable data with TTL/invalidation. If you add **Service Bus** for async workflows, DB commits and message publishing require outbox/idempotency when consistency matters; never assume an HTTP request spans an atomic transaction across a DB and a broker.

## 2. Choosing Azure SQL Database or Azure Database for PostgreSQL?

### 2.1. Technology Comparison

| Criterion | Azure SQL Database | Azure Database for PostgreSQL Flexible Server |
|---|---|---|
| Engine | Microsoft SQL Server-compatible, T-SQL | PostgreSQL, SQL/PLpgSQL |
| JDBC driver | `com.microsoft.sqlserver:mssql-jdbc` | `org.postgresql:postgresql` |
| JDBC URL | `jdbc:sqlserver://...:1433;databaseName=...` | `jdbc:postgresql://...:5432/...` |
| Auto-increment ID | `IDENTITY(1,1)` | `GENERATED ... AS IDENTITY` |
| JSON features | SQL Server JSON functions/features per engine/version | `json`/`jsonb`, operators/indexes |
| Upsert | T-SQL patterns, `MERGE` requires concurrency review | `INSERT ... ON CONFLICT` |
| Locking/isolation | SQL Server locking + row versioning per config | PostgreSQL MVCC and isolation levels |
| Query tuning | Actual execution plan, Query Store, DMVs | `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements` |
| Authentication | SQL login or Microsoft Entra via JDBC driver | PostgreSQL password or Microsoft Entra token/role |
| Networking | Azure SQL logical server firewall/Private Endpoint | Flexible Server public/private networking models, DNS |
| Availability | Azure SQL HA/geo features per tier | Flexible Server HA/backup/PITR per configuration |

**Do not treat "SQL Server" and "Azure SQL Database" as identical in every feature**: Azure SQL Database is a PaaS database with service and compute tier boundaries, not a Windows SQL Server instance permitting every server-level operation.

### 2.2. When to Prefer Each Service?

**Azure SQL Database** fits organizations invested in T-SQL tooling, existing Microsoft SQL systems, SQL Server features supported on Azure SQL, and managed compute options.

**PostgreSQL Flexible Server** fits teams using PostgreSQL extensions/SQL, requiring PostgreSQL compatibility, or familiar with the Java/PostgreSQL ecosystem. Verify which extensions/versions Azure supports rather than assuming any Postgres extension can be installed freely.

Base the choice on **queries/indexes, transaction behavior, data model, SLA/backups, regional availability, networking, and total cost**, not merely the database name.

### 2.3. Two Common Network Topologies

~~~mermaid
flowchart LR
    APP[App Service/AKS/Container Apps] --> VNET[Outbound VNet path]
    VNET --> DNS[Private DNS resolver]
    DNS --> PE[Private Endpoint or private VNet route]
    PE --> DB[(Azure managed database)]
    APP -. TLS + DB credentials .-> DB
    PUBLIC[Public Internet client] -. Blocked per policy .-> DB
~~~

For Azure SQL Database, a **Private Endpoint** exposes a private IP inside the VNet, yet does not automatically mean `publicNetworkAccess` is disabled. For PostgreSQL Flexible Server, distinguish **Private access / VNet-injected server** from **Private Endpoint in supported networking modes**: these are distinct architectures, not interchangeable via a single checkbox. In all cases, use the **canonical server FQDN**, proper DNS, and TLS hostname verification; never hardcode a private IP in the JDBC URL.

## 3. Prerequisites and Azure Permissions

### 3.1. Application Environment

- Java 21 or a Java LTS supported by your chosen Spring Boot version.
- Maven 3.9+ or compatible Gradle, source control, and CI pipeline.
- Spring Boot + Spring Data JPA + JDBC drivers.
- An authorized **isolated lab** Azure subscription/resource group—never a production DB.
- An empty database schema on Azure SQL **or** PostgreSQL Flexible Server with permission to run migrations.
- Network reachability from the dev machine/runner **to the target Azure endpoint** (private or public per policy).
- Approved Microsoft Entra identities, SQL/PG roles, or lab credentials.
- Azure Monitor/Application Insights/DB metrics if measuring live performance.

**If Azure resources are not provisioned yet**, you can still learn the entity, repository, and query patterns here; never create databases with unauthorized accounts or drop production firewalls to test.

### 3.2. Administrative Permissions ≠ Data Permissions

| Permission | What it grants | What it does not automatically grant |
|---|---|---|
| Azure RBAC Contributor | Create/update resources within scope | SQL `SELECT`/`INSERT` on tables |
| Azure SQL Entra admin | Bootstrap Entra principals/DB authorization | Access outside DB scope |
| PostgreSQL server/Entra admin | Create roles and grant privileges per model | Azure subscription Owner |
| App database role | Query/mutate granted tables | Creating firewalls or private endpoints |
| Migration role | Create/alter schemas in pipelines | Should not be the runtime app role |

Separate the **app runtime principal** from the **migration/DBA principal**. The app usually only needs `SELECT/INSERT/UPDATE/DELETE` on business tables, not `db_owner`/superuser or schema-altering rights.

## 4. Spring Boot Dependencies and Project Layout

### 4.1. Reference Maven `pom.xml`

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

**Version `3.5.7` is only a pinned illustrative baseline** showing Maven structure. Before deploying, align Spring Boot, Flyway, PostgreSQL driver, and Microsoft JDBC driver versions with your organization's dependency management/BOM and latest security patches. Some Flyway versions package database support differently; verify exact `flyway-sqlserver`/`flyway-database-postgresql` artifacts. Do not simultaneously add the Spring Data JDBC starter just because the app uses Spring Data JPA; they are separate abstractions requiring a clear choice.

### 4.2. Illustrative Source Layout

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

This is a **layout for learners to create in their own project**, not an instruction to write extra files in the STEP 4 workspace. This task updates only the assigned Markdown and its corresponding YAML `status` field.

### 4.3. Entry Point

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

Place the entry point in root package `vn.demo.azure` so Spring Boot scans `catalog` components and entities. If repositories live outside that package tree, configure scanning explicitly rather than adding an unbounded `@ComponentScan("**")`.

## 5. Two Spring Profiles: SQL Server and PostgreSQL

### 5.1. Shared Base Configuration `application.yml`

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

**Meaning:** `ddl-auto=validate` requires entity mappings to match the Flyway-created schema; it never auto-creates or alters production tables. `open-in-view=false` forces the service layer to handle lazy associations inside transactions, avoiding holding DB sessions open during HTTP response serialization.

**Note:** Hikari timeouts are in **milliseconds**. `maximum-pool-size=10` is an illustrative baseline, not optimal for every tier or replica count. When running Flyway inside the app, the runtime principal needs DDL permissions; in production, prefer separating a migration pipeline or using controlled privileges.

### 5.2. Azure SQL Profile `application-sqlserver.yml`

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

Example **JDBC URL** (no credentials):

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;loginTimeout=30;
~~~

`encrypt=true` protects the transport channel; `trustServerCertificate=false` enforces certificate validation. Never set `encrypt=false` or `trustServerCertificate=true` to bypass DNS/TLS errors in production. Even with a Private Endpoint, use the **standard `*.database.windows.net` server FQDN**, not a private IP.

### 5.3. PostgreSQL Profile `application-postgres.yml`

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

Example URL with **TLS hostname validation**:

~~~text
jdbc:postgresql://my-pg-server.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory
~~~

`sslmode=verify-full` enforces a valid certificate chain and matching hostname. `DefaultJavaSSLFactory` uses Java's trust configuration; ensure the proper root/intermediate CAs exist in the JVM truststore compatible with your PostgreSQL JDBC driver version. In environments using `sslrootcert` or another SSL factory, configure per driver docs; **never substitute `sslmode=disable` or `require` for `verify-full`** when policy requires server identity verification.

PostgreSQL Flexible Server normally uses the granted **database role** as username—do not blindly copy `user@server` conventions from legacy Azure Database for PostgreSQL Single Server guides.

### 5.4. Lab Environment Variables

~~~bash
export SPRING_PROFILES_ACTIVE=postgres
export AZURE_PG_JDBC_URL="jdbc:postgresql://<pg-server>.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory"
export AZURE_PG_USER="<app-db-user>"

# Retrieve the password from a lab secret store; never commit to Git.
# Use an interactive shell prompt or environment secret injection.

./mvnw spring-boot:run
~~~

**Never copy usernames, passwords, or tokens into shell history or build logs**. `./mvnw` only works if your project includes Maven Wrapper; otherwise use a trusted installed Maven binary. Normally `AZURE_PG_PASSWORD` must be supplied via controlled secret injection; leaving it unset without Entra auth configured will fail connection.

### 5.5. Never Mix Credentials Across Profiles

| Mistake | Consequence |
|---|---|
| `SPRING_PROFILES_ACTIVE` unset | Missing `spring.datasource.url`, app fails startup |
| `sqlserver` profile with PostgreSQL JDBC URL | Driver/dialect mismatch, connection fails |
| Running SQL Server migration on PostgreSQL | `IDENTITY`/datatype/DDL syntax failure |
| Putting SQL passwords in `application.yml` | Secret leaked to Git/image |
| Activating both `sqlserver,postgres` | Properties override unpredictably |
| Setting `spring.jpa.hibernate.ddl-auto=update` in prod | Schema drift and uncontrolled mutations |

**Rule:** one deployment → one vendor profile → one `DataSource`/dialect → one migration set. Needing two `DataSource` instances simultaneously is a separate architectural problem requiring explicit configuration.

## 6. Schema Management with Flyway: Two Migrations, One Domain

### 6.1. Why Not Let Hibernate Create Tables Automatically?

JPA/Hibernate can generate schemas in labs, yet **a production schema is a long-lived contract**: column, index, constraint, and datatype changes require review. With multiple replicas, having every instance mutate schemas at startup risks races, drift, and downtime.

Recommendations:

1. Keep migration scripts in source control.
2. Version them immutably with code reviews.
3. Test against the **actual database engine/version** (SQL Server and PostgreSQL).
4. Roll out incompatible changes via **expand → migrate data → switch code → contract**.
5. Run apps with `ddl-auto=validate`, never `update` or `create-drop`.
6. Separate the DDL migration principal from the runtime principal.
7. Prepare backups, restores, rollbacks, or forward-fix plans before destructive DDL.

### 6.2. SQL Server Migration

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

SQL Server specifics:

- `IDENTITY(1,1)` generates auto-incrementing surrogate keys.
- `NVARCHAR` stores Unicode product names; `VARCHAR` columns require collation/UTF-8 considerations if storing Unicode.
- `DATETIME2(6)` **carries no timezone**; the application standardizes on UTC.
- The unique index on `sku` enforces uniqueness in the **database**, not merely in service code.
- `dbo` is the common default schema; if a database role uses another default schema, align schema/mapping explicitly.

### 6.3. PostgreSQL Migration

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

PostgreSQL specifics:

- `GENERATED BY DEFAULT AS IDENTITY` is the standard identity column in modern PostgreSQL.
- PostgreSQL `VARCHAR` supports Unicode per database encoding/collation (typically UTF-8).
- `NUMERIC(12,2)` provides exact decimal precision matching `BigDecimal`.
- `TIMESTAMP WITHOUT TIME ZONE` requires a **UTC convention**; the DB attaches no timezone offset.
- `public` is the common default schema; roles need proper `USAGE`/`GRANT` rights.

**Never run SQL Server migrations against PostgreSQL:** `IDENTITY(1,1)`, `NVARCHAR`, and `DATETIME2` differ in DDL semantics. Conversely, `GENERATED ... AS IDENTITY` and `public` do not replace `dbo` in SQL Server.

### 6.4. Hibernate Mappings Must Be Verified

For SQL Server, the entity uses `@Nationalized` on `name` to signal `NVARCHAR` Unicode intent. On PostgreSQL, the Hibernate dialect handles Unicode strings per its supported types. This exemplifies why **schema-validation integration tests are needed for both dialects**; never assume every ORM version maps nationalized strings identically.

If Flyway errors when the driver/DB rejects migrations, check:

- Active profile and `spring.flyway.locations`.
- Driver/Flyway database module version compatibility.
- Connectivity, DDL role, target schema (`dbo`/`public`), and existing tables.
- Flyway schema history for failed/incomplete prior migrations.
- Naming format `V1__...sql` with **two underscores**.

**Never blindly enable `baseline-on-migrate=true` to bypass errors on an existing database**. A production database with live data needs a controlled baseline plan and verified migration history.

### 6.5. Backward-Compatible Schema Changes

Example adding a `currency` column:

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

Maintain **two migration scripts** for SQL Server and PostgreSQL with the same logical version yet vendor-specific DDL. Never deploy JPA code expecting a column not yet migrated in production. Across multi-replica rolling deployments, backward compatibility prevents transient outages.

## 7. JPA Entity: Mapping `Product` for Both Databases

### 7.1. `Product.java` Class

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

**Key design points:**

- `@Entity` shares one Java model whether persisted to Azure SQL or PostgreSQL.
- `GenerationType.IDENTITY` aligns with SQL Server and PostgreSQL identity DDL, though it can constrain JDBC insert batching.
- Use `BigDecimal` for money—**never `double`** for financial arithmetic.
- `@Version` enables **optimistic locking**: concurrent updates to the same row reject stale writes instead of silently overwriting them.
- `@Nationalized` is a **Hibernate** annotation, not pure JPA; test portability across dialects.
- `updatedAtUtc` uses `LocalDateTime` **by UTC convention** matching timezone-less timestamp DDL. If business logic needs absolute instants across timezones, evaluate `Instant`/`OffsetDateTime` with matching SQL types and driver tests.
- The `protected` no-args constructor lets JPA instantiate entities. Services must never manually assign `id` or `version`.

### 7.2. Never Return Entities Directly from an API

Entities grow to include relationships, internal audit columns, or sensitive fields. Return a **DTO/record** instead:

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

In production, DTOs should expose only fields clients are authorized to see; `version` can serve as an optimistic concurrency token (e.g., HTTP `ETag`/`If-Match`), enforced explicitly by the API. **`@Version` alone does not force HTTP clients to submit an expected version**; it only guards changes between loading and flushing within a transaction.

## 8. Spring Data JPA Repository: CRUD, Query Derivation, and Pagination

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

Spring Data generates queries for `findBySku` and `findByNameContainingIgnoreCase` from entity metadata and dialect. No hand-written boilerplate CRUD SQL is needed.

### 8.1. Common Spring Data Repository Methods

| Method | Purpose | Note |
|---|---|---|
| `findById(id)` | Lookup by primary key | Returns `Optional` |
| `findBySku(sku)` | Lookup by business key | Backed by a unique index |
| `existsBySku(sku)` | Existence check | Does not prevent race conditions without a unique constraint |
| `save(product)` | Insert/update per entity state | SQL flushes per transaction lifecycle |
| `saveAndFlush(product)` | Save and flush immediately | Does not commit the transaction |
| `findAll(pageable)` | Paging/sorting | Offset pagination slows down at deep pages |
| `deleteById(id)` | Delete by ID | Respect constraints and business deletion rules |

### 8.2. Query Derivation ≠ Absolute Vendor-Independence

`findByNameContainingIgnoreCase` translates into a `LIKE`/lower/collation expression. **SQL Server collations** and **PostgreSQL collations/`ILIKE` semantics** differ on Unicode, Vietnamese diacritics, case folding, and wildcards. Test with strings like:

~~~text
"Cà phê"
"ca phe"
"CÀ PHÊ"
"Đèn LED"
"den led"
~~~

Do not assume `IgnoreCase` implies **accent-insensitivity** or full-text search. For rich search, leverage database-specific indexes, collations, or full-text engines, using vendor-specific repository adapters where needed.

### 8.3. JPQL and Native SQL

Example portable **JPQL** (use only when needed):

~~~java
// Inside ProductRepository, additional example method:
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

This is an **illustrative snippet to place inside the repository interface**, not a standalone Java file. Always bind parameters to prevent SQL injection; never concatenate user input into SQL strings. With native SQL, account for T-SQL vs. PostgreSQL syntax, pagination, and type casting; **never write `TOP 10` expecting PostgreSQL to understand it**.

### 8.4. Bounded Pagination and Stable Sorting

For an API call:

~~~text
GET /products?name=phone&page=0&size=20
~~~

Spring Data uses `PageRequest.of(page, size, Sort.by("sku"))`. Ensure:

- Bounded `size`, e.g., maximum 100.
- Deterministic sort with a unique tie-breaker key (such as unique `sku`).
- Indexes covering common filter and sort patterns.
- **Keyset/seek pagination** instead of offset for very deep pages.
- Never interpolate user-supplied sort column names into raw SQL; use an allowlist.

`Page<T>` runs an extra **count query**, which can be expensive on large tables; if you only need to know whether a next page exists, consider `Slice<T>` or a tailored query. Query planners differ across engines, so measure both.

## 9. Service Layer and Transaction Boundaries

### 9.1. Validated Input DTOs

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

**API validation does not replace database constraints.** Two concurrent requests creating the same SKU can both pass `existsBySku`, leaving the DB unique index to enforce final integrity.

### 9.2. `ProductService`

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

**Why use `@Transactional` in the service?**

- Wraps business logic and DB writes inside an explicit transaction boundary.
- With JPA, dirty checking happens inside the persistence context; `saveAndFlush` sends SQL early, though **without committing yet**.
- `readOnly=true` optimizes flush mode/hints, **not DB access control**; true read-only enforcement requires database permissions, schemas, or transaction policies.
- Spring rolls back on unchecked exceptions by default; checked exceptions and propagation require deliberate design.
- **Self-invocation within the same object** bypasses Spring proxies, so `@Transactional` on private methods or internal calls may not activate as expected.

### 9.3. Optimistic Locking in Practice

Suppose two transactions load the same `Product` with `version=3`:

~~~text
Transaction A: read price 100, version 3
Transaction B: read price 100, version 3
Transaction A: update price 120; version becomes 4; COMMIT
Transaction B: update price 130 with expected version 3
→ update affects 0 rows → optimistic locking failure
~~~

`@Version` stops one transaction from overwriting another **when both loaded the entity in conflicting state**. However, the REST API above loads and updates within a single request; if a browser views a product at 09:00 and sends PATCH at 09:10, the server loads the latest version right before patching and can still overwrite earlier changes. To prevent **lost updates across HTTP requests**, pass an expected version/`ETag` and check it in the service before modifying.

### 9.4. Long Transactions Cause Harm

Avoid:

~~~text
BEGIN TRANSACTION
  SELECT product
  Call external payment API (wait 30 seconds)
  Send Service Bus message
  UPDATE product
COMMIT
~~~

Connections and locks remain held too long, and external services are not part of the local DB transaction. Prefer **short transactions**, using outbox/saga/idempotency patterns for multi-service workflows. `@Transactional` does not create an atomic commit across Azure SQL, PostgreSQL, HTTP APIs, and Service Bus.

## 10. REST Controller and Safe HTTP Error Handling

### 10.1. `ProductController`

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

This HTTP API is for learning; production requires **authentication/authorization** via Spring Security/API gateway, rate limits, request IDs, audit events, and principal-level permission checks before updating prices. Never expose a public price-mutation endpoint just because the localhost sample runs without auth.

### 10.2. Mapping Exceptions to Safe Responses

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

**Never return raw SQL errors** exposing database endpoints, SQL statements, constraint metadata, or sensitive values to clients. Internally, log the exception class and trace ID with redacted data; note `DataIntegrityViolationException` covers various constraint violations, so classify carefully if the API needs granular error codes.

### 10.3. Example HTTP Requests

~~~http
POST /products HTTP/1.1
Content-Type: application/json

{"sku":"SKU-001","name":"Wireless Headphones","price":1200000.00}
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
GET /products?name=Wire&page=0&size=20 HTTP/1.1
~~~

When switching profiles from `sqlserver` to `postgres`, the API contract **remains unchanged** and the repository code stays the same once DDL/mappings are verified. Only the JDBC profile, driver, schema migrations, database provisioning, and connection grants change.

## 11. Secure Connectivity: Firewalls, Private Endpoints, DNS, and TLS

A Spring Boot app can boot cleanly in local Docker yet time out on Azure if network paths or DNS differ. **A valid connection string is not enough**: you need an outbound path from runtime to database, proper hostname resolution, valid TCP/TLS, and database permissions.

### 11.1. Azure SQL Database

Azure SQL Database runs under a **logical server** with an FQDN like:

~~~text
<server>.database.windows.net
TCP 1433
~~~

Network options:

- **Public endpoint + firewall rules:** permit only approved source IP ranges. Never open `0.0.0.0/0`.
- **Private Endpoint:** routes traffic to Azure SQL over a private IP in a VNet; the **application** needs an outbound VNet path and matching DNS.
- **Public network access disabled:** configure explicitly per policy; having a Private Endpoint **does not automatically prove** the public path is disabled.
- **Connection policy:** depending on server/network settings, SQL clients may use **proxy or redirect**; redirect requires additional outbound port/network rules. Check Azure SQL connection policy and NSGs/firewalls rather than opening all ports broadly.

### 11.2. Azure Database for PostgreSQL Flexible Server

Server FQDN format:

~~~text
<server>.postgres.database.azure.com
TCP 5432
~~~

Flexible Server offers distinct connectivity architectures:

- **Public access with network/firewall rules**, optionally combined with Private Endpoints in supported configurations/service modes.
- **Private access / VNet integration** via a **delegated subnet** and private DNS per the supported model.
- Chosen **networking mode** affects switching capability, Private Endpoints, and IP addressing. **Do not treat "Private Endpoint" and "VNet-injected server" as two names for the same setup.**

Select the networking mode at provisioning time and verify regional/version capabilities at deployment time. Never copy legacy PostgreSQL **Single Server** networking guides when configuring Flexible Server.

### 11.3. Access Paths from Each Hosting Service

| Spring Boot host | What must be configured |
|---|---|
| **Azure App Service** | **Outbound VNet Integration** to private DB, proper DNS/routing |
| **Azure Container Apps** | Environment VNet/egress, network restrictions, and DNS |
| **AKS** | VNet/Pod egress, NetworkPolicy, Private DNS, NSG/UDR/Firewall |
| **Azure VM** | Subnet routes, DNS, NSG, managed identity |
| **On-premises** | VPN/ExpressRoute, routing, and private DNS forwarding |
| **Hosted CI runner** | Not inside your private VNet by default; use a self-hosted/private runner or approved migration path |

**An inbound Private Endpoint on App Service** controls incoming callers to App Service; it does not grant outbound reachability to a database's Private Endpoint.

### 11.4. Ordered Network Debugging Flow

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

From the **failing runtime**, run authorized diagnostic tools:

~~~bash
nslookup "<sql-server>.database.windows.net"
nslookup "<pg-server>.postgres.database.azure.com"

# If netcat is available in the image/host; proves TCP reachability only, not auth.
nc -vz "<sql-server>.database.windows.net" 1433
nc -vz "<pg-server>.postgres.database.azure.com" 5432
~~~

Never put a private IP directly in the JDBC URL as a "quick DNS fix": TLS hostname verification may fail and IPs can change. **Never disable certificate checks** as a production networking workaround.

### 11.5. Verifying TLS per Driver

**Microsoft JDBC Driver for SQL Server:**

~~~text
encrypt=true
trustServerCertificate=false
~~~

**PostgreSQL JDBC Driver:**

~~~text
sslmode=verify-full
~~~

In PostgreSQL, `sslmode=require` encrypts transport yet **must not be treated as a safe substitute for `verify-full`** when server identity verification is required. For SQL Server, `trustServerCertificate=true` skips chain/hostname verification; never use it in production.

TLS relies on up-to-date JDBC drivers and JDK truststores aligned with Azure's certificate policies. Keep the CA chain current and inspect the JVM truststore inside the **container image**, not only on a developer laptop.

### 11.6. Never Open a Public Firewall Just for Migrations

If the database is private-only, use an approved **private CI runner, in-VNet migration job, or bastion/admin host**. Opening Internet firewall rules and forgetting to close them is a classic security regression. After network changes, test **app runtime + migrations + DBA tools + scheduled jobs**, not just a single GET endpoint.

## 12. Authentication: SQL Passwords, Microsoft Entra, and Managed Identity

### 12.1. Why Prefer Passwordless Over Static Passwords?

Static database passwords can leak via source code, Git history, container environment inspection, CI logs, or backups. For Azure-hosted workloads, **managed identity** lets the app acquire Entra tokens without storing client secrets, provided the database supports the matching **authentication method and database principal mapping**.

| Aspect | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Lab password auth | SQL authentication login/user | PostgreSQL user/password |
| Production passwordless | Entra auth supported by Microsoft JDBC Driver | Entra token passed via PostgreSQL login protocol/role |
| Token audience/scope | Handled by JDBC driver per auth mode | Typically `https://ossrdbms-aad.database.windows.net/.default` |
| Database authorization | Contained user/role `FROM EXTERNAL PROVIDER` + `GRANT` | Entra principal mapped to a PG role + `GRANT` |
| Refresh | JDBC driver/auth integration refreshes tokens per mode | Pool must supply a fresh token when opening new connections |
| User-assigned identity | Configure identity/client ID per driver version | `DefaultAzureCredential`/Workload Identity selects intended identity |

**Azure RBAC Contributor or Managed Identity on a VM does not automatically grant `SELECT` on a database.** A database administrator must create the principal/role and grant object permissions.

### 12.2. Azure SQL Database with System-Assigned Managed Identity

Flow:

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

JDBC URL for **system-assigned identity** when supported by runtime/driver:

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;
~~~

With a dedicated `sqlserver-mi` profile:

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

Omit `spring.datasource.username`/`password` when the driver acquires credentials via managed identity. **For user-assigned identities**, driver versions vary in how **client ID** and auth properties are specified; consult the exact Microsoft JDBC Driver docs rather than conflating object ID and client ID.

For the database to accept the principal, configure an Entra admin on the Azure SQL logical server and have a DBA create the user from external provider (run inside the **target database**):

~~~sql
CREATE USER [catalog-app-mi] FROM EXTERNAL PROVIDER;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON OBJECT::dbo.products TO [catalog-app-mi];
~~~

**Prerequisite:** `catalog-app-mi` must resolve uniquely to the Microsoft Entra principal in the tenant. For name collisions or disambiguation by object ID, Azure SQL supports specifying ID/`SID` depending on engine version; verify Azure SQL docs with DBA approval. The app principal **does not need `CREATE TABLE`** if migrations run under a separate identity.

### 12.3. PostgreSQL Flexible Server with Microsoft Entra Tokens

The PostgreSQL JDBC protocol expects a **username/password**. With Entra authentication:

1. Flexible Server is configured with Microsoft Entra auth (and an Entra admin).
2. The Entra principal/managed identity is mapped to a **PostgreSQL database role** with grants.
3. The application acquires a token for the appropriate scope.
4. When opening a JDBC connection, **username is the mapped DB role**, and **password is the short-lived access token**, not a static secret.
5. The connection pool/credential provider must **fetch a fresh token for new connections opened after the previous token expires**.

Acquiring a token via the Azure Identity SDK:

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

**This snippet only illustrates token acquisition**; it requires compatible `com.azure:azure-identity` and `com.azure:azure-core` versions from the BOM, plus a verified **Hikari/DataSource passwordless integration**. Never paste a one-off token into `AZURE_PG_PASSWORD` for a 24/7 app: once Hikari opens new connections after expiry, logins will fail.

You can adopt the **Spring Cloud Azure passwordless JDBC integration** matching your Spring Boot/Cloud Azure version, or implement credential refresh where **new connections** are created with token caching and expiry guards. Starter names, properties, and Flexible Server support evolve across releases; check compatibility guides, run integration tests, and obtain security approval before production.

Never pass SQL Server's `authentication=ActiveDirectoryManagedIdentity` in a PostgreSQL URL: it is a **driver-specific property**, not a universal JDBC standard.

### 12.4. PostgreSQL Entra Role / GRANT

On PostgreSQL Flexible Server, the DBA/Entra admin must create or map the Entra principal to a **PostgreSQL role** via Azure-supported procedures (e.g., `pgaadauth` management functions per feature/version) and grant:

~~~sql
-- Illustrative grants only for an already-created/mapped DB role.
GRANT USAGE ON SCHEMA public TO catalog_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.products TO catalog_app_role;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO catalog_app_role;
~~~

**`catalog_app_role` in the example is an assumed existing DB role**, not auto-created by Azure RBAC. For PostgreSQL identity sequences, sequence privileges depend on how identity/generated values are used and PostgreSQL version; grant least privilege verified via integration tests. Never grant `SUPERUSER` or server-wide roles to the app.

### 12.5. Rotation and Existing Open Connections

| Authentication | When credentials expire / rotate | What to design |
|---|---|---|
| SQL/PG static password | New connections fail after rotation | Secret store + overlap/roll windows + pool recycling |
| Azure SQL Managed Identity | Driver refreshes tokens per auth mode | Driver version, identity assignment, DB user, reconnect |
| PostgreSQL Entra access token | Fresh token needed for **new JDBC connections** | Passwordless provider/refresh logic, pool lifecycle |
| TLS CA/cert update | Clients may stop trusting new chains | Update JVM truststore / container base image |
| Database roles/GRANTs | Login succeeds yet queries are denied | Audit privileges and least-privilege migrations |

Entra token expiration **does not necessarily** kill all already-open JDBC sessions immediately; driver and server behaviors vary. However, every **new connection** must authenticate validly; test Hikari under pool recycling, scale-out, and failover.

### 12.6. Do Not Mistake a Secret Manager for SQL Permissions

Azure Key Vault only stores and dispenses credentials per policy; it never automatically:

- creates PostgreSQL database roles;
- creates contained SQL users;
- grants `SELECT`/`INSERT` on tables;
- builds routes from App Service to Private Endpoints;
- fixes SSL certificate hostname mismatches.

Distinguish **secret access**, **database authentication**, **database authorization**, and **network reachability** during diagnosis.

## 13. Connection Pooling with HikariCP

HikariCP reuses JDBC connections to avoid TLS and auth handshakes on every HTTP request. Still, database connections are a **finite resource**, especially on small Azure SQL compute tiers or low-vCore PostgreSQL Flexible Servers.

### 13.1. Pool Sizing Relative to Replica Count

Suppose:

~~~text
Azure Container Apps replicas (peak):  20
Hikari maximumPoolSize per replica:   10
Potential app connections:            200
Migration/DBA/monitoring headroom:    30
Peak total plan:                      ~230 connections
~~~

If the database tier supports fewer connections, oversized pools cause login timeouts and throttling. Conversely, if the app uses only 3 concurrent connections yet configures 100 per replica, scaling up the DB just to hold idle sockets wastes money.

**Base sizing on** measured concurrency, query latency, request queuing, replica count, and DB connection limits—never treat `"CPU cores × 10"` as an absolute law.

### 13.2. Settings and Trade-Offs

| Hikari setting | Meaning | Consideration |
|---|---|---|
| `maximumPoolSize` | Max connections per app instance | `replicas × pool` must stay within budget |
| `minimumIdle` | Target idle connections | Too high wastes DB connections |
| `connectionTimeout` | Wait time to borrow a connection | Too short triggers errors during bursts |
| `validationTimeout` | Timeout for validating live connections | Must be less than `connectionTimeout` |
| `maxLifetime` | Max connection lifetime in pool | Shorter than any network/service hard cap |
| `idleTimeout` | Threshold to evict excess idle connections | Effective for dynamic pools |
| `keepaliveTime` | Ping idle connections when appropriate | Avoid excessive pings across thousands of replicas |
| `leakDetectionThreshold` | Flags connections held too long (debug) | Avoid flooding production logs |

`maxLifetime` **does not fix PostgreSQL Entra token refresh** if the credential provider keeps returning an expired cached token for new connections. With user-assigned MI, verify client ID selection on every replica / AKS Workload Identity.

### 13.3. Pool Exhaustion

Symptom:

~~~text
HikariPool-1 - Connection is not available,
request timed out after 3000ms.
~~~

Do not jump to "SQL Server is down." Possible causes:

- Transactions hold connections due to slow queries or external HTTP calls inside `@Transactional`.
- Pool is smaller than actual concurrency demand.
- DB tier is throttled or CPU/IO saturated.
- Connection leaks where connections fail to return to the pool.
- Network/TLS/auth latency slowing new connection creation.
- A post-outage retry storm saturating the pool.

Inspect **active/idle/pending connections, query latency, database CPU/locks, and error classes** before bumping `maximumPoolSize`.

### 13.4. Retry at the Right Layer—Avoid Duplicate Transactions

An HTTP request creating a product might behave like:

~~~text
POST /products
  → INSERT succeeds, commit succeeds
  → connection drops before response
  → client retries POST
  → duplicate SKU / conflict
~~~

**Not every connection error means the transaction rolled back.** For side-effecting writes, enforce **idempotency keys / business unique constraints** and verify authoritative state before retrying. Retry only classified transient failures with bounded exponential backoff + jitter; never infinitely retry HTTP 400, 403, or invalid SQL.

## 14. Transactions, Isolation, and Concurrency Across Both Engines

### 14.1. What Does `@Transactional` Do?

Spring scopes transactions to the **active DataSource/EntityManager**:

~~~java
@Transactional
public void renameAndReprice(String sku, String newName, BigDecimal newPrice) {
    // Pseudocode: both changes occur on one managed entity/transaction.
    Product p = repository.findBySku(sku).orElseThrow();
    p.changePrice(newPrice);
    // A real entity setter for name would be required to rename it.
}
~~~

This is a **transaction illustration**, not a runnable method since `Product` here has no rename setter. Never copy it without adding proper domain methods and validation.

In `updatePrice` (section 9), dirty checking and `@Version` cooperate to catch certain lost updates. Yet isolation and database-side locking still vary by engine.

### 14.2. Read Committed and MVCC

| Topic | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Default transaction isolation | Typically READ COMMITTED; row-versioning behavior depends on DB settings | PostgreSQL READ COMMITTED |
| Dirty reads | Prevented in standard configurations | Prevented |
| Readers vs. writers | Depends on row-versioning vs. locking configuration | MVCC snapshots per isolation level |
| Deadlocks | Possible; handle/retry transactions appropriately | Possible, SQLSTATE `40P01` |
| Serialization conflicts | Depends on isolation/data patterns | SQLSTATE `40001` under Serializable |
| Update conflicts | Catchable via JPA `@Version` | Catchable via JPA `@Version` |

**Never assume READ COMMITTED behaves identically across both engines**. SQL Server distinguishes lock-based read committed from `READ_COMMITTED_SNAPSHOT`; PostgreSQL MVCC captures statement-level snapshots in read committed. Test concurrent read–modify business flows on both.

### 14.3. Pessimistic Locking When Truly Needed

A repository can declare:

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

**Place this snippet inside `ProductRepository`**, not standalone. Hibernate emits different locking SQL on SQL Server and PostgreSQL; benchmark both and evaluate deadlock/lock-wait risks. Use optimistic locking when conflicts are rare; reserve pessimistic locking for workflows requiring upfront row locks with timeouts and runbooks.

### 14.4. One Transaction Does Not Span Two Databases

~~~text
App transaction in Azure SQL: COMMIT
App transaction in PostgreSQL: ROLLBACK
Result: data differs if the process treats both as one operation.
~~~

Remember **distributed consistency**. Never assume `@Transactional` makes simultaneous writes to Azure SQL and PostgreSQL atomic. Partition ownership, use outbox, saga, or compensation patterns, or evaluate supported distributed transaction mechanisms with their cost/risk trade-offs; avoid cross-database writes whenever unnecessary.

### 14.5. Transaction Principles

1. Keep transactions as **short** as possible.
2. Keep HTTP calls and slow file I/O outside transactions.
3. Use database constraints to protect uniqueness and integrity.
4. Use optimistic versions or explicit locks under concurrent writes.
5. Retry only transient errors while preserving idempotency.
6. Do not expose entities/lazy loading over HTTP post-transaction when `open-in-view=false`.
7. Audit throughput and lock contention before altering isolation levels.

## 15. Spring Data JDBC as an Alternative When ORM Is Unwanted

For simple aggregates not needing JPA lazy loading or complex entity graphs, **Spring Data JDBC** offers more transparent data access. Pick **one primary persistence paradigm** clearly—never include both starters just because both say "Spring Data."

### 15.1. Spring Data JPA vs. JDBC

| Factor | Spring Data JPA | Spring Data JDBC |
|---|---|---|
| Model | Entity graphs, persistence context, ORM | Aggregate-oriented repositories |
| Lazy loading | Supported per mapping and transaction | No JPA lazy loading |
| Change tracking | Hibernate dirty checking | Explicit aggregate saves |
| Query language | JPQL/Criteria/SQL | SQL and generated repository queries |
| Vendor portability | Dialect/ORM-based, differences remain | Requires more active SQL/dialect ownership |
| Best fit | Complex domains, associations, ORM features | Simple CRUD aggregates and tight SQL control |

### 15.2. `JdbcTemplate` for Specialized Queries

Even with JPA, Spring Boot auto-configures `JdbcTemplate` on the same `DataSource` for specialized queries. Example using **vendor-neutral SQL**:

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

`JdbcTemplate` uses **prepared statements / bound parameters** for inputs:

~~~java
var names = jdbc.query(
    "SELECT name FROM products WHERE sku = ?",
    (rs, rowNum) -> rs.getString("name"),
    "SKU-001"
);
~~~

These snippets assume the same configured `DataSource`. Switching from JPA to **Spring Data JDBC repositories** requires changing starters, mapping annotations/aggregate models, and repository config; never copy `jakarta.persistence.Entity` classes expecting Spring Data JDBC to treat them as JDBC entities.

### 15.3. When Native SQL Is Necessary

If a query needs PostgreSQL `jsonb`, GIN indexes, or `ON CONFLICT`, do not contort it into portable JPQL. Create **vendor-specific DAO/query adapters** selected by profile, test them, and inspect execution plans. Manage SQL Server T-SQL/Query Store optimizations separately behind a shared business service interface.

## 16. Testing Against Real Database Engines: Testcontainers and Azure Staging

One of the riskiest habits is testing every repository on **H2 in-memory** and assuming Azure SQL or PostgreSQL will behave identically. H2 differs in syntax, types, locking, collations, and migrations; "green unit tests" do not validate database migrations.

### 16.1. Testing Pyramid

| Test | Covers | Cannot verify |
|---|---|---|
| **Service unit tests** | Business validation, DTO mapping, mocked repositories | SQL dialects, constraints, real transactions |
| **Testcontainers PostgreSQL repository tests** | PostgreSQL schema/Flyway/queries/locking | Azure Flexible Server networking/Entra/HA |
| **Testcontainers SQL Server repository tests** | T-SQL, identity, unique constraints, Hibernate SQL dialect | Azure SQL Database firewalls/Private Link/tiers |
| **Azure staging smoke tests** | TLS, Entra/DB grants, Private DNS, host networking, Flyway permissions | Full production peak throughput |
| **Load/resilience tests** | Pool saturation, retries, failover, and degradation | Unscripted failure modes |

**A SQL Server container is not equivalent to Azure SQL Database** across all PaaS features, yet it catches basic DDL/ORM incompatibilities before deploy. Production features (Query Store, elastic pools, Azure SQL authentication) still require real Azure staging validation.

### 16.2. Adding Testcontainers Dependencies (Test Scope Only)

In Maven `<dependencies>`, add:

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

These are **dependency snippets for `pom.xml`** using artifact coordinates common to the Testcontainers 1.x line managed by Spring Boot 3.x BOMs. **Testcontainers 2.x introduced module/artifact naming changes**, so verify coordinates against your project's actual dependency versions and image support before applying.

### 16.3. Integration Test with PostgreSQL Testcontainers

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

This example requires Docker/Testcontainers support and Flyway migrations. The PostgreSQL test container typically connects **without TLS** locally between test runner and Docker host; that **does not waive `verify-full` TLS requirements on Azure**. Validate TLS separately in Azure staging.

### 16.4. Equivalent SQL Server Test

Create a separate test class with:

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

**This fragment goes inside a test class**, not a standalone Java file. The test class needs `@ActiveProfiles("sqlserver")`, `@SpringBootTest`, `@Testcontainers`, and matching repository/test methods. Accept the SQL Server license **only when authorized and agreeing to its terms**, with sufficient CPU/RAM/disk and compatible Docker architecture/virtualization; pin the `2022-latest` image by digest or exact version in production CI.

### 16.5. Minimum Test Cases for Both DBs

- [ ] Flyway V1 creates `products` and Hibernate `ddl-auto=validate` passes.
- [ ] Insert Product with SKU and **Vietnamese Unicode** name.
- [ ] PostgreSQL/SQL Server returns DB-generated ID and preserves `BigDecimal(12,2)` precision.
- [ ] Read by SKU using the unique index.
- [ ] Duplicate SKU insert is rejected by the database and mapped safely to 409.
- [ ] `findByNameContainingIgnoreCase` tested with appropriate Unicode/collations.
- [ ] Deterministic paging/sorting; page sizes outside `[1..100]` rejected.
- [ ] Concurrent updates trigger optimistic locking conflicts on stale versions.
- [ ] Transactions roll back cleanly on business validation or DB constraint errors.
- [ ] Vendor-specific native SQL (if any) tested independently.
- [ ] Re-running migrations respects Flyway history without recreating or overwriting data.
- [ ] Azure staging verifies TLS, Entra, Private DNS, and real Azure DB roles.

### 16.6. Unit Tests Do Not Replace Authentication Tests

Mocking `ProductRepository` touches zero JDBC code; it will never catch:

~~~text
PKIX path building failed
SQL Server Error 18456: Login failed
PostgreSQL SQLSTATE 28P01: password authentication failed
Private endpoint DNS resolves to wrong IP
Flyway cannot CREATE TABLE due to insufficient grant
~~~

Those failures require **integration/smoke tests from the real network runtime**, not additional Mockito mocks.

## 17. SQL Portability and Query Performance

### 17.1. Portable Only at the Right Abstraction Level

Common JPA operations can be shared, yet differences remain in:

| Area | SQL Server | PostgreSQL | Decision |
|---|---|---|---|
| Auto ID | `IDENTITY` | `GENERATED AS IDENTITY` | Vendor-specific Flyway migrations |
| Unicode text | `NVARCHAR` or `VARCHAR` per collation | UTF-8 `VARCHAR`/`TEXT` | Hibernate mapping + DB tests |
| JSON | SQL Server JSON functions/features | `jsonb` with dedicated operators/indexes | Vendor-specific repository |
| Upsert | T-SQL patterns/`MERGE` with concurrency review | `ON CONFLICT` | Keep native SQL separate |
| Case/accents | Collation governs comparisons | Collation/`ILIKE`, locale | Test search semantics |
| Time types | `DATETIME2`/`DATETIMEOFFSET` | `timestamp`/`timestamptz` | Explicit UTC mapping policy |
| Array types | No PG array semantics | Native arrays | Dedicated adapter |
| Native pagination | `OFFSET...FETCH` | `LIMIT/OFFSET` | Use `Pageable` or dialect-specific SQL |
| Indexing | SQL Server B-tree/columnstore/full-text | B-tree/GIN/GiST/BRIN... | Query-plan-driven |
| Lock hints | T-SQL `UPDLOCK`... | `FOR UPDATE` | JPA lock or dedicated adapter |

### 17.2. Fast `findBySku` Queries Need an Index

Repository:

~~~java
Optional<Product> findBySku(String sku);
~~~

This needs a DB unique index/constraint. On a multi-million-row table without an index on `sku`, lookups can full-scan the table and hold connections open.

**PostgreSQL query plan:** run on staging with a safe SELECT:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, sku, name, price, version, updated_at_utc
FROM public.products
WHERE sku = 'SKU-001';
~~~

**Note:** `EXPLAIN ANALYZE` actually **executes the statement**. Never run `EXPLAIN ANALYZE UPDATE/DELETE` on live data without a wrapping transaction/rollback plan.

**Azure SQL Database:** inspect Query Store / Actual Execution Plans / authorized DMVs, or measure:

~~~sql
SET STATISTICS IO ON;

SELECT id, sku, name, price, version, updated_at_utc
FROM dbo.products
WHERE sku = 'SKU-001';

SET STATISTICS IO OFF;
~~~

Run diagnostics only on lab/staging databases. Never paste SQL plans or parameter values containing sensitive data into public bug reports.

### 17.3. Queries with `%term%` May Skip B-Tree Indexes

`findByNameContainingIgnoreCase` performs substring matching:

~~~sql
WHERE LOWER(name) LIKE '%coffee%'
~~~

This is an **illustrative equivalent**, not necessarily the exact SQL Hibernate generates. Standard B-tree indexes generally cannot accelerate leading-wildcard searches. At scale:

- PostgreSQL can use `pg_trgm` and GIN/GiST indexes **if supported and enabled on Azure**.
- SQL Server can use **full-text indexes** or an appropriate search model.
- For multi-field search and ranking, consider Azure AI Search as a dedicated search engine.

Never add production indexes solely based on an example. Evaluate query plans, I/O, selectivity, write overhead, and storage cost.

### 17.4. N+1 Queries with JPA Relationships

Suppose `Product` later has multiple `ProductCategory` records. When code runs:

~~~java
for (Product p : repository.findAll()) {
    // Accessing a lazy relation per product:
    // p.getCategories().size();
}
~~~

Hibernate may fire **1 query for products + N queries for categories**. Mitigations include:

- DTO projections.
- `@EntityGraph` or controlled JPQL join fetches.
- Appropriate batch fetching.
- Avoiding `EAGER` on every association and never serializing entities straight to JSON.
- Counting JDBC SQL statements and latency in integration tests.

Watch out for **join-fetching collections with `Pageable`**: it can trigger in-memory pagination or unexpected row counts. Check query plans and ORM metrics on both engines.

### 17.5. Batch Writes and IDENTITY

`GenerationType.IDENTITY` requires the DB to assign IDs at insert time, which can inhibit JDBC batching in some Hibernate versions. For multi-million-row ingestion, evaluate engine-specific sequence strategies, bulk SQL, `JdbcTemplate.batchUpdate`, or staging pipelines—these are **vendor-specific optimizations** requiring benchmarks; never swap ID strategies lightly on populated production tables.

### 17.6. Cursors/Streaming and Query Timeouts

Never call `findAll()` to load 10 million rows into the JVM:

- Use paging/batch queries or streaming with explicit transaction lifecycles.
- Cap `size` and enforce stable sorting.
- Set JDBC statement/query timeouts where appropriate.
- Monitor JVM memory and transaction duration.
- For large analytical reads, use an analytics store or read replicas per product/tier instead of overloading the OLTP DB.

**Azure SQL and PostgreSQL both enforce resource limits**. Adding app replicas without sizing the database and pools can degrade throughput due to excess concurrent connections.

## 18. Observability: Measuring in Both Spring Boot and Azure Databases

### 18.1. Three Layers to Correlate

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

A slow API request can stem from:

- JVM / Garbage Collection / serialization.
- Hikari pool waiting for a free connection.
- Unindexed SQL queries.
- Lock contention or deadlocks inside transactions.
- Network/TLS/login/retry delays.
- Database CPU/IO saturation or tier throttling.
- Slow non-DB downstream dependencies.

Measure every layer instead of staring only at `500 Internal Server Error`.

### 18.2. Spring Boot Actuator and Micrometer

With `spring-boot-starter-actuator`, the app can expose health/metrics, and Hikari/Micrometer emits pool metrics when auto-configured. Key signals to watch:

| Metric intent | What to look at |
|---|---|
| HTTP latency p50/p95/p99 | Slow API routes by endpoint/status |
| JDBC/Hikari active/idle/pending | Pool near saturation or queued threads |
| Hikari acquisition time | Wait time borrowing connections |
| JDBC query duration | SQL dependency latency |
| Transaction failures/rollbacks | Commit, constraint, or optimistic lock errors |
| Database CPU/IO/storage | Resource saturation |
| Deadlocks/blocked sessions | Concurrency and transaction design |
| DB logins/new connections | Connection churn and token refreshes |
| Flyway startup duration/errors | Migration lock or schema permission issues |

**Do not assume every metric appears automatically just by adding Actuator**: some require JDBC/OpenTelemetry instrumentation/agents or custom meters. Protect Actuator endpoints—never expose `env`, `configprops`, or `heapdump` to the Internet.

### 18.3. Application Insights / OpenTelemetry

In App Service/AKS/Container Apps, use **Azure Monitor OpenTelemetry instrumentation** or the Application Insights Java agent per the support matrix. Trace IDs should span controller → repository → SQL dependency, while never recording **raw SQL parameter values, access tokens, or PII** in traces. Use controlled sampling and retain enough correlation on failed requests.

Distinguish:

~~~text
HTTP latency:       1,200 ms
Hikari wait:          800 ms
SQL execution:        150 ms
Other app processing: 250 ms
~~~

Adding SQL vCores will not cure Hikari pool exhaustion caused by too many replicas or long transactions; fix **pool sizing and transaction lifetimes**.

### 18.4. Azure SQL Metrics vs. PostgreSQL Metrics

**Azure SQL Database:** CPU/DTU or vCore utilization, data/log IO, deadlocks, blocked sessions, Query Store, failed connections, and tier-specific alerts.

**PostgreSQL Flexible Server:** CPU, memory/storage, active connections, IOPS, query statistics/`pg_stat_statements` where available, locks, replication/HA health, and server logs/diagnostics.

Never compare "80% CPU on Azure SQL" directly with "80% CPU on PostgreSQL" as identical throughput. Query patterns, indexes, tiers, and engine behaviors differ; benchmark on real workloads.

### 18.5. Health Checks Must Not Cause an Outage

Spring Boot `/actuator/health` checks the `DataSource` by default and reports `DOWN` when the DB is unreachable. That can fit **readiness**, yet **liveness** should not depend tightly on transient DB availability and trigger mass container restarts that spark a reconnect storm.

Design:

- **Liveness:** is the process/JVM healthy enough to operate?
- **Readiness:** can the instance serve traffic given dependencies and SLOs?
- **Startup probe:** allows time for init, migrations, and pool warm-up if needed.
- DB failures can degrade readiness or trigger business fallbacks.

Never expose database hostnames or credentials in readiness/liveness responses.

## 19. Deploying Spring Boot to Azure Without Exposing Secrets

### 19.1. Reference Architecture Flow

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

**The app uses one database per profile**; the two arrows to SQL and PG represent **two environment choices**, not simultaneous writes per request.

### 19.2. Azure App Service

Key steps:

1. Select an App Service Plan/Java runtime or custom container image.
2. Assign a **system-assigned or user-assigned managed identity** to the app.
3. Configure **outbound VNet Integration** if the database is private-only.
4. Configure app settings: `SPRING_PROFILES_ACTIVE`, JDBC URL, non-secret settings.
5. Provision the Entra/database principal and DB grants separately.
6. If a lab password is needed, inject it via Key Vault References/secret manager—never inside the Docker image.
7. Run the migration job/pipeline inside an authorized network.
8. Deploy the artifact, smoke-test GET/POST/PATCH, and monitor logs/metrics.

**Do not confuse App Service outbound VNet Integration with an inbound Private Endpoint.** An API can accept public HTTPS ingress while keeping its database private-only; those are two independent network paths requiring review.

### 19.3. Azure Container Apps

- Ensure the Container Apps environment has matching VNet/egress topology.
- Attach managed identity and inject config via environment variables/secrets.
- Cap **maximum replicas × Hikari `maximumPoolSize`** within the DB connection limit.
- Under scale-to-zero/cold start, Entra token acquisition, DNS/TLS, and DB connection initialization add startup latency.
- Avoid running Flyway DDL on every replica during peak traffic when a dedicated migration pipeline exists.
- During rolling releases, apply **backward-compatible schema migrations** before rolling out application code.

### 19.4. AKS

- Use **Microsoft Entra Workload Identity** where supported for apps/SDKs instead of unmanaged long-lived secrets in Kubernetes Secrets.
- Verify Pod egress/NetworkPolicy, CoreDNS/Private DNS, NSG/UDR, and firewalls allow DB access.
- Pair HPA/cluster autoscalers with a **database connection budget**; 50 pods × 30 connections quickly exhausts a DB.
- Keep readiness/liveness semantics clean so DB downtime does not restart the entire Pod fleet.
- Run migrations as an isolated job with a distinct identity, locking, and retry policy.

### 19.5. Migration Identity Differs from Runtime Identity

Typical separation:

~~~text
ci-migration-principal:
  CREATE/ALTER/INDEX on approved schema
  executes Flyway once during controlled release

catalog-runtime-principal:
  SELECT/INSERT/UPDATE/DELETE only on required tables
  no CREATE/ALTER/DROP privileges
~~~

If Flyway runs **at app startup** while the runtime identity lacks DDL privileges, the app fails whenever migrations alter schemas. The fix is not granting `db_owner`/superuser to all app replicas; run migrations in an approved pipeline job, keep `ddl-auto=validate` on the app, and optionally disable runtime Flyway (`spring.flyway.enabled=false` when using an external migration job) per your release standard.

### 19.6. CI/CD Across Both Profiles

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

When supporting both SQL Server and PostgreSQL environments, run a dual test matrix: at minimum **both vendor unit/integration suites** plus staging smoke tests on the target engine. Never ship a SQL Server migration solely because PostgreSQL tests passed.

### 19.7. Production Secret and Config Checklist

- App profile, version, and dialect match the target DB.
- JDBC URL contains only host, database, and options—no passwords or tokens.
- TLS certificate validation is enabled with an up-to-date truststore.
- Managed identity and DB role mapping verified.
- Runtime identity holds zero unnecessary DDL privileges.
- Outbound private path verified from both app runtime and migration runner.
- Hikari pool sizing fits replica count and DB tier.
- Logs, Actuator, and metrics leak no credentials or sensitive SQL parameters.
- Connection and query timeouts configured; no unbounded retries.
- Rollback plans exist for both app code and schema changes.

## 20. Troubleshooting: Pinpointing the Failing Layer

### 20.1. Practical Symptom Table

| Symptom | Possible root cause | Investigation |
|---|---|---|
| `Failed to configure a DataSource` | Missing profile, env URL, or driver | Spring profiles, `application-*.yml`, effective config |
| `No suitable driver` | Missing driver dependency or wrong JDBC prefix | Maven dependency tree, driver class, JDBC URL |
| `PKIX path building failed` | JVM CA chain/truststore or cert issue | JDK truststore, TLS hostname, SSL options |
| SQL Server login failed `18456` | Invalid SQL/Entra principal | Entra admin, contained DB user, grants, auth mode |
| SQL firewall denied / timeout | Public firewall, Private Endpoint, or DNS | Network mode, DNS from runtime, TCP 1433 |
| PostgreSQL `28P01` auth failed | Expired password/token or wrong role map | DB user, token audience, managed identity |
| PostgreSQL `42501` insufficient privilege | Login succeeded but missing GRANT | Schema USAGE, table/sequence grants |
| SQL Server permission denied | SQL login succeeded, missing object grant | DB roles, object-level grants |
| PostgreSQL `42P01` relation does not exist | Flyway didn't create table or wrong schema | `spring.flyway.locations`, `search_path`/schema |
| SQL Server invalid object name | Wrong database/schema or unapplied migration | `databaseName`, `dbo`, schema history |
| `FlywayValidateException` | Edited an already-applied migration / checksum mismatch | History, immutable migration policy |
| `Schema-validation: missing table/column` | Entity/DDL mismatch or wrong DB profile | Inspect migrations, dialect, table schema |
| `HikariPool - connection not available` | Pool waiting, slow DB, or slow logins | Active/idle/pending counts, long transactions |
| SQL Server deadlock victim `1205` | Concurrent transactions contending on locks | Query Store / deadlock graph, lock ordering |
| PostgreSQL `40P01` deadlock | Lock order mismatch / long transactions | PostgreSQL logs / `pg_stat_activity` |
| PostgreSQL `40001` serialization failure | Isolation conflict | Retry whole transaction if idempotent |
| Unique constraint conflict | Duplicate SKU / data race | DB index, safe 409 API mapping |
| JPA optimistic locking exception | Row modified concurrently by another transaction | Client concurrency token / retry design |
| Hibernate `LazyInitializationException` | Lazy association accessed outside transaction | DTO projections / transaction boundaries |
| 5xx surge after scale-out | `pool × replicas` exceeded DB budget | DB connection limits, HPA/Hikari sizing |
| Slow p95 post-migration | Missing index, query plan, or collation | Explain/Query Store, compare query plans |
| Works locally, fails in Azure | VNet/DNS/MI differs from local | Test network and identity from deployed runtime |

### 20.2. App-to-Database Diagnostic Sequence

**Step 1 — Scope:** right Spring profile, database service/region/server FQDN, and deployment version?

**Step 2 — Config:** `spring.datasource.url` and driver accurate? Database name and schema accurate?

**Step 3 — Network:** does DNS resolve to the expected private IP; are TCP ports and routes open?

**Step 4 — TLS:** are chain, hostname, and JVM truststore valid without `trustServerCertificate=true` or `sslmode=disable`?

**Step 5 — Authentication:** SQL login/Entra token/PG role valid? Do tokens refresh on new connections?

**Step 6 — Authorization:** `SELECT`/`INSERT` granted on tables? App lacks DDL; migration job has DDL?

**Step 7 — Schema:** Flyway history/version, SQL dialect, column types, and Hibernate validation clean?

**Step 8 — Runtime:** Hikari active/idle/pending, query durations, deadlocks, IO/CPU/throttling?

**Step 9 — Business correctness:** optimistic locking, duplicate rows, idempotency, and transaction outcomes?

**Step 10 — Recovery:** verify API tests, DB state, and metrics; update runbooks and remove temporary exceptions.

### 20.3. TLS Errors Are Never a Reason to Disable Security

If PostgreSQL reports certificate verification failure:

~~~text
JDBC URL: jdbc:postgresql://10.0.0.12:5432/catalogdb?sslmode=verify-full
Observation: certificate issued for server FQDN, not private IP.
~~~

Fix by switching to the **canonical FQDN** backed by Private DNS resolving to the routed IP, and update the CA/truststore. Same for SQL Server: use `*.database.windows.net` per connection policy/certificates—never drop `trustServerCertificate=false`.

### 20.4. Database Credential Errors Are Not Network Errors

~~~text
TCP 5432 succeeded
TLS handshake verified
PostgreSQL login SQLSTATE 28P01
~~~

Network and TLS succeeded; investigate the database role, token/password, Entra config, and pool credential refresh. Creating a second Private Endpoint will not fix a login failure.

### 20.5. Optimistic Lock Failures Differ from Unique Conflicts

- **Unique conflict:** two requests insert the same SKU; protected by the DB unique index.
- **Optimistic lock:** two transactions modify the same stale entity version; protected by JPA `@Version`.
- **Database deadlock:** locks acquired in conflicting order; fix transaction/query order and use controlled retries.

Never return HTTP 500 for everything. Map conflicts to **409 Conflict** cleanly; map DB unavailability to 503 with safe retry policies without leaking internal details.

### 20.6. Caution with Side-Effecting Diagnostic Commands

Never "test connectivity" by running:

~~~sql
DROP TABLE products;
DELETE FROM products;
~~~

Test health using read-only **`SELECT`/metadata queries** in authorized environments; never dump PII tables or wipe migration history. When debugging production, never crank up SQL logging to print customer parameter values.

## 21. FinOps: Right-Sized Connectivity Also Saves Cost

### 21.1. Total Cost Goes Beyond Price per GB

| Component | Azure SQL Database | PostgreSQL Flexible Server |
|---|---|---|
| Compute | vCore/DTU/tier/serverless/elastic pool per choice | vCores/compute tier, scaling/HA |
| Storage | Data/log storage, backup/retention | Storage, backups, log/IO features |
| Networking | Private Endpoint, DNS, egress/Firewall | Private networking, DNS, egress |
| High availability | Geo/replication/availability per tier | HA/standby/PITR/replicas per config |
| Application | App Service/Container Apps/AKS, replicas, CPU/RAM | Same |
| Observability | Query Store, logs, Azure Monitor/App Insights | Server logs/monitoring/pg stats |
| Operations | Schema migrations, permissions, restore tests | Schema migrations, extensions, restore tests |

Pricing varies by **region, time, tier, storage/HA config, and reservations/commitments**. Use the Azure Pricing Calculator and Cost Management rather than hard-coding numbers from examples.

### 21.2. Hidden Cost of Oversized Pools

Suppose 40 app replicas run with `maximumPoolSize=20`:

\[
40\times20=800\ \text{potential DB connections}.
\]

If the DB tier has a lower connection budget and requests contend for sockets, a team might mistakenly double DB compute spend. Try **pool sizing, transaction tuning, query indexing, and scale limits** before buying more capacity. On PostgreSQL, evaluate service-supported connection pooling/proxies when appropriate, testing transaction/session semantics, prepared statements, and auth.

### 21.3. Missing Indexes Raise Both Latency and Bills

When `findBySku` lacks an index:

~~~text
Average query duration:       150 ms
DB CPU high under peak
Hikari active connections:    near max
API p95:                      >1 second
~~~

After adding the right index (and checking write overhead):

~~~text
Query duration may drop materially
Connections return to pool faster
Fewer vCores/replicas may be needed
~~~

This illustrates a **causal pattern**, not a guaranteed 10× speedup on every dataset. Benchmark with **actual execution plans, data sizes, distributions, and read/write ratios**. Too many indexes also raise write I/O and maintenance costs.

### 21.4. Serverless, Scale-to-Zero, and Connection Storms

If Azure SQL serverless pauses per policy, the first connection after idle incurs **cold resume latency**. If hundreds of app instances start or scale simultaneously, they can trigger a login storm. Design:

- Adequate startup/readiness grace periods.
- Bounded connection retries with exponential backoff + jitter.
- Modest Hikari `minimumIdle` across many replicas.
- Warm-up aligned with business SLOs.
- Never enable auto-pause on workloads intolerant of cold starts.

Flexible Server has its own compute/stop/start behaviors per tier; never assume SQL Database serverless semantics carry over identically to PostgreSQL.

### 21.5. Budgets and Governance

- Tag resources with `application`, `environment`, `owner`, `costCenter`.
- Review spend across DB compute, storage, HA, backups, and private networking.
- Watch cost jumps when deployments raise replicas, pools, or connections.
- Set backup retention around RPO—never slash backups blindly to save money.
- Restore tests incur cost and need approved scope.
- Delete only **dedicated lab resources** after sessions, never shared databases/schemas.
- Budget alerts **are not hard spending caps**; assign owners and actions.

**Sound FinOps:** optimize total cost while preserving **business correctness, p95 latency, availability, and recovery objectives**—never merely pick the cheapest tier.

## 22. Case Study: Multi-Customer Product Catalog on Two Database Engines

### 22.1. Requirements

A SaaS vendor serves two enterprise customers using the **same Spring Boot codebase**:

| Attribute | Customer A | Customer B |
|---|---|---|
| Database | Azure SQL Database | PostgreSQL Flexible Server |
| Hosting | Azure App Service | Azure Container Apps |
| Connectivity | Private Endpoint + App Service VNet Integration | Flexible Server private network + Container Apps VNet |
| Authentication | Managed identity/Entra | Managed identity/Entra, PG role + token |
| Data model | Product ID, SKU, name, price, version | Same domain |
| Schema migrations | Flyway SQL Server | Flyway PostgreSQL |
| Monitoring | App Insights + Azure SQL metrics | App Insights + PostgreSQL metrics |
| Target p95 | GET product under 200 ms | GET product under 200 ms |
| Availability | Product API critical; DB failures must surface in health | Same |

Business requirements:

- Unique SKU within each database.
- Store prices with exact decimal precision.
- Users of A and B never see each other's data.
- Concurrent price updates never silently overwrite each other.
- Migrations, backups, and DR have owners and evidence.
- No DB passwords in Git, Docker images, or REST responses.
- Release rollback plan that does not corrupt production schemas.

### 22.2. Deployment Design

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

**Deliberate environment isolation**: each customer has its own runtime, DB principal, and database. Profiles are not a security boundary if two credentials can read the same database; verify authorization and network isolation independently.

### 22.3. Release v1: Creating Schemas

1. Migrate SQL Server using `db/migration/sqlserver/V1__create_products.sql` on Database A.
2. Migrate PostgreSQL using `db/migration/postgres/V1__create_products.sql` on Database B.
3. Test tables, unique indexes, and permissions on each engine.
4. Deploy the Spring Boot image from the **same source version** with the two profiles.
5. Verify Flyway history and confirm JPA `ddl-auto=validate` performs zero schema edits.
6. Test CRUD, TLS, and managed identity from each runtime.

**Never apply both migrations to the same database.** With A using Entra JDBC driver auth and B using PG token integration, test both auth flows separately—including hourly token rotation and pool scaling.

### 22.4. Incident 1: App B Runs for 1 Hour Then Fails to Connect

Symptoms:

~~~text
09:00 Container Apps starts; app creates pool with PostgreSQL Entra token.
09:05 GET /products succeeds.
10:10 DB connections are recycled after scale/failover.
10:10 New connections fail with authentication error.
~~~

Root cause: App B copied a one-time access token into `spring.datasource.password` at startup; **the token expired**, yet new Hikari connections kept sending the stale token. Resolution:

1. Separate auth failure from DNS/TLS using connection/SQLSTATE evidence.
2. Verify token audience, object identity, and mapped PostgreSQL role.
3. Implement a **supported passwordless credential provider** acquiring fresh tokens whenever connections authenticate, with caching/refresh before expiry.
4. Load test across at least one full token rotation cycle and connection churn.
5. Do not revert the DB to static passwords long-term without review.

### 22.5. Incident 2: App Service A Cannot Reach Azure SQL After Going Private-Only

Symptoms:

~~~text
Azure SQL has Private Endpoint.
Public access is disabled.
Developer laptop on VPN can connect.
App Service JDBC times out.
~~~

Likely cause: **App Service lacks outbound VNet Integration**, or VNet/Private DNS links or routes/NSGs block traffic. Test from runtime A rather than trusting VPN laptop reachability. Fix VNet Integration, Private DNS, and TCP 1433 per architecture—never open public access broadly as a "quick test."

### 22.6. Incident 3: Two Users Edit Price Concurrently

~~~text
User A reads SKU-001, price 1,200,000, version 8.
User B reads SKU-001, price 1,200,000, version 8.
User B updates to 1,150,000, version 9.
User A submits old UI form with price 1,180,000.
~~~

In the demo API, the server loads entity version 9 when PATCH arrives; `@Version` does not stop User A from overwriting User B's edit because A's browser held stale state. To enforce **cross-request concurrency**, require an expected version (or `If-Match` ETag) in the API and check it:

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

`expectedVersion` and `newPrice` must be added to the API contract and validated—they do not exist automatically in the demo `updatePrice`. Database-level `@Version` remains essential to catch races **between that check and commit**.

### 22.7. Incident 4: Unicode Search Differs Across Engines

On SQL Server, DB collation may be **case-insensitive and accent-insensitive**; on PostgreSQL, `lower(name) like ...` follows different rules. Searching `"ca phe"` may yield different matches for `"Cà phê"`. Never strip diacritics across your source data as a workaround; define business search semantics, choose matching collations/indexes/search engines, and write **contract tests** for both profiles.

### 22.8. Canary Gate Before Release v2

| Check | Pass condition |
|---|---|
| Flyway migrations | Zero errors, valid history, schema validated |
| Login and TLS | Entra/DB principals valid, server certs verified |
| Private network | DNS/TCP verified from runtime, public denied per policy |
| CRUD | Create/read/update work, duplicate SKU returns 409 |
| Concurrency | Expected version + JPA optimistic lock tests pass |
| Unicode | Product names and search match approved semantics |
| Performance | p95 and DB CPU/IO meet targets |
| Hikari | Active/pending counts and connection churn show zero timeouts |
| Reliability | DB failover/reconnect uses bounded retries |
| Security | No secrets/PII in logs; DDL identity separate from app identity |

**Conclusion:** one Spring Data codebase can serve both Azure SQL and PostgreSQL, provided **database-specific DDL, identity/TLS/networking, Unicode semantics, and integration tests** are governed as explicit contracts.

## 23. End-to-End Hands-On Lab

This lab is strictly for **approved trial subscriptions/databases**. If you lack Azure creation permissions, complete the SQL/JPA design and Testcontainers portions locally on an authorized machine; never alter firewalls on someone else's database.

### 23.1. Lab A — PostgreSQL Flexible Server

1. Obtain server FQDN, database name, and a test database role.
2. Verify network mode (lab source-IP firewall or private path) and TCP 5432.
3. Confirm `sslmode=verify-full` and truststore/certificates.
4. Create the schema with Flyway using the **migration principal**.
5. Set `SPRING_PROFILES_ACTIVE=postgres` and inject lab JDBC URL/user/password from a secret store.
6. Boot Spring Boot and confirm connection/Flyway success logs without secret leaks.
7. Exercise the REST CRUD API.
8. Inspect rows, indexes, and constraints via a separate DBA client.
9. Test invalid credentials or blocked firewall in the lab; confirm layered diagnostics.
10. If Entra is enabled, switch to passwordless integration and verify token refresh on a long-running instance.

### 23.2. Lab B — Azure SQL Database

1. Obtain Azure SQL logical server, database name, and network path.
2. Verify FQDN/port 1433, Private DNS, and TLS `encrypt=true;trustServerCertificate=false`.
3. Create the schema using Flyway migration `sqlserver/V1__...sql`.
4. Set `SPRING_PROFILES_ACTIVE=sqlserver` and inject lab credentials or enable the managed identity profile.
5. Run the same REST CRUD tests as Lab A.
6. Verify UTF-8/Unicode names, identity IDs, and the version column.
7. Verify the unique SKU index and HTTP 409 on duplicate insert.
8. Practice safe read-only `SELECT`/Query Store or execution plan inspection.
9. If using MI, verify Entra contained user/DB grants and credential-free startup.
10. Only after the private path works, test disabling public access per change policy.

### 23.3. HTTP Test Examples

With the lab app running at `http://localhost:8080` and the API secured or running locally:

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

**These commands write data to the configured database**; use only lab DBs and synthetic data. Once the initial insert succeeds, re-running POST with the same SKU returns a conflict—expected unique-constraint behavior, not a random failure.

### 23.4. Lab Self-Check Questions

- Did **Java code** change between the two profiles, or only config and migrations?
- If the app pairs a SQL Server URL with the PostgreSQL driver, does failure occur before or after authentication?
- Why are `ddl-auto=validate` and Flyway two distinct mechanisms?
- Why does SQL Server accepting a username/password not mean an Entra token user automatically has `SELECT` permission?
- What proves you achieved TLS hostname verification rather than merely an open TCP port?
- If the price changes after a browser loaded stale data, does `@Version` alone protect against overwriting?
- When scaling from 5 to 50 replicas, how do you recalculate Hikari pool sizes?
- Why can a SQL Server migration script not be reused verbatim on PostgreSQL?

### 23.5. Completion Criteria

| Criterion | Evidence |
|---|---|
| `application-sqlserver.yml` / `application-postgres.yml` valid | Profiles run independently |
| Engine-specific Flyway migrations | Schema history, tables/indexes, `ddl-auto=validate` |
| Accurate JPA mappings | CRUD IDs, decimals, Unicode, and version work |
| Unique SKU | Database rejects duplicates |
| Paging | Max size 100, deterministic sorting |
| TLS | Chain and hostname verified from runtime |
| Identity | App principal holds DML only; migration principal holds DDL |
| Private network | DNS/route/TCP valid, public access governed by policy |
| Monitoring | Hikari + API + DB metrics captured |
| Operations | Backup/rollback/cleanup plans documented |

## 24. Comprehensive Review Exercises and Sample Answers

### 24.1. Questions

1. Explain how **Spring Data JPA** differs from **Spring Data JDBC**.
2. Trace the chain Controller → Service → Repository → Hibernate/JDBC → Hikari → Azure DB.
3. Contrast Azure SQL Database with SQL Server on a VM.
4. Contrast PostgreSQL Flexible Server public networking with private VNet-injected networking.
5. Write an Azure SQL JDBC URL enforcing TLS hostname verification.
6. Write a PostgreSQL JDBC URL using `sslmode=verify-full` and a Java truststore.
7. Explain `SPRING_PROFILES_ACTIVE` and the risk of activating both profiles simultaneously.
8. List Maven dependencies for Spring Data JPA, JDBC drivers, and Flyway.
9. Write two Flyway migrations creating `Product` with an auto-increment ID and decimal price.
10. Explain `@Id`, `@GeneratedValue(IDENTITY)`, `@Version`, and `@Nationalized`.
11. Write a repository method looking up a product by SKU.
12. Write a pageable search enforcing a bounded page size.
13. Why does `@Transactional(readOnly=true)` not replace a database read-only role?
14. Describe a lost-update scenario detected by `@Version`.
15. Explain why `@Version` alone cannot prevent stale UI edits across HTTP requests.
16. State how SQL Server and PostgreSQL differ on case-insensitive Unicode searches.
17. Explain the cause and prevention of JPA N+1 queries.
18. Compare `BigDecimal` vs. `double` for monetary values.
19. Compute total connections for 25 replicas × Hikari 12 connections.
20. Analyze PostgreSQL token expiration when a pool opens new connections.
21. Explain how SQL Server Entra managed identity differs from PostgreSQL JDBC token-as-password.
22. Why does Azure Contributor not automatically grant SQL `SELECT`?
23. Write the ordered verification sequence: DNS → TCP → TLS → auth → grants.
24. Design a CI/CD pipeline with pre-rollout migrations and canary deployment.
25. Identify metrics distinguishing pool saturation from slow SQL.
26. Design a retry policy for serialization/deadlock errors without double-charging.
27. Explain when Testcontainers suffices vs. when Azure staging is required.
28. Analyze cost and risks when scaling from 5 to 50 app replicas.
29. Design backup/restore testing and a data-migration strategy when switching engines.
30. List commands and actions that must never be run on production just for learning.

### 24.2. Selected Answers

**Question 5 — Azure SQL URL:**

~~~text
jdbc:sqlserver://my-sql-server.database.windows.net:1433;databaseName=catalogdb;encrypt=true;trustServerCertificate=false;
~~~

**Question 6 — PostgreSQL URL:**

~~~text
jdbc:postgresql://my-pg-server.postgres.database.azure.com:5432/catalogdb?sslmode=verify-full&sslfactory=org.postgresql.ssl.DefaultJavaSSLFactory
~~~

**Question 11 — Spring Data Repository:**

~~~java
Optional<Product> findBySku(String sku);
~~~

**Question 19 — pool:** 25 × 12 = **300 potential app connections**, excluding migration, DBA, and monitoring connections. If the DB connection budget is lower, reduce pool size or review scaling/tier.

**Question 20 — PG Entra:** short-lived tokens must never sit statically in Hikari's password field. Use a credential provider/new-connection token refresher or a verified Spring Cloud Azure integration.

**Question 21 — auth:** Microsoft SQL JDBC Driver supports `authentication=ActiveDirectoryManagedIdentity` where applicable; PG JDBC uses a DB username/role plus a refreshed token in the password field via integration.

**Question 24 — release:** prepare backward-compatible expand DDL migrations, run via DDL principal in a private runner, smoke test, canary app rollout, measure SQL/PG performance, and roll back the image or run a forward-fix migration if data was already written.

**Question 26 — retry:** retry only whole idempotent transactions with backoff/jitter for classified transient errors, using idempotency keys for side-effecting operations. Never infinitely retry 400s or unique conflicts.

### 24.3. Rubric

| Criterion | Passing standard |
|---|---|
| **Spring Data** | Distinguishes JPA/JDBC, repositories, and transactions |
| **Database portability** | Vendor dialects, migrations, Unicode, and locking verified |
| **Security** | TLS `verify-full`, Private DNS, Entra/DB grants separated from RBAC |
| **Data integrity** | Unique constraints, decimals, optimistic locks/idempotency |
| **Reliability** | Pool sizing, retries, failover, and backup/restore strategies |
| **Testing** | Testcontainers for both dialects + Azure staging smoke tests |
| **Observability** | HTTP, pool, query, and DB metrics |
| **FinOps** | Connections, compute, storage, HA, and budgets sized |

## 25. Pre-, During-, and Post-Production Deployment Checklists

### 25.1. Architecture and Service Selection

- [ ] Confirm whether each deployment targets **Azure SQL Database** or **PostgreSQL Flexible Server**.
- [ ] Pick tier, region, HA, backup, and compute matching SLO, RPO/RTO, and budget.
- [ ] Assign business/data owners and data classification.
- [ ] Establish an authoritative database—never treat caches or event buses as the sole transaction ledger.
- [ ] Define private/public network topology, DNS, and runtime egress clearly.
- [ ] Never design one `@Transactional` spanning two databases without a distributed consistency strategy.

### 25.2. Application and Schema

- [ ] Lock supported Java/Spring Boot/driver/Flyway versions and review security advisories.
- [ ] Exactly one vendor profile active per deployment.
- [ ] JDBC URL matches driver, host, port, database, and dialect.
- [ ] Separate SQL Server/PostgreSQL Flyway scripts reviewed and tested.
- [ ] Hibernate `ddl-auto=validate`; never auto-mutate production schemas.
- [ ] Entity mappings for Unicode, numeric, UTC timestamps, `IDENTITY`, and `@Version` tested on both engines.
- [ ] Unique constraints/indexes enforced in the database, not only in service code.
- [ ] DTO/Bean Validation and safe REST error responses; never leak entities or SQL exceptions.
- [ ] Bounded, deterministic paging; query indexes measured on realistic data volumes.
- [ ] Concurrent writes, optimistic locking, and HTTP stale-version checks tested.

### 25.3. Security and Networking

- [ ] Azure SQL uses `encrypt=true;trustServerCertificate=false`.
- [ ] PostgreSQL uses `sslmode=verify-full` with proper truststore/CA.
- [ ] Canonical FQDN and Private DNS resolve accurately from the **runtime**.
- [ ] App Service/Container Apps/AKS have outbound network paths; CI migration runners can also connect.
- [ ] Public network access/firewalls restricted by policy with no leftover broad exceptions.
- [ ] Microsoft Entra principals and **DB users/roles/grants** properly configured.
- [ ] Entra managed identity/token refresh tested across pool connection churn.
- [ ] App principal has only required DML; migration principal has DDL.
- [ ] No passwords, tokens, or sensitive SQL parameters in Git, images, logs, or dumps.
- [ ] Key Vault/secret stores follow least privilege with a rotation plan if passwords remain in use.

### 25.4. Performance and Operations

- [ ] `Hikari pool × max app replicas` fits within the connection budget.
- [ ] Connection, query, and request timeouts aligned consistently.
- [ ] Transient retries use backoff, jitter, and idempotency without double-writes.
- [ ] Long transactions, N+1 queries, missing indexes, and deep offset pagination addressed.
- [ ] Readiness/liveness probes avoid restart storms during DB outages.
- [ ] HTTP p95/p99, active/pending pools, and DB CPU/IO/locks/deadlocks monitored.
- [ ] App Insights/OpenTelemetry strip secrets and PII.
- [ ] Alerts have owners, runbooks, SLOs, and sensible thresholds/suppression.
- [ ] PITR/backup restores and database failovers tested against business RPO/RTO.
- [ ] Scaling, HA, and DR plans exist—not just a single default instance.

### 25.5. Release

- [ ] Testcontainers/CI run migrations and repository tests for **both engines**.
- [ ] Azure staging tests real TLS, Entra, Private DNS, and permissions.
- [ ] Production migrations approved and executed under a DDL identity.
- [ ] Schema changes remain backward-compatible with older app versions during rolling deployments.
- [ ] Canary rollout monitors 5xx rates, Hikari pending threads, query latency, and DB throttling.
- [ ] App rollback and **schema forward-fix** plans prepared for live data.
- [ ] Data verification performed post-deploy rather than checking only green container status.

### 25.6. Incident Response

- [ ] Confirm exact database engine, profile, subscription, and resource IDs.
- [ ] Isolate layer by layer: DNS → TCP → TLS → authentication → authorization → SQL/schema.
- [ ] Confirm outages, pool starvation, slow SQL, or lock contention before scaling blindly.
- [ ] Never open wide public firewalls, grant `db_owner`, or disable TLS as a "quick fix."
- [ ] Capture secret-free/PII-free evidence and trace DB errors by correlation ID.
- [ ] Check transaction outcomes before retrying data-mutating operations.
- [ ] Verify backups/DR if data loss is suspected.
- [ ] Post-recovery, verify business correctness, close temporary exceptions, and update runbooks.

## 26. Lab Cleanup and Avoiding Accidental Database Deletion

Azure SQL and PostgreSQL Flexible Server can **continue accruing charges** even after Spring Boot stops. Yet production databases, private DNS zones, VNets, or resource groups may be **shared resources**—never delete them blindly just to clean up a lab.

### 26.1. Inventory Resources Using Read-Only Commands

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table

# Azure SQL server; replace placeholders with authorized lab resources.
az sql server show \
  --resource-group "<approved-lab-resource-group>" \
  --name "<lab-sql-logical-server>" \
  --output json

# PostgreSQL Flexible Server; read-only command.
az postgres flexible-server show \
  --resource-group "<approved-lab-resource-group>" \
  --name "<lab-pg-flexible-server>" \
  --output json
~~~

These commands **do not mutate resources** but require read access. Never assume a resource named `dev` or `test` is automatically disposable; check owners and dependencies.

### 26.2. Cleanup Procedure

1. Confirm exact **subscription, resource group, server, database**, and owner.
2. Inventory any apps, CI jobs, DBAs, or reporting tools still using the database.
3. Confirm retention, backup, or export needs before deletion.
4. Revoke secrets and delete **only lab-specific principals/test data** per change approval.
5. Close temporary lab firewall exceptions or public access rules.
6. Delete **lab-dedicated resources** (database/server/Private Endpoint) only when confirmed unshared.
7. Never delete Private DNS zones, Resolvers, VNets, or Key Vaults shared with production.
8. Check Cost Management for lingering DB compute, backups, Private Endpoints, or log charges.
9. Archive lab findings, SQL migration versions, and lessons learned without storing passwords or tokens in reports.

Commented deletion examples (**no execution required**):

~~~bash
# DO NOT RUN on production or unapproved resources.
# az sql db delete --resource-group "<rg>" --server "<server>" \
#   --name "<lab-database>" --yes

# az postgres flexible-server delete \
#   --resource-group "<rg>" --name "<lab-server>" --yes

# Only when the resource group is 100% dedicated to the lab and all owners agree.
# az group delete --name "<approved-lab-resource-group>" --yes
~~~

**Never configure Flyway test cleanup to run `DROP SCHEMA` against a real database**. Testcontainers spins up and tears down ephemeral local databases; misconfigured environment variables or profiles could point tests at Azure production without guardrails.

### 26.3. Guardrails for Dangerous SQL Statements

Never use these statements **to debug connectivity**:

~~~sql
DROP TABLE products;
TRUNCATE TABLE products;
DELETE FROM products;
~~~

To check connectivity, target a lab table/DB and run a side-effect-free `SELECT`, such as:

~~~sql
SELECT COUNT(*) FROM products;
~~~

On a shared database, even `COUNT(*)` over huge tables can generate load; prefer lightweight health probes and privilege checks. Never delete `flyway_schema_history` to "re-run V1" in production.

## 27. References and Takeaways

### 27.1. Technical References

In real implementations, consult documentation matching your **exact versions** of Spring Boot, drivers, and Azure services:

- [Spring Data JPA reference](https://docs.spring.io/spring-data/jpa/reference/) — repository methods, projections, paging, transaction integration.
- [Spring Boot data access reference](https://docs.spring.io/spring-boot/reference/data/sql.html) — DataSource/Hikari/JPA/Flyway.
- [Hibernate ORM documentation](https://hibernate.org/orm/documentation/) — dialects, mappings, optimistic locking.
- [Flyway documentation](https://documentation.red-gate.com/fd) — versioned migrations, database support, schema history.
- [Microsoft JDBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server) — driver, authentication, TLS, and connection properties.
- [Microsoft Entra authentication with Microsoft JDBC Driver](https://learn.microsoft.com/sql/connect/jdbc/connecting-using-azure-active-directory-authentication) — managed identity/identity selection and prerequisites.
- [Azure SQL Database connectivity](https://learn.microsoft.com/azure/azure-sql/database/connectivity-architecture) — networking/connection policies.
- [Azure SQL Microsoft Entra authentication](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview) — principals and data-plane permissions.
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — connectivity/networking/HA.
- [PostgreSQL Flexible Server Microsoft Entra authentication](https://learn.microsoft.com/azure/postgresql/flexible-server/how-to-configure-sign-in-azure-ad-authentication) — Entra principals and token logins.
- [PostgreSQL JDBC documentation](https://jdbc.postgresql.org/documentation/) — `sslmode`, SSL factories, parameters, and type mapping.
- [Azure Spring and Java developer documentation](https://learn.microsoft.com/azure/developer/java/) — managed identity, deployment, and SDK compatibility.
- [Spring Testcontainers documentation](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — realistic DB integration testing.

**Note:** URLs and feature availability may change. Before using any Maven version, Spring Cloud Azure passwordless starter, SQL Server managed identity authentication, PostgreSQL Entra role mapping, or networking mode in production, consult the matching Microsoft/Spring/driver release documentation and run real tests. Never let examples override security policies or DBA authority.

### 27.2. Twelve Core Principles

1. **Spring Data is a data-access abstraction**, not an eraser for SQL Server vs. PostgreSQL differences.
2. **One vendor profile per deployment:** JDBC driver, dialect, Flyway locations, and DB permissions must align.
3. **Vendor-specific DDL**: SQL Server `IDENTITY/NVARCHAR/DATETIME2` differ from PostgreSQL `IDENTITY/VARCHAR/timestamp`.
4. **ORM portability has limits**: Unicode/collations, JSON/native SQL, locking, paging, and query plans require tests.
5. **Manage schemas via migrations**: Flyway versioned scripts, `ddl-auto=validate`, reviews, and backward compatibility.
6. **DB constraints provide final data protection**: unique indexes, decimals, optimistic versions, and transactions.
7. **`@Transactional` never turns multiple databases or a message broker into one ACID transaction**.
8. **TLS is mandatory**: SQL Server `encrypt=true;trustServerCertificate=false`, PostgreSQL `sslmode=verify-full`, valid CAs and hostnames.
9. **Private networking and DB auth are two separate layers**: outbound VNet/Private DNS must work; Azure RBAC never replaces SQL/PG `GRANT`.
10. **Managed identity differs by JDBC driver**: SQL Server's driver has dedicated auth modes; PostgreSQL relies on token-as-password/roles with proper refresh.
11. **Size connection pools against total replicas**: oversized pools, retry storms, and slow queries can each cause outages.
12. **Testing and operations must target real databases**: Testcontainers for both engines, Azure staging smoke tests, tracing/metrics, backup/DR, and FinOps.

### 27.3. Conclusion

A Spring Boot application using Spring Data to access **Azure SQL Database or Azure Database for PostgreSQL Flexible Server** is well-deployed only when **entities and migrations match the engine, JDBC connects over TLS through approved networking, identities hold exact database grants, transactions and constraints protect data integrity, pools and queries meet SLOs, both profiles are tested, and operations include monitoring, rollback, recovery, and cost control**.
