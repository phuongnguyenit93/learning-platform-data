# Thực hành ứng dụng Spring Data JPA với Cloud SQL

> **Chương:** Cloud SQL và AlloyDB  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Trong bài này, ta xây dựng REST API **danh mục sản phẩm** bằng **Java 21, Spring Boot, Spring Data JPA, Hibernate và PostgreSQL trên Cloud SQL**. API hỗ trợ tạo, xem và phân trang sản phẩm; schema được quản lý bằng Flyway. Chạy local dùng **Cloud SQL Auth Proxy**, còn triển khai lên **Cloud Run** dùng **Cloud SQL Java Connector** và mật khẩu lưu trong Secret Manager.

Đây là bài thực hành **Cloud SQL for PostgreSQL**, không phải hướng dẫn tạo AlloyDB cluster. Hai sản phẩm đều có giao thức PostgreSQL ở những trường hợp thích hợp nhưng khác mô hình quản lý, hiệu năng, tính năng và chi phí; không mặc nhiên thay endpoint Cloud SQL bằng AlloyDB mà giữ nguyên toàn bộ cách kết nối.

**Nguyên tắc:** ưu tiên instance lab hoặc dev có sẵn. Cloud SQL là database được provision và **có thể tính phí ngay cả khi không có request**. Không tạo/xóa instance, cấp quyền public hay thao tác trên dữ liệu sản xuất khi chưa được chủ sở hữu phê duyệt.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **Cloud SQL instance, PostgreSQL database/user/schema**, JPA Entity, Repository và transaction.
2. Tạo REST API Spring Data JPA với validation, ràng buộc unique và xử lý lỗi phù hợp.
3. Dùng **Flyway versioned migrations** và Hibernate **ddl-auto=validate** để kiểm soát schema.
4. Kết nối local qua **Cloud SQL Auth Proxy** và Cloud Run qua **Java Connector**, hiểu public/private IP và IAM.
5. Triển khai private Cloud Run service, tách runtime identity, DB credentials và quyền PostgreSQL.
6. Tính connection budget của HikariCP với Cloud Run autoscaling, tránh cạn database connections.
7. Kiểm tra kết quả thực tế, nhận biết lỗi schema/IAM/password/network, theo dõi logs/Query Insights và chi phí.
8. Giải thích ranh giới transaction/JPA, backup, HA, rollback và khi nào cân nhắc AlloyDB.

## 1. Kiến trúc end-to-end

~~~mermaid
flowchart LR
    CLIENT["HTTP client đã xác thực"] --> RUN["Cloud Run\nSpring Boot REST API"]
    RUN --> JPA["Spring Data JPA\nHibernate"]
    JPA --> POOL["HikariCP\nmax pool 5"]
    POOL --> CONNECTOR["Cloud SQL Java Connector\nIAM + TLS"]
    CONNECTOR --> PG[("Cloud SQL PostgreSQL\ncatalog database")]
    MIGRATION["Flyway\nV1__create_products.sql"] --> PG
    SECRET["Secret Manager\nDB password"] -. "Secret reference" .-> RUN
    IAM["Runtime service account\nCloud SQL Client"] -. "IAM" .-> CONNECTOR
~~~

**Hai lớp xác thực phải cùng đúng:**

- **Cloud SQL Connector/IAM**: Cloud Run runtime service account có quyền **Cloud SQL Client** để kết nối instance và Java Connector lấy thông tin/thiết lập kênh mã hóa.
- **PostgreSQL authentication/authorization**: user **catalog_app**, password hợp lệ, được phép **CONNECT** vào database và thao tác trên schema/bảng tương ứng. Cloud SQL Client **không tự cấp SELECT/INSERT** cho PostgreSQL user.

Các yêu cầu về quyền database độc lập với quyền **Cloud Run Invoker** của HTTP client. Chúng không được thay thế bằng nhau.

### 1.1. Luồng request và transaction

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

**@Transactional** quản lý đơn vị công việc của database; không bao gồm tự động các API calls bên ngoài transaction như gửi email, Pub/Sub hoặc HTTP webhook. Với side effects liên dịch vụ, cân nhắc **transactional outbox**.

## 2. Chuẩn bị trước khi tạo tài nguyên

Môi trường minh họa: **Cloud Shell/Linux/macOS Bash**, JDK 21, Maven, gcloud CLI, psql và Cloud SQL Auth Proxy (v2) nếu chạy local. Các lệnh có **gcloud sql/run/secrets ... create/deploy** tạo thay đổi thật và chỉ dùng trong project lab có billing/quota được duyệt.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
INSTANCE="catalog-pg-lab"
DB_NAME="catalog"
DB_USER="catalog_app"
SERVICE="catalog-api-lab"
RUNTIME_SA="catalog-runtime@$PROJECT_ID.iam.gserviceaccount.com"

# CHỈ ĐỌC — xác định đúng project và resources đã tồn tại.
gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud services list --enabled --project="$PROJECT_ID"
~~~

Cloud SQL, Cloud Run, Cloud Build, Artifact Registry và Secret Manager APIs phải được enable theo phạm vi thực hành. Người bật API cần quyền **serviceusage.services.enable**. Không tự enable API ở production để thử một lệnh.

~~~bash
# THAY ĐỔI PROJECT — chỉ với phê duyệt.
gcloud services enable \
  sqladmin.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

### 2.1. Chọn đúng phương án Cloud SQL

| Phương án | Nên chọn khi | Lưu ý |
|---|---|---|
| **Instance dev có sẵn** | Tổ chức đã có môi trường học tập | Chỉ tạo database/schema riêng; không đổi IAM/network chung nếu chưa duyệt |
| **Instance zonal riêng cho lab** | Cần cô lập và đã dự toán tiền | Không HA, chỉ cho dữ liệu giả lập; xóa đúng owner sau bài |
| **Instance HA/regional** | Dữ liệu production có yêu cầu availability | Chi phí cao hơn; cần backup, PITR, runbook failover |
| **Public IP + Java Connector** | Lab đơn giản, policy cho phép | Connector có IAM+TLS; không cần mở authorized networks để Java Connector dùng public IP |
| **Private IP + Java Connector** | Hệ thống đã có VPC/private networking | Cần đường VPC egress thực sự và **ipTypes=PRIVATE**; connector không tạo network path |
| **AlloyDB** | Workload PostgreSQL cần đặc tính hiệu năng/kiến trúc của AlloyDB | Phải đánh giá pricing, connector/network riêng, không thay Cloud SQL connection name trực tiếp |

