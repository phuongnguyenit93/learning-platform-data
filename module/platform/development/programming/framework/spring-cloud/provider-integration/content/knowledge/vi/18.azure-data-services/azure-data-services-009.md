# Chọn API dữ liệu đồng bộ hoặc reactive theo luồng xử lý

Spring Boot có thể truy cập cùng một loại dữ liệu bằng API **đồng bộ (imperative/blocking)** hoặc **bất đồng bộ/reactive (non-blocking)**. Ví dụ, Azure Cosmos DB Java SDK v4 cung cấp `CosmosClient` và `CosmosAsyncClient`; Spring Data Cosmos có `CosmosRepository` và `ReactiveCosmosRepository`. Với relational database, JDBC thường đi cùng Spring MVC, còn R2DBC thường đi cùng Spring WebFlux. Spring Data Redis cũng cung cấp `RedisTemplate` và `ReactiveRedisTemplate`.

Chọn API theo toàn bộ đường đi của request: web server, application service, database driver, lời gọi mạng khác và cách trả response. Chỉ đổi controller sang WebFlux trong khi bên dưới vẫn gọi JDBC blocking không tạo thành một pipeline non-blocking. Ngược lại, một ứng dụng Spring MVC có thể dùng một client async ở một số chỗ mà không cần chuyển cả hệ thống sang reactive.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này dùng Azure Cosmos DB, Azure Database for PostgreSQL/MySQL/SQL và Redis để minh họa cách chọn API.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt synchronous, asynchronous, non-blocking và reactive programming.
- Chọn Spring MVC + JDBC/JPA hoặc WebFlux + R2DBC theo workload và dependency thực tế.
- Chọn `CosmosClient` hay `CosmosAsyncClient`, `CosmosRepository` hay `ReactiveCosmosRepository`.
- Chọn `RedisTemplate` hay `ReactiveRedisTemplate` với Lettuce.
- Xây dựng luồng `Mono`/`Flux` không chặn event loop và có backpressure.
- Nhận diện lỗi khi dùng `block()`, `subscribe()` hoặc JDBC trong WebFlux.
- Phân biệt transaction imperative với reactive transaction.
- Kiểm thử và benchmark hai mô hình bằng cùng một workload.

## 2. Làm rõ bốn khái niệm

Các thuật ngữ này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Synchronous** | Caller chờ lời gọi trả kết quả trước khi đi tiếp | `repository.findById(id)` trả `Optional<T>` |
| **Asynchronous** | Kết quả hoàn tất sau; caller nhận callback/future/publisher | `CompletableFuture<T>`, `Mono<T>` |
| **Non-blocking I/O** | Thread không phải đứng chờ network I/O; completion được báo khi có kết quả | Netty, R2DBC, CosmosAsyncClient |
| **Reactive Streams** | Mô hình Publisher/Subscriber có demand/backpressure, thường biểu diễn bằng `Mono`/`Flux` | `ReactiveCrudRepository` |

Một API async không tự động là reactive. Ví dụ `CompletableFuture` là async nhưng không có giao thức backpressure của Reactive Streams. Một API trả `Mono` cũng không bảo đảm mọi đoạn code bên trong non-blocking: nếu method gọi JDBC hoặc `Thread.sleep`, nó vẫn chặn thread đang thực thi.

**Reactive không có nghĩa là chạy song song.** Reactor có thể thực thi pipeline tuần tự trên một thread, chuyển thread khi cần và quản lý demand. Muốn chạy nhiều tác vụ đồng thời phải thiết kế concurrency rõ ràng.

## 3. Mô hình thread: Spring MVC và Spring WebFlux

### 3.1. Spring MVC với API blocking

Spring MVC chạy trên Servlet stack. Mỗi request thường được xử lý trên một worker thread; nếu truy vấn database mất 100 ms, worker thread đó chờ trong khoảng thời gian I/O. Thread pool có thể tăng để phục vụ nhiều request đang chờ, nhưng mỗi thread và request vẫn tiêu thụ tài nguyên.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as MVC worker thread
    participant DB as Database
    C->>W: HTTP request
    W->>DB: JDBC query
    Note over W,DB: Worker thread waits for I/O
    DB-->>W: Result
    W-->>C: HTTP response
~~~

Mô hình này dễ hiểu, phù hợp với JDBC/JPA, transaction imperative và phần lớn ứng dụng CRUD có tải vừa phải. Khi database call blocking, việc thread chờ là hành vi dự kiến của mô hình.

### 3.2. Spring WebFlux với API non-blocking

