# Tích hợp Java hoặc Spring Data với kiểm thử tự động trên MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Thực hành tổng hợp  
> **Bài học:** Tích hợp Java hoặc Spring Data với kiểm thử tự động

## 1. Bài toán tổng hợp: API quản lý sản phẩm và giữ hàng

Một dịch vụ Java phục vụ cửa hàng cần:

- Tạo và đọc sản phẩm theo tenant, mã SKU.
- Lưu giá tiền chính xác ở đơn vị nhỏ nhất bằng BSON Int64.
- Chống hai sản phẩm cùng `sku` trong cùng `tenantId`.
- Giữ một lượng hàng khi nhận request đặt hàng.
- Không để số lượng tồn kho âm nếu hai request đồng thời.
- Nhận lại cùng một request khi client timeout mà không giữ hàng hai lần.
- Trả lỗi phân biệt hết hàng, yêu cầu sai, trùng mã và lỗi MongoDB.
- Chạy **kiểm thử tự động với MongoDB thật**, không chỉ mock repository.
- Có thể chạy trong CI/CD, không chạm dữ liệu production.

Một giao diện thử nghiệm:

```http
POST /api/demo/tenants/tenant-a/products
Content-Type: application/json

{
  "sku": "BOOK-101",
  "priceCents": 125000,
  "available": 12
}
```

Một yêu cầu giữ hàng:

```http
POST /api/demo/tenants/tenant-a/products/prod_123/reservations
Idempotency-Key: reserve-tenant-a-order-999
Content-Type: application/json

{
  "quantity": 2
}
```

Nếu request đầu đã thành công nhưng response bị mất, lần gửi lại với cùng `Idempotency-Key` **không được trừ tồn kho thêm lần nữa**. Nếu hàng chỉ còn 1, request giữ 2 phải thất bại mà không làm `available = -1`.

Mục tiêu là kết hợp **MongoDB data modeling, index/validation, Java integration, atomic updates, transactions, error handling và automated tests** thành một bài thực hành có thể kiểm chứng.

### 1.1. Sơ đồ đường đi

```text
      HTTP client / test
              |
              v
      Spring REST controller
      Bean Validation / auth
              |
              v
         StockService
              |
       +------+-------+
       |              |
       v              v
   ProductRepository  ReservationRepository
    / MongoTemplate      / Spring Data
       |              |
       +------+-------+
              |
       MongoTransactionManager
              |
              v
        MongoDB replica set
         /           \
    products       reservations
       |                |
   tenant+sku       requestId
   unique index     unique _id
              ^
              |
       JUnit 5 integration tests
       Testcontainers MongoDB
```

Ứng dụng này là **demo định hướng kiểm thử**. Việc xác thực tenant, thanh toán thực, quản lý đơn hàng, idempotency đa hệ thống và dữ liệu production cần các thành phần bổ sung.

### 1.2. Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt Java Sync Driver thuần, Spring Data MongoDB và Reactive driver.
2. Thiết lập dự án Java 17, Spring Boot, MongoDB Driver, Maven và JUnit 5.
3. Ánh xạ document bằng `@Document`, `@Id`, `@Version`, các kiểu BSON.
4. Viết repository bằng `MongoRepository` và truy vấn có tenant scope.
5. Dùng `MongoTemplate` cho atomic conditional update.
6. Định nghĩa unique index đúng phạm vi và kiểm error trùng khóa.
7. Ghi reservation ledger và trừ hàng trong **một MongoDB transaction**.
8. Dùng idempotency key để retry HTTP request có kiểm soát.
9. Viết integration tests trên MongoDB replica set ephemeral qua Testcontainers.
10. Kiểm BSON type, null/missing, array query, validator, transaction rollback.
11. Tách unit tests, slice tests, integration tests và API tests.
12. Thiết kế test data isolation, cleanup, CI và troubleshooting khi Docker/MongoDB không sẵn.
13. Quan sát lỗi, write concern, index plan, retry semantics và security boundaries.
14. Triển khai theo từng bước mà không biến ví dụ test thành script phá dữ liệu thật.

## 2. Chọn Java Sync Driver hay Spring Data MongoDB

### 2.1. Java Sync Driver thuần

MongoDB Java Sync Driver cung cấp các API như:

```java
MongoClient client = MongoClients.create(uri);
MongoDatabase db = client.getDatabase("app");
MongoCollection<Document> products =
        db.getCollection("products");

products.find(Filters.eq("_id", "SKU-1")).first();
```

Lợi thế:

- Gần MongoDB command semantics.
- Truy cập trực tiếp `Bson`, `Document`, `BsonDocument`.
- Dễ kiểm soát query/filter/update/aggregation cụ thể.
- Dùng được ngoài Spring Framework.
- Phù hợp worker đơn giản, library và utility độc lập.

Điểm cần tự xây thêm:

- Dependency injection và lifecycle.
- Repository abstractions.
- Mapping POJO/codecs.
- Application validation, transaction boundary.
- Exception mapping/HTTP endpoints.
- Test setup và configuration.

### 2.2. Spring Data MongoDB

Spring Data MongoDB bổ sung:

- `@Document` và mapping entity.
- `MongoRepository`/query derivation.
- `MongoTemplate` cho các phép cập nhật/aggregation phức tạp.
- `@Version` cho optimistic locking.
- `MongoTransactionManager` để tích hợp `@Transactional`.
- Spring Boot auto-configuration.
- Spring Test/JUnit integration.
- Spring Data auditing khi được bật.

Lưu ý: Spring Data không làm MongoDB có foreign keys, không làm toàn bộ writes tự thành transaction, không biến retry thành exactly-once và không bảo đảm mọi query repository tạo đúng index.

### 2.3. Reactive MongoDB

Reactive driver/Spring WebFlux dùng Publisher/Flux/Mono và lifecycle bất đồng bộ:

- Cần backpressure và xử lý subscription.
- Transaction dùng reactive context/manager tương ứng.
- Không trộn thread-blocking driver trong event-loop.
- Tests dùng `StepVerifier` và kỹ thuật reactive tương ứng.

Bài này chọn **Spring Data MongoDB bản synchronous** để tập trung vào consistency và JUnit. Cuối bài có hướng thay bằng Java Sync Driver thuần.

### 2.4. Bảng chọn nhanh

| Nhu cầu | Java Sync Driver | Spring Data MongoDB | Reactive |
| --- | --- | --- | --- |
| CRUD bằng BSON trực tiếp | Rất phù hợp | Qua `MongoTemplate` | Qua reactive driver/template |
| Repository abstraction | Tự viết | Có sẵn | Có sẵn cho reactive |
| Spring Boot application | Được nhưng thêm wiring | Tự nhiên | Tự nhiên với WebFlux |
| Có nhiều API Spring services | Nhiều công việc thủ công | Phù hợp | Nếu toàn stack reactive |
| Transaction | `ClientSession` | `MongoTransactionManager` | ReactiveTransactionManager |
| Test MongoDB thật | JUnit + Testcontainers | Spring Test + Testcontainers | Reactor + Testcontainers |
| Dễ debug blocking flow | Thuận tiện | Thuận tiện | Cần hiểu async chain |
| I/O concurrency cao | Thread-per-blocking-op | Thread blocking | Non-blocking theo driver |

Không dùng hai drivers/sessions khác nhau trong cùng business transaction rồi nghĩ Spring `@Transactional` tự bao trùm tất cả: phải kiểm **cùng transaction manager/session context**.

## 3. Môi trường và các điều kiện quan trọng

### 3.1. Yêu cầu thực hành

- JDK 17 hoặc phiên bản Java được Spring Boot đang dùng hỗ trợ.
- Maven hoặc Gradle.
- Spring Boot và Spring Data MongoDB **cùng bộ phiên bản tương thích**.
- JUnit Jupiter 5 và Spring Boot Test.
- MongoDB replica set test, hoặc Testcontainers có khả năng khởi tạo replica set.
- Docker/container runtime cho Testcontainers; CI phải được cấp quyền container.
- MongoDB Java Sync Driver do Spring Data Boot BOM quản lý phiên bản.
- Không dùng credentials production.

Ví dụ cấu trúc dưới đây theo các API phổ biến ở **Spring Boot 3.x / Spring Data MongoDB 4.x, Java 17 và MongoDB Java Sync Driver tương ứng**. Khi chạy thực tế, hãy chọn phiên bản Spring Boot/driver/Testcontainers đã được kiểm trong project. Spring Boot 4.x và Testcontainers 2.x có thể thay dependency/artifact/package; dùng tài liệu đúng version.

### 3.2. Vì sao Testcontainers phải dùng MongoDB replica set?

Single-node standalone MongoDB đủ kiểm một số CRUD/filter. Nhưng transaction đa document và change streams yêu cầu **replica set hoặc sharded cluster** phù hợp.

`MongoDBContainer` của Testcontainers có thể khởi chạy một MongoDB container dưới chế độ replica set cho integration tests. Test code dùng `getReplicaSetUrl()` thay vì URI standalone tự chế.

Nếu production dùng sharded cluster, test trên single-node replica set **không đủ** chứng minh các constraints liên quan shard key/unique index và behavior cross-shard; cần test bổ sung trên staging topology tương đương.

### 3.3. Không có MongoDB embedded giả thay thế mọi semantics

Mock `MongoRepository` có thể test service branching, nhưng không xác minh:

- MongoDB atomic conditional update.
- `$jsonSchema` validation.
- BSON type persistence.
- Unique index thật.
- Transaction rollback.
- `$elemMatch` vs dot notation.
- Retryable writes/driver error labels.
- Query planner/index usage.

Những cơ chế này cần integration test với MongoDB Server thực.

## 4. Dự án Maven: các dependency chính

Một `pom.xml` khung:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>SPRING_BOOT_VERSION_DA_CHOT</version>
    <relativePath/>
  </parent>

  <groupId>vn.demo</groupId>
  <artifactId>mongo-row465</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
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
      <artifactId>spring-boot-starter-data-mongodb</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>mongodb</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <!-- Nếu BOM Spring Boot đã quản lý Testcontainers thì
       không khai báo thêm BOM trùng; nếu chưa, import
       Testcontainers BOM tương thích với bản đã chốt. -->

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

**Quan trọng:** `SPRING_BOOT_VERSION_DA_CHOT` là placeholder cần thay bằng version thật đã xác nhận; `pom.xml` này chưa chạy được cho đến khi thay. Với các release Testcontainers mới có thể đổi group/artifact/module; dùng dependency matrix tương ứng, không trộn code API Testcontainers 1.x với artifacts của 2.x một cách máy móc.

Nếu dùng Gradle, giữ cùng nhóm dependencies:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:mongodb")
}

