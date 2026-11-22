# R2DBC và các thư viện Spring Data reactive trong kiến trúc tổng thể

## 1. Mục tiêu và bối cảnh

Spring WebFlux xây dựng tầng HTTP dựa trên `Mono`, `Flux` và I/O không chặn. Tuy nhiên, một endpoint trả Mono vẫn có thể chặn event-loop nếu service bên dưới gọi JDBC, JPA hoặc một SDK đồng bộ. Kiến trúc reactive cần được xem **từ HTTP, service, data client, driver đến database**, chứ không chỉ ở kiểu trả về của controller.

**R2DBC** (Reactive Relational Database Connectivity) là specification cho truy cập cơ sở dữ liệu quan hệ bằng Reactive Streams. **Spring Framework R2DBC** cung cấp `DatabaseClient`, kết nối và transaction infrastructure. **Spring Data R2DBC** bổ sung entity mapping, `R2dbcEntityTemplate` và repository. Các module Spring Data reactive khác hỗ trợ MongoDB, Redis, Elasticsearch, Cassandra hoặc một số datastore khác, với mức độ tính năng và semantics không giống nhau.

Học xong bài này, bạn cần:

1. Phân biệt JDBC/JPA với R2DBC và Spring Data R2DBC.
2. Biết chọn `ReactiveCrudRepository`, `R2dbcEntityTemplate` hay `DatabaseClient`.
3. Hiểu entity mapping, query, transaction Reactor Context và optimistic locking.
4. Phối hợp R2DBC với WebFlux, WebClient, cache, document DB, search index và message broker.
5. Thiết kế đúng ranh giới transaction khi có nhiều datastore.
6. Có ví dụ Spring Boot Java 17+ với R2DBC H2, REST API, transaction và kiểm thử.

## 2. Bức tranh kiến trúc

~~~text
Browser / API client
         |
         v
Spring WebFlux Controller -- Mono / Flux
         |
         v
Application Service (validation / domain logic)
         |
         +----------------------+-----------------+
         |                      |                 |
         v                      v                 v
Spring Data R2DBC      Spring Data MongoDB   Spring Data Redis
         |                      |                 |
         +-- Reactive repository +                 |
         +-- R2dbcEntityTemplate |           ReactiveRedisTemplate
         +-- DatabaseClient      |                 |
         |                      v                 v
         v                 Mongo reactive       Lettuce
   ConnectionFactory         driver               |
         |                      |                 v
    R2DBC driver               MongoDB            Redis
         |
         v
 PostgreSQL / H2 / SQL
         |
  R2DBC transaction
~~~

Bên ngoài các nhánh này còn có message broker, search index, metrics và tracing. Việc cùng sử dụng Mono/Flux **không có nghĩa** một transaction SQL sẽ tự động bao phủ Redis, MongoDB hoặc Kafka.

Một data flow tốt giữ nguyên publisher từ repository đến controller:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> get(@PathVariable long id) {
    return productService.findById(id);
}
~~~

~~~java
public Mono<Product> findById(long id) {
    return productRepository.findById(id);
}
~~~

WebFlux sẽ subscribe publisher để gửi response. Service không tự gọi `subscribe()` hoặc `block()` chỉ để kích hoạt query.

## 3. JDBC, JPA, R2DBC và Spring Data R2DBC

| Công nghệ | Bản chất | Kiểu I/O/API | Điểm nổi bật |
| --- | --- | --- | --- |
| JDBC | API chuẩn truy vấn SQL trong Java | API blocking | DataSource, Connection, PreparedStatement |
| Spring JDBC | Abstraction trên JDBC | Blocking | JdbcTemplate, JdbcClient |
| JPA/Hibernate | ORM và persistence context | Chủ yếu blocking | EntityManager, JpaRepository, lazy loading |
| R2DBC SPI | Reactive API cho SQL | Publisher/non-blocking tùy driver | ConnectionFactory, Connection |
| Spring Framework R2DBC | SQL fluent client, transaction, exception translation | Reactive | DatabaseClient, R2dbcTransactionManager |
| Spring Data R2DBC | Entity mapping và repository | Reactive | R2dbcEntityTemplate, ReactiveCrudRepository |

Điểm không được nhầm:

- Bọc JDBC bằng `Mono.fromCallable` rồi chạy trên `Schedulers.boundedElastic()` chỉ **cô lập blocking work** sang thread pool; nó không biến JDBC thành giao thức non-blocking.
- R2DBC không phải “JPA reactive”. Spring Data R2DBC không có Hibernate EntityManager, dirty checking hay lazy relationship loading kiểu JPA.
- `spring.jpa.hibernate.ddl-auto` không phải cơ chế tạo bảng cho Spring Data R2DBC. Cần schema.sql hoặc migration.
- Reactor type chỉ là một phần mô hình. Nếu query SQL chậm, pool cạn connection hoặc thiếu index, reactive không tự khắc phục được.

