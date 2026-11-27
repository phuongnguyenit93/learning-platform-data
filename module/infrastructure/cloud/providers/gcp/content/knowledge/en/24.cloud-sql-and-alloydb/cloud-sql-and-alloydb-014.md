# Hands-On Spring Data JPA Application with Cloud SQL

> **Chapter:** Cloud SQL and AlloyDB  
> **Module:** **CLOUD_PROVIDERS_GCP** — Exploring Google Cloud from project, IAM, and VPC organization to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, secure resources, automate delivery, and monitor reliability and cost.

In this lesson, we build a **product catalog** REST API using **Java 21, Spring Boot, Spring Data JPA, Hibernate, and PostgreSQL on Cloud SQL**. The API supports creating, fetching, and paginating products, with schemas managed by Flyway. Local runs use **Cloud SQL Auth Proxy**, while **Cloud Run** deployments use the **Cloud SQL Java Connector** with passwords stored in Secret Manager.

This is a **Cloud SQL for PostgreSQL** lab, not an AlloyDB cluster tutorial. Both products speak PostgreSQL where applicable, yet differ in management models, performance, features, and pricing; never blindly swap a Cloud SQL endpoint for AlloyDB while assuming identical connection behavior.

**Guiding rule:** prefer an existing lab or dev instance. Cloud SQL is a provisioned database and **can incur charges even with zero requests**. Never create/delete instances, expose public access, or touch production data without owner approval.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Cloud SQL instance, PostgreSQL database/user/schema**, JPA Entities, Repositories, and transactions.
2. Build a Spring Data JPA REST API with validation, unique constraints, and proper error handling.
3. Use **Flyway versioned migrations** and Hibernate **`ddl-auto=validate`** to govern schemas.
4. Connect locally via **Cloud SQL Auth Proxy** and on Cloud Run via **Java Connector**, understanding public/private IP and IAM.
5. Deploy a private Cloud Run service separating runtime identity, DB credentials, and PostgreSQL privileges.
6. Calculate HikariCP connection budgets with Cloud Run autoscaling to avoid exhausting database connections.
7. Verify live behavior, diagnose schema/IAM/password/network errors, and monitor logs, Query Insights, and cost.
8. Explain transaction/JPA boundaries, backups, HA, rollbacks, and when to consider AlloyDB.

## 1. End-to-End Architecture

~~~mermaid
flowchart LR
    CLIENT["Authenticated HTTP client"] --> RUN["Cloud Run\nSpring Boot REST API"]
    RUN --> JPA["Spring Data JPA\nHibernate"]
    JPA --> POOL["HikariCP\nmax pool 5"]
    POOL --> CONNECTOR["Cloud SQL Java Connector\nIAM + TLS"]
    CONNECTOR --> PG[("Cloud SQL PostgreSQL\ncatalog database")]
    MIGRATION["Flyway\nV1__create_products.sql"] --> PG
    SECRET["Secret Manager\nDB password"] -. "Secret reference" .-> RUN
    IAM["Runtime service account\nCloud SQL Client"] -. "IAM" .-> CONNECTOR
~~~

**Both authentication layers must succeed:**

- **Cloud SQL Connector/IAM**: Cloud Run's runtime service account holds **Cloud SQL Client** to connect to the instance while the Java Connector fetches metadata and establishes an encrypted tunnel.
- **PostgreSQL authentication/authorization**: user **`catalog_app`**, with a valid password, permitted to **CONNECT** to the database and operate on the target schema/tables. Cloud SQL Client **never automatically grants `SELECT/INSERT`** to a PostgreSQL user.

Database permission requirements are independent of HTTP callers' **Cloud Run Invoker** permissions. One never substitutes for the other.

### 1.1. Request and Transaction Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant CTRL as ProductController
    participant S as ProductService @Transactional
    participant R as ProductRepository
    participant PG as PostgreSQL
    C->>CTRL: POST /api/products
    CTRL->>S: create(validated DTO)
    S->>R: saveAndFlush(entity)
    R->>PG: INSERT INTO catalog_app.products
    PG-->>R: Generated identity / constraint status
    R-->>S: Saved entity
    S-->>CTRL: ProductResponse
    CTRL-->>C: HTTP 201 Location
~~~

**`@Transactional`** manages the database unit of work; it does not automatically wrap external calls such as sending emails, Pub/Sub messages, or HTTP webhooks. For cross-service side effects, consider a **transactional outbox**.

## 2. Preparation Before Creating Resources

Illustrative environment: **Cloud Shell/Linux/macOS Bash**, JDK 21, Maven, `gcloud` CLI, `psql`, and Cloud SQL Auth Proxy (v2) for local runs. Commands running **`gcloud sql/run/secrets ... create/deploy`** make real changes — run only in an approved lab project with billing and quota.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
INSTANCE="catalog-pg-lab"
DB_NAME="catalog"
DB_USER="catalog_app"
SERVICE="catalog-api-lab"
RUNTIME_SA="catalog-runtime@$PROJECT_ID.iam.gserviceaccount.com"

# READ-ONLY — confirm exact project and existing resources.
gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud services list --enabled --project="$PROJECT_ID"
~~~

Cloud SQL, Cloud Run, Cloud Build, Artifact Registry, and Secret Manager APIs must be enabled for the lab scope. Enabling APIs requires **`serviceusage.services.enable`**. Never enable APIs in production just to test a command.

~~~bash
# MODIFIES PROJECT — only with approval.
gcloud services enable \
  sqladmin.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

### 2.1. Choosing the Right Cloud SQL Setup