tasks.test {
    useJUnitPlatform()
}
```

Gradle snippet cần Spring Boot plugin và dependency-management/BOM tương ứng được cấu hình ở build của project. Trong STEP 4 này **không chạy Maven/Gradle**; code dành cho người học áp dụng trong môi trường riêng.

## 5. Cấu trúc project đề xuất

```text
mongo-row465/
  pom.xml
  src/
    main/
      java/vn/demo/row465/
        MongoRow465Application.java
        MongoTxConfig.java
        Product.java
        Reservation.java
        ProductRepository.java
        ReservationRepository.java
        StockService.java
        ReservationController.java
        ApiErrorHandler.java
      resources/
        application.yml
    test/
      java/vn/demo/row465/
        StockServiceIT.java
        ReservationApiIT.java
        BsonAndSchemaIT.java
        StockServiceUnitTest.java
```

Đây là bố cục hướng dẫn. Trong các code snippets, tên class/package cần khớp khi chép vào file. Một số integration test dùng mã khung; nếu viết thêm unit test thì cần dependency/mocking theo framework đã chọn.

## 6. Cấu hình kết nối an toàn

### 6.1. Main application

```java
package vn.demo.row465;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MongoRow465Application {
    public static void main(String[] args) {
        SpringApplication.run(
            MongoRow465Application.class, args
        );
    }
}
```

`application.yml`:

```yaml
spring:
  data:
    mongodb:
      uri: \${MONGODB_URI}
      database: \${MONGODB_DATABASE:row465_app}
      auto-index-creation: false

server:
  port: 8080
```

Ở file thực, ký tự `\${MONGODB_URI}` biểu thị placeholder của Spring; cần bỏ dấu backslash nếu hệ thống copy tool để literal escape khác. Cấu hình ý định:

```text
spring.data.mongodb.uri = môi trường MONGODB_URI
spring.data.mongodb.database = môi trường MONGODB_DATABASE
```

**Không commit URI chứa password**. Production nên dùng secrets/secret manager/TLS, role tối thiểu và database migrations riêng để quản lý indexes.

### 6.2. Về `auto-index-creation`

Spring Data có thể tạo indexes dựa trên annotations nếu bật auto index creation. Mặc định ở nhiều Spring Data releases là **false**, vì tạo index tự động khi application khởi động có thể:

- Chạy DDL đột ngột trên collection lớn.
- Gây duplicate key build failure.
- Cạnh tranh I/O với traffic.
- Khó quản lý thứ tự rollout nhiều app versions.
- Không có change ticket/capacity plan.

Trong integration tests với MongoDB container rỗng, có thể bật để kiểm annotations. Production cần process quản lý index migrations rõ ràng, không đơn giản bật true cho mọi service.

### 6.3. Các thông số phải hiểu trước khi tuning

- `serverSelectionTimeoutMS`: driver tìm node phù hợp.
- `connectTimeoutMS`: thiết lập connection.
- `socketTimeoutMS` hoặc `timeoutMS` theo phiên bản driver.
- `retryWrites`: driver-level retry của các writes đủ điều kiện.
- `w`, `j`, `wtimeout`: durability/acknowledgment.
- Pool size và wait queue theo driver version.
- Read preference/read concern/session semantics.

Không đặt timeout cực thấp để tests nhanh rồi dùng cùng config trên production. Một request timeout không tự chứng minh MongoDB đã rollback operation.

## 7. Mô hình dữ liệu Product

### 7.1. Product document

```javascript
{
  _id: "prod_e8d59a",
  tenantId: "tenant-a",
  sku: "BOOK-101",
  priceCents: NumberLong("125000"),
  available: NumberInt(12),
  version: NumberLong("0")
}
```

Bất biến:

- `tenantId` không rỗng, mọi query có tenant scope.
- `sku` không rỗng và unique theo tenant.
- `priceCents` là số nguyên không âm trong phạm vi Int64.
- `available` là số nguyên không âm.
- `version` thay đổi với update để phát hiện stale writes.
- `_id` không được sinh lại khi cùng product/business identity cần retry.

### 7.2. Entity Spring Data

```java
package vn.demo.row465;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "row465_products")
@CompoundIndex(
    name = "tenant_sku_unique",
    def = "{'tenantId': 1, 'sku': 1}",
    unique = true
)
public class Product {
    @Id
    private String id;
    private String tenantId;
    private String sku;
    private long priceCents;
    private int available;

    @Version
    private Long version;

    public Product() {
        // Cho mapping framework.
    }

    public Product(
            String id,
            String tenantId,
            String sku,
            long priceCents,
            int available) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.priceCents = priceCents;
        this.available = available;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public int getAvailable() {
        return available;
    }

    public Long getVersion() {
        return version;
    }
}
```

`@Id` ánh xạ sang MongoDB `_id`. Ở demo dùng ID dạng `prod_...` để không vô tình trông giống ObjectId hex 24 ký tự; Spring Data có thể chuyển String ID hợp lệ dạng ObjectId tùy mapping/annotation.

`@Version` dùng optimistic locking cho các thao tác mapping được Spring Data hỗ trợ, đặc biệt `save`; nó không có nghĩa mọi raw driver command tự increment version. Phần giữ hàng dùng `MongoTemplate.findAndModify` với mapped entity; theo Spring Data MongoDB, update operation có thể tự tăng version khi `@Version` không nằm trong `Update`. Kiểm behavior bằng integration tests trên đúng framework version.

### 7.3. Tại sao chọn `long` cho giá?

`125000` có thể được gửi trong HTTP JSON như number. Trong Java field kiểu `long`, Spring Data/driver thường lưu thành BSON Int64; test cần assert type sau write.

Không dùng `double` cho money nếu cần chính xác theo đơn vị. Với loại tiền tệ có phần lẻ hoặc số lượng cực lớn, có thể dùng `Decimal128`, `BigDecimal` + converters hoặc money value object với currency.

### 7.4. Vì sao không embed reservations vào Product?

Reservations có thể tăng không giới hạn theo thời gian. Nếu nhét mọi reservation vào một product document:

- Document có thể lớn dần tới giới hạn 16 MiB.
- Mỗi insert làm tăng contention trên hot product.
- Audit và retention khó tách.
- Khó query reservations của khách hàng.

Demo dùng collection `row465_reservations` riêng và transaction để bảo vệ nhiều documents.

## 8. Reservation ledger và idempotency key

### 8.1. Document

```javascript
{
  _id: "reserve-tenant-a-order-999",
  tenantId: "tenant-a",
  productId: "prod_e8d59a",
  quantity: NumberInt(2),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

`_id` là **request identity**, không phải ID ngẫu nhiên mới cho mỗi retry. Nếu cùng request ID đến lần hai với cùng payload, service trả reservation đã tồn tại.

Nếu cùng ID nhưng payload khác, phải **conflict**, không nhận như một request mới.

### 8.2. Entity

```java
package vn.demo.row465;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "row465_reservations")
public class Reservation {
    @Id
    private String requestId;
    private String tenantId;
    private String productId;
    private int quantity;
    private Instant createdAt;

    public Reservation() {}

    public Reservation(
            String requestId,
            String tenantId,
            String productId,
            int quantity,
            Instant createdAt) {
        this.requestId = requestId;
        this.tenantId = tenantId;
        this.productId = productId;
        this.quantity = quantity;
        this.createdAt = createdAt;
    }

    public String getRequestId() {
        return requestId;
    }
    public String getTenantId() {
        return tenantId;
    }
    public String getProductId() {
        return productId;
    }
    public int getQuantity() {
        return quantity;
    }
    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Trong production có thể thêm `requestHash`, state machine `PENDING/CONFIRMED/CANCELLED`, expiration/lease và business order ID. **Không thêm TTL tự động** vào reservation có tác dụng tồn kho nếu chưa thiết kế quy trình release/compensation; xóa ledger có thể làm mất bằng chứng idempotency.

## 9. Repository interfaces

```java
package vn.demo.row465;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    Optional<Product> findByTenantIdAndSku(
        String tenantId, String sku
    );

    Optional<Product> findByIdAndTenantId(
        String id, String tenantId
    );
}
```

```java
package vn.demo.row465;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface ReservationRepository
        extends MongoRepository<Reservation, String> {
}
```

Spring Data dùng method names để sinh query. Tuy tiện lợi, nhưng không nên viết repository method dài với các predicates array/nested phức tạp mà chưa biết nó tạo `$elemMatch` hay dot notation.

### 9.1. Truy vấn phải gắn tenant

Sai về bảo mật:

```java
productRepository.findById(productId);
```

rồi trả thẳng cho người dùng ở tenant A; ID có thể thuộc tenant B.

Đúng hơn:

```java
productRepository.findByIdAndTenant(
    productId, authorizedTenantId
);
```

Ở code demo, tên đúng là `findByIdAndTenantId`. Quan trọng: `authorizedTenantId` phải lấy từ identity/authorization context đáng tin, **không chỉ tin một path parameter**.

### 9.2. Index unique không được thay bằng `findBySku` rồi `save`

Hai threads:

```text
Thread A: find sku -> absent
Thread B: find sku -> absent
Thread A: insert sku
Thread B: insert sku
```

Nếu không có unique index, cả hai inserts có thể thành công. Cần unique compound index `{tenantId:1,sku:1}` và bắt duplicate key error. Unique index trên sharded collection còn cần thỏa shard-key prefix restrictions.

## 10. Transaction manager cho MongoDB

```java
package vn.demo.row465;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    public MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Điều kiện:

- MongoDB deployment hỗ trợ multi-document transactions (replica set/sharded cluster theo phiên bản).
- Các repository/template operations dùng transaction context do Spring quản lý.
- Không dùng một MongoClient/session khác ngoài context rồi giả định nó tham gia cùng transaction.
- Transaction nên ngắn, không thực hiện HTTP calls hoặc chờ người dùng.
- Xem write concern/read concern/transaction options cho nghiệp vụ.
- `@Transactional` trên self-invocation có thể không chạy vì Spring proxy boundary.
- Test trên standalone sẽ lỗi khi bắt đầu transaction.

### 10.1. Tại sao không chỉ dùng `@Transactional` cho mọi method?

Transaction có overhead và tạo write conflicts, đặc biệt với hot products. Nếu một nghiệp vụ chỉ update một document, một atomic conditional update có thể đủ. Ở bài này cần **hai changes nhất quán**: trừ `available` và ghi reservation ledger; vì vậy transaction hợp lý.

## 11. StockService: atomic check và idempotent reservation

### 11.1. Mã service