**Kết nối:** Cloud SQL Java Connector cung cấp IAM authorization và encryption, **không** tự tạo đường mạng tới private IP. Cloud Run dùng **Direct VPC egress** hoặc cơ chế VPC được hỗ trợ nếu chọn private IP. <https://docs.cloud.google.com/sql/docs/postgres/connect-connectors>

### 2.2. Tạo instance tùy chọn (chỉ lab riêng)

Nếu chưa có instance, sau khi xác nhận bảng giá/quota và chủ sở hữu, một ví dụ cấu hình **Cloud SQL Enterprise**, **PostgreSQL 16**, **zonal**:

~~~bash
# THAY ĐỔI CÓ CHI PHÍ — chỉ dùng project/instance lab đã duyệt.
gcloud sql instances create "$INSTANCE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-custom-1-3840 \
  --availability-type=ZONAL \
  --storage-size=10

# CHỈ ĐỌC thông tin instance và IP settings.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,databaseVersion,connectionName,ipAddresses,settings)"
~~~

**Không dùng kích cỡ trên làm sizing cho production**. Tùy phiên bản, edition, region, khả năng lưu trữ và chính sách tổ chức, cần điều chỉnh cấu hình. Với PostgreSQL 16+, **phải chỉ định edition** nếu muốn tránh mặc định phiên bản/edition không như dự kiến. Instance mới phát sinh chi phí cho VM/storage/backup dù API không có request.

### 2.3. Tạo database và database user

~~~bash
# CHỈ ĐỌC xem database/user hiện có.
gcloud sql databases list \
  --instance="$INSTANCE" --project="$PROJECT_ID"

gcloud sql users list \
  --instance="$INSTANCE" --project="$PROJECT_ID"

# THAY ĐỔI — chỉ nếu database 'catalog' chưa có và owner cho phép.
gcloud sql databases create "$DB_NAME" \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

Tạo **built-in PostgreSQL user catalog_app** trong **Google Cloud Console → Cloud SQL → instance → Users**, đặt một password mạnh rồi cất vào Secret Manager. Không đặt password trong CLI history, file application.properties, Git hoặc ví dụ tài liệu. Nếu quản trị qua CLI, **gcloud sql users create** có tùy chọn **--password**; không truyền literal password trong câu lệnh được lưu lịch sử ở môi trường dùng chung.

**Cấp quyền PostgreSQL:** kết nối bằng **tài khoản quản trị database đã được phép**, vào database **catalog**, chạy:

~~~sql
-- CHẠY TRÊN DATABASE catalog bằng DBA có quyền CREATE SCHEMA.
-- Tài khoản catalog_app phải tồn tại trước.
CREATE SCHEMA IF NOT EXISTS catalog_app AUTHORIZATION catalog_app;
GRANT CONNECT ON DATABASE catalog TO catalog_app;
~~~

Schema **catalog_app** do DB role **catalog_app** sở hữu để Flyway của **lab** tạo bảng. Trong production nên tách **migration role** có quyền DDL và **runtime role** chỉ có DML (SELECT/INSERT/UPDATE/DELETE); tránh cho ứng dụng runtime quyền tùy ý thay schema.

**Lưu ý Cloud SQL PostgreSQL:** user Cloud SQL được quản lý ở mức instance, còn quyền trên từng **database/schema/table** được cấp qua PostgreSQL SQL. Nếu schema đã tồn tại thuộc owner khác, không cố đổi owner hoặc GRANT rộng khi chưa có phê duyệt.

## 3. Cấu trúc project Java

Tạo **thư mục thực hành riêng của người học** (không tạo thêm file trong module Markdown knowledge này):

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

### 3.1. pom.xml — Spring Boot 3, JPA, PostgreSQL, Flyway

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

**Về phiên bản:** file trên cố định Spring Boot **3.5.7** và Java Connector **1.31.0** để minh họa phụ thuộc. Khi triển khai thật, rà soát artifact versions/BOM, tính tương thích và CVE. Với Spring Boot 3.5, dùng **flyway-core** cùng **flyway-database-postgresql** cho PostgreSQL; Spring Boot tự cấu hình Flyway khi phát hiện dependencies phù hợp trên classpath. Xác minh bằng Maven dependency tree trước khi deploy.

### 3.2. Spring Boot entrypoint

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

## 4. Flyway migration và mapping JPA

### 4.1. V1__create_products.sql

~~~sql
-- DB: catalog; schema catalog_app thuộc database role catalog_app.
CREATE TABLE catalog_app.products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_products_name ON catalog_app.products (name);
~~~

Flyway thực thi migration **một lần** và ghi version/checksum vào bảng history theo cấu hình. Tránh chỉnh sửa migration V1 đã được áp dụng; hãy thêm **V2__...sql** cho thay đổi tiếp theo. Trên hệ thống nhiều Cloud Run instances, không để mỗi instance tùy ý chạy DDL production: dùng migration job/pipeline chuyên biệt có khóa/lịch và phân quyền; ví dụ lab chỉ có một schema nhỏ.

### 4.2. Product.java

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

    protected Product() {} // JPA yêu cầu no-arg constructor.

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

**Tại sao dùng BigDecimal?** Giá tiền không nên lưu bằng floating-point nhị phân **double** khi cần chính xác phép tính; **NUMERIC(12,2)** biểu diễn giá trị thập phân có kiểm soát. Với hệ thống đa đơn vị tiền tệ, cần thêm **currency**, quy tắc làm tròn và contract rõ ràng.