| Option | When to Choose | Notes |
|---|---|---|
| **Existing dev instance** | Organization already provides a learning environment | Create only an isolated DB/schema; never alter shared IAM/networking without approval |
| **Dedicated zonal lab instance** | Isolation needed and budget approved | No HA, synthetic data only; clean up with owner after the lab |
| **HA / regional instance** | Production data with availability requirements | Higher cost; requires backups, PITR, and failover runbooks |
| **Public IP + Java Connector** | Simple lab where policy permits | Connector handles IAM+TLS; no need to open authorized networks for Java Connector over public IP |
| **Private IP + Java Connector** | Environment already has VPC/private networking | Requires real VPC egress path and **`ipTypes=PRIVATE`**; connector does not create routes |
| **AlloyDB** | PostgreSQL workload needing AlloyDB performance/architecture | Evaluate pricing, separate connectors/networking; never drop an AlloyDB ID directly into Cloud SQL connection names |

**Connectivity:** Cloud SQL Java Connector handles IAM authorization and encryption; it **does not** create a network path to a private IP. Cloud Run needs **Direct VPC egress** or a supported VPC mechanism when using private IP. <https://docs.cloud.google.com/sql/docs/postgres/connect-connectors>

### 2.2. Optional Instance Creation (Dedicated Lab Only)

If no instance exists, after confirming pricing/quotas and ownership, an example **Cloud SQL Enterprise**, **PostgreSQL 16**, **zonal** setup:

~~~bash
# BILLABLE CHANGE — use only in an approved lab project/instance.
gcloud sql instances create "$INSTANCE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-custom-1-3840 \
  --availability-type=ZONAL \
  --storage-size=10

# READ-ONLY inspect instance details and IP settings.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,databaseVersion,connectionName,ipAddresses,settings)"
~~~

**Never use this sizing for production.** Adjust machine, edition, region, storage, and org policies as needed. For PostgreSQL 16+, **explicitly specify `--edition`** to avoid unexpected edition defaults. A new instance accrues VM/storage/backup charges even with zero API traffic.

### 2.3. Creating the Database and Database User

~~~bash
# READ-ONLY list existing databases and users.
gcloud sql databases list \
  --instance="$INSTANCE" --project="$PROJECT_ID"

gcloud sql users list \
  --instance="$INSTANCE" --project="$PROJECT_ID"

# MODIFIES — only if 'catalog' does not exist and owner approves.
gcloud sql databases create "$DB_NAME" \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

Create the **built-in PostgreSQL user `catalog_app`** in **Google Cloud Console → Cloud SQL → instance → Users**, set a strong password, and store it in Secret Manager. Never put passwords in CLI history, `application.properties`, Git, or documentation examples. When automating via CLI, **`gcloud sql users create`** accepts **`--password`**; never pass literal passwords in history-logged commands on shared hosts.

**Grant PostgreSQL privileges:** connect using an **authorized database admin account** into database **`catalog`** and run:

~~~sql
-- RUN ON DATABASE catalog as a DBA with CREATE SCHEMA rights.
-- Account catalog_app must exist first.
CREATE SCHEMA IF NOT EXISTS catalog_app AUTHORIZATION catalog_app;
GRANT CONNECT ON DATABASE catalog TO catalog_app;
~~~

Schema **`catalog_app`** is owned by DB role **`catalog_app`** so Flyway in this **lab** can create tables. In production, separate a **migration role** with DDL privileges from a **runtime role** restricted to DML (`SELECT/INSERT/UPDATE/DELETE`); avoid letting runtime apps alter schemas arbitrarily.

**Cloud SQL PostgreSQL note:** Cloud SQL users are managed at the instance level, whereas privileges on each **database/schema/table** are granted via PostgreSQL SQL. If a schema already exists under another owner, never reassign ownership or grant broad privileges without approval.

## 3. Java Project Structure

Create a **personal practice directory** (do not create extra files inside this Markdown knowledge module):

~~~text
catalog-api-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/catalog/
        │   ├── CatalogApplication.java
        │   ├── Product.java
        │   ├── ProductRepository.java
        │   ├── ProductService.java
        │   ├── ProductController.java
        │   └── ApiErrors.java
        └── resources/
            ├── application.properties
            ├── application-cloudsql.properties
            └── db/migration/V1__create_products.sql
~~~

### 3.1. `pom.xml` — Spring Boot 3, JPA, PostgreSQL, Flyway

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>catalog-api-lab</artifactId>
  <version>1.0.0</version>
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
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
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
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>com.google.cloud.sql</groupId>
      <artifactId>postgres-socket-factory</artifactId>
      <version>1.31.0</version>
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

**About versions:** this file pins Spring Boot **3.5.7** and Java Connector **1.31.0** to illustrate dependencies. For real deployments, audit artifact versions/BOMs, compatibility, and CVEs. With Spring Boot 3.5, include both **`flyway-core`** and **`flyway-database-postgresql`** for PostgreSQL; Spring Boot auto-configures Flyway when matching dependencies are on the classpath. Verify with `mvn dependency:tree` before deploying.

### 3.2. Spring Boot Entrypoint

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

## 4. Flyway Migration and JPA Mapping

### 4.1. `V1__create_products.sql`

~~~sql
-- DB: catalog; schema catalog_app owned by database role catalog_app.
CREATE TABLE catalog_app.products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_products_name ON catalog_app.products (name);
~~~

Flyway runs each migration **once**, recording version and checksum in its history table. Never edit an already-applied `V1` migration; add **`V2__...sql`** for subsequent changes. On multi-instance Cloud Run deployments, never let every instance run production DDL at startup: use a dedicated migration job/pipeline with locking, scheduling, and scoped permissions; this lab keeps one small schema for clarity.