**Khi nào nên cân nhắc R2DBC?** Khi ứng dụng có lượng lớn tác vụ I/O đồng thời, đã dùng WebFlux, driver database có hỗ trợ tốt và workload phù hợp với mô hình reactive. Nếu ứng dụng hiện tại dùng JPA với các quan hệ phức tạp và tải không cao, chi phí chuyển đổi có thể lớn hơn lợi ích; hãy đo trước.

## 4. ConnectionFactory, driver và cấu hình Boot

JDBC có `DataSource`; R2DBC có `ConnectionFactory`. Một ConnectionFactory tạo R2DBC Connection thông qua driver. Spring Boot cấu hình nó qua `spring.r2dbc.*`.

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/inventory
spring.r2dbc.username=inventory_app
spring.r2dbc.password=\${INVENTORY_DB_PASSWORD}
~~~

Chuỗi `\${INVENTORY_DB_PASSWORD}` là cơ chế placeholder của Spring cho biến môi trường, không phải một mật khẩu thực. Không commit credential vào source.

Một số lưu ý:

- URL R2DBC bắt đầu bằng `r2dbc:`, khác với `jdbc:`.
- Cần dependency driver R2DBC tương ứng với H2/PostgreSQL/DB mục tiêu.
- Spring Boot tự xác định driver từ R2DBC Connection Factory discovery, không nhất thiết cần driver-class-name.
- Nếu có ConnectionFactory, JDBC DataSource auto-configuration thông thường có thể back off.
- Chỉ có một ứng dụng dùng R2DBC không có nghĩa đã cấu hình sẵn một JDBC DataSource cho Flyway hoặc Liquibase.
- Driver không bảo đảm mọi tính năng JDBC đều có một tương đương R2DBC.

Sơ đồ trách nhiệm:

~~~text
Repository / Template / DatabaseClient
              |
              v
      ConnectionFactory
              |
              v
       R2DBC driver
              |
              v
     Database connections
              |
              v
        SQL database
~~~

Driver và pool phải được chọn theo khả năng hỗ trợ database version, TLS, data types, generated keys, transaction và timeout.

## 5. Ba tầng Spring API: Repository, Template và SQL

Chọn abstraction dựa trên nhu cầu; không nhất thiết mọi thao tác đều phải dùng raw SQL.

### 5.1. ReactiveCrudRepository

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByStockLessThan(int stock);

    Mono<Product> findByName(String name);
}
~~~

Repository có những method như:

| Method | Kết quả |
| --- | --- |
| `findById(id)` | `Mono<Product>`, empty khi không có |
| `findAll()` | `Flux<Product>` |
| `save(product)` | `Mono<Product>` |
| `deleteById(id)` | `Mono<Void>` |
| `existsById(id)` | `Mono<Boolean>` |
| `count()` | `Mono<Long>` |

Thư viện tạo implementation từ interface và mapping metadata. Query method thích hợp cho CRUD đơn giản, finder có điều kiện và tên method đọc được.

### 5.2. R2dbcEntityTemplate

~~~java
Flux<Product> lowStock =
    template.select(Product.class)
        .matching(
            Query.query(
                Criteria.where("stock").lessThanOrEquals(5)
            )
        )
        .all();
~~~

Template hỗ trợ query động, criteria, insert/update/delete theo entity và mapping metadata. Các terminal như `all()` trả Flux, `one()` hoặc `first()` trả Mono. `one()` yêu cầu tối đa một hàng; nếu query trả nhiều hàng có thể phát lỗi về số lượng kết quả.

### 5.3. DatabaseClient

~~~java
Mono<Integer> currentStock = databaseClient
    .sql("SELECT stock FROM products WHERE id = :id")
    .bind("id", 42L)
    .map((row, metadata) ->
        row.get("stock", Integer.class)
    )
    .one();
~~~

`DatabaseClient` thuộc `org.springframework.r2dbc.core`; nó quản lý statement, connection lifecycle, lỗi và map row với SQL do bạn viết. Phù hợp SQL join, projection hoặc query tối ưu cụ thể.

**Luôn bind parameter** cho giá trị do client cung cấp. Không nối `"... WHERE id = " + userInput`, vì đó là nguy cơ SQL injection.

| Nhu cầu | Chọn |
| --- | --- |
| CRUD/finder đơn giản | ReactiveCrudRepository |
| Criteria/query động và object mapping | R2dbcEntityTemplate |
| SQL phức tạp, join, projection/bulk query | DatabaseClient |

## 6. Entity mapping không giống JPA

Spring Data R2DBC có mapping metadata cho relational aggregate. Các annotation thường gặp:

| Annotation | Ý nghĩa |
| --- | --- |
| `@Table("products")` | Bảng ánh xạ |
| `@Id` | Primary key |
| `@Column("product_id")` | Tên cột tùy chỉnh |
| `@Version` | Optimistic locking |
| `@Embedded` | Value object vào các cột cùng row |
| `@MappedCollection` | Quan hệ collection trong aggregate |
| `@Transient` | Bỏ qua persistence |
| `@ReadOnlyProperty` | Đọc nhưng không viết lại |