Entity không đại diện cho toàn bộ API public: controller sẽ trả DTO thay vì serialize JPA entity để tránh vô tình lộ các quan hệ lazy, trường nội bộ và tạo lỗi **N+1** ngoài ý muốn.

## 5. Spring Data Repository, Service và REST Controller

Spring Data JPA giúp tạo các truy vấn CRUD thông dụng từ **Repository interface**; Hibernate chuyển các thao tác Entity thành SQL và dùng JDBC DataSource. Điều này **không loại bỏ** nhu cầu hiểu SQL, transaction, indexes và query plans.

### 5.1. ProductRepository.java

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
~~~

**findBySku** là một derived query; Spring Data tạo truy vấn từ tên method. Với nghiệp vụ kiểm tra trùng SKU, database **UNIQUE constraint** vẫn là lớp bảo vệ cuối cùng khi nhiều requests chạy đồng thời. Không dùng riêng **existsBySku** rồi tưởng đã loại bỏ race condition.

### 5.2. ProductService.java

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

- **@Transactional** bắt đầu/hoàn tất một transaction trong Spring proxy invocation; unchecked exceptions mặc định kích hoạt rollback.
- **saveAndFlush** ép Hibernate gửi SQL sớm để các ràng buộc database có thể báo lỗi ngay trong service call; **không** làm thay đổi tính nguyên tử của transaction.
- **@Transactional(readOnly=true)** thể hiện ý định chỉ đọc và cho phép tối ưu tùy driver/JPA; không phải ranh giới bảo mật. Database role vẫn phải được cấp quyền đúng.
- **Page** tiện cho API nhỏ nhưng có thể chạy **COUNT**; với bảng rất lớn, cần xem pagination/keyset index và SQL execution plan.

### 5.3. ProductController.java

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

**DTO validation** chặn đầu vào sai ở lớp HTTP, còn các ràng buộc **UNIQUE, NOT NULL, CHECK, NUMERIC(12,2)** vẫn được database enforce. Hãy giữ cả hai: validation trước request cải thiện phản hồi, constraint trong PostgreSQL bảo đảm nhất quán khi có nhiều clients hoặc jobs.

### 5.4. ApiErrors.java — không lộ SQL exception ra client

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
        // Không trả SQL/constraint details, vì có thể lộ cấu trúc nội bộ.
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

Trong lab, vi phạm unique SKU thường trả **409**, lỗi validation trả **400**, ID không tồn tại trả **404**. Ở production nên phân biệt loại constraint theo mã SQLSTATE/constraint name đã allowlist, không gom toàn bộ lỗi database thành 409, và bổ sung correlation ID/structured logs. **Không trả stack trace, username, JDBC URL hoặc raw query** cho client.

## 6. Hai cấu hình DataSource: local và Cloud SQL

### 6.1. application.properties — local qua Cloud SQL Auth Proxy TCP

~~~properties
spring.application.name=catalog-api
server.port=${PORT:8080}
spring.datasource.url=jdbc:postgresql://${DB_HOST:127.0.0.1}:${DB_PORT:5432}/${DB_NAME:catalog}
spring.datasource.username=${DB_USER:catalog_app}
spring.datasource.password=${DB_PASS}

# Mỗi instance JVM có tối đa 5 connections trong pool này.
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

**Cloud SQL Auth Proxy** tạo listener local TCP, JDBC dùng **localhost:5432**. Proxy dùng ADC/IAM để tạo kênh mã hóa với Cloud SQL nhưng vẫn cần **PostgreSQL username/password** trong ví dụ này.

**Không dùng ddl-auto=update/create/create-drop cho production:** Hibernate không được tự biến đổi schema mỗi lần scale-out. **Flyway** quản lý thay đổi có phiên bản và **validate** giúp ứng dụng fail sớm nếu Entity không khớp schema. Đối với zero-downtime rollout, cần migration mở rộng trước rồi thu hẹp sau (**expand/contract**) và giữ tương thích giữa app revisions.

### 6.2. application-cloudsql.properties — Cloud SQL Java Connector

~~~properties
# JDBC Socket Factory dùng ADC của Cloud Run runtime service account.
spring.datasource.url=jdbc:postgresql:///${DB_NAME:catalog}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&cloudSqlRefreshStrategy=lazy&ipTypes=${DB_IP_TYPES:PUBLIC}
~~~

Profile **cloudsql** chỉ override JDBC URL; username/password, pool và Hibernate/Flyway ở application.properties vẫn áp dụng. Những thông số chính:

| Cấu hình | Ý nghĩa |
|---|---|
| **INSTANCE_CONNECTION_NAME** | **project:region:instance** của Cloud SQL, không phải Cloud Run service URL |
| **socketFactory** | **com.google.cloud.sql.postgres.SocketFactory** của Java Connector |
| **cloudSqlRefreshStrategy=lazy** | Refresh credentials khi cần; thích hợp môi trường serverless có CPU bị throttle |
| **DB_IP_TYPES=PUBLIC** | Kết nối qua IP public của instance với Connector |
| **DB_IP_TYPES=PRIVATE** | Chọn IP private khi đã có đường VPC egress |
| **DB_USER/DB_PASS** | PostgreSQL database credentials, khác Cloud IAM identity |
| **DB_POOL_SIZE** | Giới hạn connections trên **mỗi Cloud Run container instance** |

Java Connector dùng IAM/TLS nhưng **không tự cấp PostgreSQL privileges** và **không tạo đường VPC** tới private IP. Khi dùng built-in Cloud Run connection qua Unix socket, cấu hình sẽ khác; với **Java Connector** trong bài, không cần đặt thêm **--add-cloudsql-instances** để tạo socket mount. Đừng trộn JDBC Socket Factory với đường Unix socket khi chưa biết hai chế độ.

**Về thông tin mật:** DB_PASS không đặt mặc định trong source. Local người học nhập tương tác; Cloud Run lấy từ Secret Manager. Environment variable chứa secret vẫn có thể bị process đọc hoặc vô tình log; production nên kiểm soát IAM/rotation và cân nhắc mount secret volume/cách truy xuất phù hợp.