WebFlux thường chạy trên Netty với một số event-loop thread nhỏ. Khi gửi query qua R2DBC hoặc Cosmos async API, event loop không chờ socket response; thread có thể xử lý request khác trong lúc I/O đang diễn ra. Khi dữ liệu về, pipeline tiếp tục:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant E as WebFlux event loop
    participant DB as Non-blocking driver
    C->>E: HTTP request
    E->>DB: Start async query
    Note over E,DB: Event loop is free while I/O is pending
    DB-->>E: Publisher emits result
    E-->>C: HTTP response
~~~

WebFlux phù hợp khi phần lớn đường đi có thể non-blocking, có nhiều request đồng thời đang chờ I/O, cần stream dữ liệu hoặc ghép nhiều dịch vụ từ xa. Reactive/non-blocking không nhất thiết làm một request riêng lẻ chạy nhanh hơn; lợi ích chính là sử dụng thread và memory hiệu quả hơn dưới tải có độ trễ I/O đáng kể.

Spring Framework khuyến nghị Spring MVC cho kiến trúc phổ biến có blocking persistence như JPA/JDBC. Có thể gọi blocking API trong WebFlux trên scheduler riêng, nhưng khi đó ứng dụng không tận dụng đầy đủ mô hình non-blocking và phải quản lý thread pool cho các đoạn blocking.

## 4. Quy tắc chọn: nhìn toàn bộ pipeline

Đừng quyết định chỉ dựa trên controller hoặc tên thư viện. Hãy liệt kê các thao tác I/O trên một request:

~~~text
HTTP request
  -> application service
  -> database query
  -> Redis cache
  -> HTTP call tới service khác
  -> serialize response
~~~

Nếu database dùng JDBC blocking, Redis dùng API blocking và HTTP client blocking, Spring MVC thường là lựa chọn đơn giản, nhất quán. Nếu database dùng R2DBC, Redis dùng reactive template và HTTP call dùng WebClient, WebFlux có thể giữ pipeline non-blocking từ đầu đến cuối.

| Tình huống | Hướng chọn ban đầu |
| --- | --- |
| CRUD thông thường, JDBC/JPA, transaction SQL | Spring MVC + JDBC/JPA |
| Dùng Spring Data Cosmos sync repository, throughput vừa phải | Spring MVC + `CosmosRepository` |
| Nhiều request đồng thời chờ network, driver reactive sẵn có | Spring WebFlux + R2DBC/ReactiveCosmosRepository |
| Cosmos DB cần throughput cao và pipeline đã dùng Reactor | `CosmosAsyncClient` hoặc `ReactiveCosmosRepository` |
| Redis dùng trong pipeline WebFlux | `ReactiveRedisTemplate` |
| Batch job xử lý theo lô, code imperative dễ kiểm soát | API sync hoặc async tùy throughput và giới hạn concurrency |
| Một số dependency blocking chưa thể thay | Giữ MVC hoặc cô lập blocking trong scheduler riêng |

Hãy cân nhắc thêm độ trưởng thành của driver, transaction support, khả năng debug, kinh nghiệm đội ngũ và chi phí chuyển đổi. Không chuyển toàn bộ hệ thống sang reactive chỉ để đổi vài repository method.

## 5. Ma trận API dữ liệu Azure

| Dịch vụ | API imperative/sync | API async/reactive | Điểm cần chú ý |
| --- | --- | --- | --- |
| **Azure Cosmos DB for NoSQL** | Java SDK `CosmosClient`; Spring Data `CosmosRepository` | Java SDK `CosmosAsyncClient`; Spring Data `ReactiveCosmosRepository` | SDK v4 có cả hai API; Async dùng Reactor và non-blocking I/O |
| **Azure Database for PostgreSQL** | PostgreSQL JDBC; Spring Data JDBC/JPA | R2DBC PostgreSQL; Spring Data R2DBC | Driver và TLS/authentication config khác JDBC |
| **Azure Database for MySQL** | MySQL Connector/J; Spring Data JDBC/JPA | R2DBC MySQL; Spring Data R2DBC | Dùng R2DBC driver riêng, không phải Connector/J |
| **Azure SQL Database** | Microsoft JDBC Driver; Spring Data JDBC/JPA | R2DBC SQL Server (`r2dbc-mssql`) | JDBC authentication mode không tự chuyển sang R2DBC |
| **Azure Redis** | `RedisTemplate`, `StringRedisTemplate` | `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` | Cả hai có thể dùng Lettuce; chọn template theo pipeline |

Đây là ma trận thư viện phổ biến, không phải cam kết mọi feature của hai API tương đương. Kiểm tra transaction, bulk operation, streaming, authentication và version support của driver cụ thể trước khi chọn.

## 6. Azure Cosmos DB: Sync API và Async API

### 6.1. Hai client trong Java SDK v4

Azure Cosmos DB Java SDK v4 cung cấp hai client:

- `CosmosClient` thực thi API synchronous/blocking.
- `CosmosAsyncClient` thực thi API asynchronous dựa trên Project Reactor và Netty.