Ví dụ record Java 17:

~~~java
@Table("products")
public record Product(
    @Id Long id,
    String name,
    int stock,
    @Version Long version
) {
}
~~~

Với id null, entity mới có thể được insert và nhận id do DB cấp khi column identity được cấu hình. `@Version` dùng để phát hiện concurrent update. Khi cập nhật từ object có version cũ, Spring Data có thể phát `OptimisticLockingFailureException`.

**Không có Hibernate session tự theo dõi mọi thay đổi.** Quan hệ nhiều bảng cần thiết kế aggregate, `@MappedCollection` hoặc SQL query riêng. Với một danh sách lớn, tránh N+1 query. Một projection SQL JOIN có thể phù hợp hơn việc gọi repository từng item rồi ghép Mono hàng trăm lần.

### 6.1. Optimistic lock chống mất cập nhật

~~~text
A đọc product id=5: stock=10, version=3
B đọc product id=5: stock=10, version=3
A lưu stock=8 -> version=4
B lưu stock=7 với version=3 -> conflict
~~~

Không chỉ dựa vào một đoạn `if (stock >= qty)` ở application khi có đồng thời; hãy kết hợp constraint, transaction và optimistic locking hoặc atomic UPDATE có điều kiện tại database.

## 7. Query methods, paging và dữ liệu lớn

Derived query:

~~~java
Flux<Product> findByNameContainingIgnoreCase(String keyword);
~~~

Query có SQL riêng:

~~~java
@Query("""
    SELECT id, name, stock, version
    FROM products
    WHERE stock < :threshold
    ORDER BY stock, id
    """)
Flux<Product> lowStock(@Param("threshold") int threshold);
~~~

Với Spring Data R2DBC, các string-based `@Query` không tự động viết lại SQL tùy ý để áp Pageable/Sort. Nếu cần phân trang, ưu tiên derived query nhận Pageable, fluent `R2dbcEntityTemplate` Query có limit/offset, hoặc SQL có bind limit/offset rõ ràng.

Reactive repositories thường trả `Flux<T>` cho nhiều row; để tạo Page đầy đủ cần query count và các metadata liên quan. Không mặc định một Flux tự mang `Page<T>`.

Đặc biệt, `repository.findAll().take(20)` **không tương đương** SQL LIMIT 20 về giới hạn work ở database. Hãy áp hạn mức ngay trong query, có ORDER BY ổn định và index thích hợp. Với dữ liệu cập nhật liên tục, cursor/keyset pagination có thể tốt hơn offset lớn.

## 8. Transaction reactive và Reactor Context

Spring Framework cung cấp `R2dbcTransactionManager`, một `ReactiveTransactionManager` cho ConnectionFactory. Khác JDBC transaction dựa vào ThreadLocal, transaction reactive liên kết với **Reactor subscriber Context** và một publisher chain.

### 8.1. @Transactional với Publisher

~~~java
@Service
public class InventoryService {
    private final ProductRepository products;
    private final InventoryAuditRepository audits;

    public InventoryService(
            ProductRepository products,
            InventoryAuditRepository audits) {
        this.products = products;
        this.audits = audits;
    }

    @Transactional
    public Mono<Product> reserve(long id, int quantity) {
        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Unknown product")
            ))
            .flatMap(current -> {
                if (current.stock() < quantity) {
                    return Mono.error(
                        new IllegalStateException("Insufficient stock")
                    );
                }
                return products.save(new Product(
                    current.id(),
                    current.name(),
                    current.stock() - quantity,
                    current.version()
                ));
            })
            .flatMap(saved ->
                audits.save(
                    new InventoryAudit(null, saved.id(), quantity)
                ).thenReturn(saved)
            );
    }
}
~~~

Đây là đoạn tập trung vào transaction; cần validate quantity dương ở API thực tế. Khi hai repository dùng cùng ConnectionFactory và reactive transaction manager, cập nhật product và insert audit có thể thuộc cùng một SQL transaction. Nếu audit insert thất bại, transaction rollback.

### 8.2. TransactionalOperator

Có thể dùng transaction programmatic:

~~~java
Mono<Product> workflow =
    products.save(product)
        .flatMap(saved ->
            audits.save(
                new InventoryAudit(null, saved.id(), 1)
            ).thenReturn(saved)
        );

Mono<Product> transactionalWorkflow =
    workflow.as(transactionalOperator::transactional);
~~~

`TransactionalOperator` giúp tạo transaction boundary rõ ràng với một Mono/Flux. Transaction bắt đầu tại subscription, không phải khi tạo biến Mono.

### 8.3. Những điều cần tránh

Không làm:

~~~java
@Transactional
public Mono<Void> wrong() {
    products.findAll().subscribe(System.out::println);
    return Mono.empty();
}
~~~