## 7. Chạy local qua Cloud SQL Auth Proxy

### 7.1. Xác minh instance connection name

~~~bash
# CHỈ ĐỌC.
INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)')"

printf 'Instance connection name: %s\n' "$INSTANCE_CONNECTION_NAME"
~~~

Cài **Cloud SQL Auth Proxy v2** từ hướng dẫn chính thức cho hệ điều hành. Cloud SQL Admin API phải bật và principal đăng nhập cần **roles/cloudsql.client** trên project/instance thích hợp. Trong môi trường local được phép:

~~~bash
# Tương tác: tạo ADC cho tài khoản lab, không dùng key file lâu hạn.
gcloud auth application-default login

# Terminal 1 — giữ proxy chạy trong quá trình kiểm thử.
# Chỉ dùng khi port 5432 chưa được service khác sử dụng.
cloud-sql-proxy --port 5432 "$INSTANCE_CONNECTION_NAME"
~~~

Nếu instance chỉ có private IP, máy đang chạy proxy phải có đường mạng tới VPC hoặc kết nối phù hợp; thêm **--private-ip** theo tài liệu khi cần. **Proxy không tạo VPN/VPC network path** và không thay firewall/organization policy.

### 7.2. Chạy ứng dụng

Trên terminal khác, trong thư mục **catalog-api-lab/**, nhập mật khẩu của **catalog_app** mà không lưu vào command history:

~~~bash
# Cloud Shell/bash. Không gõ password trực tiếp trong câu lệnh.
read -r -s -p "PostgreSQL catalog_app password: " DB_PASS
printf '\n'
export DB_PASS

# CHỈ BUILD + CHẠY LOCAL (không tạo tài nguyên Google Cloud).
mvn -B -DskipTests package
java -jar target/catalog-api-lab-1.0.0.jar

# Khi hoàn thành, đóng app rồi chạy: unset DB_PASS
~~~

Lúc khởi động, Flyway phải áp dụng **V1__create_products.sql**, Hibernate **validate** mapping và HikariCP mở connections khi cần. Nếu lần khởi động đã báo thiếu schema/DB role, giải quyết quyền sở hữu schema và migrations trước khi thử API; không tăng IAM lên Owner.

**Kiểm tra read-only bằng psql**, nếu đã cài Postgres client và đang dùng proxy:

~~~bash
# Mở terminal khác; psql hỏi database password tương tác.
psql -h 127.0.0.1 -p 5432 -U catalog_app -d catalog \
  -c 'SELECT version, description, success FROM catalog_app.flyway_schema_history ORDER BY installed_rank;'

psql -h 127.0.0.1 -p 5432 -U catalog_app -d catalog \
  -c 'SELECT id, sku, unit_price FROM catalog_app.products ORDER BY id LIMIT 10;'
~~~

Nếu Flyway history thuộc schema khác do cấu hình trước đó, hãy kiểm tra **spring.flyway.default-schema**, không tự xóa bảng history để “chạy lại từ đầu”.

## 8. Kiểm thử REST API và ràng buộc PostgreSQL

### 8.1. Tạo sản phẩm

~~~bash
# LOCAL: chỉ gửi dữ liệu giả lập vào database lab.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-001","name":"Java Cloud Guide","unitPrice":159000.00}'
~~~

Kỳ vọng: **HTTP 201 Created**, Location chứa **/api/products/{id}**, response JSON có ID được PostgreSQL sinh, SKU, tên, unitPrice.

### 8.2. Đọc theo ID và phân trang

~~~bash
# Thay ID thực từ response trước.
curl -i http://127.0.0.1:8080/api/products/1

curl -i 'http://127.0.0.1:8080/api/products?page=0&size=10&sort=id,asc'

# ID chưa tồn tại.
curl -i http://127.0.0.1:8080/api/products/999999
~~~

Kỳ vọng GET một ID hợp lệ trả **200**; ID không tồn tại trả **404**; danh sách trả **Page** với content/pagination metadata. Truy vấn nên được giới hạn page size tối đa để tránh làm nặng database.

### 8.3. Thử unique constraint và validation

~~~bash
# SKU BOOK-001 đã tồn tại -> kỳ vọng HTTP 409.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-001","name":"Duplicated","unitPrice":100.00}'

# unitPrice âm -> HTTP 400 do @DecimalMin.
curl -i -X POST http://127.0.0.1:8080/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-002","name":"Invalid price","unitPrice":-1}'
~~~

**Không dùng một lượt test tuần tự để chứng minh đã xử lý concurrency:** thử hai requests đồng thời cùng SKU và xác minh PostgreSQL chỉ lưu **một** bản ghi. Ứng dụng có thể báo **409** trên một request, nhưng database UNIQUE constraint mới bảo vệ dữ liệu trong race.

### 8.4. Cần test gì trước production?

| Loại test | Kiểm chứng |
|---|---|
| Unit test Service | Mapping DTO, xử lý 404, transaction boundaries |
| Repository integration | Unique SKU, NUMERIC(12,2), Flyway schema |
| Web slice | @Valid, 400/404/409/201 và pagination |
| Concurrent write | Hai requests cùng SKU không tạo hai rows |
| Migration smoke | V1 và các Vn tiếp theo áp được trên DB clone |
| Cloud SQL connectivity | IAM + DB password + network + TLS |
| Fault injection | DB timeout/failover/retry, không duplicate side effect |
| Load test | DB connections, Hikari pending threads, p95 latency |

**Không dùng database production cho destructive integration tests.** Với CI, ưu tiên Testcontainers PostgreSQL hoặc DB staging tách biệt; không test migration bằng cách drop schema của app production.

## 9. Triển khai private Cloud Run với Cloud SQL và Secret Manager

### 9.1. Runtime identity và quyền kết nối

~~~bash
# THAY ĐỔI IAM — chỉ trong project lab, khi SA chưa tồn tại.
gcloud iam service-accounts create catalog-runtime \
  --project="$PROJECT_ID" \
  --display-name="Catalog API runtime identity"