### 4.2. `Product.java`

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products", schema = "catalog_app")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal unitPrice;

    protected Product() {} // JPA requires a no-arg constructor.

    public Product(String sku, String name, BigDecimal unitPrice) {
        this.sku = sku;
        this.name = name;
        this.unitPrice = unitPrice;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
~~~

**Why use `BigDecimal`?** Monetary prices should never use binary floating-point **`double`** where exact arithmetic is required; **`NUMERIC(12,2)`** stores exact decimal values. For multi-currency systems, add an explicit **currency** column, rounding rules, and clear contracts.

Entities are not the public API contract: the controller returns DTOs rather than serializing JPA entities directly, preventing accidental exposure of lazy relations, internal fields, and unexpected **N+1** queries.

## 5. Spring Data Repository, Service, and REST Controller

Spring Data JPA generates common CRUD queries from a **Repository interface**; Hibernate translates Entity operations into SQL over the JDBC `DataSource`. This **does not eliminate** the need to understand SQL, transactions, indexes, and query plans.

### 5.1. `ProductRepository.java`

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
~~~

**`findBySku`** is a derived query; Spring Data builds the query from the method name. For SKU uniqueness checks, the database **`UNIQUE` constraint** remains the final safeguard under concurrent requests. Never rely on **`existsBySku`** alone and assume race conditions are eliminated.

### 5.2. `ProductService.java`

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public record ProductResponse(
            Long id, String sku, String name, BigDecimal unitPrice) {}

    @Transactional
    public ProductResponse create(
            String sku, String name, BigDecimal unitPrice) {
        Product saved = repository.saveAndFlush(
                new Product(sku, name, unitPrice));
        return toResponse(saved);
    }

    @Transactional(readOnly = true)
    public ProductResponse find(Long id) {
        return repository.findById(id)
                .map(ProductService::toResponse)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Product not found"));
    }

    @Transactional(readOnly = true)
    public Page<ProductResponse> list(Pageable pageable) {
        return repository.findAll(pageable)
                .map(ProductService::toResponse);
    }

    private static ProductResponse toResponse(Product p) {
        return new ProductResponse(
                p.getId(), p.getSku(), p.getName(), p.getUnitPrice());
    }
}
~~~

- **`@Transactional`** starts and completes a transaction around the Spring proxy call; unchecked exceptions roll back by default.
- **`saveAndFlush`** flushes SQL immediately so database constraints surface inside the service call; it **does not** alter transaction atomicity.
- **`@Transactional(readOnly=true)`** signals read-only intent and permits driver/JPA optimizations; it is not a security boundary. The database role must still enforce least privilege.
- **`Page`** is convenient for small APIs yet runs a **`COUNT`** query; on very large tables, evaluate keyset pagination, indexes, and SQL execution plans.

### 5.3. `ProductController.java`

~~~java
package com.example.catalog;

import com.example.catalog.ProductService.ProductResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.net.URI;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    public record CreateProductRequest(
            @NotBlank @Size(max = 40)
            @Pattern(regexp = "[A-Za-z0-9_-]+")
            String sku,
            @NotBlank @Size(max = 120) String name,
            @NotNull @DecimalMin("0.00")
            @Digits(integer = 10, fraction = 2)
            BigDecimal unitPrice) {}

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse created = service.create(
                request.sku(), request.name(), request.unitPrice());
        return ResponseEntity.created(
                URI.create("/api/products/" + created.id()))
                .body(created);
    }

    @GetMapping("/{id}")
    public ProductResponse find(@PathVariable Long id) {
        return service.find(id);
    }

    @GetMapping
    public Page<ProductResponse> list(
            @PageableDefault(size = 20) Pageable pageable) {
        return service.list(pageable);
    }
}
~~~

**DTO validation** catches bad input at the HTTP boundary, while **`UNIQUE`, `NOT NULL`, `CHECK`, and `NUMERIC(12,2)`** remain enforced by the database. Keep both: early validation improves UX, while PostgreSQL constraints protect consistency across multiple clients or jobs.

### 5.4. `ApiErrors.java` — Never Leak SQL Exceptions to Clients

~~~java
package com.example.catalog;

import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<Map<String, String>> databaseConstraint() {
        // Do not return raw SQL/constraint details, which could leak internal schema.
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "Product conflicts with a DB constraint"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, String>> invalidRequest() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid product fields"));
    }
}
~~~

In this lab, unique SKU violations return **409**, validation errors return **400**, and missing IDs return **404**. In production, classify specific allowlisted SQLSTATE codes/constraint names rather than mapping every DB error to 409, and attach correlation IDs to structured logs. **Never return stack traces, usernames, JDBC URLs, or raw queries** to callers.

## 6. Two DataSource Configs: Local and Cloud SQL

### 6.1. `application.properties` — Local via Cloud SQL Auth Proxy TCP

~~~properties
spring.application.name=catalog-api
server.port=${PORT:8080}
spring.datasource.url=jdbc:postgresql://${DB_HOST:127.0.0.1}:${DB_PORT:5432}/${DB_NAME:catalog}
spring.datasource.username=${DB_USER:catalog_app}
spring.datasource.password=${DB_PASS}

# Each JVM instance holds at most 5 connections in this pool.
spring.datasource.hikari.maximum-pool-size=${DB_POOL_SIZE:5}
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=10000
spring.datasource.hikari.max-lifetime=1800000

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.flyway.enabled=true
spring.flyway.schemas=catalog_app
spring.flyway.default-schema=catalog_app
spring.data.web.pageable.max-page-size=50
management.endpoints.web.exposure.include=health,info
~~~

**Cloud SQL Auth Proxy** exposes a local TCP listener, so JDBC connects to **`localhost:5432`**. The proxy uses ADC/IAM to establish an encrypted tunnel to Cloud SQL, while still requiring the **PostgreSQL username/password** in this example.

**Never use `ddl-auto=update/create/create-drop` in production:** Hibernate must not mutate schemas on every scale-out. **Flyway** manages versioned changes, and **`validate`** fails fast if Entities drift from the schema. For zero-downtime rollouts, expand first and contract later (**expand/contract**) while keeping revisions compatible.

### 6.2. `application-cloudsql.properties` — Cloud SQL Java Connector

~~~properties
# JDBC Socket Factory uses ADC from the Cloud Run runtime service account.
spring.datasource.url=jdbc:postgresql:///${DB_NAME:catalog}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&cloudSqlRefreshStrategy=lazy&ipTypes=${DB_IP_TYPES:PUBLIC}
~~~

The **`cloudsql`** profile overrides only the JDBC URL; username/password, pool settings, and Hibernate/Flyway properties from `application.properties` still apply. Key parameters:

| Setting | Meaning |
|---|---|
| **`INSTANCE_CONNECTION_NAME`** | Cloud SQL **`project:region:instance`**, not the Cloud Run service URL |
| **`socketFactory`** | **`com.google.cloud.sql.postgres.SocketFactory`** from the Java Connector |
| **`cloudSqlRefreshStrategy=lazy`** | Refreshes credentials on demand; suits serverless runtimes with CPU throttling |
| **`DB_IP_TYPES=PUBLIC`** | Connects to the instance's public IP via the Connector |
| **`DB_IP_TYPES=PRIVATE`** | Picks private IP when a VPC egress path exists |
| **`DB_USER/DB_PASS`** | PostgreSQL database credentials, distinct from Cloud IAM identity |
| **`DB_POOL_SIZE`** | Connection limit **per Cloud Run container instance** |

The Java Connector handles IAM/TLS, yet **never grants PostgreSQL privileges** and **never creates a VPC route** to a private IP. Built-in Cloud Run Unix socket integration uses a different setup; with the **Java Connector** shown here, you do not need **`--add-cloudsql-instances`** to mount a Unix socket. Never mix JDBC Socket Factory with Unix socket paths without understanding both modes.

**On secrets:** `DB_PASS` has no default in source files. Locally the learner supplies it interactively; Cloud Run pulls it from Secret Manager. Environment variables holding secrets can still be read by processes or accidentally logged; production setups should enforce IAM/rotation and evaluate mounted secret volumes or direct secret APIs.

## 7. Running Locally via Cloud SQL Auth Proxy

### 7.1. Verify the Instance Connection Name

~~~bash
# READ-ONLY.
INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)')"

printf 'Instance connection name: %s\n' "$INSTANCE_CONNECTION_NAME"
~~~

Install **Cloud SQL Auth Proxy v2** for your OS from official instructions. The Cloud SQL Admin API must be enabled and your principal needs **`roles/cloudsql.client`** on the target project/instance. In an authorized local environment:

~~~bash
# Interactive: creates ADC for your lab account without long-lived key files.
gcloud auth application-default login

# Terminal 1 — keep the proxy running during testing.
# Use port 5432 only if no other local service is bound to it.
cloud-sql-proxy --port 5432 "$INSTANCE_CONNECTION_NAME"
~~~

If the instance has only a private IP, the proxy host must have a VPC route or approved path; add **`--private-ip`** per docs when needed. **The proxy does not create VPN/VPC paths** and does not bypass firewalls or org policies.

### 7.2. Run the Application

In another terminal inside **`catalog-api-lab/`**, enter the **`catalog_app`** password without saving it to shell history:

~~~bash
# Cloud Shell/bash. Never type the literal password directly in a command.
read -r -s -p "PostgreSQL catalog_app password: " DB_PASS
printf '\n'
export DB_PASS

# BUILD + RUN LOCALLY ONLY (creates no Google Cloud resources).
mvn -B -DskipTests package
java -jar target/catalog-api-lab-1.0.0.jar

# When finished, stop the app and run: unset DB_PASS
~~~

At startup, Flyway applies **`V1__create_products.sql`**, Hibernate **`validate`** checks mappings, and HikariCP opens connections on demand. If startup fails on missing schemas or DB roles, fix schema ownership and migrations before testing the API — never escalate IAM to Owner.

**Read-only check via `psql`**, if Postgres client is installed and the proxy is running:

~~~bash
# Open another terminal; psql prompts interactively for the DB password.
psql -h 127.0.0.1 -p 5432 -U catalog_app -d catalog \
  -c 'SELECT version, description, success FROM catalog_app.flyway_schema_history ORDER BY installed_rank;'

psql -h 127.0.0.1 -p 5432 -U catalog_app -d catalog \
  -c 'SELECT id, sku, unit_price FROM catalog_app.products ORDER BY id LIMIT 10;'
~~~

If Flyway history landed in another schema from an earlier run, check **`spring.flyway.default-schema`** rather than dropping the history table to "start over."

## 8. Testing the REST API and PostgreSQL Constraints

### 8.1. Create a Product

~~~bash
# LOCAL: send synthetic test data to the lab database only.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-001","name":"Java Cloud Guide","unitPrice":159000.00}'
~~~

Expected: **HTTP 201 Created**, `Location` header containing **`/api/products/{id}`**, and JSON response with the PostgreSQL-generated ID, SKU, name, and `unitPrice`.

### 8.2. Read by ID and Pagination

~~~bash
# Substitute actual ID from the prior response.
curl -i http://127.0.0.1:8080/api/products/1

curl -i 'http://127.0.0.1:8080/api/products?page=0&size=10&sort=id,asc'

# Non-existent ID.
curl -i http://127.0.0.1:8080/api/products/999999
~~~

Expected: valid `GET` returns **200**; missing ID returns **404**; list returns a **`Page`** with content and pagination metadata. Always enforce a max page size to protect the database.

### 8.3. Test Unique Constraints and Validation

~~~bash
# SKU BOOK-001 already exists -> expect HTTP 409.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-001","name":"Duplicated","unitPrice":100.00}'

# Negative unitPrice -> HTTP 400 from @DecimalMin.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-002","name":"Invalid price","unitPrice":-1}'
~~~

**Never rely on sequential tests alone to prove concurrency safety:** fire two concurrent requests with the same SKU and confirm PostgreSQL stores **only one** row. The app may return **409** to one caller, while the database `UNIQUE` constraint protects integrity during races.

### 8.4. What to Test Before Production?

| Test Type | What It Verifies |
|---|---|
| Service unit tests | DTO mapping, 404 handling, transaction boundaries |
| Repository integration | Unique SKU, `NUMERIC(12,2)`, Flyway schema |
| Web slice | `@Valid`, 400/404/409/201, and pagination |
| Concurrent writes | Two simultaneous requests with same SKU never create two rows |
| Migration smoke test | `V1` and subsequent `Vn` apply cleanly on a cloned DB |
| Cloud SQL connectivity | IAM + DB password + networking + TLS |
| Fault injection | DB timeout/failover/retries with zero duplicate side effects |
| Load test | DB connections, Hikari pending threads, p95 latency |