Subscription độc lập có thể mất Reactor Context, transaction/error/cancellation của request. Không dùng `block()` trong service WebFlux để chờ commit.

Cũng chú ý `@Transactional` proxy: method cùng class gọi một method transactional khác qua `this.method()` thường bỏ qua interceptor trong proxy mode. Đặt transaction boundary tại public service method được gọi từ bean khác, hoặc dùng TransactionalOperator.

Không mở transaction quanh Flux vô hạn. Publisher kéo dài có thể giữ connection quá lâu; ưu tiên transaction hữu hạn, commit trước khi đẩy dữ liệu streaming kéo dài.

## 9. Atomicity với nhiều datastore: phải tách rõ

`R2dbcTransactionManager` quản lý ConnectionFactory của một SQL database. Nó không tự tạo distributed transaction với Redis, MongoDB, Elasticsearch, Kafka hay HTTP API.

Ví dụ sau **không bảo đảm atomic** trên toàn hệ thống:

~~~java
@Transactional
public Mono<Void> completeOrder() {
    return orderRepository.save(order)
        .then(reactiveRedisTemplate.opsForValue()
            .set(cacheKey, value))
        .then(publisher.send(event))
        .then();
}
~~~

Giả sử broker nhận event nhưng SQL commit thất bại: consumer có thể thấy event không tương ứng dữ liệu đã commit. Hoặc SQL commit rồi gửi event thất bại: nghiệp vụ thành công nhưng downstream không biết.

### 9.1. Transactional outbox

~~~text
Trong một SQL transaction R2DBC:
  UPDATE orders
  INSERT outbox_events
         |
         v
       COMMIT
         |
         v
  Worker phát events từ outbox
         |
         +--> Message broker
         +--> Elasticsearch projector
         +--> Redis cache invalidator
         |
         v
  Mark delivered / retry / dedupe
~~~

Outbox row cần lưu cùng SQL database và transaction với business row. Worker đọc sau commit, gửi tới broker với idempotency key, retry/backoff và metrics. Không cam kết exactly-once end-to-end chỉ vì dùng outbox; thường cần idempotent consumer và xử lý at-least-once.

Khi một quy trình trải qua nhiều service và không thể dùng một database transaction, có thể chọn saga/compensation.

## 10. Spring Data reactive khác trong cùng kiến trúc

| Store | API reactive đặc trưng | Vai trò | Lưu ý |
| --- | --- | --- | --- |
| R2DBC SQL | ReactiveCrudRepository, R2dbcEntityTemplate | Dữ liệu quan hệ/transaction | SQL driver, aggregate mapping |
| MongoDB | ReactiveMongoRepository, ReactiveMongoTemplate | Document | Document mapping, session/transaction tùy topology |
| Redis | ReactiveRedisTemplate, ReactiveStringRedisTemplate | Cache/pub-sub/key-value | Lettuce reactive, serialization, cache consistency |
| Elasticsearch | ReactiveElasticsearchOperations, ReactiveElasticsearchRepository | Search/index | Index consistency/rebuild |
| Cassandra | ReactiveCassandraTemplate, reactive repository khi hỗ trợ | Wide-column | Partition-key-driven queries |
| Neo4j | Reactive driver / reactive repository khi hỗ trợ | Graph | Graph modeling và driver compatibility |

Không giả định API Redis repository truyền thống tự là reactive; Redis reactive thường dùng template/operations với Lettuce. Một store có reactive API không nghĩa nó tham gia transaction R2DBC.

### 10.1. Đọc nhiều store bằng Mono.zip

~~~java
return Mono.zip(
    productRepository.findById(productId),
    customerRepository.findById(customerId)
).map(pair ->
    new ProductCustomerView(pair.getT1(), pair.getT2())
);
~~~

Nếu một nhánh Mono empty, zip có thể hoàn tất mà không phát kết quả. Cần xử lý empty cụ thể nếu cả product và customer đều bắt buộc tồn tại.

Đây là tổng hợp **read model**, không phải cross-database transaction.

### 10.2. Redis cache-aside

~~~java
return redis.opsForValue().get(cacheKey)
    .switchIfEmpty(
        products.findById(productId)
            .map(Product::name)
            .flatMap(name ->
                redis.opsForValue()
                    .set(cacheKey, name, Duration.ofMinutes(5))
                    .thenReturn(name)
            )
    );
~~~

Cần xử lý cache invalidation, stampede, lỗi Redis, stale value và fallback strategy. Không ghi Redis rồi giả định transaction SQL rollback cũng rollback cache.

### 10.3. Search index và event-driven updates

Dữ liệu nguồn SQL có thể được đưa vào Elasticsearch qua outbox/broker:

~~~text
R2DBC PostgreSQL -> SQL outbox -> Broker -> Elasticsearch
                          |
                          +-------> Redis invalidation
~~~

Các projection có thể cập nhật trễ: hệ thống nên định nghĩa eventual consistency, reconciliation/replay và idempotency.

## 11. Backpressure, connection pool và giới hạn concurrency