RUNTIME_SA="catalog-runtime@$PROJECT_ID.iam.gserviceaccount.com"

# THAY ĐỔI IAM — Java Connector cần Cloud SQL Client.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/cloudsql.client"
~~~

Nếu Cloud SQL nằm **ở project khác** thì Cloud SQL Admin API phải bật ở cả project ứng dụng và project database; runtime principal cần quyền Cloud SQL Client trên **project chứa instance**. Deployer cần quyền source build/deploy và **iam.serviceAccounts.actAs** trên RUNTIME_SA. Không dùng Owner để chữa lỗi 403. Quyền Cloud SQL Client **không** cấp quyền SELECT/INSERT trong PostgreSQL; các quyền DB vẫn thuộc catalog_app.

### 9.2. Lưu mật khẩu trong Secret Manager

~~~bash
# THAY ĐỔI — chỉ khi secret chưa tồn tại.
gcloud secrets create catalog-db-password \
  --project="$PROJECT_ID" \
  --replication-policy="automatic"

# Cloud Shell/bash: nhập tương tác, không ghi password vào history.
read -r -s -p "Database password: " DB_PASS
printf '\n'
printf '%s' "$DB_PASS" | gcloud secrets versions add catalog-db-password \
  --project="$PROJECT_ID" --data-file=-
unset DB_PASS

# CHỈ ĐỌC: xem phiên bản/metadata, không đọc giá trị secret.
gcloud secrets versions list catalog-db-password \
  --project="$PROJECT_ID"
~~~

Nếu secret đã có, không chạy create lại; chỉ bổ sung version sau review. Trong lab, xác minh **version 1** có thật; production nên dùng **version pin** khi triển khai và tạo revision mới khi rotate thay vì dựa vào latest. Không in mật khẩu ra log hay đặt trong CLI literal.

~~~bash
# THAY ĐỔI IAM — cấp trên đúng secret, không trên cả project.
gcloud secrets add-iam-policy-binding catalog-db-password \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

### 9.3. Deploy bằng Java Connector

Trong thư mục **catalog-api-lab/** của người học, sau khi đã thử database/migration local:

~~~bash
# CHỈ ĐỌC.
INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)')"

# THAY ĐỔI: Cloud Build build Java, Cloud Run tạo private revision.
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

# CHỈ ĐỌC: trạng thái và cấu hình revision.
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Điều kiện:** Cloud SQL instance có **public IP** cho bài lab, Cloud SQL Client và DB credentials đúng, Cloud SQL Admin API bật và egress không bị chặn. Java Connector cung cấp IAM authorization + encryption, nhưng DB_USER/password vẫn là phương thức xác thực **PostgreSQL built-in user**. Cloud Run không cần flag **--add-cloudsql-instances** của đường Unix socket khi ứng dụng đang dùng **Java Connector** như ví dụ. Chọn một cơ chế kết nối nhất quán.

**Lưu ý vận hành:** Spring profile cloudsql nạp Flyway khi ứng dụng khởi động. Production nên chạy migration qua pipeline/job riêng trước khi rollout nhiều replicas và **không** cấp runtime account quyền DDL; ví dụ lab chấp nhận một schema nhỏ để người học thấy cơ chế.

### 9.4. Nếu instance chỉ có private IP

Java Connector không tạo VPC route. Cloud Run phải có **Direct VPC egress** hoặc VPC connector phù hợp để kết nối tới Cloud SQL private IP. Ví dụ tạo revision mới sau khi VPC/subnet đã được tổ chức chấp thuận:

~~~bash
# THAY ĐỔI — chỉ dùng network/subnet thật và đã được duyệt.
gcloud run services update "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --network="YOUR_VPC" \
  --subnet="YOUR_SUBNET" \
  --vpc-egress=private-ranges-only \
  --update-env-vars=DB_IP_TYPES=PRIVATE
~~~

Đường private còn phụ thuộc routes/firewall, Private Services Access hoặc PSC theo loại instance, egress đến Google APIs và quyền trên subnet (đặc biệt Shared VPC). Không dùng giá trị **YOUR_VPC**/**YOUR_SUBNET** nguyên văn.

### 9.5. Kiểm thử Cloud Run private

Người gọi có quyền **roles/run.invoker** trên service có thể dùng tunnel auth bằng gcloud:

~~~bash
# Terminal 1 — developer đã được cấp quyền Invoker.
gcloud run services proxy "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --port=8081

# Terminal 2:
curl -i -X POST http://127.0.0.1:8081/api/products \
  -H "Content-Type: application/json" \
  --data '{"sku":"BOOK-CLOUD-001","name":"Cloud SQL JPA Lab","unitPrice":99000.00}'

curl -i 'http://127.0.0.1:8081/api/products?page=0&size=10'
~~~

Nếu thành công, endpoint tạo trả **201** và danh sách trả **200**. Nếu bị 403 trước khi vào Spring, xem Cloud Run IAM/invoke; nếu controller nhận request nhưng DB lỗi, xem Secret Manager, Cloud SQL IAM, PostgreSQL privileges và network trước khi tăng quyền. **Không bật allow-unauthenticated để thử kết nối database**.

## 10. Connection pooling và transaction trong môi trường autoscale

### 10.1. Tính connection budget

Mỗi **Cloud Run instance** giữ một HikariCP pool riêng. Với **max-instances=3** và **maximum-pool-size=5**, tổng mức pool của một revision theo cấu hình là:

\[
3 \times 5 = 15\ \text{connections}
\]

Đây là **ước lượng giới hạn pool của workload**, chưa tính instances của revisions cũ trong rollout, services khác, migration jobs, admin sessions và connections nội bộ. Ngoài giới hạn mỗi Cloud Run instance, **PostgreSQL max_connections** của Cloud SQL instance và RAM còn giới hạn toàn server. Cloud Run có thể vượt max instances ngắn hạn trong một số tình huống; luôn dành headroom.