SDK v4 dùng chung một Maven artifact `com.azure:azure-cosmos`. Sync API về cơ bản là một lớp wrapper blocking trên Async API. Chọn API khi khởi tạo client; không lấy một `CosmosAsyncClient` rồi kỳ vọng nó trả object sync hoặc ngược lại.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosAsyncClient;

// Imperative/blocking
CosmosClient syncClient = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(key)
    .buildClient();

// Asynchronous/reactive
CosmosAsyncClient asyncClient = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(key)
    .buildAsyncClient();
~~~

Trong production, dùng credential phù hợp như Managed Identity/TokenCredential theo cấu hình bảo mật của ứng dụng. Ví dụ chỉ minh họa điểm khác nhau ở API khởi tạo; không lưu account key trong source code.

### 6.2. Khi nào chọn Sync API?

Sync API phù hợp khi:

- Application service và controller đang theo imperative model.
- Throughput không phải nút thắt chính và request/response tuần tự dễ hiểu hơn.
- Phần lớn dependency khác là blocking.
- Team ưu tiên code dễ debug và transaction/application flow imperative.
- Workload batch hoặc worker có concurrency được kiểm soát.

Ví dụ:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final CosmosContainer orders;

    public OrderLookupService(CosmosContainer orders) {
        this.orders = orders;
    }

    public OrderDocument find(String id, String tenantId) {
        return orders.readItem(
            id,
            new PartitionKey(tenantId),
            OrderDocument.class
        ).getItem();
    }
}
~~~

Method trả object ngay sau khi network call hoàn tất. Trong Spring MVC, worker thread chờ kết quả là điều bình thường.

### 6.3. Khi nào chọn Async API?

Async API phù hợp khi:

- Cần khai thác throughput cao và nhiều request đồng thời.
- Pipeline dùng WebFlux/Reactor.
- Cần compose query với Redis, HTTP hoặc nhiều thao tác async khác.
- Cần stream kết quả thay vì giữ toàn bộ collection trong memory.
- Muốn cancellation/backpressure và giới hạn concurrency trong pipeline.

Ví dụ:

~~~java
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderLookupService {
    private final CosmosAsyncContainer orders;

    public ReactiveOrderLookupService(CosmosAsyncContainer orders) {
        this.orders = orders;
    }

    public Mono<OrderDocument> find(String id, String tenantId) {
        return orders.readItem(
                id,
                new PartitionKey(tenantId),
                OrderDocument.class)
            .map(response -> response.getItem());
    }
}
~~~

Method trả `Mono<OrderDocument>`; caller subscribe thông qua WebFlux hoặc pipeline phía trên. Không gọi `.block()` trong service để lấy item rồi trả về object đồng bộ.

### 6.4. Spring Data Cosmos repositories

Spring Data Cosmos cung cấp hai abstraction:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {
}
~~~

~~~java
import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {
}
~~~

Repository sync trả kiểu imperative như `Optional<T>`, `List<T>` hoặc entity; reactive repository trả `Mono<T>`/`Flux<T>`. Với cấu hình nhiều repository package, dùng `@EnableCosmosRepositories` hoặc `@EnableReactiveCosmosRepositories` và trỏ đúng template (`CosmosTemplate` hoặc `ReactiveCosmosTemplate`). Tránh cấu hình hai repository scan cùng package rồi vô tình đăng ký sai template.

### 6.5. Khác biệt hiệu năng

Microsoft mô tả Async API là non-blocking I/O và là lựa chọn tối ưu nếu mục tiêu là khai thác tối đa throughput được provision. Sync API block khi chờ response; throughput có thể giảm khi latency request/response tăng. Sync vẫn là lựa chọn hợp lý khi mô hình ứng dụng chủ yếu đồng bộ và throughput không phải ưu tiên.

Async API không làm giảm RU của một thao tác. RU vẫn phụ thuộc query, partition routing, index và dữ liệu. Async giúp client tận dụng tài nguyên và gửi/điều phối request hiệu quả hơn; phải benchmark cùng query và cùng cấu hình throughput để so sánh.

## 7. Relational database: JDBC hay R2DBC?

### 7.1. JDBC và Spring Data JDBC/JPA

JDBC là API blocking. Khi gọi `JdbcTemplate.query(...)` hoặc `JpaRepository.findById(...)`, thread chờ database trả kết quả. Đây là mô hình tự nhiên cho Spring MVC.

~~~java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Service imperative:

~~~java
public Customer findCustomer(long id) {
    return customerRepository.findById(id)
        .orElseThrow(CustomerNotFoundException::new);
}
~~~

JDBC có hệ sinh thái driver, pool, transaction, migration và monitoring trưởng thành. Nếu workload không có mức concurrency I/O quá cao hoặc đội ngũ muốn đơn giản hóa transaction, MVC + JDBC/JPA thường là lựa chọn tốt.