Reactive không có nghĩa DB có vô hạn connection hoặc memory.

Spring Boot có thể sử dụng `r2dbc-pool` khi dependency có sẵn. Cấu hình minh họa:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-acquire-time=5s
spring.r2dbc.pool.max-idle-time=30m
~~~

Các giá trị này chỉ để minh họa, không phải cấu hình tối ưu chung. Tổng số connection có thể lên tới số instance nhân với pool.max-size. Ví dụ 10 pod * 20 connection = 200 connection có thể cạnh tranh trên database.

Hãy quan sát:

- Pool acquired, idle, pending và timeout.
- Query latency theo statement/operation.
- SQL locks, CPU, I/O và index usage.
- Transaction duration và tỷ lệ rollback.
- Concurrent inbound HTTP requests.
- Driver/network errors và retry counts.

Khi có hàng nghìn operations:

~~~java
Flux<Product> saved = incomingProducts
    .flatMap(repository::save, 12);
~~~

Tham số concurrency 12 giới hạn số save đang in-flight trong ví dụ; không lấy đó làm giá trị chuẩn cho mọi hệ thống. Tối ưu SQL, batching phù hợp và pool sizing quan trọng hơn chỉ thay operator Reactor.

Backpressure truyền qua publisher nhưng driver/database có giới hạn buffer/prefetch riêng. Không dùng `collectList()` trên dataset vô hạn hoặc rất lớn, và không để transaction mở qua streaming vô hạn.

## 12. Lỗi, timeout và retry đúng chỗ

| Tình huống | Dấu hiệu thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có row | Mono.empty | switchIfEmpty thành NotFound |
| Unique constraint | DataIntegrityViolationException | 409 hoặc validation response |
| Concurrent update | OptimisticLockingFailureException | 409, reload/retry có giới hạn |
| Pool hết connection | Acquire timeout | Pool/traffic tuning |
| DB mất kết nối | Driver/connection exception | Retry có backoff nếu an toàn |
| Sai SQL/schema | DataAccessException tương ứng | Sửa query/migration |
| Transaction rollback | Mono error | Trả lỗi và bảo toàn tính nhất quán |

Để map optimistic locking:

~~~java
return service.reserve(id, quantity)
    .onErrorMap(
        OptimisticLockingFailureException.class,
        error -> new ResponseStatusException(
            HttpStatus.CONFLICT,
            "Product changed concurrently",
            error
        )
    );
~~~

**Không retry mọi INSERT/UPDATE.** Nếu DB đã commit nhưng response bị mất, retry có thể tạo giao dịch trùng. Xác định retryable errors, dùng idempotency key và đặt retry bên ngoài transaction boundary khi thực hiện lại toàn bộ workflow.

Timeout của Reactor ở Mono và timeout connection/query của driver là các cơ chế khác nhau. `timeout(Duration)` không biến một tác vụ JDBC blocking thành có thể hủy tức thì.

## 13. Schema migration: Spring Data R2DBC không tạo bảng JPA

Demo/test có thể dùng `schema.sql` và `data.sql` với Spring Boot SQL initialization. Production thường nên quản lý schema bằng Flyway/Liquibase hoặc migration job được kiểm soát:

- Đặt version và lịch sử migration.
- Kiểm tra index/constraints và loại dữ liệu.
- Đảm bảo backward/forward compatibility khi rolling deploy.
- Không để mọi replica cùng chạy migration không được điều phối.
- Có rollback/forward-fix plan và backup.

Flyway/Liquibase truyền thống thường dùng JDBC connection, dù runtime SQL chính dùng R2DBC. Nếu dùng cả hai, hãy cấu hình migration bằng JDBC driver/connection riêng có chủ đích. Không cho rằng `ConnectionFactory` tự cung cấp một JDBC DataSource.

## 14. Testing và observability

Phân lớp kiểm thử:

- Unit: kiểm tra validation và reactive composition bằng mock repository hoặc fake publisher.
- `@DataR2dbcTest`: test mapping/repositories trong application context thu hẹp.
- `StepVerifier`: test value, empty, error, cancel và virtual-time logic.
- WebTestClient: test WebFlux HTTP + service + database.
- Testcontainers + PostgreSQL thật: test dialect, transaction, concurrency, constraint, generated keys, SQL và migration.

H2 chỉ phù hợp làm bài demo hoặc test nhanh; H2 pass không bảo đảm PostgreSQL/MySQL pass ở SQL syntax, lock/isolation và behavior của driver.

Observability nên có SQL query latency, pool wait, transaction duration, error rate và correlation ID. Không log SQL parameter chứa token, PII hoặc credential. Reactor Context thường được dùng để truyền context trong asynchronous pipeline; không dựa hoàn toàn vào ThreadLocal.

## 15. Demo chạy được: Java 17 + Spring Boot 3.5 + WebFlux + R2DBC H2

Demo tạo một API inventory: tạo product, lấy theo ID, lọc ít tồn, reserve số lượng và lưu audit trong transaction.