| Thông số | Giá trị lab | Ý nghĩa |
|---|---|---|
| Hikari maximumPoolSize | 5 | Connections tối đa **trên một JVM** |
| Hikari minimumIdle | 0 | Không cố giữ nhiều idle sessions |
| Cloud Run max instances | 3 | Quy mô dự kiến của service |
| Cloud Run concurrency | 20 | Requests tối đa đồng thời mỗi container, **không phải** kết nối DB |
| Hikari connection timeout | 10s | Chờ mượn connection trước khi báo lỗi |
| PostgreSQL max_connections | Tùy instance | Capacity tổng của database |

Một instance có thể nhận 20 HTTP requests cùng lúc nhưng chỉ cho 5 transactions đồng thời mượn connection; các request khác phải chờ. Tăng pool size có thể giảm wait nhưng cũng có thể đẩy database vượt capacity. Cần xem **p95 latency, pool pending threads, slow queries và active sessions** trước khi điều chỉnh.

### 10.2. Những anti-pattern

- Tạo JDBC connection hoặc DataSource mới cho từng HTTP request.
- Đặt mỗi pool 100 connections rồi cho service scale tới 50 instances.
- Giữ **@Transactional** mở trong khi gọi HTTP API chậm hay chờ người dùng.
- Bật **ddl-auto=update/create** trên nhiều instances production.
- Trả tất cả rows không phân trang; không thiết kế indexes theo truy vấn thực.
- Serialize JPA Entity có lazy relations trực tiếp gây **N+1 queries**.
- In SQL bindings/credentials/PII ra Cloud Logging.
- Chỉ tăng Cloud Run CPU mà không kiểm tra PostgreSQL I/O/locks/queries.

### 10.3. Đồng thời và phiên bản bản ghi

**UNIQUE(sku)** ngăn tạo trùng SKU; nó không giải quyết **lost update** khi hai clients cùng sửa một bản ghi. Nếu sau bài này thêm chức năng sửa sản phẩm, dùng **optimistic locking** khi cần:

~~~java
// Trích đoạn bổ sung Entity; không tự áp nếu chưa migrate DB.
@Version
@Column(nullable = false)
private Long version;
~~~

Flyway phải bổ sung migration tạo **version BIGINT NOT NULL** (kèm backfill hợp lệ) trước khi rollout Entity mới. Có thể bổ sung HTTP **ETag/If-Match** nếu API cho phép cập nhật có điều kiện. Không thêm @Version rồi để Hibernate tự thay database schema.

Spring **@Transactional** hoạt động thông qua proxy; self-invocation trong cùng bean có thể không đi qua transactional interceptor. Transactions không bao bọc Pub/Sub, email hay Cloud Storage một cách nguyên tử; với side effects dùng **outbox** hoặc quy trình idempotent.

## 11. Quan sát và xử lý lỗi kết nối

### 11.1. Lệnh chỉ đọc

~~~bash
# Cloud Run: Ready revision và application logs.
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.latestReadyRevisionName,status.conditions)"

gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=100

# Cloud SQL: instance và hoạt động quản trị.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,connectionName,settings)"

gcloud sql operations list \
  --project="$PROJECT_ID" --instance="$INSTANCE"
~~~

Nếu được bật trên instance/edition phù hợp, **Cloud SQL Query Insights** giúp phân tích SQL latency, database load và truy vấn chậm. Tạo dashboard cho **active connections**, CPU/memory/disk usage, lock waits, Hikari active/idle/pending, Cloud Run 4xx/5xx, p95 latency và số lần khởi động thất bại.

### 11.2. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Cloud Run revision không Ready | Flyway lỗi, DB unavailable, thiếu secret, app startup | Build/runtime logs và revision conditions |
| HTTP 403 trước Controller | Caller thiếu Invoker/ID token | Cloud Run IAM |
| Java Connector permission denied | Thiếu Cloud SQL Client hoặc SQL Admin API | Runtime SA, project IAM |
| Password authentication failed | DB_USER/password/secret version sai | PostgreSQL user và Secret Manager |
| Permission denied for schema | Thiếu ownership/GRANT trong PostgreSQL | catalog_app schema owner/permissions |
| Flyway validate failed | Sửa migration đã apply, schema drift | flyway_schema_history, checksum |
| Hibernate missing table | Flyway chưa chạy hoặc sai database/schema | profile/JDBC URL và PostgreSQL metadata |
| Connection refused/timeout | Sai IP type, public IP không có, private VPC thiếu route | DB_IP_TYPES, network/firewall/egress |
| Duplicate key | Vi phạm UNIQUE SKU | API 409 và DB constraint |
| Hikari connection timeout | Pool cạn, transactions quá lâu, DB load | Hikari metrics, pg_stat_activity, Query Insights |
| Too many clients already | Tổng pools lớn hơn DB max_connections | Max instances, pool sizes, connections |
| HTTP 500 sau failover | Stale connections/transient failures | Retry policy, pool validation, DB failover logs |
| API latency tăng | N+1, index thiếu, lock contention | SQL EXPLAIN, Query Insights |
| Phí tăng dù API idle | Cloud SQL instance/storage/backup còn chạy | Billing theo SKU và uptime |

**Đừng chữa tất cả lỗi bằng cách tăng IAM lên Owner hoặc mở database public**. Hãy phân biệt **Cloud Run invoke → Java Connector IAM → network path → PostgreSQL login → schema privileges → SQL performance**.

### 11.3. Không retry POST vô điều kiện

Nếu client timeout sau khi database đã **COMMIT**, retry POST có thể tạo hai objects. Trong bài, **UNIQUE SKU** giúp từ chối một kiểu trùng, nhưng API order/payment thật cần **idempotency key**, durable outcome record, transaction và response replay phù hợp. Khi kết nối gặp lỗi tạm thời, retry **đúng loại lỗi** với backoff và budget; không retry lỗi constraint hoặc authorization sai.

## 12. Bảo mật, backup, HA và chi phí