```java
package vn.demo.row465;

import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@Service
public class StockService {
    private final MongoTemplate template;
    private final ReservationRepository reservations;

    public StockService(
            MongoTemplate template,
            ReservationRepository reservations) {
        this.template = template;
        this.reservations = reservations;
    }

    @Transactional
    public Reservation reserve(
            String tenantId,
            String requestId,
            String productId,
            int quantity) {

        if (tenantId == null || tenantId.isBlank()
                || requestId == null || requestId.isBlank()
                || productId == null || productId.isBlank()
                || quantity < 1) {
            throw new IllegalArgumentException(
                    "Invalid reservation input"
            );
        }

        Reservation previous = reservations
                .findById(requestId)
                .orElse(null);

        if (previous != null) {
            boolean sameCommand =
                Objects.equals(previous.getTenantId(), tenantId)
                && Objects.equals(
                    previous.getProductId(), productId
                )
                && previous.getQuantity() == quantity;

            if (!sameCommand) {
                throw new IllegalStateException(
                    "Idempotency key reused with different payload"
                );
            }

            return previous;
        }

        Query filter = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(tenantId)
                .and("available").gte(quantity)
        );

        Update change = new Update()
                .inc("available", -quantity);

        Product changed = template.findAndModify(
            filter,
            change,
            FindAndModifyOptions.options().returnNew(true),
            Product.class
        );

        if (changed == null) {
            throw new IllegalStateException(
                    "Product missing or insufficient stock"
            );
        }

        // Cùng MongoDB transaction với findAndModify.
        return reservations.insert(new Reservation(
            requestId,
            tenantId,
            productId,
            quantity,
            Instant.now()
        ));
    }
}
```

### 11.2. Vì sao query có `available >= quantity`?

```javascript
{
  _id: productId,
  tenantId: tenantId,
  available: { $gte: quantity }
}
```

MongoDB thực hiện filter và update lên **một document một cách atomic**. Nếu hai requests cùng muốn giữ 8 sản phẩm trong kho 10, chỉ request đầu hoặc một request có điều kiện còn đủ hàng có thể trừ thành công; request còn lại không được tạo tồn âm.

Không làm:

```text
read available=10
if available >= 8:
    update available = available - 8
```

vì hai threads có thể cùng đọc 10 rồi cùng ghi. Cần atomic predicate/update hoặc transaction có điều kiện phù hợp.

### 11.3. Vì sao transaction bao cả insert reservation?

Nếu giảm `available` thành công nhưng `reservations.insert` thất bại, không được giữ hàng “ma” mà không có ledger.

Trong transaction MongoDB:

```text
begin transaction
  |
  v
check and decrement product
  |
  v
insert reservation with unique request ID
  |
commit transaction
```

Nếu insert duplicate key, transaction có thể abort, product decrement cùng transaction được rollback. Nếu transaction commit result unknown, phải **đối soát request ledger** thay vì blind retry.

### 11.4. Hai requests cùng `requestId` đồng thời

Đọc `reservations.findById` ở đầu service **không tự ngăn race**. Hai transactions có thể cùng thấy chưa tồn tại, rồi tranh chấp product write/unique reservation `_id`.

Trên production:

- Sử dụng stable request ID.
- Unique `_id` của reservation.
- Khi write conflict/transient transaction error, retry **toàn transaction** theo policy/driver.
- Khi commit unknown, retry **commit cùng transaction/session** hoặc reconcile; không tự ném business request mới.
- Nếu sau rollback có duplicate key, đọc existing reservation và so payload.
- Giới hạn retry và backoff để tránh retry storm.

Ví dụ trên chỉ xử lý một request transaction; **không có vòng retry đầy đủ**. Các tests tuần tự chứng minh idempotency cơ bản; thêm tests concurrency riêng để xác nhận logic retry/ownership.

### 11.5. `@Version` và update operator

`Product.version` được quản lý bởi Spring Data. Tài liệu Spring Data mô tả update operations có thể tự tăng version nếu field version không có trong `Update`. Điều này khác với raw Java driver `updateOne`, vốn chỉ đổi các fields đã nêu.

Vì vậy không tự thêm `.inc("version",1)` vào snippet Spring Data mà không kiểm cơ chế tự tăng trên đúng framework release: có nguy cơ tăng hai lần hoặc behavior không như dự kiến. Integration test phải đọc lại version sau reserve và khẳng định tiến độ.

### 11.6. Yêu cầu giữ hàng không bằng thanh toán

Reservation ở ví dụ chỉ giảm available và tạo ledger. Với order/payment thật còn có:

- TTL/expiration semantics và release stock.
- Cancellation/return inventory.
- Order payment state machine.
- Idempotency khi external gateway timeout.
- Outbox để phát ReservationCreated.
- Retry/reconciliation khi commit outcome chưa rõ.

Không tự “rollback” một external payment bằng cách xóa reservation MongoDB.

## 12. REST controller và Bean Validation

### 12.1. DTO không để client đặt mọi field

```java
package vn.demo.row465;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateProductRequest(
    @NotBlank String sku,
    @PositiveOrZero long priceCents,
    @PositiveOrZero int available
) {}

public record ReserveRequest(
    @Min(1) int quantity
) {}

public record ReservationResponse(
    String requestId,
    String tenantId,
    String productId,
    int quantity
) {
    public static ReservationResponse from(Reservation r) {
        return new ReservationResponse(
            r.getRequestId(),
            r.getTenantId(),
            r.getProductId(),
            r.getQuantity()
        );
    }
}
```

Đây là ba Java records riêng; nếu chép thành files, mỗi public record phải đặt trong file mang đúng tên hoặc đổi visibility theo cấu trúc dự án. Không đặt toàn bộ ba public records trong một file `CreateProductRequest.java`.

### 12.2. Controller minh họa

```java
package vn.demo.row465;

import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/demo/tenants/{tenantId}/products")
public class ReservationController {
    private final ProductRepository products;
    private final StockService stockService;

    public ReservationController(
            ProductRepository products,
            StockService stockService) {
        this.products = products;
        this.stockService = stockService;
    }

    @PostMapping
    public ResponseEntity<Product> create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreateProductRequest body) {

        Product product = new Product(
            "prod_" + UUID.randomUUID(),
            tenantId,
            body.sku(),
            body.priceCents(),
            body.available()
        );

        return ResponseEntity.ok(products.insert(product));
    }

    @PostMapping("/{productId}/reservations")
    public ResponseEntity<ReservationResponse> reserve(
            @PathVariable String tenantId,
            @PathVariable String productId,
            @RequestHeader("Idempotency-Key")
                String requestId,
            @Valid @RequestBody ReserveRequest body) {

        Reservation saved = stockService.reserve(
            tenantId,
            requestId,
            productId,
            body.quantity()
        );

        return ResponseEntity.ok(
            ReservationResponse.from(saved)
        );
    }
}
```

**Cảnh báo an toàn:** đây là route demo **chưa có authentication/authorization**. Trên production, tenant ID phải được xác thực từ principal/claims và kiểm ownership. Không tin một giá trị do client tự điền trong path/header.

### 12.3. Exception mapping

Một `IllegalStateException` trong code trên chưa đủ để API phân biệt “hết hàng” với “same idempotency key, payload khác”, và có thể mặc định trả HTTP 500. Nên có domain exceptions:

```java
public class StockUnavailableException
        extends RuntimeException {
    public StockUnavailableException(String message) {
        super(message);
    }
}

public class IdempotencyConflictException
        extends RuntimeException {
    public IdempotencyConflictException(String message) {
        super(message);
    }
}
```

Trong code `StockService` thực tế, thay `IllegalStateException` bằng exception tương ứng. Có thể map:

```java
@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(StockUnavailableException.class)
    ResponseEntity<?> outOfStock(
            StockUnavailableException e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "STOCK_UNAVAILABLE"
            ));
    }

    @ExceptionHandler(IdempotencyConflictException.class)
    ResponseEntity<?> reusedKey(
            IdempotencyConflictException e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "IDEMPOTENCY_CONFLICT"
            ));
    }

    @ExceptionHandler(
        org.springframework.dao.DuplicateKeyException.class
    )
    ResponseEntity<?> duplicateKey(Exception e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "DUPLICATE_KEY"
            ));
    }
}
```

Đoạn này là skeleton bổ sung imports/package khi đưa vào source. Không trả raw exception message chứa dữ liệu nhạy cảm/DB internals cho HTTP client. Lỗi network/commit unknown không nên bị gộp thành một `409` giả; cần log và protocol reconciliation phù hợp.

## 13. Index và schema validation ở tầng database

### 13.1. Compound unique index

`@CompoundIndex` khai báo ý định. Production nên tạo/migrate index theo quy trình DDL được kiểm soát:

```javascript
db.row465_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "tenant_sku_unique",
    unique: true
  }
);
```

Lưu ý:

- Index unique phải được build sau khi audit duplicates trong collection hiện hữu.
- Cần xem semantics của missing/null trong compound unique key.
- Đối với sharded collection, unique index cần thỏa shard-key prefix rules.
- Index không tự enforce `priceCents >= 0` hoặc đúng BSON type.
- Application validation không ngăn một script khác ghi trực tiếp dữ liệu sai nếu DB không có validator.

### 13.2. Validator mô tả hợp đồng

Ví dụ:

```javascript
const productValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "sku",
      "priceCents",
      "available"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      sku: {
        bsonType: "string",
        minLength: 1
      },
      priceCents: {
        bsonType: "long",
        minimum: 0
      },
      available: {
        bsonType: "int",
        minimum: 0
      }
    }
  }
};
```

Tùy mapping/driver, `version` có thể được lưu với BSON Int64 và không bị validator ràng buộc ở đây. Muốn kiểm version, audit type thực trước rồi mở rộng validator.

`required` có nghĩa field phải tồn tại; kết hợp `bsonType` mới loại `null` theo yêu cầu. Không đặt `additionalProperties:false` ở root nếu chưa liệt kê `_id` và metadata hợp lệ.

### 13.3. Lập validator trên collection test

```javascript
db.runCommand({
  collMod: "row465_products",
  validator: productValidator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Không chạy `collMod` vào collection production chỉ để “kiểm code hoạt động”. Với dữ liệu legacy có thể không hợp schema mới, cần rollout `warn/moderate/error/strict` theo giai đoạn và backfill.

### 13.4. Cả validator và unique index đều phải được test

Một test thành công chỉ vì API Java từ chối `priceCents=-1` **không chứng minh** MongoDB validator đang chạy. Cần một integration test dùng MongoDB driver/template chèn document invalid trực tiếp vào namespace test và assert server rejection.

Tương tự, unit test repository mock không chứng minh unique index đã tồn tại; phải thử insert hai documents có cùng `tenantId+sku` vào MongoDB thật.

## 14. Chọn test pyramid phù hợp

### 14.1. Bốn tầng

```text
               End-to-end API
               HTTP -> Spring -> MongoDB
                      /\
                     /  \
               Integration
           MongoTemplate/Repository/Txn
                   /      \
                  /        \
             Slice tests
      MVC / mapping / configuration
                /          \
               /            \
          Unit tests
     pure rules and branching