### 15.1. Cấu trúc dự án

~~~text
inventory-r2dbc-demo/
  settings.gradle
  build.gradle
  src/main/
    java/demo/inventory/
      InventoryApplication.java
      Product.java
      InventoryAudit.java
      ProductRepository.java
      InventoryAuditRepository.java
      CreateProductRequest.java
      ProductService.java
      ProductController.java
    resources/
      application.properties
      schema.sql
      data.sql
  src/test/java/demo/inventory/
      ProductApiTest.java
~~~

### 15.2. settings.gradle

~~~groovy
rootProject.name = 'inventory-r2dbc-demo'
~~~

### 15.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 15.4. application.properties

~~~properties
spring.application.name=inventory-r2dbc-demo
spring.r2dbc.url=r2dbc:h2:mem:///inventory?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.sql.init.mode=always
~~~

H2 dùng memory database, không bền qua restart. `spring.sql.init.mode=always` áp SQL initialization từ resources khi khởi động.

### 15.5. schema.sql

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    stock INTEGER NOT NULL,
    version BIGINT
);

CREATE TABLE inventory_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_audit_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

### 15.6. data.sql

~~~sql
INSERT INTO products (name, stock, version)
VALUES ('USB-C Hub', 7, 0);

INSERT INTO products (name, stock, version)
VALUES ('Mechanical Keyboard', 12, 0);
~~~

### 15.7. InventoryApplication.java

~~~java
package demo.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

### 15.8. Product.java

~~~java
package demo.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
    @Id Long id,
    String name,
    int stock,
    @Version Long version
) {
}
~~~

### 15.9. InventoryAudit.java

~~~java
package demo.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("inventory_audit")
public record InventoryAudit(
    @Id Long id,
    @Column("product_id") Long productId,
    int quantity
) {
}
~~~

### 15.10. ProductRepository.java

~~~java
package demo.inventory;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

### 15.11. InventoryAuditRepository.java

~~~java
package demo.inventory;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface InventoryAuditRepository
        extends ReactiveCrudRepository<InventoryAudit, Long> {
}
~~~

### 15.12. CreateProductRequest.java

~~~java
package demo.inventory;

public record CreateProductRequest(
    String name,
    int stock
) {
}
~~~

### 15.13. ProductService.java

~~~java
package demo.inventory;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final ProductRepository products;
    private final InventoryAuditRepository audits;
    private final R2dbcEntityTemplate template;

    public ProductService(
            ProductRepository products,
            InventoryAuditRepository audits,
            R2dbcEntityTemplate template) {
        this.products = products;
        this.audits = audits;
        this.template = template;
    }

    public Mono<Product> create(CreateProductRequest request) {
        if (request.name() == null || request.name().isBlank()
                || request.stock() < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Name must be nonblank and stock nonnegative"
            ));
        }

        return products.save(new Product(
            null, request.name().strip(), request.stock(), null
        ));
    }

    public Mono<Product> findById(long id) {
        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found"
                )
            ));
    }

    public Flux<Product> findAll() {
        return products.findAll();
    }

    public Flux<Product> findLowStock(int threshold) {
        if (threshold < 0) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "maxStock must be nonnegative"
            ));
        }

        return template.select(Product.class)
            .matching(Query.query(
                Criteria.where("stock")
                    .lessThanOrEquals(threshold)
            ))
            .all();
    }

    @Transactional
    public Mono<Product> reserve(long id, int quantity) {
        if (quantity <= 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Quantity must be positive"
            ));
        }

        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Product not found"
                )
            ))
            .flatMap(product -> {
                if (product.stock() < quantity) {
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.CONFLICT,
                            "Insufficient stock"
                        )
                    );
                }

                Product updated = new Product(
                    product.id(),
                    product.name(),
                    product.stock() - quantity,
                    product.version()
                );

                return products.save(updated);
            })
            .flatMap(saved ->
                audits.save(new InventoryAudit(
                    null, saved.id(), quantity
                )).thenReturn(saved)
            )
            .onErrorMap(
                OptimisticLockingFailureException.class,
                error -> new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Product updated concurrently",
                    error
                )
            );
    }
}
~~~

Controller gọi service qua Spring bean proxy. Với reactive transaction manager và cùng ConnectionFactory, thao tác save product và save audit được thực hiện trong một transaction.

### 15.14. ProductController.java

~~~java
package demo.inventory;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Product> all() {
        return service.findAll();
    }

    @GetMapping("/low-stock")
    public Flux<Product> lowStock(
            @RequestParam(defaultValue = "5") int maxStock) {
        return service.findLowStock(maxStock);
    }

    @GetMapping("/{id}")
    public Mono<Product> byId(@PathVariable long id) {
        return service.findById(id);
    }

    @PostMapping
    public Mono<ResponseEntity<Product>> create(
            @RequestBody Mono<CreateProductRequest> body) {
        return body
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Request body required"
                )
            ))
            .flatMap(service::create)
            .map(saved -> ResponseEntity
                .created(URI.create("/api/products/" + saved.id()))
                .body(saved));
    }

    @PutMapping("/{id}/reserve")
    public Mono<Product> reserve(
            @PathVariable long id,
            @RequestParam int quantity) {
        return service.reserve(id, quantity);
    }
}
~~~