| Chủ đề | Quy tắc vận hành |
|---|---|
| **Cloud SQL IAM** | Cloud SQL Client cho đúng runtime principal, không phải Owner |
| **PostgreSQL privileges** | Role runtime tối thiểu, schema owner/migration role riêng |
| **DB credentials** | Secret Manager, rotation, không lưu trong Git/image/log |
| **Network** | Connector mã hóa, private IP cần VPC egress; public IP không đồng nghĩa DB mở cho mọi client |
| **Schema** | Flyway có version/review, Hibernate validate |
| **Backup/PITR** | Bật và thử khôi phục theo RPO/RTO, kiểm tra retention |
| **HA** | Regional availability/failover theo tier/edition, đo failover và app retry |
| **Read replicas** | Đọc scale-out nếu phù hợp; replication lag và consistency phải được xử lý |
| **Observability** | Query Insights, metrics, log redaction, audit |
| **Chi phí** | Instance compute, SSD/IO, HA/replicas, backup/PITR, network, Cloud Run/Build/Secrets/Logs |

### 12.1. Vì sao không xóa instance sau bài nếu chưa xác minh?

Cloud SQL chứa **dữ liệu bền vững**: xóa instance khác với xóa Cloud Run revision. Nếu instance thuộc team khác hoặc có backup/replica/retention, xóa có thể mất dữ liệu hoặc phá dịch vụ. Chỉ chủ sở hữu môi trường lab mới được phê duyệt cleanup hạ tầng database.

### 12.2. Khi nào cân nhắc AlloyDB thay Cloud SQL?

**Cloud SQL for PostgreSQL** phù hợp nhiều ứng dụng giao dịch quan hệ truyền thống và cung cấp trải nghiệm PostgreSQL được quản lý. **AlloyDB** cung cấp kiến trúc khác, các tính năng tối ưu cho những workload PostgreSQL đòi hỏi hiệu năng/quy mô phù hợp, nhưng cần đánh giá riêng **cluster/instance roles, networking, connector, backup, HA và chi phí**.

Không tự thay **INSTANCE_CONNECTION_NAME** của Cloud SQL trong JDBC Socket Factory thành AlloyDB cluster ID. **AlloyDB dùng phương thức kết nối/client phù hợp riêng**, cần đọc hướng dẫn AlloyDB và kiểm thử SQL/extension compatibility, operations và benchmark trước khi quyết định chuyển.

## 13. Case study: danh mục sản phẩm của hệ thống thương mại điện tử

### 13.1. Bối cảnh và thiết kế

Một nhóm Java có **Catalog API** chạy trên Cloud Run, lưu dữ liệu sản phẩm tại Cloud SQL for PostgreSQL. Mỗi sản phẩm có SKU duy nhất và đơn giá thập phân. Khi lưu lượng tăng vào giờ cao điểm, Cloud Run tăng instances trong khi database có giới hạn CPU, memory và connections.

**Phương án được duyệt:**

- Spring Data JPA xử lý truy vấn CRUD nhưng không dùng Entity làm API response.
- Flyway kiểm soát schema; JPA chỉ validate.
- Java Connector dùng Cloud Run runtime identity có Cloud SQL Client; DB role/catalog schema có privilege tối thiểu.
- Password nằm trong Secret Manager; HTTP Cloud Run private.
- HikariCP maximum pool size **5**, Cloud Run max instances **3** cho lab; production sizing theo load test/DB capacity.
- Cloud Monitoring/Query Insights đo p95 latency, errors, slow SQL, connections và phí theo SKU.

### 13.2. Hai lỗi thực tế

**Lỗi A — Hai requests tạo cùng SKU:** mỗi request thấy SKU chưa có rồi cùng INSERT. Nếu chỉ kiểm tra bằng Java **existsBySku** trước khi save, cả hai có thể vượt qua. Database **UNIQUE(sku)** cho phép tối đa một INSERT; request còn lại nhận lỗi constraint và API chuyển thành 409 có kiểm soát. Nếu business muốn idempotent create, bổ sung idempotency key/response replay.

**Lỗi B — Pool timeout khi scale-out:** cấu hình production giả định Hikari pool 30 và 20 Cloud Run instances → tới **600 connections tiềm năng**, vượt capacity của PostgreSQL instance nhỏ. Việc tăng Cloud Run instances chỉ chuyển bottleneck xuống database. Nhóm phải rightsize pool, giới hạn instances/concurrency, giảm query duration, thêm indexes và kiểm tra DB sizing/HA trước khi mở rộng.

### 13.3. Điều kiện nghiệm thu

| Hạng mục | PASS khi |
|---|---|
| Schema | Flyway V1 applied, Hibernate validate không báo lệch |
| Create | POST hợp lệ trả 201 + Location |
| Read | GET id tồn tại 200, id không tồn tại 404 |
| Validation | Giá âm/SKU sai 400, duplicate SKU 409 |
| Storage | Dữ liệu vẫn còn sau restart Cloud Run |
| Security | Không có allUsers Invoker; password không ở source |
| Connectivity | IAM, PG login, network và Secret Manager đều đạt |
| Scaling | Pool wait/DB connections trong ngưỡng; p95 đạt SLO |
| Recovery | Có backup/restore test và kế hoạch migration rollback |
| FinOps | Cloud SQL/Run/Build/Secrets/Storage/Logs được kiểm kê |

## 14. Bài tập thực hành và đáp án

### 14.1. Bài A — JPA và Flyway

1. Tạo database/schema riêng trong lab.
2. Tạo Maven project như mục 3, đặt Entity và migration V1.
3. Chạy local qua Cloud SQL Auth Proxy và xác nhận bảng **catalog_app.products**.
4. Tạo **BOOK-001**, đọc lại, thử POST duplicate và giá âm.
5. Ghi HTTP status, row count, Flyway version/checksum vào báo cáo.

**Đáp án định hướng:** Flyway tạo bảng, Hibernate validate thành công; 201/200/409/400 theo tình huống. Nếu database báo permission denied, sửa **PostgreSQL role/schema** chứ không gán thêm Cloud SQL Client cho mọi principal.