```

Không nhất thiết số lượng test theo đúng hình kim tự tháp ở mọi project. Mục tiêu là mỗi layer kiểm **đúng trách nhiệm**, tránh mock sai cấp.

### 14.2. Unit tests nên kiểm gì?

- Xác minh quantity lớn hơn 0.
- Canonical hóa SKU theo business rule.
- Kiểm requestId/payloadHash.
- Mapper/formatter không truy cập DB.
- Giá tiền không overflow khi cộng nhân.
- Business transition state machine.

Có thể dùng plain JUnit 5 và Mockito, không mở Spring context.

### 14.3. Repository integration tests nên kiểm gì?

- MongoDB mapping BSON.
- Unique index.
- Filter tenant.
- `$elemMatch`.
- Null vs missing.
- Query return/sort/paging.
- Transactions/rollback.
- Optimistic locking và version.
- Serialization Decimal128/ObjectId/Date.

Cần MongoDB thật. Mock repository chỉ trả những gì ta lập trình cho mock, không chứng minh server semantics.

### 14.4. Controller/API tests nên kiểm gì?

- JSON validation: missing/invalid fields.
- HTTP status/error contract.
- Idempotency-Key được bắt buộc.
- Tenant authorization.
- Response không lộ fields nhạy cảm.
- Kết nối đúng service/transaction layer.
- Timeout/unknown outcome được map đúng.

`@WebMvcTest` có thể tách controller với mocked service; `@SpringBootTest + MockMvc` đi qua toàn stack.

## 15. Testcontainers: MongoDB thực cho JUnit 5

### 15.1. Nguyên tắc

- Test container là tài nguyên ephemeral của riêng suite.
- MongoDB image được pin ở version phù hợp production/staging.
- `MongoDBContainer.getReplicaSetUrl()` cấp connection string đúng topology.
- Không hardcode `localhost:27017` trong test.
- Không dùng MongoDB production URI trong CI.
- Test có thể chạy bằng `mvn test` trong môi trường người học; worker STEP 4 **không thực thi**.
- Một Docker image `mongo:7.0` chỉ là ví dụ; khi hệ thống dùng MongoDB 8.x/9.x, cần matrix tương thích riêng.

### 15.2. Cấu hình integration test

```java
package vn.demo.row465;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Assertions;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class StockServiceIT {
    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    private static final String DB_NAME =
        "row465_it_" +
        UUID.randomUUID().toString().replace("-", "");

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
        registry.add(
            "spring.data.mongodb.database",
            () -> DB_NAME
        );
        registry.add(
            "spring.data.mongodb.auto-index-creation",
            () -> "true"
        );
    }

    @Autowired
    ProductRepository products;

    @Autowired
    ReservationRepository reservations;

    @Autowired
    StockService stockService;

    @Autowired
    MongoTemplate template;

    private String productId;
    private String requestId;

    @BeforeEach
    void setUp() {
        productId = "prod_" + UUID.randomUUID();
        requestId = "req_" + UUID.randomUUID();
    }

    private Product seed(int available) {
        return products.insert(new Product(
            productId,
            "tenant-test",
            "SKU_" + productId,
            125000L,
            available
        ));
    }

    @AfterEach
    void cleanup() {
        if (requestId != null) {
            reservations.deleteById(requestId);
        }
        if (productId != null) {
            products.deleteById(productId);
        }
        // DB_NAME là database ephemeral của riêng suite.
        // Không xóa toàn database của môi trường dùng chung.
    }

    @Test
    void reserveReducesAvailableAndSavesLedger() {
        seed(10);

        Reservation result = stockService.reserve(
            "tenant-test",
            requestId,
            productId,
            3
        );

        Assertions.assertEquals(
            requestId, result.getRequestId()
        );
        Assertions.assertEquals(3, result.getQuantity());

        Product after = products.findById(productId).orElseThrow();

        Assertions.assertEquals(7, after.getAvailable());
        Assertions.assertTrue(
            reservations.findById(requestId).isPresent()
        );
    }

    @Test
    void sameRequestIdDoesNotReserveTwice() {
        seed(10);

        Reservation first = stockService.reserve(
            "tenant-test", requestId, productId, 2
        );

        Reservation again = stockService.reserve(
            "tenant-test", requestId, productId, 2
        );

        Assertions.assertEquals(
            first.getRequestId(),
            again.getRequestId()
        );

        Assertions.assertEquals(
            8,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
        Assertions.assertEquals(
            1,
            reservations.count()
        );
    }

    @Test
    void insufficientStockDoesNotWriteReservation() {
        seed(1);

        Assertions.assertThrows(
            IllegalStateException.class,
            () -> stockService.reserve(
                "tenant-test", requestId, productId, 2
            )
        );

        Assertions.assertEquals(
            1,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
        Assertions.assertFalse(
            reservations.findById(requestId).isPresent()
        );
    }

    @Test
    void reusedKeyWithDifferentQuantityIsRejected() {
        seed(10);

        stockService.reserve(
            "tenant-test", requestId, productId, 1
        );

        Assertions.assertThrows(
            IllegalStateException.class,
            () -> stockService.reserve(
                "tenant-test", requestId, productId, 2
            )
        );

        Assertions.assertEquals(
            9,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
    }

    @Test
    void duplicateSkuWithinTenantIsRejected() {
        seed(10);

        String otherId = "prod_" + UUID.randomUUID();

        try {
            Assertions.assertThrows(
                DuplicateKeyException.class,
                () -> products.insert(new Product(
                    otherId,
                    "tenant-test",
                    "SKU_" + productId,
                    125000L,
                    1
                ))
            );
        } finally {
            products.deleteById(otherId);
        }
    }
}
```

### 15.3. Vì sao test này đáng tin hơn mock?

- `reserveReduces...` gọi MongoDB thật để trừ stock và insert ledger.
- `sameRequestId...` chứng minh retry tuần tự không trừ hai lần.
- `insufficientStock...` chứng minh atomic predicate từ chối khi thiếu hàng.
- `duplicateSku...` chứng minh **index thực sự tồn tại và enforce**, không phải chỉ có annotation.
- MongoDBContainer chạy replica set để `@Transactional` có thể hoạt động.
- Test DB có tên ngẫu nhiên của riêng suite; test records có IDs riêng.

**Chưa bao phủ:** retry transaction errors, commit unknown, concurrent same key, secondary failover, sharded uniqueness, API authentication, và full performance SLO. Những trường hợp đó cần tests riêng.

### 15.4. Một lưu ý về `reservations.count()`

Trong ví dụ, mỗi suite có database ngẫu nhiên và chỉ một reservation được tạo trong test; nếu chạy parallel tests chia sẻ DB, `count()` có thể không ổn định do test khác đang tạo reservation.

Khi bật parallel tests, dùng filter theo `requestId`/runId và isolation mỗi test, hoặc không bật parallelization trên shared state. Mục tiêu là tests **độc lập**, không dựa vào thứ tự thực thi.

## 16. Kiểm tra BSON type sau khi ghi

### 16.1. Vì sao JSON assertions chưa đủ?

HTTP JSON:

```json
{
  "priceCents": 125000
}
```

không thể chứng minh MongoDB lưu BSON `Int64` thay vì `Int32` hoặc `Double`.

### 16.2. Read raw BSON từ collection test

```java
import org.bson.BsonDocument;
import org.bson.BsonType;
import com.mongodb.client.MongoCollection;
import static com.mongodb.client.model.Filters.eq;

// Sau khi đã tạo Product:
MongoCollection<BsonDocument> rawProducts =
    template.getDb().getCollection(
        "row465_products",
        BsonDocument.class
    );

BsonDocument stored = rawProducts.find(
    eq("_id", productId)
).first();

Assertions.assertNotNull(stored);
Assertions.assertEquals(
    BsonType.INT64,
    stored.get("priceCents").getBsonType()
);

Assertions.assertEquals(
    BsonType.INT32,
    stored.get("available").getBsonType()
);
```

Các imports và `template/productId` lấy từ integration test class ở phần trên. Kiểm thêm `version` dựa theo behavior version của framework và contract; không đoán mọi field Number có type giống nhau.

### 16.3. Số lớn và Decimal128

Tạo test:

```java
long large = 9_007_199_254_740_993L;
```

Đây là số vượt mức integer chính xác của JavaScript Number. MongoDB Java `long` lưu được, nhưng nếu frontend gửi trực tiếp dưới dạng JS Number có thể làm tròn **trước khi Java nhận**.

Với tiền decimal:

```java
org.bson.types.Decimal128 dec =
    new org.bson.types.Decimal128(
        new java.math.BigDecimal("125.50")
    );
```

Kiểm tròn/scale/đơn vị qua boundary. Không dùng `new BigDecimal(0.1)` để giả định decimal 0.1 chính xác.

## 17. Null, missing và patch semantics

### 17.1. Hai trạng thái giống nhau qua `Document.get()`

```java
org.bson.Document missing =
    new org.bson.Document("_id", "missing");

org.bson.Document explicitNull =
    new org.bson.Document("_id", "null")
        .append("nickname", null);

Assertions.assertNull(missing.get("nickname"));
Assertions.assertNull(explicitNull.get("nickname"));

Assertions.assertFalse(
    missing.containsKey("nickname")
);
Assertions.assertTrue(
    explicitNull.containsKey("nickname")
);
```

`get()==null` không phân biệt missing với BSON Null; `containsKey` có thể.

### 17.2. Truy vấn MongoDB

```javascript
db.profile_cases.find({
  nickname: null
});
```

có thể match cả missing và explicit null. Ngược lại:

```javascript
db.profile_cases.find({
  nickname: { $exists: false }
});

db.profile_cases.find({
  nickname: { $type: "null" }
});
```

phân biệt theo mục tiêu. Với field array, `$type` dạng query có thể match phần tử array, nên cần thêm fixtures.

### 17.3. PATCH không gửi field khác gửi null

```json
{}
```

và:

```json
{"nickname": null}
```

phải được định nghĩa khác nhau nếu API PATCH có semantics “missing = không thay đổi, null = xóa/đặt null”. Một DTO Java `String nickname` đơn thuần dễ làm mất khác biệt sau deserialization.

Có thể dùng JSON Patch, wrapper field-presence hoặc inspect JSON keys an toàn rồi chuyển thành:

- `$set` cho giá trị mới.
- `$set:{nickname:null}` nếu contract là explicit null.
- `$unset:{nickname:""}` nếu contract là xóa field.

Test cả HTTP JSON → DTO → MongoDB readback, không chỉ test method update.

## 18. Mảng: truy vấn đúng bằng `$elemMatch`

### 18.1. Fixture

```javascript
{
  _id: "order-cross",
  lines: [
    { sku: "A", quantity: 1 },
    { sku: "B", quantity: 10 }
  ]
}
```

Truy vấn:

```javascript
{
  "lines.sku": "A",
  "lines.quantity": { $gte: 5 }
}
```

có thể match do mỗi điều kiện được đáp ứng bởi **phần tử khác nhau**.

### 18.2. Truy vấn cần một phần tử thỏa cả hai

```javascript
{
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}
```

Document trên không match. Spring Data:

```java
Query q = Query.query(
    Criteria.where("lines").elemMatch(
        Criteria.where("sku").is("A")
            .and("quantity").gte(5)
    )
);
```

Một integration test nên seed cả document cross-element và same-element để assert counts 0 vs 1. Nếu chỉ mock `MongoTemplate.find`, test không phát hiện được sai khác query semantics.

### 18.3. Mảng rỗng/thiếu/null

Những cases phải phân biệt:

```javascript
{}
{ tags: null }
{ tags: [] }
{ tags: [null] }
{ tags: ["java"] }
{ tags: "java" }
```

`{tags:"java"}` có thể match cả scalar String và array chứa String. Nếu schema yêu cầu tags là array, thêm `$jsonSchema`/Bean validation và tests đọc BSON, không coi query membership là type validation.

## 19. Schema validator integration test

### 19.1. Dùng namespace dành riêng cho test

Trong integration test, tạo một collection mới có tên ngẫu nhiên, dùng validator. Không sửa validator của collection được ứng dụng khác sử dụng.

```java
String name =
    "validation_row465_" +
    java.util.UUID.randomUUID().toString()
        .replace("-", "");

org.bson.Document jsonSchema =
    new org.bson.Document("bsonType", "object")
        .append("required", java.util.List.of(
            "sku", "priceCents"
        ))
        .append("properties",
            new org.bson.Document()
                .append("sku",
                    new org.bson.Document(
                        "bsonType", "string"
                    ))
                .append("priceCents",
                    new org.bson.Document(
                        "bsonType", "long"
                    ).append("minimum", 0))
        );

org.bson.Document validator =
    new org.bson.Document("$jsonSchema", jsonSchema);

template.getDb().createCollection(
    name,
    new com.mongodb.client.model.CreateCollectionOptions()
        .validationOptions(
            new com.mongodb.client.model.ValidationOptions()
                .validator(validator)
                .validationLevel(
                    com.mongodb.client.model.ValidationLevel.STRICT
                )
                .validationAction(
                    com.mongodb.client.model.ValidationAction.ERROR
                )
        )
);
```

Tùy Java Driver release, import enum/option API từ `com.mongodb.client.model` như trên và đối chiếu Javadocs.

### 19.2. Test insert đúng/sai type

```java
MongoCollection<org.bson.Document> collection =
    template.getDb().getCollection(name);

collection.insertOne(new org.bson.Document()
    .append("_id", "valid")
    .append("sku", "A")
    .append("priceCents", 125000L));

Assertions.assertThrows(
    com.mongodb.MongoWriteException.class,
    () -> collection.insertOne(
        new org.bson.Document()
            .append("_id", "invalid")
            .append("sku", "B")
            .append("priceCents", "125000")
    )
);
```

Phép insert thứ hai phải bị server từ chối vì `priceCents` là BSON String, không phải Long.

### 19.3. Cleanup

Vì collection này được tạo **bởi riêng test** trong database Testcontainers riêng, có thể dọn sau test bằng logic:

```java
try {
    // Run test assertions against own collection.
} finally {
    template.getDb().getCollection(name).drop();
}
```

Chỉ `drop()` trên chính collection được test tạo và đã xác minh name/ownership. **Không** copy pattern drop sang database dùng chung/production. Nếu muốn nguyên tắc chặt hơn, test có thể delete theo exact `_id` rồi để container bị hủy cùng CI job.

### 19.4. Validator không phải thay thế unique index

`$jsonSchema` chỉ kiểm shape/type/value trong một document. Hai products khác nhau cùng tenant+sku đều có thể thỏa JSON Schema, nên vẫn cần unique index; các tests phải kiểm cả hai cơ chế.

## 20. Test transaction rollback thật

### 20.1. Vấn đề cần chứng minh

`@Transactional` được viết trên method chưa chứng minh rằng transaction thực sự được tạo. Cần test cố tình ném exception **sau một write**, rồi kiểm dữ liệu được rollback.

### 20.2. Dùng `TransactionTemplate` trên MongoDB container

```java
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.data.mongodb.core.query.Criteria;

TransactionTemplate tx =
    new TransactionTemplate(mongoTransactionManager);

int before = products.findById(productId)
    .orElseThrow().getAvailable();

Assertions.assertThrows(
    IllegalStateException.class,
    () -> tx.execute(status -> {
        template.updateFirst(
            Query.query(
                Criteria.where("_id").is(productId)
            ),
            new Update().inc("available", -1),
            Product.class
        );

        throw new IllegalStateException(
            "Injected error after write"
        );
    })
);

int after = products.findById(productId)
    .orElseThrow().getAvailable();

Assertions.assertEquals(before, after);
```

Trong test class, inject:

```java
@Autowired
MongoTransactionManager mongoTransactionManager;
```

Test chỉ chạy được trên deployment transaction-compatible; nếu vô tình test trên standalone hoặc thiếu transaction manager, kết quả khác và phải sửa môi trường, không “bỏ `@Transactional` cho pass”.

### 20.3. Cẩn thận rollback khi commit unknown

Test exception **trong body** và transaction abort khác với network timeout **ngay lúc commit**. Với `UnknownTransactionCommitResult`, transaction có thể đã commit. Ứng dụng không được mặc định chạy lại giữ hàng bằng request ID mới.

Dùng stable request ID và reconciliation:

- Read reservation ledger theo request ID.
- Xác nhận product/ledger consistency theo durability contract.
- Retry commit cùng session khi còn phù hợp hoặc dùng protocol recovery.
- Không trừ stock thêm lần nữa.

## 21. Test optimistic locking với `@Version`

### 21.1. Hai phiên bản entity

```text
T0: Thread A reads Product(version=5)
T1: Thread B reads Product(version=5)
T2: A saves updated product -> version=6
T3: B attempts save version=5 -> optimistic lock failure
```

Spring Data MongoDB kiểm version với `save` cho entity có `@Version` (theo mapping semantics). Test có thể:

```java
Product a = products.findById(productId).orElseThrow();
Product b = products.findById(productId).orElseThrow();

// Cần entity update method/setter trong domain model
// nếu muốn mutate + save trực tiếp.
// Sau khi A save version mới, B save với version cũ
// phải bị xử lý như stale update.
```

Không bắt chước mô hình này bằng cách save cùng instance reference `a==b`, vì test không có hai snapshots riêng.

### 21.2. `@Version` không bảo vệ raw update nếu dùng sai

Nếu dùng raw driver:

```java
collection.updateOne(
    Filters.eq("_id", productId),
    Updates.set("priceCents", newPrice)
);
```

MongoDB không tự kiểm `version` vì POJO có annotation. Muốn bảo vệ, thêm filter:

```java
Filters.and(
    Filters.eq("_id", productId),
    Filters.eq("version", expectedVersion)
);
```

và update version theo protocol. Lưu ý query/updated fields dùng đúng BSON type của version.

### 21.3. Version vs business state

Đọc version mới không có nghĩa request trước đã thành công; version có thể được tăng bởi writer khác. Dùng `requestId` hoặc operation ledger để phân biệt idempotent replay với conflict.

## 22. Concurrency tests phải kiểm invariant chứ không dựa vào thứ tự threads

### 22.1. Tình huống

Kho có 5 sản phẩm. Hai requests đồng thời đều muốn giữ 4.

Kết quả hợp lệ:

- Tổng reservation quantity ≤ 5.
- `available >= 0`.
- Không có hai reservations thành công mỗi cái quantity 4.
- Không có ledger thành công mà stock không giảm tương ứng.
- Lỗi transient được retry/đối soát theo policy.

### 22.2. Dùng barrier để chạy cùng lúc

Một skeleton test:

```java
ExecutorService pool =
    Executors.newFixedThreadPool(2);

CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

Callable<Reservation> task1 = () -> {
    ready.countDown();
    go.await();
    return stockService.reserve(
        "tenant-test", "req-A", productId, 4
    );
};

Callable<Reservation> task2 = () -> {
    ready.countDown();
    go.await();
    return stockService.reserve(
        "tenant-test", "req-B", productId, 4
    );
};

Future<Reservation> f1 = pool.submit(task1);
Future<Reservation> f2 = pool.submit(task2);

ready.await();
go.countDown();

// Thu cả success/failure, không assume request nào thắng.
// Retry policy riêng có thể cần cho WriteConflict.
pool.shutdown();
```

Đây là skeleton; khi triển khai phải:

- Dùng timeout với `await()/get()` để tránh test treo.
- Bắt `ExecutionException` và phân loại nguyên nhân.
- Cleanup cả hai request IDs trong `finally`.
- Đảm bảo transactional service có retry logic khi transient conflicts.
- Assert final MongoDB state và sum reservations.
- Không dùng shared mutable Java objects giữa tasks.

### 22.3. Vì sao một lần test không chứng minh mọi race?

Concurrency bugs không phải lúc nào cũng xảy ra. Có thể chạy nhiều iterations trên test container, sử dụng fault injection có seed, quan sát invariant; nhưng không cố gây resource exhaustion trên cluster dùng chung.

Cần tách **độ đúng của atomic predicate/transaction** khỏi timing của scheduler.

## 23. Kiểm tra filter tenant trong test

### 23.1. Một user không được đọc/sửa tenant khác

Ví dụ:

```javascript
{ _id: "prod-A", tenantId: "tenant-A" }
{ _id: "prod-B", tenantId: "tenant-B" }
```

Integration tests:

- `findByIdAndTenantId("prod-A","tenant-A")` trả product.
- `findByIdAndTenantId("prod-A","tenant-B")` trả empty.
- `reserve("tenant-B", ..., "prod-A", 1)` thất bại.
- Product A vẫn giữ stock.
- Không có reservation mang tenant B trỏ product A.

### 23.2. Test ở controller còn cần authentication

Một path:

```text
/api/demo/tenants/tenant-A/products/...
```

không tự được coi là nguồn chứng thực tenant. Khi tích hợp Spring Security, xác thực principal/JWT/scope, map authorized tenant, test client tenant B không thể giả mạo path tenant A.

**Query có filter tenant** là hàng rào dữ liệu quan trọng nhưng không thay cho authorization. Đừng tin raw `tenantId` từ request mà không verify.

## 24. Controller test bằng MockMvc

### 24.1. Kích hoạt MockMvc

Dùng:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class ReservationApiIT {
    @Autowired MockMvc mvc;
    // @Container + @DynamicPropertySource MongoDB setup
    // tương tự StockServiceIT.
}
```

Với test thực, cần khai báo MongoDB Testcontainers/DynamicPropertySource cho context và dựng product fixtures trong cùng test database.

### 24.2. Test JSON invalid

```java
mvc.perform(
    post("/api/demo/tenants/tenant-test/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "sku": "",
              "priceCents": -1,
              "available": 5
            }
            """)
).andExpect(status().isBadRequest());
```

Spring MVC cần Bean Validation starter, `@Valid` và handler trả 400 cho validation errors. Với custom handler, không vô tình map mọi exceptions thành 500/409.

### 24.3. Test thiếu Idempotency-Key

```java
mvc.perform(
    post("/api/demo/tenants/tenant-test/products/"
         + productId + "/reservations")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":1}")
).andExpect(status().isBadRequest());
```

`@RequestHeader` mặc định required, nên thiếu header thường được Spring MVC xử lý thành 400. Nếu handler tùy biến, verify API contract vẫn đúng.

### 24.4. Test response data minimization

Không trả entity MongoDB trực tiếp trên mọi endpoint production nếu có internal metadata hoặc fields nhạy cảm. Demo create endpoint trả `Product` để đơn giản, nhưng production nên trả response DTO, có phân quyền và ẩn trường nội bộ.

## 25. Java Sync Driver thuần: biến thể không dùng Spring Data

Nếu project không dùng Spring Boot, vẫn có thể kiểm MongoDB với Java Sync Driver + JUnit + Testcontainers.

### 25.1. Khởi tạo client

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

try (MongoClient client =
         MongoClients.create(mongodbReplicaSetUri)) {

    MongoDatabase db =
        client.getDatabase("row465_driver_test");

    MongoCollection<Document> products =
        db.getCollection("products");

    // Tạo data bằng IDs/ngữ cảnh test riêng.
}
```

### 25.2. Atomic conditional update

```java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

var result = products.updateOne(
    and(
        eq("_id", "prod_123"),
        eq("tenantId", "tenant-test"),
        gte("available", 2)
    ),
    inc("available", -2)
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Out of stock or missing product"
    );
}
```

Raw driver không tự áp Spring `@Version`. Nếu cần version CAS, bổ sung predicate/update đúng type.

### 25.3. Transaction với `ClientSession`

```java
import com.mongodb.client.ClientSession;

try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {
        products.updateOne(
            session,
            and(
                eq("_id", "prod_123"),
                gte("available", 2)
            ),
            inc("available", -2)
        );

        reservations.insertOne(
            session,
            new Document("_id", "request-123")
                .append("productId", "prod_123")
                .append("quantity", 2)
        );

        return null;
    });
}
```

Đoạn này minh họa **API**, chưa đủ production: phải kiểm `matchedCount`, tenant, request payload, transaction options, duplicate IDs và reconcile khi commit unknown. Nếu update match 0 nhưng vẫn insert reservation, invariant bị phá. Trong code thật phải throw/abort nếu `matchedCount!=1` trước khi insert.

### 25.4. Mối quan hệ của tests

Có thể dùng cùng Testcontainers MongoDB uri cho cả:

- Spring repository integration suite.
- Java driver integration suite.

Không tự tạo 10 MongoDB containers cho 10 test methods nếu CI bị giới hạn resources. Tái dùng container theo suite với database/test data isolation rõ; không chia sẻ test state theo thứ tự chạy.

## 26. Thực hành riêng trong `mongosh`: hiểu dữ liệu mà tests bảo vệ

### 26.1. Quy định an toàn

- Chạy trên MongoDB test database đã được phép.
- Không dùng production data, admin/config/local databases.
- Tạo collection riêng bằng runId.
- Không chạy `dropDatabase()` hoặc `deleteMany({})` trên collection dùng chung.
- Không thay cluster/replica config/FCV.
- Cleanup theo exact `_id` + `runId`.
- Lệnh dưới là **mô hình dữ liệu và assertions**, không phải thay thế JUnit integration suite.

### 26.2. Tạo namespace test

```javascript
const lab = db.getSiblingDB("mongo_java_row465_lab");
const runId = "row465_" + new ObjectId().toHexString();
const productCollection = "products_" + runId;
const reservationCollection = "reservations_" + runId;