**Never use a production database for destructive integration tests.** In CI, prefer Testcontainers PostgreSQL or an isolated staging DB; never test migrations by dropping a live app schema.

## 9. Deploying Private Cloud Run with Cloud SQL and Secret Manager

### 9.1. Runtime Identity and Connection Permissions

~~~bash
# MODIFIES IAM — only in lab project, if SA does not yet exist.
gcloud iam service-accounts create catalog-runtime \
  --project="$PROJECT_ID" \
  --display-name="Catalog API runtime identity"

RUNTIME_SA="catalog-runtime@$PROJECT_ID.iam.gserviceaccount.com"

# MODIFIES IAM — Java Connector needs Cloud SQL Client.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/cloudsql.client"
~~~

If Cloud SQL lives **in a different project**, enable the Cloud SQL Admin API in both the app project and the database project, and grant Cloud SQL Client to the runtime principal on the **instance project**. The deployer needs build/deploy rights and **`iam.serviceAccounts.actAs`** on `RUNTIME_SA`. Never grant Owner to work around 403 errors. Cloud SQL Client **does not** grant `SELECT/INSERT` in PostgreSQL; DB grants still belong to `catalog_app`.

### 9.2. Storing the Password in Secret Manager

~~~bash
# MODIFIES — only if the secret does not exist yet.
gcloud secrets create catalog-db-password \
  --project="$PROJECT_ID" \
  --replication-policy="automatic"

# Cloud Shell/bash: interactive entry, keeps password out of history.
read -r -s -p "Database password: " DB_PASS
printf '\n'
printf '%s' "$DB_PASS" | gcloud secrets versions add catalog-db-password \
  --project="$PROJECT_ID" --data-file=-
unset DB_PASS

# READ-ONLY: check version/metadata without printing secret payload.
gcloud secrets versions list catalog-db-password \
  --project="$PROJECT_ID"
~~~

If the secret already exists, do not run `create` again; add a new version only after review. In this lab, confirm **version 1** exists; production should **pin secret versions** and deploy new revisions on rotation rather than tracking `latest`. Never print passwords to logs or pass them as CLI literals.

~~~bash
# MODIFIES IAM — bind strictly on the secret, not the entire project.
gcloud secrets add-iam-policy-binding catalog-db-password \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

### 9.3. Deploying with the Java Connector

Inside your **`catalog-api-lab/`** directory after verifying local database and migrations:

~~~bash
# READ-ONLY.
INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)')"

# MODIFIES: Cloud Build builds Java; Cloud Run creates a private revision.
gcloud run deploy "$SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --cpu=1 \
  --memory=1Gi \
  --max-instances=3 \
  --concurrency=20 \
  --timeout=60s \
  --set-env-vars="SPRING_PROFILES_ACTIVE=cloudsql,DB_NAME=$DB_NAME,DB_USER=$DB_USER,INSTANCE_CONNECTION_NAME=$INSTANCE_CONNECTION_NAME,DB_IP_TYPES=PUBLIC,DB_POOL_SIZE=5" \
  --set-secrets="DB_PASS=catalog-db-password:1"

# READ-ONLY: inspect revision status and configuration.
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Prerequisites:** the Cloud SQL instance has a **public IP** for this lab, Cloud SQL Client and DB credentials are valid, the Cloud SQL Admin API is enabled, and egress is unblocked. The Java Connector handles IAM authorization and encryption, while `DB_USER`/password still authenticate as a **built-in PostgreSQL user**. Cloud Run does not need the **`--add-cloudsql-instances`** Unix socket flag when using the **Java Connector** as shown here. Stick to one consistent connection mechanism.

**Operational note:** Spring's `cloudsql` profile runs Flyway on app startup. Production should run migrations via a separate pipeline/job before scaling replicas and **never** give the runtime account DDL rights; this lab keeps a single small schema so learners can observe the full flow.

### 9.4. If the Instance Has Only a Private IP

The Java Connector does not create VPC routes. Cloud Run needs **Direct VPC egress** or an appropriate VPC connector to reach Cloud SQL's private IP. Example creating a new revision once your org approves a VPC and subnet:

~~~bash
# MODIFIES — substitute real, approved network and subnet values.
gcloud run services update "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --network="YOUR_VPC" \
  --subnet="YOUR_SUBNET" \
  --vpc-egress=private-ranges-only \
  --update-env-vars=DB_IP_TYPES=PRIVATE
~~~

Private paths also depend on routes/firewalls, Private Services Access or PSC per instance type, egress to Google APIs, and subnet permissions (especially with Shared VPC). Never pass literal **`YOUR_VPC`** / **`YOUR_SUBNET`**.

### 9.5. Testing Private Cloud Run

Callers holding **`roles/run.invoker`** on the service can open an authenticated gcloud proxy tunnel:

~~~bash
# Terminal 1 — developer granted Invoker role.
gcloud run services proxy "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --port=8081

# Terminal 2:
curl -i -X POST http://127.0.0.1:8081/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-CLOUD-001","name":"Cloud SQL JPA Lab","unitPrice":99000.00}'

curl -i 'http://127.0.0.1:8081/api/products?page=0&size=10'
~~~

If everything works, creation returns **201** and listing returns **200**. If you hit 403 before reaching Spring, check Cloud Run IAM/invoker; if the controller receives requests yet the DB fails, check Secret Manager, Cloud SQL IAM, PostgreSQL privileges, and networking before adding permissions. **Never enable `allow-unauthenticated` just to test DB connectivity.**

## 10. Connection Pooling and Transactions Under Autoscaling

### 10.1. Calculating the Connection Budget

Each **Cloud Run instance** keeps its own HikariCP pool. With **`max-instances=3`** and **`maximum-pool-size=5`**, the configured pool total for one revision is:

\[
3 \times 5 = 15\ \text{connections}
\]

This is only the **workload pool estimate**, excluding older revisions overlapping during rollouts, other services, migration jobs, admin sessions, and internal connections. Beyond per-Cloud-Run-instance limits, the Cloud SQL instance's **PostgreSQL `max_connections`** and RAM cap the entire server. Cloud Run can briefly exceed `max-instances` in some cases; always leave headroom.

| Parameter | Lab Value | Meaning |
|---|---|---|
| Hikari `maximumPoolSize` | 5 | Max connections **per JVM** |
| Hikari `minimumIdle` | 0 | Avoids holding idle sessions unnecessarily |
| Cloud Run `max_instances` | 3 | Expected scale cap of the service |
| Cloud Run concurrency | 20 | Max concurrent HTTP requests per container — **not** DB connections |
| Hikari connection timeout | 10s | Wait time to borrow a connection before failing |
| PostgreSQL `max_connections` | Instance-dependent | Total database connection capacity |

One instance may accept 20 concurrent HTTP requests while letting only 5 concurrent transactions borrow DB connections; the rest wait in line. Raising pool size cuts wait time yet can push the database over capacity. Inspect **p95 latency, Hikari pending threads, slow queries, and active sessions** before tuning.

### 10.2. Anti-Patterns to Avoid

- Opening a new JDBC connection or `DataSource` per HTTP request.
- Setting every pool to 100 connections and letting the service scale to 50 instances.
- Holding **`@Transactional`** open across slow HTTP API calls or external waits.
- Leaving **`ddl-auto=update/create`** enabled across multiple production instances.
- Returning all rows unpaginated; failing to index real query patterns.
- Serializing JPA Entities with lazy relationships directly, triggering **N+1 queries**.
- Printing SQL parameter bindings, credentials, or PII into Cloud Logging.
- Scaling up Cloud Run CPU without inspecting PostgreSQL I/O, locks, and queries.

### 10.3. Concurrency and Entity Versioning

**`UNIQUE(sku)`** prevents duplicate SKU inserts; it does not prevent **lost updates** when two clients edit the same row simultaneously. If you later add product update endpoints, add **optimistic locking** where appropriate:

~~~java
// Entity addition snippet; never apply without migrating the DB first.
@Version
@Column(nullable = false)
private Long version;
~~~

Flyway must first ship a migration adding **`version BIGINT NOT NULL`** (with proper backfill) before rolling out the updated Entity. You can also pair this with HTTP **`ETag`/`If-Match`** headers for conditional updates. Never add `@Version` and let Hibernate mutate the database schema automatically.

Spring **`@Transactional`** works via proxies; self-invocation within the same bean bypasses the transactional interceptor. Transactions do not atomically wrap Pub/Sub, email, or Cloud Storage; handle external side effects with an **outbox** or idempotent workflows.

## 11. Observability and Troubleshooting Connection Errors

### 11.1. Read-Only Commands

~~~bash
# Cloud Run: ready revision and application logs.
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.latestReadyRevisionName,status.conditions)"

gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=100

# Cloud SQL: instance state and admin operations.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,connectionName,settings)"

gcloud sql operations list \
  --project="$PROJECT_ID" --instance="$INSTANCE"
~~~

Where enabled on eligible instances/editions, **Cloud SQL Query Insights** helps analyze SQL latency, database load, and slow queries. Build dashboards for **active connections**, CPU/memory/disk usage, lock waits, Hikari active/idle/pending, Cloud Run 4xx/5xx, p95 latency, and failed startups.

### 11.2. Symptom Matrix

| Symptom | Likely Cause | Check |
|---|---|---|
| Cloud Run revision fails to become Ready | Flyway failure, DB unreachable, missing secret, startup error | Build/runtime logs and revision conditions |
| HTTP 403 before reaching Controller | Caller lacks Invoker or ID token | Cloud Run IAM |
| Java Connector permission denied | Missing Cloud SQL Client or SQL Admin API | Runtime SA, project IAM |
| Password authentication failed | Wrong `DB_USER`/password/secret version | PostgreSQL user and Secret Manager |
| Permission denied for schema | Missing ownership/GRANT in PostgreSQL | `catalog_app` schema owner and permissions |
| Flyway validate failed | Edited an applied migration, schema drift | `flyway_schema_history`, checksums |
| Hibernate missing table | Flyway didn't run or wrong DB/schema | Profile/JDBC URL and PostgreSQL metadata |
| Connection refused/timeout | Wrong IP type, no public IP, private VPC lacks route | `DB_IP_TYPES`, networking/firewalls/egress |
| Duplicate key | `UNIQUE` SKU violation | API 409 and DB constraint |
| Hikari connection timeout | Pool exhausted, long transactions, DB overload | Hikari metrics, `pg_stat_activity`, Query Insights |
| Too many clients already | Total pools exceed DB `max_connections` | Max instances, pool sizes, active connections |
| HTTP 500 after failover | Stale sockets / transient faults | Retry policy, pool validation, DB failover logs |
| Rising API latency | N+1 queries, missing indexes, lock contention | SQL `EXPLAIN`, Query Insights |
| Costs climb while API is idle | Cloud SQL instance/storage/backups running continuously | Billing by SKU and uptime |

**Never try to fix all errors by granting Owner or making the database public.** Step cleanly through **Cloud Run invoke → Java Connector IAM → network path → PostgreSQL login → schema privileges → SQL performance**.

### 11.3. Never Retry POST Blindly

If a client times out right after the database **COMMIT**s, retrying `POST` can create duplicate objects. Here, **`UNIQUE(sku)`** rejects one duplicate type, yet real order/payment APIs need **idempotency keys**, durable outcome records, transactions, and response replay. On transient connection errors, retry **only retryable errors** with backoff and budgets — never retry constraint violations or authorization failures.

## 12. Security, Backups, HA, and Cost