### 14.2. Bài B — Migration có kiểm soát

Thêm field **stockOnHand** kiểu integer không âm và mặc định 0. Tạo một migration **mới**, không sửa V1:

~~~sql
-- V2__add_stock.sql
ALTER TABLE catalog_app.products
    ADD COLUMN stock_on_hand INTEGER NOT NULL DEFAULT 0
    CHECK (stock_on_hand >= 0);
~~~

Sau đó cập nhật Entity, DTO hoặc use case phù hợp. Với rollout thực, kiểm tra compatibility: thêm cột có default thường ít rủi ro hơn xóa/đổi tên cột, nhưng còn phụ thuộc khối lượng dữ liệu, locks, PostgreSQL version và application logic.

**Câu hỏi:** nếu đổi tên **unit_price** và xóa cột cũ ngay khi vẫn còn Cloud Run revision cũ đang chạy, chuyện gì xảy ra?

**Đáp án:** revision cũ có thể query/INSERT lỗi. Dùng chiến lược **expand/contract**, deploy code tương thích song song, backfill/dual-read/write theo yêu cầu, rồi mới drop cột cũ.

### 14.3. Bài C — Tính connection budget

Giả sử mỗi JVM đặt pool **8** và Cloud Run có **6 instances** đang chạy. Ngoài ra một batch worker dùng 12 connections, DBA dùng 5 sessions. Tính tổng connections tiềm năng chưa kể connections hệ thống:

\[
6\times 8 + 12 + 5 = 65
\]

**Câu hỏi:** PostgreSQL cấu hình max_connections=60 có đủ không? Giảm Cloud Run **concurrency** từ 20 xuống 5 có tự bảo đảm giảm tổng pool connections không?

**Đáp án:** không đủ nếu các pools đều được sử dụng hết; phải có headroom cho PostgreSQL/other workloads. Giảm concurrency không trực tiếp thay đổi **pool maximum** hoặc số instances; có thể còn làm tăng instances nếu traffic giữ nguyên.

### 14.4. Bài D — Chẩn đoán 403 và lỗi password

Phân loại ba tình huống:

| Triệu chứng | Bước kiểm tra đầu tiên |
|---|---|
| Gọi HTTP Cloud Run trả **403** trước khi app log request | Cloud Run IAM Invoker/token |
| Java Connector trả **Permission denied** | Runtime SA Cloud SQL Client, API, project đúng |
| PostgreSQL trả **password authentication failed** | DB_USER/DB_PASS/secret version, role built-in |

**Giải thích:** một request đi qua nhiều lớp. Không dùng sai quyền để giải quyết lỗi ở lớp khác; secret rotation cũng không tự cập nhật mọi Cloud Run revision nếu pin version cũ.

### 14.5. Bài E — Chọn Cloud SQL hay AlloyDB

Một ứng dụng Java hiện chạy Cloud SQL PostgreSQL, đạt SLO với chi phí hợp lý. Nhóm đề xuất chuyển sang AlloyDB chỉ vì “AlloyDB cũng PostgreSQL”.

**Hãy nêu** các yếu tố cần xác minh: truy vấn/throughput/latency, extension compatibility, chi phí, HA/backup, VPC/private connectivity, Java client/connector phù hợp, migration/cutover plan, RPO/RTO và benchmark. **Đáp án:** không chuyển hệ quản trị chỉ theo tên giao thức; quyết định phải dựa trên workload và bằng chứng.

### 14.6. Biên bản kiểm tra mẫu

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

Ghi **PASS** chỉ khi thực sự quan sát. Không đưa mật khẩu, IAM tokens, connection URLs chứa credentials hoặc dữ liệu khách hàng vào báo cáo.

## 15. Dọn lab và tài liệu tham khảo

### 15.1. Dọn theo quyền sở hữu

**Không chạy lệnh xóa khi dùng database/instance chung hoặc có người dùng khác phụ thuộc.** Kiểm kê trước:

~~~bash
# CHỈ ĐỌC.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud sql instances describe "$INSTANCE" --project="$PROJECT_ID"
gcloud sql databases list --instance="$INSTANCE" --project="$PROJECT_ID"
gcloud secrets versions list catalog-db-password --project="$PROJECT_ID"
~~~

Nếu **Cloud Run service do bạn tạo riêng cho lab**, đã xác nhận không còn consumers:

~~~bash
# XÓA TÀI NGUYÊN THẬT — chỉ trong lab và có owner approval.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Nếu **database catalog** và schema chỉ phục vụ lab, sau khi kiểm tra backups/retention và không còn clients, DBA có thể xóa database bằng lệnh quản trị đã được duyệt. **Không dùng lệnh xóa toàn bộ Cloud SQL instance trong bài**: instance có thể chứa database khác, backups, replicas hoặc dữ liệu cần giữ. Nếu instance được tạo riêng cho lab, hãy dùng change checklist để xóa chính xác instance đó sau khi quyết định cách giữ/xóa backup. Các **Secret Manager secrets, IAM bindings, Artifact Registry images và Cloud Build logs** không tự biến mất khi xóa Cloud Run service; dọn theo owner và retention riêng.

### 15.2. Nguồn kỹ thuật chính thức

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

**Checklist kết thúc:** đúng project/instance → database user và schema có quyền phù hợp → Flyway V1 → Entity/Repository/Service/Controller → local proxy + CRUD tests → runtime Cloud SQL Client + Secret Manager → private Cloud Run + Java Connector → đo pool/latency/SQL → backup, rollback và chi phí → chỉ dọn tài nguyên đúng ownership.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** bài thực hành kết nối **Spring Data JPA và PostgreSQL được quản lý** với các nền tảng đã học: **Cloud Run, IAM, VPC, Secret Manager, Artifact Registry/Cloud Build, Logging/Monitoring và Cloud Billing**. Thành công không chỉ là endpoint trả 200: cần **dữ liệu nhất quán, quyền tối thiểu, schema có phiên bản, độ tin cậy và chi phí được kiểm soát**.