for (const name of [productCollection, reservationCollection]) {
  if (lab.getCollectionNames().includes(name)) {
    throw new Error("Namespace already exists");
  }
}

lab.createCollection(productCollection);
lab.createCollection(reservationCollection);

const products = lab.getCollection(productCollection);
const reservations = lab.getCollection(reservationCollection);

printjson({
  database: lab.getName(),
  runId,
  productCollection,
  reservationCollection
});
```

### 26.3. Tạo unique index và data

```javascript
products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "tenant_sku_unique",
    unique: true
  }
);

const tenantId = "tenant_" + runId;
const productId = "prod_" + runId;

products.insertOne({
  _id: productId,
  runId,
  tenantId,
  sku: "SKU-465",
  priceCents: NumberLong("125000"),
  available: NumberInt(10),
  version: NumberLong("1")
});
```

### 26.4. Kiểm type raw BSON

```javascript
const typed = products.aggregate([
  { $match: { _id: productId, runId } },
  {
    $project: {
      priceType: { $type: "$priceCents" },
      availableType: { $type: "$available" },
      versionType: { $type: "$version" }
    }
  }
]).toArray()[0];

printjson(typed);

if (typed.priceType !== "long" ||
    typed.availableType !== "int" ||
    typed.versionType !== "long") {
  throw new Error("Unexpected BSON types");
}
```

### 26.5. Giữ hàng có điều kiện và kiểm kết quả

```javascript
const requestId = "reserve_" + runId;
const qty = 3;