| Area | Operational Rule |
|---|---|
| **Cloud SQL IAM** | Cloud SQL Client on the exact runtime principal, never Owner |
| **PostgreSQL privileges** | Minimal runtime role; separate schema owner/migration role |
| **DB credentials** | Secret Manager, rotation, never in Git, images, or logs |
| **Networking** | Encrypted Connector; private IP needs VPC egress; public IP does not mean open to all clients |
| **Schema** | Versioned/reviewed Flyway migrations, Hibernate `validate` |
| **Backups/PITR** | Enabled and restore-tested for RPO/RTO; verify retention |
| **HA** | Regional availability/failover per tier/edition; test failover and app retries |
| **Read replicas** | Offload reads if suited; handle replication lag and consistency |
| **Observability** | Query Insights, metrics, log redaction, auditing |
| **Cost** | Instance compute, SSD/IO, HA/replicas, backups/PITR, network, Cloud Run/Build/Secrets/Logs |

### 12.1. Why Shouldn't You Delete an Instance After This Lab Without Checking?

Cloud SQL holds **persistent data**: deleting an instance is not like deleting a Cloud Run revision. If another team shares the instance or it holds backups/replicas/retention data, deletion can destroy data or break services. Only the lab environment owner should approve deleting database infrastructure.

### 12.2. When to Consider AlloyDB Instead of Cloud SQL?

**Cloud SQL for PostgreSQL** fits most traditional relational OLTP apps with a straightforward managed PostgreSQL experience. **AlloyDB** provides a different architecture tuned for PostgreSQL workloads with demanding performance/scale needs, requiring separate evaluation of **cluster/instance roles, networking, connectors, backups, HA, and cost**.

Never swap Cloud SQL's **`INSTANCE_CONNECTION_NAME`** in JDBC Socket Factory for an AlloyDB cluster ID. **AlloyDB uses its own connectivity/client tooling** — consult AlloyDB documentation and validate SQL/extension compatibility, operations, and benchmarks before deciding to migrate.

## 13. Case Study: E-Commerce Product Catalog

### 13.1. Context and Design

A Java team runs a **Catalog API** on Cloud Run, storing products in Cloud SQL for PostgreSQL. Each product has a unique SKU and decimal unit price. During peak shopping hours, Cloud Run scales out instances while the database has fixed CPU, memory, and connection caps.

**Approved design:**

- Spring Data JPA handles CRUD queries without returning Entities as API responses.
- Flyway governs schemas; JPA only validates.
- Java Connector uses Cloud Run's runtime identity with Cloud SQL Client; DB role/catalog schema follow least privilege.
- Password lives in Secret Manager; Cloud Run HTTP is private.
- HikariCP max pool size **5** and Cloud Run max instances **3** for lab; production sized from load tests and DB capacity.
- Cloud Monitoring/Query Insights track p95 latency, errors, slow SQL, connections, and SKU-level costs.

### 13.2. Two Real-World Bugs

**Bug A — Two requests create the same SKU:** both see the SKU is absent and attempt `INSERT`. Relying only on Java **`existsBySku`** before saving lets both pass. The database **`UNIQUE(sku)`** lets only one `INSERT` succeed; the second gets a constraint violation mapped cleanly to 409. If business logic wants idempotent creates, add an idempotency key and response replay.

**Bug B — Pool timeouts during scale-out:** an assumed production config of Hikari pool 30 × 20 Cloud Run instances creates up to **600 potential connections**, overwhelming a small PostgreSQL instance. Scaling Cloud Run instances simply pushes the bottleneck onto the database. The team must right-size pools, bound instances/concurrency, shorten queries, add indexes, and evaluate DB sizing/HA before scaling further.

### 13.3. Acceptance Criteria

| Item | PASS When |
|---|---|
| Schema | Flyway V1 applied; Hibernate `validate` reports zero drift |
| Create | Valid `POST` returns 201 + `Location` |
| Read | Existing `GET` ID returns 200; missing ID returns 404 |
| Validation | Negative price / invalid SKU returns 400; duplicate SKU returns 409 |
| Storage | Data persists across Cloud Run restarts |
| Security | No `allUsers` Invoker; zero passwords in source |
| Connectivity | IAM, PG login, networking, and Secret Manager all work |
| Scaling | Pool waits and DB connections stay within budget; p95 meets SLO |
| Recovery | Backup/restore tested and migration rollback plan documented |
| FinOps | Cloud SQL/Run/Build/Secrets/Storage/Logs inventoried |

## 14. Practice Exercises and Answers

### 14.1. Exercise A — JPA and Flyway

1. Create a dedicated database/schema in the lab.
2. Create the Maven project from Section 3 with the Entity and V1 migration.
3. Run locally via Cloud SQL Auth Proxy and confirm **`catalog_app.products`** exists.
4. Create **`BOOK-001`**, read it back, then test a duplicate `POST` and negative price.
5. Record HTTP statuses, row counts, and Flyway version/checksum in your report.

**Guided answer:** Flyway creates the table and Hibernate validates cleanly; responses are 201/200/409/400 respectively. If the DB throws permission denied, fix **PostgreSQL role/schema** privileges rather than granting Cloud SQL Client to more principals.

### 14.2. Exercise B — Controlled Migration

Add a non-negative integer field **`stockOnHand`** defaulting to 0. Create a **new** migration without modifying V1:

~~~sql
-- V2__add_stock.sql
ALTER TABLE catalog_app.products
    ADD COLUMN stock_on_hand INTEGER NOT NULL DEFAULT 0
    CHECK (stock_on_hand >= 0);
~~~

Then update the Entity, DTOs, and services accordingly. In real rollouts, verify compatibility: adding a column with a default is usually lower risk than dropping/renaming columns, though impact still depends on table size, locks, PostgreSQL version, and app logic.

**Question:** if you rename **`unit_price`** and drop the old column while an older Cloud Run revision is still serving traffic, what happens?

**Answer:** the old revision's queries and `INSERT`s will fail. Use **expand/contract**, deploy compatible code side-by-side, run backfills and dual-reads/writes as needed, and drop the old column last.