### 7.2. R2DBC và Spring Data R2DBC

R2DBC là SPI non-blocking cho relational database. Spring Data R2DBC cung cấp `ReactiveCrudRepository`, `DatabaseClient` và reactive transaction manager. Cần dùng R2DBC driver thực sự; JDBC driver không trở thành non-blocking chỉ bằng cách bọc trong `Mono`.

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
    Flux<Customer> findByStatus(String status);
}
~~~

Controller WebFlux:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class CustomerController {
    private final ReactiveCustomerRepository customers;

    public CustomerController(ReactiveCustomerRepository customers) {
        this.customers = customers;
    }

    @GetMapping("/customers")
    public Flux<Customer> findActiveCustomers() {
        return customers.findByStatus("ACTIVE");
    }
}
~~~

Spring Boot thường cấu hình `ConnectionFactory` từ `spring.r2dbc.*`; production nên dùng R2DBC pool phù hợp. Azure có tài liệu hướng dẫn R2DBC cho PostgreSQL Flexible Server, MySQL Flexible Server và Azure SQL Database. Các driver là riêng biệt, ví dụ:

| Database | R2DBC driver artifact |
| --- | --- |
| PostgreSQL | `org.postgresql:r2dbc-postgresql` |
| MySQL | `io.asyncer:r2dbc-mysql` |
| SQL Server | `io.r2dbc:r2dbc-mssql` |

Xác minh version driver, URL scheme, TLS, authentication và feature support theo tài liệu driver hiện hành. Passwordless JDBC starter không tự động cấu hình token cho R2DBC driver; Entra/Managed Identity support phải được xác minh riêng cho driver và version đang dùng.

Ví dụ cấu hình R2DBC PostgreSQL theo dạng URL pool:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:pool:postgres://${DB_HOST}.postgres.database.azure.com:5432/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    properties:
      sslMode: REQUIRE
~~~

Đây là cấu hình minh họa theo PostgreSQL R2DBC driver; property TLS và authentication có thể khác theo driver/version. Với MySQL và SQL Server, URL scheme và option tương ứng khác nhau. Không copy `spring.datasource.*` của JDBC sang `spring.r2dbc.*`.

### 7.3. Giới hạn và trade-off của R2DBC

- Không phải mọi tính năng JDBC/ORM đều có bản reactive tương đương.
- Một số driver có khác biệt về stored procedure, batch, generated key, metadata, isolation và transaction.
- Không dùng JPA/Hibernate blocking trong reactive pipeline rồi coi hệ thống đã non-blocking.
- R2DBC connection pool cần sizing theo database max connections và concurrency; không mở connection không giới hạn.
- Kiểm thử TLS, Entra, failover và reconnect trên Azure thật; Testcontainers chỉ kiểm tra engine/driver local.

## 8. Redis: RedisTemplate hay ReactiveRedisTemplate?

Spring Data Redis cung cấp hai API template. Cả hai có thể dùng Lettuce; khác biệt là contract của application code:

~~~java
// Imperative
String value = stringRedisTemplate.opsForValue().get("product:42");
~~~

~~~java
// Reactive
Mono<String> value =
    reactiveStringRedisTemplate.opsForValue().get("product:42");
~~~