const changed = products.updateOne(
  {
    _id: productId,
    runId,
    tenantId,
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      version: NumberLong("1")
    }
  }
);

if (changed.matchedCount !== 1) {
  throw new Error("Insufficient stock or conflict");
}

printjson(products.findOne({
  _id: productId, runId
}));
```

Trong lab, transaction/idempotency không được triển khai ở đoạn này; đây chỉ là atomic update của **một document**. Đừng dùng nó như một đảm bảo rằng reservation ledger và stock thay đổi atomically.

### 26.6. Mô phỏng ledger cho request ID

```javascript
reservations.updateOne(
  { _id: requestId, runId },
  {
    $setOnInsert: {
      tenantId,
      productId,
      quantity: NumberInt(qty),
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Lần gọi upsert thứ hai với cùng `requestId` không tạo document mới. **Nhưng** nếu code trừ stock trước bước này mỗi lần retry, stock vẫn bị trừ thêm. Đây là lý do business flow cần transaction + idempotency check **trước** decrement, như phần `StockService`.

### 26.7. Cleanup theo ownership

```javascript
const ownedProducts = products.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

const ownedReservations = reservations.find(
  { _id: requestId, runId }, { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedProducts: ownedProducts.length,
  ownedReservations: ownedReservations.length,
  runId
});

for (const item of ownedReservations) {
  reservations.deleteOne({
    _id: item._id, runId
  });
}

for (const item of ownedProducts) {
  products.deleteOne({
    _id: item._id, runId
  });
}

printjson({
  productsRemaining: products.countDocuments({ runId }),
  reservationsRemaining:
      reservations.countDocuments({ runId })
});
```

Không xóa toàn database. Collections/index còn lại có thể do test environment quản lý theo prefix/owner/retention sau khi xác minh.

## 27. Test index plan và performance

### 27.1. Query shape

```javascript
db.row465_products.find({
  tenantId: "tenant-test",
  sku: "SKU-A"
});
```

Với compound unique index `{tenantId:1,sku:1}`, query có thể dùng index. Nhưng plan phụ thuộc dataset/statistics và server version.

### 27.2. `explain("executionStats")`

```javascript
db.row465_products.find({
  tenantId: "tenant-test",
  sku: "SKU-A"
}).explain("executionStats");
```

Các thông số cần xem:

- `winningPlan` và index name.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- Filter/selectivity.
- Sort stage có index hỗ trợ không.
- p95/p99 trên workload thực.

Một collection test chỉ có vài documents có thể được planner chọn COLLSCAN vì rẻ hơn; không coi một `explain` nhỏ là benchmark production.

### 27.3. Test data size

Performance tests cần dataset có:

- Cardinality tương tự.
- Hot tenants/products.
- Tỉ lệ writes/reads.
- Query filter combinations.
- Document size và index density.
- Concurrent reservations.
- Replication topology và latency.

Unit/integration tests nhỏ kiểm **correctness**; load tests đo **performance**. Không trộn hai mục tiêu bằng cách bắt mọi JUnit test phải đáp ứng một thời hạn 10 ms trên laptop.

## 28. Kiểm thử failure windows và retries

### 28.1. Một transaction có thể commit dù response bị mất

```text
T0: reserve(tenant, requestId=R1)
T1: Product stock decremented
T2: Reservation R1 inserted
T3: Transaction commit succeeds
T4: Commit response lost
T5: Application sees UnknownTransactionCommitResult
```

Nếu application chạy lại business command với **requestId khác**, có thể trừ thêm stock. Nếu giữ cùng request ID và có reconciliation, ledger là bằng chứng giúp xác định command đã có.

### 28.2. Phân biệt hai error labels

| MongoDB error label | Ý nghĩa | Chiến lược |
| --- | --- | --- |
| `TransientTransactionError` | Transaction body lỗi tạm, có thể retry toàn bộ | Retry whole transaction theo driver policy |
| `UnknownTransactionCommitResult` | Client chưa biết commit đã thành công chưa | Retry **commit cùng transaction/session** khi còn có thể; sau đó reconcile |

Đừng catch mọi `MongoException` rồi gọi lại `reserve` vô hạn không budget.

### 28.3. Retryable writes không thay idempotency HTTP

`retryWrites=true` giúp driver retry những writes hỗ trợ trong cùng logical operation. Hai HTTP requests mới từ client có thể tạo hai logical MongoDB operations khác nhau. Vì vậy cần `Idempotency-Key` ở API.

### 28.4. Fault injection không nên phá cluster

Có thể test application khi:

- Repository mock ném exception sau bước giả định commit.
- Adapter trả timeout nhưng một record đã tồn tại.
- Request bị gửi hai lần với same key.
- Một event/outbox publish thành công nhưng ACK mất.
- Batch insert thành công một phần.
- Worker shutdown giữa side effect và checkpoint.

Không thực hiện `rs.stepDown()`, kill MongoDB primary hoặc ngắt mạng trên production để chứng minh code xử lý lỗi.

### 28.5. Khi nào cần reconciliation worker?

Nếu commit result unknown và application đã đóng session, hoặc external system trả kết quả chưa rõ:

- Ghi durable `NEEDS_RECONCILIATION` state.
- Đọc command/reservation theo request ID.
- So tenant/product/quantity/result.
- Đối chiếu durability (write/read concern).
- Không tạo request ID mới để “thử lại”.
- Alert nếu quá timeout budget hoặc conflict.

## 29. Schema evolution và kiểm thử hồi quy

### 29.1. Thêm field mới

Giả sử Product v2 thêm `currency`:

```javascript
{
  priceCents: NumberLong("125000"),
  currency: "VND"
}
```

Nếu application cũ không ghi currency và validator mới lập tức yêu cầu field, các writes cũ bị từ chối.

Quy trình:

1. Reader hiểu missing `currency` theo rule đã thống nhất.
2. Deploy writers ghi currency.
3. Audit/backfill legacy docs.
4. Bật validator warn/moderate.
5. Khi tất cả writers tương thích và dữ liệu sạch, chuyển strict.
6. Bổ sung regression tests cho old/new schema.
7. Chỉ loại fallback sau thời gian rollback plan.

### 29.2. Không tự gán default thiếu ý nghĩa

Một document không có `currency` không tự chứng minh đơn vị là VND. Cần source of truth hoặc business rule đã được xác nhận trước khi backfill.

### 29.3. Test backward compatibility

Nếu code cũ đọc BSON Int32 còn code mới ghi Int64:

- Test both types trong fixtures.
- Kiểm mapping/overflow.
- Kiểm DTO/JSON conversions.
- Nếu validator chỉ cho Int64, backfill Int32 trước.
- Đảm bảo rollback code cũ đọc được data mới.

Không tự coi số có cùng value là cùng BSON type.

## 30. Spring Data slicing vs full context

### 30.1. `@DataMongoTest`

`@DataMongoTest` tập trung vào MongoDB repositories/mapping components; thích hợp test query/index/codec với real MongoDB test connection. Nhưng:

- Có thể không load `StockService` và controller mặc định.
- Transaction manager/custom config có thể cần import.
- Phải cung cấp connection URI/test container tương ứng.
- Không tự giả định embedded MongoDB được bật.

### 30.2. `@SpringBootTest`

Load nhiều ứng dụng hơn:

- Controller/service/repository configuration.
- `MongoTransactionManager` và `@Transactional`.
- Bean validation.
- Integration với real MongoDB.
- Có thể kết hợp `@AutoConfigureMockMvc`.

Đổi lại thời gian khởi động và resources cao hơn. Nên giữ test classes/suites tối ưu, không tạo context mới không cần thiết cho mỗi method.

### 30.3. `@Transactional` trên test method có thể tạo hiểu nhầm

Test frameworks có cơ chế test-managed transaction ở một số contexts. Nếu test itself nằm trong transaction chưa commit, application thread khác có thể không thấy fixtures. Với MongoDB driver, transaction support/topology và session propagation phải được hiểu rõ.

Trong các test của bài, **không gắn `@Transactional` lên toàn test method** trừ khi đang chủ động kiểm behavior đó. Để service tự mở transaction; assertions đọc sau method return.

## 31. Test data isolation và cleanup

### 31.1. Không dùng fixed `_id` chung khi parallel tests

Sai:

```java
products.insert(new Product(
    "product-1", "test", "SKU-1", 100L, 10
));
```

trong nhiều test chạy song song; dễ nhận DuplicateKey và pollution.

Dùng:

```java
String runId = "row465_" + UUID.randomUUID();
String productId = "prod_" + runId;
```

Cũng phải bảo đảm `sku` và `tenantId` phù hợp unique constraint, và lưu IDs để cleanup.

### 31.2. Testcontainers per suite vs per test

| Chiến lược | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| Một container per test | Cô lập rất mạnh | Chậm và tốn Docker |
| Một container per class | Setup hợp lý | Cần cleanup/test isolation |
| Một container per suite | Nhanh hơn | Đồng bộ lifecycle và parallelization khó |
| Database riêng per test | Query/schema/index độc lập | Tăng namespace/initialization cost |
| Random IDs trong shared test DB | Đơn giản | Tests có thể ảnh hưởng global counts |
| Shared staging DB | Gần topology thật | Nguy cơ pollution; cần quyền/ownership |

Trong CI, ưu tiên ephemeral containers + namespace ngẫu nhiên. Test kết quả không được phụ thuộc thứ tự thực thi.

### 31.3. Cleanup không che lỗi gốc

`@AfterEach` nên dọn exact IDs ngay cả khi assertion fail. Nhưng nếu cleanup ném exception, nó có thể che nguyên nhân fail ban đầu.

Có thể collect cleanup failures riêng qua logs/test framework, và trong Testcontainers DB ephemeral để container tự hủy. Không tạo script `deleteMany({})` trên một database có thể dùng chung.

### 31.4. Không log data nhạy cảm trong failures

Test logs nên có test case, namespace, runId, expected/actual BSON types và errors redacted. Không dump credentials, full customer documents hoặc payment tokens.

## 32. Chạy kiểm thử trong CI

### 32.1. Một pipeline khái quát

```text
Checkout
   |
Resolve dependencies with locked versions
   |
Compile Java
   |
Run fast unit tests
   |
Start Testcontainers MongoDB replica set
   |
Run Spring Data integration tests
   |
Run API tests
   |
Collect sanitized reports
   |
Stop/remove ephemeral resources
   |
Package artifact if all gates pass
```

### 32.2. Trên developer machine

Lệnh minh họa cho người học:

```bash
mvn test
```

Hoặc:

```bash
./gradlew test
```

Các lệnh này **không được chạy bởi worker ở STEP 4**. Chỉ chạy trong môi trường project đã khai báo dependency versions hợp lệ và Docker/container runtime sẵn có.

### 32.3. Những gì CI cần

- Docker daemon/container runtime được cho phép.
- Quyền kéo image MongoDB version được pin.
- Network nội bộ để test container host/driver truy cập.
- Cấp đủ CPU/RAM/disk.
- Không dùng production credentials.
- Các test tránh phụ thuộc vào wall-clock hoặc kết quả theo thứ tự.
- Cleanup khi job bị hủy.
- Log JUnit test failures mà không lộ secrets.
- Cache dependencies phù hợp.
- Một test matrix phù hợp version MongoDB đang dùng và target upgrade.

### 32.4. Container không khởi động là lỗi môi trường

Nếu Testcontainers báo không tìm thấy Docker environment:

- Kiểm Docker/Podman provider hỗ trợ.
- Kiểm user có quyền truy cập runtime.
- Kiểm image pull, proxy, registry policy.
- Kiểm Docker Desktop/WSL/CI runner health.
- Không sửa test thành mock MongoDB rồi tuyên bố integration tests đã pass.

Nếu không thể chạy container trong CI, dùng MongoDB test cluster được cấp riêng với URI/quyền thích hợp và test isolation tương đương.

## 33. Quan sát ứng dụng Java/MongoDB

### 33.1. Metrics thiết yếu

- HTTP request rate/latency/error theo endpoint.
- MongoDB command latency và errors.
- Connection pool waits/timeouts.
- Transaction begin/commit/abort/retry.
- Duplicate key error rate.
- Validation failure rate.
- Inventory conflicts/out-of-stock.
- Idempotency reused-key/conflict events.
- Unknown commit outcomes.
- Replica set election/replication lag.
- p95/p99 query và document examined.
- JVM heap/GC/thread pools.

### 33.2. Một log minh họa

```json
{
  "event": "reservation_attempt",
  "requestId": "req_...",
  "tenantScope": "tenant-demo",
  "productId": "prod_...",
  "quantity": 2,
  "outcome": "CONFIRMED",
  "transactionDurationMs": 24,
  "duplicateRequest": false
}
```

Trong production, cân nhắc hash request ID hoặc hạn chế log identity theo data retention/privacy. Không log full MongoDB URI, secrets hay toàn bộ customer payload.

### 33.3. Sức khỏe API khác sức khỏe consumer

Nếu thêm change stream/outbox worker:

- API có thể khỏe nhưng CDC consumer lag.
- Consumer có thể chạy nhưng checkpoint không tiến.
- Readiness/liveness nên phản ánh role của service.
- Cần alert trên oplog history window và failed reconciliations.
- Một "connected=true" không chứng minh projections đã nhất quán.

## 34. Những lỗi tích hợp phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| Test transaction báo standalone | URI tới standalone MongoDB | Dùng replica set Testcontainers URL |
| `@Transactional` không rollback | Thiếu MongoTransactionManager, self-call, session mismatch | Kiểm bean/proxy, integration rollback test |
| Duplicate sku test vẫn pass cả hai insert | Unique index chưa tạo | Kiểm `getIndexes()`/auto-index-creation |
| Product version không tăng như kỳ vọng | Raw update bỏ version hoặc mapping khác | Kiểm @Version vs raw driver behavior |
| Data price đọc thành Integer/Double | Mapper/JSON conversion | Assert BSON type và DTO |
| JSON validation không chạy | Thiếu starter-validation/@Valid | MockMvc negative test |
| Transaction write conflict | Hot product/concurrent writes | Retry bounded, version/CAS, partition hot keys |
| DuplicateKey khi retry request | Same request race hoặc payload conflict | Read ledger/compare identity |
| Hết stock nhưng đã có reservation | Thiếu transaction hoặc error handling | Atomic write+ledger rollback test |
| Timeout sau commit | Outcome unknown | Retry commit/reconciliation; không blind reserve |
| Spring app không kết nối DB | URI/credentials/TLS/network/server selection | Log sanitized connection metadata |
| Testcontainers không start | Docker runtime/image/network | CI provider/daemon |
| `@DataMongoTest` không load service | Slice context chỉ chứa data layer | Import/config hoặc dùng SpringBootTest |
| Test phụ thuộc test trước | Shared IDs, global count, no cleanup | Random keys/isolated DB |
| Test pass local nhưng fail CI | Different MongoDB version/timing/capacity | Pin versions và loại sleeps |
| Query chậm trên dataset lớn | Index/plan/cardinality | Explain/metrics trên data đại diện |
| BSON ObjectId vs String mismatch | ID converter/annotation | Raw BSON test |
| `$elemMatch` bị thay bằng dot filters | Cross-element false positive | Array regression fixtures |
| Invalid schema insert thành công | Validator action warn/off | Kiểm collectionInfo/options |
| Field null/missing bị nhập làm một | DTO/mapping không giữ field presence | API-to-BSON tests |
| Multiple tenants đọc chéo | Thiếu tenant filter/auth | Security negative tests |
| Data migration làm app cũ lỗi | Strict validator trước khi tất cả writers cập nhật | Expand/migrate/contract |
| Index được tạo trên startup production | Auto index creation bật sai môi trường | Tách migration/DDL |
| Mock returns success nhưng DB thực reject | Unit test thay integration test | Testcontainers suite |

## 35. Quy trình triển khai production với confidence từ tests

### 35.1. Trước deployment

- Chốt MongoDB Server/FCV, driver/Spring Boot compatibility.
- Kiểm tất cả indexes và validators trên target database.
- Audit duplicated tenant+sku và legacy BSON types.
- Kiểm data retention, backup/PITR và restore drills.
- Xác định API ownership/auth scope.
- Kiểm connection pool và write/read concerns.
- Kiểm transaction error/retry behavior theo driver.
- Có feature flags và SLO/metrics.
- Chạy automated tests trên MongoDB test topology tương đương.

### 35.2. Deploy từng giai đoạn

```text
Schema/contract design
      |
      v
Create compatible indexes / data migration
      |
      v
Deploy reader compatible with old/new shape
      |
      v
Deploy writer new shape (canary)
      |
      v
Backfill legacy data
      |
      v
Validator moderate -> strict
      |
      v
Rollout wider traffic with monitoring
      |
      v
Remove compatibility code after rollback window
```

Không ép tất cả app instances đổi schema trong một deployment không kiểm soát. Nếu DB schema validator strict chặn old writer, rollback code có thể gây outage.

### 35.3. Monitoring sau rollout

- Lỗi 409 do stock conflict vs do idempotency key.
- Lỗi 121 document validation.
- E11000 duplicate index.
- Transaction commit retries và unknown outcomes.
- Replication lag và disk pressure.
- Product version distribution.
- Reservation ledger consistency.
- API p95/p99.
- Retry rate từ clients.

Nếu một chỉ số tăng bất thường, dừng rollout theo runbook; không tự hạ durability hoặc bỏ unique constraint để che lỗi.

### 35.4. Rollback và phục hồi dữ liệu

Rollback Java service **không hoàn tác** documents đã ghi hoặc reservations đã tạo. Có thể cần:

- Giữ schema backward compatibility.
- Reconcile reservations trước khi release tồn kho.
- Không xóa ledger của command chưa xác định.
- Restore backup/PITR theo chính sách nếu có corruption.
- Tạo compensating events khi external systems đã tiêu thụ business event.
- Giữ audit log cho mọi mutation.

## 36. Checklist thực hành theo thứ tự

1. Chọn Spring Boot/driver/Testcontainers versions tương thích; thay placeholders.
2. Tạo project Java 17 với Spring Boot starter web/data-mongodb/validation/test.
3. Tạo Product và Reservation entities.
4. Định nghĩa repositories.
5. Cấu hình MongoTransactionManager.
6. Cài StockService với atomic filter `available >= quantity` và reservation insert trong transaction.
7. Cài controller/DTO và error mapping.
8. Tạo Testcontainers MongoDB replica set và DynamicPropertySource.
9. Viết tests insert/read BSON, tenant/unique, giữ hàng, insufficient stock, idempotent retry.
10. Viết transaction rollback test và kiểm error paths.
11. Viết API invalid payload test và authentication/tenant negative tests.
12. Viết array/nullable/schema validation tests trong namespace riêng.
13. Thêm concurrency/fault injection và reconciliation tests.
14. Xem `explain` cho queries quan trọng.
15. Cấu hình CI chạy JUnit và lưu báo cáo test đã ẩn secrets.
16. Đo SLO trên dữ liệu đại diện rồi mới deploy canary.
17. Giữ rollback/data recovery plan và observability.

Đây là checklist **người học áp dụng khi xây dự án**, không phải lượt Content QA tài liệu. STEP 4 chỉ tạo bài viết và xác minh file đã lưu.

## 37. Bài tập nâng cao

### Bài A — CRUD cơ bản

Tạo `GET /products/{id}` và `PUT /products/{id}` với tenant scope. Viết integration tests cho product tồn tại, không tồn tại, tenant khác và update version.

### Bài B — Unique index

Hai products cùng tenant+sku được insert đồng thời. Xác nhận chỉ một document có key đó; phân biệt E11000 với lỗi connection/validation.

### Bài C — Money/BSON

Tạo product giá `9_007_199_254_740_993L` và kiểm Int64 round-trip từ Java tới MongoDB. Nếu client JavaScript gửi JSON Number, nguy cơ gì?

### Bài D — Bean Validation

Gửi API request có `priceCents:-1`, `sku:""`, `available:-2`. Test HTTP 400, database không có record mới.

### Bài E — Atomic reservation

Kho có 5, hai requests mỗi request giữ 4. Kiểm `available >= 0`, tổng reservations ≤5 và không tạo ledger mà không giữ stock.

### Bài F — Idempotency

Gửi hai lần cùng requestId/payload: không trừ stock thêm. Gửi cùng requestId nhưng payload khác: conflict. Sau commit timeout, dùng ledger để đối soát.

### Bài G — Optimistic locking

Hai entity snapshots version 4 cùng cập nhật price. Kiểm một stale save không ghi đè version mới. So với raw driver update không có version filter.

### Bài H — Null/missing

Tạo collection `profiles` có field nickname missing, null, empty String. Kiểm MongoDB query `{nickname:null}`, `$exists`, `$type` và Java `containsKey`.

### Bài I — Array `$elemMatch`

Tạo order có hai lines: A quantity 1 và B quantity 10. Viết query chỉ trả order nếu **cùng line A** quantity ≥5; test dot notation query sai.

### Bài J — Schema validator

Tạo collection test có `bsonType:"long"` cho price. Insert valid Long, invalid String, missing/Null; kiểm error 121 và readback.

### Bài K — Transaction rollback

Inject exception sau product decrement nhưng trước ledger insert. Kiểm toàn transaction rollback và source available không đổi.

### Bài L — Commit unknown

Thiết kế fault injection khi commit success nhưng response mất. Dự kiến API trả gì? Khi nào retry commit cùng session, khi nào reconcile requestId?

### Bài M — Performance

Một API list products lọc tenant, status, sort updatedAt. Chọn compound index và chứng minh bằng explain trên dataset đủ lớn.

### Bài N — API security

Tenant A thử reserve product B bằng productId đoán được. Kiểm controller/service/DB filters và authorized tenant resolution.

### Bài O — Testcontainers CI

Viết CI pipeline chạy unit tests rồi integration tests với container replica set. Mô tả cách xử lý Docker daemon unavailable và image pinning.

### Bài P — Schema evolution

Thêm `currency` required vào Product. Lập kế hoạch reader compatibility, writer rollout, backfill, validator warn/moderate/strict và negative tests.

### Bài Q — Change stream/outbox

Thêm event `ReservationCreated` sau commit và một worker gửi message. Viết tests dedup, ordering, lost ACK, restart/resume token và cleanup.

### Bài R — Bulk import

Nhập 100 products với 3 duplicate SKUs và 2 invalid prices. Kiểm ordered/unordered bulk behavior, partial success và retry theo stable IDs.

### Bài S — Disaster recovery

MongoDB restore lùi 15 phút trong khi service khác giữ reservations mới hơn. Đề xuất reconciliation ledger, event replay và alert ngăn oversell.

### Bài T — ADR

Viết Architecture Decision Record chọn Spring Data MongoDB so với Java Sync Driver thuần cho ứng dụng đặt chỗ, dựa trên team skill, code complexity, transaction semantics, testability và operational cost.

## 38. Tài liệu tham khảo chính thức

### MongoDB và Java

- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — kết nối, BSON, CRUD, transactions.
- [MongoDB Java Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — phiên bản driver, Java runtime và server.
- [MongoDB CRUD Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/) — insert/find/update/delete.
- [MongoDB Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — sessions, callback/core APIs và retry labels.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Int32/Int64/Decimal128/ObjectId/Date.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — `$jsonSchema`, validation levels/actions.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness/null/compound rules.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability và replication.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — write retries và giới hạn.
- [Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — CDC nếu thêm outbox consumer.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — kiểm query execution plan.

### Spring

- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — repositories, MongoTemplate, mapping, optimistic locking, transactions.
- [Spring Boot Data Access / MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — auto-configuration và properties.
- [Spring Framework Test](https://docs.spring.io/spring-framework/reference/testing/) — integration test context.
- [Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/) — `@SpringBootTest`, `MockMvc`, test slices.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/) — proxy và transaction lifecycle.

### JUnit và Testcontainers

- [JUnit User Guide](https://junit.org/junit5/docs/current/user-guide/) — Jupiter, parameterized tests và lifecycle.
- [Testcontainers Java](https://java.testcontainers.org/) — container-based integration testing.
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — `MongoDBContainer` và replica set URL theo phiên bản.
- [Spring Boot Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — tích hợp với Spring Boot.

**Version note:** Một số URLs có thể thay đổi theo docs version. MongoDB server features, Spring Boot 3/4, Spring Data major versions, Testcontainers 1/2 và Java Driver releases có compatibility khác nhau. Chốt dependency versions theo matrix chính thức, không trộn API imports/cách cấu hình của các major releases.

## 39. Kết luận

Một ứng dụng Java tích hợp MongoDB đáng tin không dừng ở lệnh `repository.save()`.

1. **Chọn API phù hợp**: Java Sync Driver cho kiểm soát BSON/commands trực tiếp; Spring Data cho mapping/repositories/template và transaction integration.
2. **Bắt đầu từ invariants**: tenant ownership, unique SKU, giá BSON Int64, available không âm, request ID không lặp.
3. **Dùng atomic conditional update** khi trừ stock và **transaction ngắn** khi cần ghi nhiều MongoDB documents cùng một nghiệp vụ.
4. **Không quên idempotency**: timeout/HTTP retry có thể giao lại cùng business request; retry với request ID mới dễ tạo side effect trùng.
5. **Đặt ràng buộc ở MongoDB**: unique index và `$jsonSchema` hỗ trợ bảo vệ tất cả writers, không chỉ một controller.
6. **Kiểm bằng MongoDB thực**: JUnit 5 + Testcontainers replica set mới chứng minh được index, BSON type, transaction rollback, filter và query semantics.
7. **Giữ test isolation**: namespace/IDs ngẫu nhiên, cleanup có phạm vi, không đụng dữ liệu thật và không phụ thuộc test order.
8. **Tách correctness và performance**: integration tests chứng minh nghiệp vụ; explain/load test chứng minh index/SLO trên workload đại diện.
9. **Quan sát cả failure paths**: duplicate key, validation, transaction transient/unknown commit, network timeout và reconciliation.
10. **Tiến hóa có kiểm soát**: khi đổi schema/index, deploy writers/readers tương thích, backfill, siết validation theo giai đoạn và giữ rollback plan.

**Nguyên tắc cốt lõi:** hãy biến mỗi bất biến quan trọng của ứng dụng thành một **kiểm thử tự động trên MongoDB Server thật**, bổ sung ràng buộc database và protocol phục hồi thích hợp. Khi tất cả điều đó cùng hoạt động, integration Java/Spring Data không chỉ “chạy được” mà còn có thể tiếp tục đúng khi request lặp, dữ liệu sai, nhiều threads cạnh tranh, transaction rollback và môi trường được nâng cấp.