### 14.3. Exercise C — Calculating Connection Budget

Suppose each JVM sets pool size **8** and Cloud Run runs **6 instances**. Additionally, a batch worker uses 12 connections and a DBA uses 5 sessions. Calculate potential total connections excluding internal system connections:

\[
6\times 8 + 12 + 5 = 65
\]

**Question:** is PostgreSQL `max_connections=60` enough? Does lowering Cloud Run **concurrency** from 20 to 5 guarantee lower total pool connections?

**Answer:** not enough if all pools saturate; you also need headroom for PostgreSQL and other callers. Lowering concurrency does not shrink **pool max size** or instance count — it can actually spin up *more* instances if incoming traffic stays constant.

### 14.4. Exercise D — Diagnosing 403 vs. Password Errors

Classify three cases:

| Symptom | First Check |
|---|---|
| HTTP Cloud Run call returns **403** before app logs the request | Cloud Run IAM Invoker / ID token |
| Java Connector throws **Permission denied** | Runtime SA Cloud SQL Client, API enablement, right project |
| PostgreSQL throws **password authentication failed** | `DB_USER`/`DB_PASS`/secret version, built-in role |

**Explanation:** a request traverses multiple layers. Never misapply permissions from one layer to fix another; note also that rotating a secret does not auto-update Cloud Run revisions pinned to an older secret version.

### 14.5. Exercise E — Choosing Cloud SQL vs. AlloyDB

A Java app currently runs cleanly on Cloud SQL PostgreSQL, meeting its SLO at a reasonable price. Someone proposes moving to AlloyDB solely because "AlloyDB is PostgreSQL too."

**List** factors that must be verified: query/throughput/latency profile, extension compatibility, cost, HA/backups, VPC/private networking, matching Java client/connector, migration/cutover plan, RPO/RTO, and benchmarks. **Answer:** never switch database platforms by protocol name alone; base decisions on workload metrics and evidence.

### 14.6. Sample Verification Checklist Report

~~~text
PROJECT_ID / REGION / OWNER:
CLOUD_SQL_INSTANCE / EDITION / VERSION / CONNECTION_NAME:
DB_NAME / DB_USER / SCHEMA:
SPRING_BOOT / JDK / JDBC_CONNECTOR_VERSION:
FLYWAY_VERSION / MIGRATION_RESULT:
LOCAL_PROXY / JDBC_CONNECTIVITY:
CLOUD_RUN_SERVICE / READY_REVISION / RUNTIME_SA:
CLOUD_SQL_CLIENT / SECRET_ACCESSOR:
IP_MODE / VPC_ROUTE:
POST_201 / GET_200 / NOT_FOUND_404:
BAD_REQUEST_400 / DUPLICATE_409:
HIKARI_POOL / MAX_INSTANCES / DB_MAX_CONNECTIONS:
LATENCY / ERROR_RATE / QUERY_INSIGHTS:
BACKUP / RESTORE_TEST / ROLLBACK_PLAN:
BILLING_RESOURCES / CLEANUP_RESULT / OPEN_ISSUES:
~~~

Mark **PASS** only when directly observed. Never paste passwords, IAM tokens, credentialed connection URLs, or customer data into reports.

## 15. Lab Cleanup and References

### 15.1. Ownership-Based Cleanup

**Never run delete commands on shared databases/instances or resources other users depend on.** Inventory first:

~~~bash
# READ-ONLY.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud sql instances describe "$INSTANCE" --project="$PROJECT_ID"
gcloud sql databases list --instance="$INSTANCE" --project="$PROJECT_ID"
gcloud secrets versions list catalog-db-password --project="$PROJECT_ID"
~~~

If the **Cloud Run service was created strictly by you for this lab** and has zero remaining callers:

~~~bash
# DELETES REAL RESOURCE — strictly in lab with owner approval.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

If the **`catalog` database** and schema are strictly for the lab, after verifying backups/retention and zero active clients, a DBA can drop the database using approved admin commands. **Do not run commands to delete the entire Cloud SQL instance in this lesson**: the instance may host other databases, backups, replicas, or retained data. If an instance was spun up exclusively for this lab, follow a change checklist to delete that exact instance after deciding backup retention/removal. **Secret Manager secrets, IAM bindings, Artifact Registry images, and Cloud Build logs** are not removed when deleting a Cloud Run service; clean them up per owner and retention rules.

### 15.2. Official Technical References

- [Cloud SQL for PostgreSQL — Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL — Java Language Connector](https://docs.cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL Java Connector — JDBC setup](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md)
- [Cloud SQL — Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL — Create and manage databases](https://docs.cloud.google.com/sql/docs/postgres/create-manage-databases)
- [Cloud SQL — Create/manage users](https://docs.cloud.google.com/sql/docs/postgres/create-manage-users)
- [Cloud SQL Auth Proxy overview](https://docs.cloud.google.com/sql/docs/postgres/sql-proxy)
- [Spring Data JPA reference](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Boot — SQL database initialization and Flyway](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Boot — Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Cloud Run — Deploy from source](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run — Configure secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [AlloyDB documentation](https://docs.cloud.google.com/alloydb/docs/overview)

**Closing checklist:** right project/instance → properly scoped DB user and schema → Flyway V1 → Entity/Repository/Service/Controller → local proxy + CRUD tests → runtime Cloud SQL Client + Secret Manager → private Cloud Run + Java Connector → measure pools/latency/SQL → backups, rollbacks, and cost → clean up only resources you own.

**Connection to the CLOUD_PROVIDERS_GCP track:** this lab bridges **Spring Data JPA and managed PostgreSQL** with core platform pillars: **Cloud Run, IAM, VPC, Secret Manager, Artifact Registry/Cloud Build, Logging/Monitoring, and Cloud Billing**. Success is more than an endpoint returning 200: it requires **consistent data, least-privilege access, versioned schemas, high reliability, and controlled costs**.