### 15.15. ProductApiTest.java

~~~java
package demo.inventory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ProductApiTest {

    @Autowired
    WebTestClient client;

    @Autowired
    InventoryAuditRepository audits;

    private Product create(String name, int stock) {
        Product product = client.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProductRequest(name, stock))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody(Product.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(product);
        assertNotNull(product.id());
        return product;
    }

    @Test
    void createsAndReadsProduct() {
        Product created = create(
            "New-" + UUID.randomUUID(),
            5
        );

        client.get()
            .uri("/api/products/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved -> {
                assertEquals(created.id(), saved.id());
                assertEquals(5, saved.stock());
            });
    }

    @Test
    void reservationWritesAudit() {
        Product created = create(
            "Stock-" + UUID.randomUUID(),
            5
        );

        client.put()
            .uri("/api/products/{id}/reserve?quantity=2",
                created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved ->
                assertEquals(3, saved.stock())
            );

        StepVerifier.create(
            audits.findAll()
                .filter(audit ->
                    audit.productId().equals(created.id()))
                .count()
        ).expectNext(1L).verifyComplete();
    }

    @Test
    void insufficientStockDoesNotCreateAudit() {
        Product created = create(
            "Low-" + UUID.randomUUID(),
            2
        );

        client.put()
            .uri("/api/products/{id}/reserve?quantity=3",
                created.id())
            .exchange()
            .expectStatus().isEqualTo(409);

        client.get()
            .uri("/api/products/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved ->
                assertEquals(2, saved.stock())
            );

        StepVerifier.create(
            audits.findAll()
                .filter(audit ->
                    audit.productId().equals(created.id()))
                .count()
        ).expectNext(0L).verifyComplete();
    }

    @Test
    void lowStockEndpointRespondsWithJson() {
        client.get()
            .uri("/api/products/low-stock?maxStock=7")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBodyList(Product.class);
    }
}
~~~

Test tạo product riêng với tên random, không phụ thuộc seed IDs. Các assertion kiểm tra HTTP 201/Location, GET, việc trừ stock và audit. Đây là integration test HTTP + database, không thay thế test PostgreSQL thật nếu production dùng PostgreSQL.

### 15.16. Chạy thử

Tại thư mục dự án:

~~~bash
gradle bootRun
~~~

Thử:

~~~bash
curl -s http://localhost:8080/api/products
~~~

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Laptop Stand","stock":9}'
~~~

Response POST trả HTTP 201 Created, có Location. Generated ID phụ thuộc trạng thái database.

Dùng ID từ response để reserve:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1/reserve?quantity=2"
~~~

Ở đây `1` chỉ là ví dụ ID; hãy dùng ID thực tế từ danh sách hoặc POST.

Lọc low stock:

~~~bash
curl -s "http://localhost:8080/api/products/low-stock?maxStock=7"
~~~

Chạy test:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper trong dự án, thay `gradle` bằng `./gradlew`. Không ghi stdout JSON cố định vì generated ID/version và thứ tự SELECT có thể thay đổi.

## 16. Checklist production

1. Driver R2DBC có hỗ trợ tốt database và các tính năng bắt buộc không?
2. WebFlux path có JDBC/JPA/blocking SDK nào chưa được cô lập không?
3. Query có index, limit và ORDER BY đúng không?
4. Có kiểm soát concurrency và pool size theo số instance không?
5. Có mapping đúng aggregate root, @Id, @Version và các quan hệ không?
6. Có transaction reactive với một ConnectionFactory, không tự subscribe/block không?
7. Có xử lý rollback, constraint, optimistic locking và idempotency không?
8. Có kế hoạch migration schema độc lập với runtime R2DBC không?
9. Nếu dùng Redis/MongoDB/Elasticsearch, consistency và source of truth được xác định chưa?
10. Có outbox/saga khi gửi event và cập nhật datastore thứ hai không?
11. Có Testcontainers với DB thật và test concurrent updates không?
12. Có metrics/log/tracing cho pool, SQL latency và transaction không?