Reactive template:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveProductCache {
    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCache(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> put(String id, String json) {
        return redis.opsForValue().set(
            "product:" + id,
            json,
            Duration.ofMinutes(5));
    }

    public Mono<String> get(String id) {
        return redis.opsForValue().get("product:" + id);
    }
}
~~~

Trong WebFlux, trả publisher để framework điều phối subscription. Với Spring MVC/JDBC, `StringRedisTemplate` thường dễ ghép hơn. Không gọi reactive template rồi `.block()` trong mọi method chỉ để đổi kiểu trả về.

Một số Spring Cache API và Redis repository abstraction có contract imperative; nếu cần reactive Redis data access rõ ràng, dùng `ReactiveRedisTemplate` hoặc API reactive cụ thể. Không suy luận rằng mọi annotation/repository trong Spring Data Redis đều tự trở thành reactive.

## 9. Backpressure và giới hạn concurrency

Reactive Streams cho subscriber quyền yêu cầu upstream phát một số lượng phần tử nhất định. Đây là **backpressure**: downstream chậm có thể giảm demand để upstream không phát vô hạn. Tuy nhiên, backpressure chỉ hoạt động qua các publisher/operator hỗ trợ; nó không tự điều chỉnh RU/s hoặc giới hạn mọi queue trong hệ thống.

### 9.1. Giới hạn concurrency khi gọi nhiều thao tác

~~~java
Flux<OrderDocument> orders = orderIds
    .flatMap(
        id -> reactiveOrderRepository.findById(id),
        16
    );
~~~

`16` giới hạn số inner publisher được subscribe đồng thời trong ví dụ. Chọn concurrency theo connection pool, throughput, RU/s, latency và khả năng downstream. Không dùng `flatMap` không giới hạn cho hàng triệu ID rồi kỳ vọng Reactor tự bảo vệ database.

Với luồng lớn, cân nhắc:

- `limitRate(n)` để điều chỉnh demand theo từng batch.
- `buffer(n)` khi cần nhóm dữ liệu, nhưng nhớ buffer tiêu thụ memory.
- `concatMap` khi cần xử lý tuần tự theo thứ tự.
- `flatMapSequential` khi muốn chạy đồng thời nhưng giữ thứ tự output.
- `onBackpressureBuffer` chỉ khi có giới hạn dung lượng và chiến lược overflow rõ ràng.

### 9.2. Stream database result

`Flux<T>` có thể phát từng item để WebFlux ghi response dần. Điều này giảm nhu cầu giữ toàn bộ kết quả trong heap, nhưng không bảo đảm driver/database luôn stream từng row ngay lập tức. R2DBC driver có fetch size/buffering riêng; Cosmos query có page/continuation và RU; Redis command thường trả một result nhỏ.

Không expose một `Flux` không giới hạn từ toàn bộ database ra HTTP endpoint. Thêm filter, pagination, maximum result size, timeout và giới hạn concurrency. Với API công khai, cursor/pagination thường an toàn và dễ kiểm soát hơn stream không giới hạn.

## 10. Không chặn event loop

Trong WebFlux, event-loop thread phải trả về nhanh. Các thao tác sau có thể chặn:

- JDBC/JPA query.
- `Thread.sleep`, file I/O blocking hoặc gọi HTTP client blocking.
- `Mono.block()`, `Flux.blockLast()`, `toIterable()`.
- CPU-intensive computation kéo dài trên thread I/O.

Ví dụ sai:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> find(@PathVariable long id) {
    Customer customer = jdbcCustomerRepository.findById(id)
        .orElseThrow(CustomerNotFoundException::new);
    return Mono.just(customer);
}
~~~

Controller trả `Mono` nhưng truy vấn JDBC đã chạy đồng bộ trước khi tạo publisher. Request vẫn block event loop.

### 10.1. Cách tốt nhất: dùng driver reactive

Thay JDBC bằng R2DBC hoặc dùng client async của dịch vụ dữ liệu:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> find(@PathVariable long id) {
    return reactiveCustomerRepository.findById(id);
}
~~~

### 10.2. Cầu nối tạm thời cho blocking API

Nếu chưa thể thay driver, cô lập blocking call trên bounded elastic scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<Customer> findCustomer(long id) {
    return Mono.fromCallable(() -> jdbcCustomerRepository.findById(id)
            .orElseThrow(CustomerNotFoundException::new))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là **bridge** để không chặn event loop; JDBC vẫn blocking và cần thread pool hữu hạn. Theo dõi queue, thread usage, timeout và database connection pool. Nếu phần lớn request đều dùng bridge, cân nhắc chuyển về Spring MVC hoặc đầu tư R2DBC thay vì mở rộng boundedElastic vô hạn.

## 11. Đừng tự subscribe trong application service

Publisher là mô tả công việc; nó chạy khi có subscription. Trong request flow, WebFlux subscribe publisher mà controller trả về. Nếu service gọi `.subscribe()` thủ công:

~~~java
public void createOrder(Order order) {
    reactiveOrderRepository.save(order).subscribe();
}
~~~

service đã tách công việc khỏi request lifecycle. Caller không biết khi nào lưu xong, exception có thể không về HTTP error handler, transaction context không đi theo flow và test khó xác minh.

Hãy trả publisher:

~~~java
public Mono<Order> createOrder(Order order) {
    return reactiveOrderRepository.save(order);
}
~~~

Chỉ gọi `.subscribe()` ở ranh giới ứng dụng có chủ đích, chẳng hạn bootstrap/background process có lifecycle, error handler và shutdown policy riêng. Không dùng nó để “kích hoạt” repository call trong controller/service.

## 12. Transaction: imperative và reactive

### 12.1. Imperative transaction

JDBC/JPA thường dùng `PlatformTransactionManager`. `@Transactional` mở transaction gắn với thread hiện tại; các repository dùng cùng transaction manager/DataSource tham gia transaction đó:

~~~java
@Transactional
public Order createOrder(Order order) {
    Order saved = jdbcOrderRepository.save(order);
    auditRepository.record("ORDER_CREATED", saved.id());
    return saved;
}
~~~

### 12.2. Reactive transaction

R2DBC dùng `ReactiveTransactionManager` (thường là `R2dbcTransactionManager`). Transaction context được gắn vào Reactor subscriber Context, không dựa vào ThreadLocal như transaction imperative. Method cần trả publisher để transaction bao trùm toàn bộ chuỗi reactive:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {
    private final ReactiveOrderRepository orders;
    private final ReactiveAuditRepository audit;

    public ReactiveOrderService(
            ReactiveOrderRepository orders,
            ReactiveAuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Mono<Order> create(Order order) {
        return orders.save(order)
            .flatMap(saved ->
                audit.record("ORDER_CREATED", saved.id())
                    .thenReturn(saved));
    }
}
~~~

Ví dụ yêu cầu cả hai repository dùng cùng R2DBC `ConnectionFactory` và reactive transaction manager. Không gọi `.subscribe()` hoặc `.block()` bên trong method; nếu kết thúc publisher trước khi transaction interceptor quản lý, transaction scope sẽ sai.

Reactive transaction không tự tạo distributed transaction giữa PostgreSQL, Cosmos DB, Redis, Blob Storage hoặc Service Bus. Khi nhiều resource độc lập cần phối hợp, vẫn cần outbox/saga/idempotency theo ranh giới dịch vụ.

### 12.3. Không trộn hai transaction manager

Nếu ứng dụng dùng cả JDBC và R2DBC, thường có hai connection factory và hai transaction manager riêng. Một `@Transactional` không tự bao trùm cả hai. Chọn một datastore làm nguồn sự thật cho transaction nghiệp vụ; phối hợp phần còn lại bằng outbox/saga hoặc thiết kế phù hợp.

## 13. Error handling, timeout và retry

Reactive pipeline có các operator xử lý lỗi:

~~~java
return reactiveOrderRepository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(TimeoutException.class,
        error -> new OrderLookupTimeoutException(id, error));
~~~

Đặt timeout ở đúng ranh giới: query timeout, HTTP deadline, pool acquire timeout và request deadline không giống nhau. Timeout ở controller không chắc đã hủy mọi thao tác ở downstream; kiểm tra cancellation support của driver.

Retry chỉ phù hợp với lỗi transient và thao tác có semantics idempotent:

- Retry read thường an toàn về side effect, nhưng dữ liệu có thể thay đổi giữa hai lần đọc.
- Retry create/update cần idempotency key, ETag/version hoặc unique constraint.
- Không retry validation, authentication, authorization hoặc lỗi schema như lỗi mạng tạm thời.
- Dùng backoff + jitter, giới hạn số lần thử và tổng deadline.
- Không retry đồng thời ở controller, service, SDK và gateway mà không có retry budget chung.

Với Cosmos DB, async hay sync không làm thay đổi RU charge, partition key hoặc consistency guarantee. Với Redis, timeout sau `INCR` có thể để lại kết quả không rõ; retry mù quáng có thể tăng hai lần.

## 14. Lifecycle của client và resource

Các client cloud thường tốn chi phí khởi tạo và quản lý connection:

- Tạo một `CosmosClient` hoặc `CosmosAsyncClient` dùng chung cho vòng đời ứng dụng; SDK khuyến nghị client singleton/thread-safe.
- Dùng Spring-managed `RedisConnectionFactory` và Lettuce client; không tạo connection factory mỗi request.
- R2DBC dùng connection pool được cấu hình theo giới hạn database.
- Đóng client, pool và subscription khi ApplicationContext shutdown.
- Không tạo `Mono` rồi giữ mãi mà không subscribe hoặc dispose.

Reactive không có nghĩa là không cần connection pool. Nếu pool quá nhỏ, publisher sẽ chờ lấy connection; nếu pool quá lớn, database có thể cạn connection. Đo active/idle/pending connection, acquisition latency, query duration và retry count.

## 15. Testing

| Mục tiêu | Công cụ/chiến lược |
| --- | --- |
| Kiểm tra publisher phát đúng item, lỗi và completion | Reactor `StepVerifier` |
| Kiểm tra endpoint WebFlux | `WebTestClient` |
| Kiểm tra JDBC/R2DBC SQL và migration | Testcontainers PostgreSQL/MySQL/SQL Server phù hợp |
| Kiểm tra Redis template/cache | Testcontainers Redis hoặc Redis container |
| Kiểm tra Cosmos repository/SDK | Cosmos DB Emulator và Azure test account |
| Kiểm tra cancellation/backpressure | StepVerifier demand, cancel và test stream lớn |
| Kiểm tra transaction rollback | Integration test với đúng transaction manager/driver |
| So sánh throughput/latency | Load test cùng dataset, query, RU, pool và hardware |

Ví dụ StepVerifier:

~~~java
StepVerifier.create(service.findById("order-42"))
    .expectNextMatches(order -> order.id().equals("order-42"))
    .verifyComplete();
~~~

Đừng chỉ test kết quả cuối. Với reactive flow, kiểm tra thêm:

- Publisher có phát lỗi đúng loại không?
- Empty result được ánh xạ đúng không?
- Cancellation có dừng downstream request không?
- Backpressure có giới hạn lượng dữ liệu đang buffer không?
- Transaction rollback khi bước thứ hai thất bại không?
- Có blocking call trên event-loop không?

## 16. Benchmark công bằng

Để quyết định bằng dữ liệu, so sánh hai implementation trên cùng workload:

1. Cùng Azure region, database tier, RU/s/throughput và dataset.
2. Cùng query/partition key/index/consistency level.
3. Cùng số client và request arrival rate.
4. Cùng connection pool limit hoặc resource budget tương đương.
5. Warm-up trước khi lấy số liệu.
6. Chạy nhiều vòng, ghi p50/p95/p99 và error rate.

Đo các chỉ số:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput (requests/s) | Số request hoàn tất trong một đơn vị thời gian |
| p50/p95/p99 latency | Độ trễ trải nghiệm, đặc biệt ở tail |
| CPU/memory | Chi phí xử lý và buffering |
| Thread count/event-loop saturation | Mức sử dụng thread và nguy cơ block |
| Connection pool pending/acquire time | Nút thắt ở pool |
| RU/query và 429 | Chi phí và throttling với Cosmos DB |
| Retry/timeout/cancellation | Độ ổn định khi tải cao hoặc dịch vụ chậm |

Reactive có thể giúp throughput cao hơn khi nhiều request chờ I/O, nhưng nếu bottleneck là RU/s, query scan, CPU serialization hoặc database connection limit, đổi API không giải quyết nguyên nhân đó. Không benchmark chỉ bằng số request trung bình; xem p95/p99 và tài nguyên sử dụng.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng WebFlux với JDBC trực tiếp trên event loop | Event loop bị block, giảm throughput toàn server | Dùng R2DBC hoặc bridge blocking có giới hạn |
| Gọi `.block()` trong controller/service reactive | Chặn thread và có thể gây deadlock/latency | Compose bằng `map`, `flatMap`, `zip` |
| Gọi `.subscribe()` trong service | Mất error/request/transaction context | Trả `Mono`/`Flux` cho caller |
| Cho rằng async luôn nhanh hơn sync | Tăng độ phức tạp nhưng không cải thiện bottleneck | Benchmark và chọn theo workload |
| Cho rằng reactive đồng nghĩa chạy song song | Race condition hoặc concurrency ngoài dự kiến | Giới hạn `flatMap`, dùng operator theo semantics |
| Dùng `flatMap` không giới hạn | Pool/DB/RU bị quá tải | Đặt concurrency và backpressure |
| Bọc JDBC bằng `Mono.just(jdbcCall())` | JDBC chạy trước khi publisher được tạo | Dùng R2DBC hoặc `fromCallable` + boundedElastic tạm thời |
| Dùng JDBC transaction manager cho R2DBC | Reactive transaction không được gắn đúng context | Dùng `R2dbcTransactionManager` |
| Nghĩ Cosmos Async giảm RU | Ước tính chi phí sai | RU phụ thuộc query/data/index, không phụ thuộc kiểu API |
| Dùng R2DBC driver nhưng copy JDBC URL/TLS/auth | Connection fail hoặc security yếu | Theo tài liệu driver cụ thể |
| Chuyển toàn bộ hệ thống sang reactive chỉ để dùng một client async | Tăng chi phí vận hành và độ phức tạp | Có thể giữ MVC và cô lập async boundary |

## 18. Quy trình ra quyết định

~~~mermaid
flowchart TD
    A[Liệt kê toàn bộ I/O trong request] --> B{Phần lớn dependency có non-blocking driver?}
    B -->|Không| C{Có thể thay driver hoặc cô lập blocking?}
    C -->|Không| D[Spring MVC + imperative API]
    C -->|Có| E[Đánh giá WebFlux + reactive pipeline]
    B -->|Có| E
    E --> F{Có nhu cầu concurrency/streaming/backpressure rõ?}
    F -->|Không| G[So sánh độ phức tạp với MVC]
    F -->|Có| H[WebFlux + Mono/Flux]
    G --> I[Benchmark và kiểm tra transaction]
    H --> I
    D --> I
    I --> J[Chọn theo p95, throughput, tài nguyên và maintainability]
~~~

Hỏi lần lượt:

1. Các lời gọi database/cache/HTTP/file trên request là blocking hay non-blocking?
2. Tải có nhiều request đồng thời đang chờ I/O không?
3. Có cần stream dữ liệu hoặc giới hạn demand không?
4. Driver reactive có hỗ trợ đầy đủ tính năng cần dùng không?
5. Transaction có nằm trong một resource hay phối hợp nhiều dịch vụ?
6. Team có thể vận hành Reactor, backpressure, scheduler và debugging không?
7. Benchmark có chứng minh lợi ích trên p95/throughput/CPU/memory không?

Nếu không có lợi ích đo được hoặc dependency vẫn blocking, giữ imperative model thường giảm độ phức tạp.

## 19. Bài tập thực hành

**Bài tập 1 — Cùng use case, hai Cosmos API.** Viết một endpoint đọc order bằng `CosmosRepository` trong Spring MVC và một endpoint bằng `ReactiveCosmosRepository` trong WebFlux. Đo latency và thread usage khi tăng concurrency.

**Bài tập 2 — R2DBC.** Tạo reactive CRUD API trên Azure Database for PostgreSQL bằng Spring Data R2DBC. Kiểm tra TLS, connection pool, `ReactiveCrudRepository` và `WebTestClient`.

**Bài tập 3 — Redis sync/reactive.** Viết cùng một cache service bằng `StringRedisTemplate` và `ReactiveStringRedisTemplate`. Kiểm tra TTL, timeout, error handling và cache miss.

**Bài tập 4 — Phát hiện blocking.** Gọi `JdbcTemplate` từ WebFlux controller, quan sát event-loop thread. Sửa bằng R2DBC, sau đó thử boundedElastic bridge và so sánh.

**Bài tập 5 — Backpressure.** Tạo `Flux` đọc nhiều item Cosmos, dùng `flatMap` concurrency 4, 16 và 64. Ghi lại throughput, RU, 429, memory và p95.

**Bài tập 6 — Transaction.** Viết một service R2DBC có hai thao tác ghi trong `@Transactional`. Cố ý làm bước thứ hai lỗi và xác minh rollback. Sau đó thêm JDBC repository và chứng minh một transaction manager không tự bao trùm cả hai.

**Bài tập 7 — Cancellation.** Dùng StepVerifier hủy subscription giữa một stream query. Kiểm tra driver có dừng việc đọc/giải phóng resource không và ghi nhận giới hạn nếu cancellation chỉ ngừng downstream.

**Bài tập 8 — Benchmark quyết định.** Chạy cùng workload bằng MVC+JDBC và WebFlux+R2DBC. So sánh p50/p95/p99, throughput, CPU, memory, thread count, pool pending và lỗi. Viết khuyến nghị kèm trade-off.

## 20. Ghi nhớ

- **Sync/async** nói về cách caller nhận kết quả; **blocking/non-blocking** nói về thread khi chờ I/O; **reactive** bổ sung Publisher/Subscriber và backpressure.
- Spring MVC phù hợp tự nhiên với JDBC/JPA và imperative service. WebFlux phát huy hiệu quả khi phần lớn pipeline dùng API non-blocking.
- Cosmos DB Java SDK v4 có `CosmosClient` (sync) và `CosmosAsyncClient` (Reactor async); Spring Data Cosmos có `CosmosRepository` và `ReactiveCosmosRepository`.
- PostgreSQL/MySQL/SQL có thể dùng R2DBC nhưng phải có driver tương ứng; JDBC driver không trở thành non-blocking khi bọc trong `Mono`.
- Redis có `RedisTemplate` và `ReactiveRedisTemplate`; chọn contract theo stack và không giả định mọi Spring Cache/repository API đều reactive.
- Không gọi `.block()` hoặc `.subscribe()` trong application service reactive. Trả publisher và compose bằng operator.
- Reactive transaction dùng `ReactiveTransactionManager` và Reactor Context; không tự tạo transaction xuyên JDBC, Cosmos, Redis hoặc broker.
- Backpressure/concurrency phải được cấu hình có chủ đích; đo p95/p99, pool, RU, 429, memory và thread thay vì chỉ nhìn requests/second.
- Chọn API theo workload và benchmark; reactive là công cụ quản lý I/O concurrency, không phải mục tiêu tự thân.

## 21. Tài liệu tham khảo

- [Spring Framework — Spring WebFlux overview and concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Data R2DBC reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
- [Spring Data Redis — Reactive and imperative templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Azure Cosmos DB Java SDK v4 — Sync and Async API performance tips](https://learn.microsoft.com/en-us/azure/cosmos-db/performance-tips-java-sdk-v4-sql)
- [Azure Cosmos DB Java SDK v4 — client library](https://learn.microsoft.com/en-us/java/api/overview/azure/cosmos-readme?view=azure-java-stable)
- [Azure Spring Data Cosmos — CosmosRepository and ReactiveCosmosRepository](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Azure Cosmos DB Developer Guide for Java](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/how-to-guides-spring-data-cosmosdb)
- [Use Spring Data R2DBC with Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-postgresql)
- [Use Spring Data R2DBC with Azure Database for MySQL](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-mysql)
- [Use Spring Data R2DBC with Azure SQL Database](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-sql-server)
- [Reactor Reference Guide — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