## 17. Lỗi thường gặp

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Gọi JPA/JDBC trực tiếp trong WebFlux handler | Blocking event loop | R2DBC hoặc boundedElastic với đánh giá kiến trúc |
| Nghĩ Mono làm JDBC non-blocking | Wrapper không đổi driver | Dùng R2DBC khi phù hợp |
| Dùng JpaRepository cho service reactive | Sai persistence model | ReactiveCrudRepository của Spring Data |
| Mong Hibernate ddl-auto tạo bảng R2DBC | Không có JPA schema lifecycle | Migration/SQL init |
| Dùng EntityManager/lazy loading giả định | Không tồn tại theo R2DBC model | Aggregate/projection/SQL rõ ràng |
| Dùng subscribe trong @Transactional method | Tách transaction context | Return publisher để compose |
| Tạo Flux vô hạn trong transaction | Giữ connection quá lâu | Transaction ngắn, hữu hạn |
| Đọc toàn bộ bảng rồi take(20) | Tải SQL không tối ưu | DB LIMIT/pagination |
| Nối user input vào SQL | Injection | Bind parameters |
| Không có @Version khi ghi cạnh tranh | Lost update | Optimistic lock/atomic SQL |
| Retry mọi write thất bại | Trùng dữ liệu | Idempotency/retry có chọn lọc |
| Nghĩ Redis cùng transaction SQL | Divergence | Outbox/cache invalidation |
| Nghĩ reactive Redis repository luôn có | Sai khả năng module | Dùng ReactiveRedisTemplate |
| Tin H2 test là đủ cho PostgreSQL | Khác dialect và locking | Testcontainers với DB thật |
| Tăng pool vô hạn để sửa latency | DB quá tải | Tối ưu query và sizing |
| Log parameters nhạy cảm | Rò rỉ secrets/PII | Redaction và bounded metrics |

## 18. Câu hỏi ôn tập có đáp án

**Câu 1. R2DBC khác JDBC thế nào?** R2DBC định nghĩa API reactive cho SQL thông qua ConnectionFactory và publisher; JDBC truyền thống cung cấp API blocking.

**Câu 2. Spring Data R2DBC có phải JPA reactive không?** Không. Nó cung cấp mapping, repository và template nhưng không có Hibernate persistence context/lazy loading.

**Câu 3. Khi nào dùng R2dbcEntityTemplate?** Khi query cần criteria/ad-hoc operations với entity mapping hơn là derived repository methods.

**Câu 4. DatabaseClient khác R2dbcEntityTemplate?** DatabaseClient làm việc trực tiếp với SQL và row mapping; template thêm entity-oriented abstraction.

**Câu 5. findById không thấy row trả gì?** Mono.empty, có thể chuyển thành 404 bằng switchIfEmpty.

**Câu 6. @Version giải quyết gì?** Optimistic locking cho các cập nhật cạnh tranh và tránh lost update thầm lặng.

**Câu 7. Transaction reactive gắn với đâu?** Reactor subscriber Context, không phải ThreadLocal JDBC thông thường.

**Câu 8. R2dbcTransactionManager có rollback Redis/cache không?** Không. Nó quản lý transaction trên ConnectionFactory của một SQL datastore.

**Câu 9. Mono.zip với MongoDB và SQL có tạo transaction chung không?** Không. Nó chỉ compose kết quả các publishers.

**Câu 10. Vì sao không dùng Flux.take(20) thay SQL LIMIT?** Vì giới hạn ở tầng publisher không bảo đảm giảm work/query/row fetching của database.

**Câu 11. Vì sao cần Testcontainers Postgres?** H2 có khác biệt về SQL dialect, locking, migrations và generated values.

**Câu 12. Dùng gì để phát event sau SQL commit đáng tin hơn?** Transactional outbox với worker, retry và idempotent consumer.

## 19. Tổng kết và tài liệu chính thức

- R2DBC là reactive specification cho SQL, **không phải** ORM hoặc Hibernate reactive.
- ConnectionFactory kết nối driver; DatabaseClient làm SQL; R2dbcEntityTemplate và repositories ánh xạ entity.
- Reactive transaction cần Reactor Context và publisher chain thống nhất.
- SQL transaction không tự bao phủ Redis, MongoDB, Elasticsearch hoặc message broker.
- Dùng migration, index, query limit, pool, optimistic locking và integration test DB thật.
- Spring Data reactive đa dạng; chọn module đúng semantics thay vì suy luận từ tên phương thức.
- Kết hợp outbox/saga và idempotency trong hệ thống nhiều datastore.

Tài liệu chính thức:

1. [Spring Data Relational — R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): template/repository và kiến trúc.
2. [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): DatabaseClient/ConnectionFactory/transaction.
3. [Spring Data — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-persistence.html): ID, version và optimistic locking.
4. [Spring Data — Query Methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html): @Query, Pageable và repository query.
5. [Spring Data — Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html): @Table, @Id, @Column, @Version, aggregates.
6. [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): reactive transaction semantics.
7. [Spring Boot 3.5 — SQL/R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): auto-config và R2DBC properties.
8. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql/data.sql.
9. [Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/): reactive document store.
10. [Spring Data Redis — Templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html): ReactiveRedisTemplate và serialization.
11. [Spring Data Elasticsearch](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html): reactive index/search.
12. [Spring Data Cassandra](https://docs.spring.io/spring-data/cassandra/reference/): Cassandra mapping/repository.
13. [Spring Boot 3.5 — R2DBC Pool Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): max-size, acquire timeout và pooling.
