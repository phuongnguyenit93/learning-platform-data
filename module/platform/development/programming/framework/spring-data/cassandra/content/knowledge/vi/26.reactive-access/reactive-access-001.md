# ReactiveCassandraRepository và ReactiveCassandraTemplate

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **reactive access** trong Spring Data Cassandra: dùng Reactor `Mono` / `Flux` và driver hỗ trợ bất đồng bộ để thực hiện truy cập dữ liệu theo mô hình không chặn luồng chờ I/O.
- Phân biệt vai trò của **`ReactiveCassandraRepository`** với **`ReactiveCassandraTemplate`** / `ReactiveCassandraOperations`; biết khi nào dùng derived query, `@Query` hoặc truy vấn động.
- Xây entity `@Table`, `@PrimaryKey` và repository reactive để đọc/ghi bản ghi Cassandra; hiểu chuỗi xử lý từ Spring WebFlux → service → repository/template → Cassandra Java Driver.
- Sử dụng đúng `Mono<T>`, `Flux<T>`, `Mono<Void>`, `flatMap`, `concatMap`, `switchIfEmpty` và `onErrorResume`; phân biệt **khởi tạo publisher** với **subscribe để thực thi**.
- Tránh chặn event loop bằng `block()`, `Thread.sleep` hoặc gọi API đồng bộ trong chuỗi reactive; biết khi nào nên cô lập việc bắt buộc phải blocking.
- Thiết kế truy vấn **có đầy đủ partition key**, giới hạn dữ liệu theo CQL `LIMIT`, clustering order, time bucket; không suy rằng reactive tự sửa `ALLOW FILTERING` hoặc thiết kế bảng sai.
- Hiểu **backpressure, fetch size, paging state** và tác động của `collectList()`, `take()`, `limitRate()` đối với tải và bộ nhớ; không nhầm reactive streaming với truy cập random page.
- Cấu hình request consistency, deadline, retry/idempotency và quan sát lỗi tại ranh giới Spring Data/Java Driver đúng semantics Cassandra.
- Viết endpoint WebFlux, kiểm thử bằng `StepVerifier` và integration test có Cassandra thực; quan sát p95/p99, pool/in-flight, hot partitions, cancellation và load.
- Phân biệt các bảo đảm của reactive programming với **transaction/CAS/LWT**, và không mặc định subscribe lặp lại hoặc `retryWhen` là an toàn cho mọi write.

Bài thuộc chương **Truy cập phản ứng** (`menuLevel1`) trong **SPRING_DATA_CASSANDRA**. Mô-đun học cách truy cập Apache Cassandra bằng Spring Data Cassandra, entity mapping, repository, `CassandraTemplate` và CQL; thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng trong mô hình dữ liệu phân tán. Trong bài này, trọng tâm là hai giao diện reactive ở tầng truy cập: `ReactiveCassandraRepository` và `ReactiveCassandraTemplate`. Chúng bổ sung khả năng tổ chức luồng không chặn, **không thay đổi quy tắc truy vấn của Cassandra**.

> **Điểm cốt lõi:** `ReactiveCassandraRepository` giúp khai báo CRUD và query methods; `ReactiveCassandraTemplate` cho quyền điều khiển truy vấn và mapping linh hoạt hơn. Cả hai có thể trả `Mono`/`Flux` và thực hiện I/O không chặn, nhưng **query chỉ hiệu quả khi schema, partition key và request options đúng**. Reactive cũng **không đồng nghĩa** transaction nhiều bảng, đúng một lần thực thi hay đọc toàn bảng miễn phí.

## 1. Reactive access giải quyết vấn đề gì?

Giả sử một API HTTP phải đọc đơn hàng từ Cassandra. Với cách viết đồng bộ, một request thread có thể bị giữ trong lúc chờ I/O:

~~~text
HTTP request thread
  -> gọi repository đồng bộ
  -> chờ Cassandra trả kết quả
  -> chuyển row thành JSON
  -> trả response
~~~

Khi hàng nghìn request cùng chờ mạng, số thread bị chiếm và chi phí context switching có thể tăng. Với mô hình reactive, ta mô tả pipeline dữ liệu bằng `Publisher`, rồi runtime đăng ký nhận kết quả bất đồng bộ:

~~~mermaid
flowchart TD
    A["HTTP request - Spring WebFlux"] --> B["Service trả Mono/Flux"]
    B --> C{"Đường truy cập?"}
    C --> D["ReactiveCassandraRepository"]
    C --> E["ReactiveCassandraTemplate"]
    D --> F["Cassandra Java Driver async/reactive"]
    E --> F
    F --> G["Cassandra cluster: partition/replicas"]
    G --> H["onNext / onComplete / onError"]
    H --> I["WebFlux encode và gửi response"]
~~~

Điểm đáng chú ý:

- **Non-blocking I/O:** request không phải giữ một thread đợi Cassandra trong toàn bộ thời gian mạng.
- **Asynchronous signals:** dữ liệu đến bằng `onNext`, kết thúc bằng `onComplete`, lỗi bằng `onError`.
- **Composition:** có thể ghép nhiều thao tác bằng `flatMap`, `zipWhen`, `concatMap`, nhưng phải hiểu chi phí và concurrency.
- **Backpressure:** downstream có thể yêu cầu lượng dữ liệu phù hợp qua `request(n)`; hiệu quả với tài nguyên thực phụ thuộc driver/page fetch và cả mã ứng dụng.
- **Cancellation:** downstream có thể hủy subscription, nhưng cancellation không bảo đảm mutation đã gửi đến Cassandra sẽ bị rollback.
- **Cold publishers:** nhiều truy vấn được xây theo mô hình lazy; một lần subscribe mới kích hoạt I/O, và subscribe lại có thể chạy lại truy vấn.

Không nên tuyên bố reactive **luôn** nhanh hơn blocking. Nó giúp quản lý concurrency, resource usage và pipeline tốt hơn trong workload phù hợp; latency của một query Cassandra vẫn bị quyết định bởi schema, replica, độ trễ mạng, dữ liệu và mức tải.

### 1.1. Bảng so sánh dễ nhớ

| Góc nhìn | Đồng bộ | Reactive |
| --- | --- | --- |
| Đơn vị phản hồi đơn | `T` hoặc `Optional<T>` | `Mono<T>` |
| Nhiều row | `List<T>`, `Iterable<T>`, `Slice<T>` | `Flux<T>` |
| Chờ I/O | Có thể block caller thread | Lõi truy cập reactive không cần block chờ I/O |
| Lỗi | Throw exception | `onError` signal |
| Thời điểm thực thi | Thường khi gọi method | Thường khi subscriber đăng ký |
| Kết hợp thao tác | Câu lệnh tuần tự | Reactor operators với concurrency được kiểm soát |
| Giới hạn Cassandra | Vẫn phải tuân thủ CQL | **Vẫn phải tuân thủ CQL** |
| Độ chính xác transaction | Phụ thuộc Cassandra và thiết kế | **Không tự tăng lên** vì dùng Flux/Mono |

### 1.2. Khi nào reactive có ích?

- API có nhiều request I/O-bound gọi Cassandra đồng thời.
- Streaming hoặc xử lý danh sách theo từng phần mà không giữ toàn bộ kết quả trong RAM.
- Ghép truy vấn với các nguồn cũng hỗ trợ reactive.
- Kiểm soát concurrency, timeout, cancellation và metrics dưới tải.
- Dịch vụ đã dùng Spring WebFlux và Reactor xuyên suốt.

Nếu ứng dụng chỉ thực hiện các tác vụ batch nhỏ đồng bộ, hoặc toàn bộ dependency của workflow là blocking, chuyển sang reactive có thể tăng độ phức tạp mà không cải thiện thực tế. Cần đo trước/sau và cân nhắc năng lực vận hành.

## 2. Reactor Mono và Flux trong Spring Data Cassandra

`Mono<T>` phát ra **0 hoặc 1 phần tử** rồi hoàn tất (hoặc phát lỗi). `Flux<T>` phát ra **0 đến nhiều phần tử**.

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

Mono<String> one = Mono.just("P001");
Mono<String> empty = Mono.empty();

Flux<Integer> several = Flux.just(1, 2, 3);
Flux<Integer> none = Flux.empty();
~~~

Các publisher trên chỉ dùng dữ liệu trong bộ nhớ. Khi method của Spring Data Cassandra trả về `Mono<Product>` hoặc `Flux<Order>`, các tín hiệu xuất phát từ **truy vấn Cassandra** được kết hợp qua Reactor. Đó là nơi phải kiểm soát câu query, tài nguyên và subscription.

### 2.1. Một luồng reactive gồm những tín hiệu gì?

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Flux/Mono
    participant D as Reactive Cassandra Driver
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P->>D: Khởi động/fetch query
    D-->>P: Rows / result
    P-->>S: onNext(value)
    P-->>S: onComplete()
~~~

Nếu query thất bại, publisher sẽ phát `onError(Throwable)` thay vì `onComplete()` thành công.

Không có dữ liệu không nhất thiết là lỗi:

- `Mono.empty()` có thể nghĩa là không tìm thấy row theo ID.
- `Flux.empty()` có thể nghĩa không có hàng khớp điều kiện.
- `onError` nghĩa truy vấn hoặc pipeline có sự cố, không nên tự đổi thành “không tìm thấy” trừ khi contract nghiệp vụ cho phép.

### 2.2. Cold publisher và subscribe lặp lại

~~~java
Mono<ProductById> lookup = repository.findById(productId);

// Thường lúc này mới có mô tả truy vấn, chưa cần thực thi I/O.
lookup.subscribe(product -> log.debug("subscriber A {}", product.getId()));
lookup.subscribe(product -> log.debug("subscriber B {}", product.getId()));
~~~

Một publisher cold khi được subscribe hai lần thường **thực thi hai lần**; vì vậy không gọi `subscribe()` hai lần chỉ để “chắc chắn”. Reactor có `cache()`, `share()` và các toán tử multicast với semantics riêng, nhưng dùng chúng cho truy vấn có dữ liệu thay đổi có thể làm stale data hoặc khó kiểm soát tài nguyên.

**Đặc biệt với write:** nếu `repository.save(entity)` hoặc mutation tương tự được subscribe hai lần, thao tác có thể được thực thi hai lần. Với counter increment, TTL, append hoặc side effect nghiệp vụ, hậu quả có thể đáng kể. Reactive không tự biến write thành lũy đẳng.

### 2.3. Ai là subscriber cuối cùng?

Trong Spring WebFlux, nếu controller trả `Mono<ResponseEntity<T>>` hoặc `Flux<T>`, **WebFlux là subscriber**. Service/repository nên **return publisher** và để framework quản lý vòng đời request.

~~~java
// Đúng: trả publisher để WebFlux subscribe.
@GetMapping("/products/{id}")
public Mono<ProductById> find(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

Không làm:

~~~java
// Sai: subscribe thủ công, trả response trước khi query hoàn tất.
@GetMapping("/products/{id}")
public Mono<Void> broken(@PathVariable UUID id) {
    productService.findById(id)
        .subscribe(product -> log.info("Found {}", product));
    return Mono.empty();
}
~~~

Mẫu sai khó kiểm soát errors, cancellation, lifecycle và tracing; request HTTP có thể kết thúc trước khi tác vụ phụ hoàn thành.

## 3. Chuẩn bị project và kết nối Cassandra

Với Spring Boot tương thích phiên bản Spring Data Cassandra, dependency reactive là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Đối với Gradle, tên dependency tương ứng:

~~~groovy
implementation "org.springframework.boot:spring-boot-starter-data-cassandra-reactive"
implementation "org.springframework.boot:spring-boot-starter-webflux"
~~~

Phiên bản Spring Boot/Spring Data/Reactor/Java Driver phải tương thích BOM. Không tự ép driver version khác BOM chỉ vì muốn một method mới. Điều này đặc biệt quan trọng khi driver có thay đổi về reactive API, codec hoặc execution profiles.

### 3.1. Cấu hình ví dụ

~~~yaml
spring:
  cassandra:
    contact-points: localhost:9042
    keyspace-name: shop
    local-datacenter: datacenter1
    schema-action: none
~~~

`localhost:9042` và `datacenter1` là giá trị minh họa cho môi trường học; phải thay bằng contact points/DC thật hoặc cấu hình cluster test. `schema-action: none` thể hiện chủ trương quản lý schema CQL bằng migration có kiểm soát.

Một cluster Cassandra cần:

- Keyspace và replication đúng topology.
- Đầy đủ bảng/index cho các câu query.
- Network/TLS/auth nếu triển khai production.
- Quyền truy cập tối thiểu cho service.
- Driver session quản lý bởi Spring, không tạo mới theo từng request.
- Cấu hình timeout, consistency, retry/speculative execution và metrics được kiểm thử.

### 3.2. Spring Boot tự cấu hình gì?

Khi dependency và properties phù hợp, Spring Boot có thể tự cấu hình `CqlSession`, infrastructure mapping/converter và các bean `ReactiveCassandraTemplate` / reactive repositories. Những API/annotation cụ thể phụ thuộc phiên bản Boot/Spring Data.

Nếu dự án không dùng auto-configuration, có thể khai báo cấu hình reactive repositories bằng annotation thích hợp như `@EnableReactiveCassandraRepositories` và các beans Cassandra cần thiết. **Không dùng cả hai cách không kiểm soát** vì có thể tạo duplicate repository registrations/session.

### 3.3. Không có “cluster reactive” riêng

Reactive Cassandra thường dùng **cùng giao thức CQL và Java Driver** để truy cập Cassandra. Phía ứng dụng khác ở API và luồng bất đồng bộ; backend Cassandra vẫn có partition, replicas, consistency levels, paging state, compaction và tombstones như thông thường.

## 4. Thiết kế schema theo đường truy vấn

Giả sử hệ thống cửa hàng có hai đường đọc:

1. Tra cứu **chi tiết sản phẩm** theo `product_id`.
2. Xem **đơn hàng gần nhất** của một khách hàng trong một tháng.

Không nên chỉ tạo một bảng `orders` rồi hi vọng reactive stream sẽ tìm/sắp xếp mọi cột hiệu quả. Cần bảng theo access pattern.

### 4.1. Bảng tra sản phẩm theo ID

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

CREATE TABLE IF NOT EXISTS shop.products_by_id (
    product_id uuid PRIMARY KEY,
    sku text,
    name text,
    price decimal,
    status text,
    updated_at timestamp
);
~~~

Tra cứu hiệu quả:

~~~sql
SELECT product_id, sku, name, price, status, updated_at
FROM shop.products_by_id
WHERE product_id = ?;
~~~

Vì query biết toàn bộ partition key, Cassandra có thể định vị partition tương ứng. Reactive không phải lý do thêm `ALLOW FILTERING`.

### 4.2. Bảng đơn hàng theo customer + month

~~~sql
CREATE TABLE IF NOT EXISTS shop.orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Truy vấn:

~~~sql
SELECT customer_id, month_bucket, created_at, order_id,
       status, total_amount
FROM shop.orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Thứ tự clustering được xác định **trong partition**. Nếu cần history qua nhiều tháng, ứng dụng phải chuyển bucket và quản lý cursor; không có global `ORDER BY` cho các partition tùy ý.

### 4.3. Vì sao composite key có tie-breaker?

Hai đơn có thể tạo trong cùng millisecond. Nếu chỉ dùng `created_at` làm clustering key, chúng có thể va chạm khóa. Bổ sung `order_id` đảm bảo primary key có khả năng phân biệt, đồng thời hữu ích cho keyset pagination dựa trên `(created_at, order_id)`.

## 5. Entity và ReactiveCassandraRepository cơ bản

Spring Data Cassandra ánh xạ row CQL thành Java object qua annotations. Ví dụ entity `ProductById`:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("products_by_id")
public class ProductById {

    @PrimaryKey("product_id")
    private UUID productId;

    @Column("sku")
    private String sku;

    @Column("name")
    private String name;

    @Column("price")
    private BigDecimal price;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    public ProductById() {}

    // Constructors, getters và setters cần thiết.
}
~~~

Đối với cột CQL `timestamp`, `Instant` là kiểu Java phù hợp cho thời điểm tuyệt đối. Lưu ý Cassandra lưu timestamp với độ phân giải milliseconds, nên không kỳ vọng giữ nanoseconds của `Instant` sau round-trip.

### 5.1. Reactive repository interface

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

public interface ProductRepository
        extends ReactiveCassandraRepository<ProductById, UUID> {
}
~~~

Repository kế thừa các phép CRUD reactive thường dùng:

| Method khái niệm | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `findById(id)` | `Mono<ProductById>` | Không có row → Mono trống |
| `existsById(id)` | `Mono<Boolean>` | Truy vấn sự tồn tại của row |
| `save(product)` | `Mono<ProductById>` | Lưu/upsert entity phù hợp mapping |
| `deleteById(id)` | `Mono<Void>` | Thao tác xóa theo ID, không phát entity |
| `findAll()` | `Flux<ProductById>` | Trả nhiều row, **có thể là quét bảng lớn** |

**Cảnh báo `findAll()`:** dù trả `Flux` và có thể không giữ hết dữ liệu trong một `List`, việc quét một bảng Cassandra lớn vẫn rất tốn kém. Reactive chỉ ảnh hưởng cách tiêu thụ và concurrency, **không biến full scan thành truy vấn có partition key**.

### 5.2. Service reactive

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductById> findById(UUID id) {
        return repository.findById(id);
    }

    public Mono<ProductById> save(ProductById product) {
        return repository.save(product);
    }

    public Mono<Void> deleteById(UUID id) {
        return repository.deleteById(id);
    }
}
~~~

Service **không gọi `block()`**. Nó trả publisher lên tầng controller để WebFlux chịu trách nhiệm subscription và phát response.

### 5.3. Controller WebFlux

~~~java
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductById>> get(
            @PathVariable UUID id) {

        return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<ProductById> create(@RequestBody ProductById product) {
        return service.save(product);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> delete(@PathVariable UUID id) {
        return service.deleteById(id);
    }
}
~~~

Đây là ví dụ cơ sở. Production cần validation/authentication, xử lý idempotency của POST, xung đột và timeout. `save` không mặc định là insert-only; nó có thể upsert trùng primary key theo semantics Cassandra. Nếu bắt buộc “tạo chỉ khi chưa tồn tại”, dùng LWT `IF NOT EXISTS` hoặc API Spring Data hỗ trợ conditional insert.

## 6. Repository query methods và @Query

Repository reactive có thể khai báo thêm method theo tên thuộc tính hoặc bằng CQL `@Query`. Tuy nhiên, việc method được parse thành công **không chứng minh query hiệu quả**: CQL vẫn đòi partition key/đường truy cập hợp lệ.

### 6.1. Tạo repository theo bảng phục vụ danh sách

Entity cho bảng đơn hàng có khóa ghép. Một cách biểu diễn là `@PrimaryKeyClass`:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class CustomerOrderKey implements Serializable {

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private UUID orderId;

    public CustomerOrderKey() {}

    // Constructors, getters/setters, equals và hashCode.
}
~~~

Entity:

~~~java
import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private CustomerOrderKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {}

    // Constructors, getters và setters.
}
~~~

**Chú ý:** `CustomerOrderKey` phải cài đặt `equals` và `hashCode` ổn định theo đủ các field khóa; ví dụ rút gọn chỉ trình bày mapping. Cột clustering/order trong entity phải nhất quán với CQL đã tạo.

### 6.2. Repository truy vấn theo partition

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import org.springframework.data.repository.query.Param;
import reactor.core.publisher.Flux;

public interface CustomerOrderRepository
        extends ReactiveCassandraRepository<
            OrderByCustomerMonth, CustomerOrderKey> {

    @Query(
        "SELECT * FROM orders_by_customer_month " +
        "WHERE customer_id = :customerId " +
        "AND month_bucket = :monthBucket " +
        "LIMIT 20"
    )
    Flux<OrderByCustomerMonth> findLatestInMonth(
        @Param("customerId") UUID customerId,
        @Param("monthBucket") String monthBucket
    );
}
~~~

Đường đọc này trả `Flux` nhưng **đã giới hạn ở CQL `LIMIT 20`**, chỉ chạm một partition. Query không có `ORDER BY` thêm vì bảng đã có clustering order. Nếu muốn thứ tự khác, cần kiểm tra ràng buộc Cassandra về `ORDER BY` trên clustering columns.

### 6.3. Derived query và @Query khác gì?

| Cách khai báo | Ưu điểm | Điểm cần kiểm soát |
| --- | --- | --- |
| `findById` có sẵn | Ngắn, đúng primary key | Không dùng cho query nhiều bản ghi |
| Derived query method | Giảm viết CQL cho truy vấn đơn giản | Đảm bảo điều kiện tương ứng partition/index |
| `@Query` viết CQL | Kiểm soát cột, LIMIT, điều kiện | String CQL cần bảo trì khi schema đổi |
| `ReactiveCassandraTemplate` | Dựng Query/Criteria linh hoạt hơn | Code nhiều hơn, vẫn phải kiểm tra access pattern |
| Java Driver reactive trực tiếp | Kiểm soát statement/profiles/paging | Phải tự mapping và error handling nhiều hơn |

Không mở API filter mọi field của entity rồi tự xây `WHERE` ngẫu nhiên trên một bảng Cassandra. Với bộ lọc nhiều chiều, cân nhắc read model khác, index phù hợp hoặc hệ tìm kiếm chuyên dụng.

## 7. ReactiveCassandraTemplate: điều khiển truy vấn linh hoạt

`ReactiveCassandraTemplate` là triển khai của các reactive Cassandra operations. Thay vì định nghĩa mọi query thành repository method, có thể dùng `Query`, `Criteria` và mapping entity để xây truy vấn có điều kiện hợp lệ.

### 7.1. Hai cách nhìn khác nhau

~~~text
ReactiveCassandraRepository
  - Interface theo entity, ID
  - Có sẵn findById/save/delete và query methods
  - Hợp CRUD/access pattern cố định

ReactiveCassandraTemplate
  - API thao tác theo Query/Criteria/entity class
  - Linh hoạt với selection, giới hạn, insert và các thao tác khác
  - Hợp custom data access không nên mở rộng thành nhiều method
~~~

Cả hai đều dựa trên infrastructure mapping Cassandra và cùng yêu cầu schema chính xác. Chúng không tự tạo join, global sorting hay transaction nhiều bảng.

### 7.2. Đọc một sản phẩm bằng template

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ProductTemplateReader {

    private final ReactiveCassandraOperations operations;

    public ProductTemplateReader(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<ProductById> findById(UUID productId) {
        return operations.selectOneById(productId, ProductById.class);
    }
}
~~~

`ReactiveCassandraOperations` là interface ưu tiên để code dễ thay implementation/test. Bạn cũng có thể inject trực tiếp `ReactiveCassandraTemplate` khi cần một API cụ thể của implementation, nhưng nên chỉ phụ thuộc lớp cụ thể khi thật sự cần.

Nếu `productId` không có row, reactive result thường hoàn tất rỗng (`Mono.empty()`). Không tự chuyển một lỗi query thành empty nếu muốn API còn phân biệt “404” với “Cassandra unavailable”.

### 7.3. Query và Criteria

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import reactor.core.publisher.Flux;

public final class ProductQueryAdapter {

    private final ReactiveCassandraOperations operations;

    public ProductQueryAdapter(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Flux<ProductById> findMatchingId(UUID productId) {
        Query query = Query.query(
            Criteria.where("product_id").is(productId)
        );

        return operations.select(query, ProductById.class);
    }
}
~~~

Mẫu này có vẻ đơn giản, nhưng thể hiện nguyên tắc: `Query` dùng tên cột CQL phù hợp metadata; việc bind/mapping được xử lý qua Spring Data, còn **khả năng thực hiện hiệu quả vẫn do partition key**.

### 7.4. Query một tháng đơn hàng bằng template

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import reactor.core.publisher.Flux;

public class CustomerOrderTemplateReader {

    private final ReactiveCassandraOperations operations;

    public CustomerOrderTemplateReader(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Flux<OrderByCustomerMonth> findMonth(
            UUID customerId,
            String monthBucket) {

        Query query = Query.query(
            Criteria.where("customer_id").is(customerId)
        ).and(
            Criteria.where("month_bucket").is(monthBucket)
        ).limit(20);

        return operations.select(
            query, OrderByCustomerMonth.class);
    }
}
~~~

Điều kiện này ràng buộc cả hai thành phần partition key. `limit(20)` là **CQL/result limit** của truy vấn do Spring Data tạo, giúp tránh một request tải toàn bộ partition. Nếu muốn phân trang, thêm hợp đồng cursor cụ thể thay vì tự nhảy offset.

### 7.5. Tạo mới bằng template

~~~java
public Mono<ProductById> insert(ProductById product) {
    return operations.insert(product);
}
~~~

Spring Data thường trả entity đã được ánh xạ từ thao tác insert. Tuy nhiên, tên `insert` **không tự đảm bảo insert-only** theo nghĩa RDBMS nếu không có điều kiện `IF NOT EXISTS`. Cassandra write thường có ngữ nghĩa upsert theo primary key. Khi tạo resource không cho phép ghi đè, phải dùng conditional insert phù hợp và kiểm tra LWT outcome.

### 7.6. Khi nào repository, khi nào template?

| Tình huống | Lựa chọn ưu tiên |
| --- | --- |
| CRUD một entity theo ID | `ReactiveCassandraRepository` |
| Một số truy vấn CQL cố định theo partition | Repository + `@Query` |
| Nhiều biến thể giới hạn/chọn cột nhưng vẫn cùng partition | Template + `Query` |
| Cần tùy chọn statement đặc biệt (execution profile, trace, paging state) | Template nếu API hỗ trợ, hoặc Java Driver reactive |
| Query phức hợp đa bảng | Thiết kế lại read model/service workflow; template không tự JOIN |
| Mutation counter với retry policy riêng | Adapter Java Driver/operations có CQL kiểm soát, không gọi save tùy tiện |
| CAS với kết quả `[applied]` tường minh | CQL điều kiện, Spring Data options hoặc driver tùy mức kiểm soát |

**Không cần dùng template cho mọi thao tác**. Repository giúp biểu đạt domain access pattern rõ ràng. Template là công cụ khi query động hoặc có logic data access đặc thù, không phải cấp độ “reactive hơn” repository.

## 8. Các Reactor operators thường dùng với Cassandra

### 8.1. map: biến đổi entity thành DTO

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;

public record ProductResponse(
    UUID id, String name, String status) {}

public Mono<ProductResponse> get(UUID id) {
    return repository.findById(id)
        .map(product -> new ProductResponse(
            product.getProductId(),
            product.getName(),
            product.getStatus()
        ));
}
~~~

`map` phù hợp phép biến đổi **đồng bộ, nhẹ, không chặn**. Không đặt REST call đồng bộ, JDBC query hoặc thao tác file lớn bên trong `map` trên event loop.

### 8.2. flatMap: thao tác tiếp theo cũng reactive

Giả sử có hai bảng/read models riêng và muốn lấy chi tiết bổ sung:

~~~java
public Mono<ProductSummary> findSummary(UUID productId) {
    return repository.findById(productId)
        .flatMap(product ->
            inventoryReactiveReader.findByProductId(productId)
                .map(stock -> combine(product, stock))
        );
}
~~~

`inventoryReactiveReader` phải thực sự trả publisher không chặn, và `combine` chỉ là xử lý CPU ngắn. Nếu inventory source chậm hoặc không sẵn sàng, kết quả tổng hợp sẽ chịu lỗi/độ trễ tương ứng. Hai read models không tự có snapshot chung; ở Cassandra, các bảng denormalized có thể cập nhật không đồng bộ.

### 8.3. switchIfEmpty: phân biệt không có row

~~~java
public Mono<ProductById> requireProduct(UUID productId) {
    return repository.findById(productId)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(productId)
        ));
}
~~~

`Mono.error` tạo signal lỗi. Phía controller/`@RestControllerAdvice` có thể ánh xạ `ProductNotFoundException` thành 404; không cần viết `subscribe` thủ công.

Nếu fallback là một truy vấn khác, nên tạo publisher lazily:

~~~java
return repository.findById(productId)
    .switchIfEmpty(Mono.defer(() ->
        legacyProductReader.findById(productId)
    ));
~~~

`Mono.defer` đặc biệt hữu ích khi code tạo fallback có side effect hoặc chi phí lúc assembly. Đảm bảo đường fallback có quyền truy cập/consistency rõ ràng, không tự lấy dữ liệu tenant khác.

### 8.4. zip và zipWhen: kết hợp dữ liệu

~~~java
Mono<ProductResponse> details = productRepo.findById(productId)
    .zipWhen(product ->
        stockReader.findAvailable(product.getProductId())
    )
    .map(tuple -> new ProductResponse(
        tuple.getT1().getProductId(),
        tuple.getT1().getName(),
        tuple.getT1().getStatus()
    ));
~~~

Đoạn ví dụ chỉ minh họa phối hợp hai nguồn; nếu muốn trả cả stock thì DTO phải có field stock. Quan trọng là các truy vấn có thể được phối hợp mà không block thread. Tuy nhiên, `zip` cũng có semantics khi một nguồn empty: cần định nghĩa fallback trước khi ghép nếu nghiệp vụ mong đợi đủ dữ liệu.

### 8.5. concatMap và flatMap trên danh sách

Giả sử cần cập nhật một tập sản phẩm đã chọn (mỗi phần tử có primary key riêng). Hai lựa chọn:

~~~java
Flux<ProductById> updates = Flux.fromIterable(products)
    .flatMap(productRepo::save, 8);
~~~

`flatMap(..., 8)` cho phép tối đa khoảng 8 inner publishers cùng được xử lý; hữu ích khi các thao tác độc lập, nhưng thứ tự kết quả có thể khác thứ tự đầu vào. Không dùng concurrency tùy tiện với nhiều writes đến **cùng một primary key**.

Nếu cần giữ thứ tự thao tác:

~~~java
Flux<ProductById> sequential = Flux.fromIterable(products)
    .concatMap(productRepo::save);
~~~

`concatMap` tuần tự hơn và giữ thứ tự phát; nhưng **chỉ giữ thứ tự gọi trong pipeline này**, không loại bỏ concurrent writers đến cùng key ở các service khác. Nếu cần CAS/business ordering, dùng LWT/revision thích hợp.

### 8.6. onErrorResume: phải giữ được khác biệt lỗi

~~~java
return repository.findById(productId)
    .onErrorResume(
        ProductNotFoundException.class,
        ex -> Mono.empty()
    );
~~~

Đây chỉ là ví dụ xử lý một **loại lỗi nghiệp vụ** đã định nghĩa. Với Cassandra timeout, unavailable, authentication failure hoặc mapping error, **không** nên áp:

~~~java
// Phản mẫu: giấu mọi lỗi cơ sở dữ liệu thành 404.
return repository.findById(productId)
    .onErrorResume(ex -> Mono.empty());
~~~

Một API trả 404 khi cluster Cassandra đang down sẽ gây sai chẩn đoán và sai dữ liệu nghiệp vụ. Nên phân loại và ánh xạ thành lỗi server tương ứng, giữ correlation ID/tracing.

## 9. Không chặn event loop trong pipeline reactive

### 9.1. Vì sao block() trong controller là nguy hiểm?

~~~java
// Phản mẫu trong ứng dụng WebFlux:
@GetMapping("/products/{id}")
public ProductById wrong(@PathVariable UUID id) {
    return repository.findById(id).block();
}
~~~

`block()` chờ I/O trên thread đang xử lý và làm mất lợi ích non-blocking; tùy runtime, việc block trên reactor non-blocking thread có thể bị từ chối bằng exception. Dùng:

~~~java
@GetMapping("/products/{id}")
public Mono<ProductById> correct(@PathVariable UUID id) {
    return repository.findById(id);
}
~~~

Trong unit test hoặc một công cụ command-line, `block()` có thể là cầu nối có kiểm soát khi thật sự cần, nhưng không nên xuất hiện trong request handler WebFlux, Reactor operator hoặc callback của driver.

### 9.2. Đừng giả vờ reactive bằng Mono.just(blockingCall())

~~~java
// Sai: blockingCall() chạy ngay khi dựng publisher.
Mono<ProductById> wrong = Mono.just(
    legacyBlockingDao.findById(productId)
);
~~~

Nếu bắt buộc gọi thư viện blocking:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<ProductById> bridge = Mono.fromCallable(
        () -> legacyBlockingDao.findById(productId)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Mẫu này cô lập blocking task sang scheduler dành cho blocking I/O; nó **không biến driver đồng bộ thành truy cập Cassandra reactive thực sự** và vẫn phải giới hạn concurrency. Nếu thư viện đã có reactive API, ưu tiên API đó.

### 9.3. Những thao tác dễ block

- `Thread.sleep`, `Future.get`, `CountDownLatch.await` trong `map`/`flatMap`.
- JDBC/JPA/blocking Cassandra repository trong WebFlux pipeline.
- Gọi REST client đồng bộ thay vì WebClient.
- Đọc ghi file bằng blocking API trên event-loop.
- Serialize payload rất lớn bằng xử lý CPU kéo dài trong một callback.
- Đặt `subscribe()` thủ công rồi chờ kết quả bằng biến chia sẻ.

Chỉ cần **một thành phần blocking** trong chuỗi có thể làm throughput và latency toàn endpoint xấu đi.

## 10. Backpressure không tự bảo đảm query rẻ

Reactive Streams cho phép subscriber yêu cầu số phần tử qua `request(n)`. Nhưng Cassandra đọc dữ liệu theo **trang của driver**, và việc phát tín hiệu `onNext` không đồng nghĩa mỗi row được truy vấn bằng một CQL round-trip riêng.

### 10.1. Backpressure hoạt động ở đâu?

~~~mermaid
flowchart LR
    A["Subscriber demand request(n)"] --> B["Reactor Flux"]
    B --> C["Driver reactive publisher"]
    C --> D["CQL pages / fetch"]
    D --> E["Cassandra replicas"]
    E --> F["Dữ liệu được giải mã"]
    F --> B
~~~

Một driver có thể prefetch hoặc giữ trong bộ nhớ một số row/trang trước khi downstream nhận hết, tùy implementation và request options. Do đó:

- `limitRate(n)` điều chỉnh nhu cầu ở tầng Reactor, **không** thay CQL `LIMIT`.
- `take(20)` hủy/hoàn thành sau khi tiêu thụ 20 item, nhưng query phía dưới có thể đã fetch nhiều hơn.
- `collectList()` phải giữ tất cả phần tử đã phát vào list, có thể gây tăng memory khi kết quả rất lớn.
- `buffer(100)` tạo các lô tại tầng client, không nhất thiết thay đổi page size/round-trip của driver.
- Dữ liệu rộng hoặc partition lớn vẫn đắt dù subscriber chỉ cần vài phần tử.

### 10.2. Query limit và Reactor take khác nhau

~~~java
// CQL không giới hạn; có thể tốn tải dù client take(20).
Flux<ProductById> risky = repository.findAll()
    .take(20);
~~~

So với:

~~~java
Query query = Query.query(
    Criteria.where("customer_id").is(customerId)
).and(
    Criteria.where("month_bucket").is(monthBucket)
).limit(20);

Flux<OrderByCustomerMonth> bounded =
    template.select(query, OrderByCustomerMonth.class);
~~~

Mẫu thứ hai ràng buộc partition và row count ở tầng CQL. `Flux` là cách nhận kết quả, không phải một chiến lược truy vấn.

### 10.3. collectList() và bộ nhớ

~~~java
// Nguy hiểm khi kết quả là hàng triệu row:
Mono<List<ProductById>> all = repository.findAll().collectList();
~~~

Ngay cả khi nguồn phát row bằng non-blocking I/O, `collectList()` vẫn phải giữ toàn bộ collection trong memory. Với HTTP JSON array, serializer/proxy có thể còn tạo buffering tùy hình thức response.

Nếu đã giới hạn query ở 20 row thì `collectList()` có thể phù hợp để dựng DTO danh sách; với export rất lớn, cần streaming/partitioning, backpressure và giới hạn kích thước thay vì `List` tất cả.

### 10.4. Điều tiết concurrency khi fan-out

Ví dụ lấy nhiều IDs từ một nguồn đáng tin cậy:

~~~java
Flux<ProductById> products = Flux.fromIterable(productIds)
    .flatMap(repository::findById, 8);
~~~

Giới hạn concurrency 8 là **giá trị minh họa**, phải đo theo số request in-flight, driver pool, p99, rate limit và tải cluster. Tránh tạo hàng nghìn truy vấn đồng thời không giới hạn chỉ vì code reactive có thể biểu diễn chúng dễ dàng.

### 10.5. Streaming HTTP không tự giải quyết dung lượng

WebFlux có thể trả `Flux<T>` thành luồng JSON/NDJSON/SSE tùy content type và client support:

~~~java
import org.springframework.http.MediaType;

@GetMapping(
    value = "/customers/{customerId}/orders/stream",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<OrderByCustomerMonth> streamRecent(
        @PathVariable UUID customerId,
        @RequestParam String month) {

    return orderRepo.findLatestInMonth(customerId, month);
}
~~~

Trong ví dụ repository `LIMIT 20` nên stream có kích thước hữu hạn. Với export hàng triệu row, phải có xác thực/ủy quyền, giới hạn số hàng, deadline, quota và chính sách xử lý client disconnect. Proxy/load balancer có thể buffer dữ liệu nên cần đo streaming end-to-end thay vì suy từ kiểu `Flux`.

## 11. Paging trong reactive Cassandra

Cassandra có **server-side paging state** và driver hỗ trợ fetch từng trang. Những nguyên tắc này **không đổi** khi truy cập reactive:

- Page size của driver định hướng số row mỗi lần fetch, không phải tổng số row của query.
- CQL `LIMIT` giới hạn số row được truy vấn trả về.
- Paging state để **đọc tiếp cùng truy vấn và bind parameters**, không phải số trang để tính offset ngẫu nhiên.
- Cassandra không cung cấp `OFFSET n LIMIT m` tổng quát cho bảng phân tán.
- Query qua nhiều partition/time bucket cần logic điều phối của ứng dụng.

### 11.1. Reactive Flux không tương đương Page<T>

~~~java
Flux<OrderByCustomerMonth> rows =
    orderRepo.findLatestInMonth(customerId, "2026-11");
~~~

`Flux` trả các row theo tiến trình query; nó không tự có `getTotalPages()`, `getTotalElements()` hoặc khả năng đến thẳng trang 100. Việc cố dựng một `PageImpl` từ `collectList()` của dữ liệu quét lớn có thể gây chi phí cực cao.

Đối với feed/timeline, hợp đồng HTTP thường tốt hơn là:

~~~json
{
  "items": [
    {
      "orderId": "11111111-1111-4111-8111-111111111111",
      "createdAt": "2026-11-25T10:00:00Z",
      "status": "PAID"
    }
  ],
  "hasMore": true,
  "nextCursor": "opaque-signed-cursor"
}
~~~

`nextCursor` có thể đại diện paging state phù hợp hoặc seek key; không gửi cursor chỉ để cho đẹp nếu service chưa có cơ chế tiếp tục query đúng.

### 11.2. Vì sao không tự dùng PageRequest.of(100, 20)?

Trong RDBMS, `PageRequest.of(100,20)` thường có nghĩa bỏ qua 2.000 row. Cassandra không có offset tổng quát. Một số API Spring Data Cassandra có cơ chế `CassandraPageRequest` và paging state, nhưng **khả năng áp dụng cho repository reactive, tên factory và cách trả next page tùy phiên bản**. Không giả định một số trang bất kỳ là có thể truy cập trực tiếp.

Nếu endpoint chỉ cần “Xem thêm”, có thể chọn keyset cursor theo clustering columns hoặc dùng driver paging state. Không đưa token paging state cho một query khác filter/bind values.

### 11.3. Keyset pagination trên clustering key

Với bảng có thứ tự:

~~~sql
PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC)
~~~

Trang đầu:

~~~sql
SELECT customer_id, month_bucket, created_at, order_id,
       status, total_amount
FROM shop.orders_by_customer_month
WHERE customer_id = ? AND month_bucket = ?
LIMIT 21;
~~~

Nếu UI hiển thị 20 row, row thứ 21 dùng để xác định `hasMore`; cursor lấy khóa của **row thứ 20 đã trả**, không phải row thứ 21.

Trang sau có thể dùng tuple restriction trên clustering columns với CQL/version phù hợp:

~~~sql
SELECT customer_id, month_bucket, created_at, order_id,
       status, total_amount
FROM shop.orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
  AND (created_at, order_id) < (?, ?)
LIMIT 21;
~~~

Vì cả hai clustering columns đều sắp xếp DESC, toán tử tuple nhỏ hơn thể hiện hàng tiếp theo có key thấp hơn mốc. Với mixed ASC/DESC hoặc bản Cassandra có giới hạn tuple restriction, cần xác minh cú pháp và chiều điều kiện cụ thể trước khi dùng.

### 11.4. Tạo response giới hạn bằng Reactor

~~~java
public Mono<OrderPageResponse> firstPage(
        UUID customerId, String monthBucket) {

    return queryFirstTwentyOne(customerId, monthBucket)
        .collectList()
        .map(rows -> {
            boolean hasMore = rows.size() > 20;
            List<OrderDto> visible = rows.stream()
                .limit(20)
                .map(this::toDto)
                .toList();

            String next = hasMore
                ? cursorFrom(rows.get(19), customerId, monthBucket)
                : null;

            return new OrderPageResponse(visible, hasMore, next);
        });
}
~~~

Đây là **skeleton dịch vụ**: `queryFirstTwentyOne` phải thật sự giới hạn ở CQL `LIMIT 21` và đủ partition key, `cursorFrom` phải xây token theo đúng khóa/cuộc truy vấn và bảo vệ chống sửa. `OrderPageResponse` / `OrderDto` là các DTO nghiệp vụ cần tự định nghĩa. Đừng dùng `collectList()` khi query không giới hạn; trong ví dụ này collection tối đa 21 row.

### 11.5. Cursor và bảo mật

Cursor cần ràng buộc:

- Customer ID/tenant đang được phép xem.
- Month bucket, filter, sort order và page size.
- Clustering key cuối hoặc paging state, với version của query/contract.
- Hạn dùng của cursor và cách trả lỗi khi schema/filter thay đổi.
- Chữ ký HMAC hoặc storage server-side; nếu chứa dữ liệu nhạy cảm có thể cần mã hóa, không chỉ base64.
- Quyền truy cập phải được kiểm tra **lại ở mỗi request**.

Cancellation/timeout hoặc insert/delete giữa các page không tạo snapshot toàn cụm. Nếu ứng dụng đòi một báo cáo bất biến có totalPages và nhảy trang, cần materialized report/checkpoint/snapshot riêng.

## 12. Consistency, timeout và request options vẫn quan trọng

Reactive I/O không thay đổi replication factor hay ngữ nghĩa của `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM`, `SERIAL` / `LOCAL_SERIAL`. Những lựa chọn này vẫn ảnh hưởng độ trễ, khả năng sẵn sàng và tính nhất quán quan sát được.

### 12.1. Regular consistency theo replica

Giả sử keyspace RF=3 trong DC cục bộ:

| CL | Mức xác nhận ví dụ | Ghi chú |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica trong DC | Nhanh hơn trong một số workload; có thể đọc phiên bản cũ |
| `LOCAL_QUORUM` | Hai trong ba replica cục bộ | Quorum trong local DC |
| `QUORUM` | Quorum trên tổng replica theo topology | Có thể khác local quorum trong multi-DC |
| `ALL` | Tất cả replica | Nhạy khi một node không sẵn sàng |
| `SERIAL` / `LOCAL_SERIAL` | Mức serial/Paxos riêng | Dùng cho LWT và serial read theo semantics hỗ trợ |

Với read model denormalized (ví dụ `orders_by_id` và `orders_by_customer_month`), tăng CL không tự đồng bộ **hai bảng nghiệp vụ**. Nếu projector cập nhật trễ, danh sách có thể trễ dù mỗi bảng được đọc ở `LOCAL_QUORUM`.

### 12.2. Driver và Spring Data chia sẻ cấu hình

Với ứng dụng sử dụng Spring Boot, cấu hình regular consistency/timeout có thể được đặt ở mức request defaults của Boot/driver:

~~~yaml
spring:
  cassandra:
    keyspace-name: shop
    local-datacenter: datacenter1
    request:
      consistency: LOCAL_QUORUM
      timeout: 3s
~~~

Đây là **một ví dụ** và cần xác minh thuộc tính có hiệu lực ở Boot version cụ thể. Driver `CqlSession` và execution profiles vẫn có thể override, còn Spring Data có các API `QueryOptions` tùy thao tác và phiên bản.

Khi cần điều khiển per-statement rõ hơn, có thể dùng driver async/reactive API với `PreparedStatement`, `BoundStatement` và `DefaultConsistencyLevel`, nhưng cần tự quản lý mapping/tracing và tránh tạo một code path blocking ngoài ý muốn.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

BoundStatement query = preparedSelect.bind(productId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100)
    .setIdempotent(true);
~~~

Ví dụ cấu hình **statement**, chưa thực thi. Ở Java Driver 4.x, setter của `BoundStatement` trả statement mới; không bỏ kết quả trả về. `setPageSize(100)` là fetch size, không có nghĩa CQL chỉ trả 100 row.

### 12.3. Reactor timeout và driver timeout khác nhau

~~~java
Mono<ProductById> value = repository.findById(productId)
    .timeout(Duration.ofSeconds(3));
~~~

`timeout` của Reactor tạo lỗi và hủy subscription nếu publisher chưa có tín hiệu phù hợp trong thời gian định nghĩa. Nó **không tự bảo đảm** câu CQL đã gửi sẽ bị server rollback hoặc chưa được áp dụng.

Driver request timeout giới hạn thời gian xử lý ở tầng driver; một cơ chế thời gian khác có thể nằm ở gateway, HTTP client, load balancer hoặc deadline của service. Phải phân định quyền sở hữu timeout để tránh hệ thống có nhiều ngưỡng xung đột khó phân tích.

### 12.4. Những lớp timeout cần điều phối

~~~text
HTTP client deadline
    > hoặc gần request deadline tại gateway?
WebFlux endpoint timeout
    > Reactor operator timeout?
Java Driver request timeout
    > server-side workload timeout?
Cassandra coordinator/replica operations
~~~

Không có một quan hệ “lớn hơn/nhỏ hơn” phù hợp cho mọi hệ thống; chọn deadline end-to-end dựa trên SLA và đảm bảo có thời gian xử lý lỗi/trả response. Nếu client hết hạn trước khi Cassandra hoàn tất một mutation, ứng dụng phải coi outcome là **không rõ**, không mặc định server hủy.

## 13. Retry, cancellation và idempotency trong reactive pipeline

### 13.1. retryWhen có thể thực thi lại truy vấn

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<ProductById> read = repository.findById(productId)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isRetryableReadFailure)
    );
~~~

`isRetryableReadFailure` là hàm phân loại lỗi **do ứng dụng định nghĩa**, không phải method built-in. Nó phải loại trừ lỗi mapping, validation, authorization, query sai và những trường hợp retry chỉ làm tăng tải. Ví dụ này dành cho **SELECT** có thể được xem là idempotent theo semantics đang dùng, với tổng số attempt và deadline có giới hạn.

`retryWhen` hoạt động bằng cách subscribe lại vào source khi có lỗi phù hợp; với publisher cold, thao tác database có thể được phát lại. Cần tính cả retry của Java Driver và gateway để tránh retry storm.

### 13.2. Không retry mutation bừa

~~~java
// Phản mẫu: có thể lưu hoặc tăng counter nhiều lần.
return counterMutationPublisher()
    .retryWhen(Retry.backoff(5, Duration.ofMillis(50)));
~~~

Một counter `views = views + 1`, list append, ghi TTL hoặc một workflow POST có side effects có thể **không idempotent**. Nếu Cassandra đã áp dụng mutation rồi response mất, retry sẽ có thể tạo hiệu ứng bổ sung.

Ngay cả `repository.save(entity)` có giá trị cuối giống nhau cũng có thể tương tác khác với write timestamps, TTL, concurrency hoặc auditing. Phải chứng minh tính lũy đẳng ở cả **hợp đồng dữ liệu và nghiệp vụ**, không chỉ nhìn tên method.

### 13.3. Cancellation không phải transaction rollback

Người dùng đóng tab khi server đang xử lý:

~~~text
HTTP client disconnect
  -> downstream cancel subscription
  -> driver có thể ngừng fetch/đẩy thêm hàng
  -> nhưng mutation đã gửi tới Cassandra có thể đã commit
~~~

Nếu API thay đổi tiền, kho, trạng thái đơn, hãy có idempotency key, chính sách kết quả chưa rõ và reconciliation. Không dựa vào cancellation để hoàn tác write.

### 13.4. doOnNext không phải nơi thực thi side effect quan trọng

~~~java
return repository.findById(productId)
    .doOnNext(product -> metrics.recordLookup(productId));
~~~

`doOnNext` hữu ích cho logging/metrics nhẹ, nhưng nó có thể chạy lại nếu publisher bị subscribe lại hoặc retry. Đừng thực hiện charge, gửi email hoặc ghi counter có ý nghĩa nghiệp vụ trong `doOnNext` và mặc định nó chạy đúng một lần.

Nếu side effect phải được đảm bảo, thiết kế một bước workflow rõ ràng có event ID/transactional boundary phù hợp, không gắn vào callback giám sát.

## 14. LWT, @Version và transaction trong reactive access

Reactive repositories có thể sử dụng Spring Data Cassandra optimistic locking trên entity hỗ trợ `@Version`, thường dựa trên **LWT**. Cơ chế này khác với các giao dịch JPA.

### 14.1. Khi nào cần CAS?

Một yêu cầu thường gặp:

> “Chỉ chuyển đơn từ CREATED sang PAID nếu version vẫn là 7.”

CQL:

~~~sql
UPDATE shop.orders_by_id
SET status = 'PAID',
    version = 8
WHERE order_id = ?
IF status = 'CREATED' AND version = 7;
~~~

Đó là conditional write; kết quả `[applied]` cần được kiểm tra. Nếu request thua CAS, bạn phải đọc trạng thái mới và quyết định business transition tiếp theo.

### 14.2. @Version trong reactive entity

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderState {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("status")
    private String status;

    @Version
    @Column("version")
    private Long version;

    public OrderState() {}

    // Getters/setters.
}
~~~

Entity `@Version` của Spring Data Cassandra có thể áp dụng conditional statements để ngăn optimistic locking conflict theo semantics framework. Trong reactive pipeline, conflict được phát qua `Mono.error(...)` / exception phù hợp chứ không được đảm bảo bởi việc dùng `flatMap`.

Nếu controller nhận update:

~~~java
public Mono<OrderState> update(OrderState candidate) {
    return reactiveOrderRepository.save(candidate);
}
~~~

Đường `save` có thể dùng version khi mapping đúng. Tuy nhiên, service vẫn phải xử lý version conflict thành kết quả HTTP/business phù hợp; không bắt mọi exception rồi tự overwrite.

### 14.3. Regular và serial consistency trong LWT

LWT có hai nhóm:

- **Regular CL:** `LOCAL_QUORUM`, `QUORUM`... cho giai đoạn learn/write và mức nhìn thấy ở phép đọc thường.
- **Serial CL:** `SERIAL` / `LOCAL_SERIAL` cho phạm vi Paxos.

Nếu một ứng dụng nhiều DC có writer cạnh tranh trên cùng key và cần invariant toàn cục, `LOCAL_SERIAL` ở hai nơi không tự là lựa chọn đủ mạnh. Reactive không thay đổi đặc tính này; phải kiểm chứng routing, failover, RF/DC và policy.

### 14.4. @Transactional không tự tạo ACID nhiều bảng

Ví dụ workflow:

~~~text
UPDATE orders_by_id
INSERT orders_by_customer_month
PUBLISH message to Kafka
SEND confirmation email
~~~

Viết các thao tác đó trong `Mono.zip(...)`, `then(...)` hoặc một method gắn `@Transactional` không tự làm chúng thành **một transaction atomic xuyên Cassandra và các hệ thống ngoài**. Cassandra logged batch cũng không thay thế giao dịch quan hệ ACID đa bảng.

Nếu thao tác B thất bại sau A, ứng dụng cần workflow, outbox, idempotency, reconciliation hoặc một kiến trúc giao dịch khác. Dùng reactive để tổ chức luồng chứ không để hứa “all-or-nothing” khi backend không cung cấp guarantee ấy.

## 15. Sắp xếp thao tác write và kiểm soát concurrency

### 15.1. then() nghĩa là nối tác vụ, không phải transaction

~~~java
public Mono<Void> saveOrderAndEvent(
        OrderState order, OrderEvent event) {

    return orderRepository.save(order)
        .then(eventRepository.save(event))
        .then();
}
~~~

`then` chỉ đảm bảo subscription cho tác vụ sau được kích hoạt khi tác vụ trước hoàn tất thành công theo signal. Nếu tác vụ thứ hai lỗi, tác vụ đầu **không được rollback tự động**. Nếu tác vụ đầu đã commit rồi client thấy timeout, outcome của nó còn có thể không rõ.

### 15.2. Khi nào zip có thể làm tăng concurrency?

~~~java
Mono<Tuple2<ProductById, Inventory>> joined =
    Mono.zip(
        productRepo.findById(productId),
        inventoryRepo.findByProductId(productId)
    );
~~~

Với hai read độc lập, `zip` có thể cho phép chạy cùng lúc và giảm latency tổng hợp. Nhưng:

- Hai bảng/read models có thể không cùng một snapshot logic.
- Nếu một nguồn empty, `zip` có thể hoàn tất empty và hủy nguồn còn lại.
- Với write, chạy `zip(writeA,writeB)` nghĩa chúng có thể khởi chạy đồng thời — **không** tự mang semantics giao dịch.
- Cần giới hạn fan-out và đo P99 nếu một endpoint kết hợp nhiều queries.

### 15.3. Không trộn blocking repository vào reactive method

~~~java
// Phản mẫu:
Mono<ProductById> read() {
    ProductById product = blockingRepository.findById(id).orElseThrow();
    return Mono.just(product);
}
~~~

Mã này thực thi truy vấn blocking **trước khi Mono được tạo**. Hãy dùng `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate`; nếu thật sự có dependency blocking không thay được, cô lập bằng `fromCallable(...).subscribeOn(boundedElastic())` và giới hạn tài nguyên.

## 16. Kiểm thử repository/template reactive

### 16.1. StepVerifier cho pipeline cơ bản

`reactor-test` cung cấp `StepVerifier` để kiểm tra signals và lỗi:

~~~java
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ProductServiceTest {

    @Test
    void findsProductWithoutBlocking() {
        UUID id = UUID.randomUUID();
        ProductById product = new ProductById();

        when(repository.findById(id))
            .thenReturn(Mono.just(product));

        StepVerifier.create(service.findById(id))
            .expectNext(product)
            .verifyComplete();

        verify(repository).findById(id);
    }
}
~~~

Đây là **skeleton test**: cần khai báo/mock `repository` và dựng `service` trong fixture thực tế, đồng thời có getters/setters/constructor cho `ProductById`. Nó minh họa cách kiểm tra publisher mà không gọi `block()`, không phải file JUnit có thể chạy độc lập.

### 16.2. Test khi row không tồn tại

~~~java
when(repository.findById(id))
    .thenReturn(Mono.empty());

StepVerifier.create(service.findById(id))
    .verifyComplete();
~~~

Trường hợp trống là hoàn tất **không có onNext**. Nếu service dùng `switchIfEmpty(Mono.error(...))`, test sẽ mong đợi loại exception nghiệp vụ thay vì completion trống.

### 16.3. Test error path

~~~java
RuntimeException failure =
    new RuntimeException("cassandra unavailable");

when(repository.findById(id))
    .thenReturn(Mono.error(failure));

StepVerifier.create(service.findById(id))
    .expectErrorMatches(e -> e == failure)
    .verify();
~~~

Không biến mọi `Mono.error` thành `Mono.empty()` và coi test qua, vì API có thể trả 404 trong lúc Cassandra không sẵn sàng.

### 16.4. Integration test với Cassandra thật

Một unit test dùng mock **không chứng minh**:

- Entity mapping khớp CQL schema.
- Compound partition key và clustering order đúng.
- Truy vấn `@Query` hợp lệ theo Cassandra version.
- CL, timeout, paging state, index và LWT làm việc như mong đợi.
- Driver thực sự xử lý I/O không chặn/under load.
- Query trả số row đúng khi có dữ liệu lớn/tombstone.

Vì thế cần integration test trên Cassandra test cluster hoặc Testcontainers có version tương thích, với schema được dựng rõ ràng.

Một kiểm thử mang tính khái niệm:

~~~java
@Test
void roundTripsAProduct() {
    ProductById newProduct = testProduct(UUID.randomUUID());

    Mono<ProductById> roundTrip =
        repository.save(newProduct)
            .flatMap(saved ->
                repository.findById(saved.getProductId())
            );

    StepVerifier.create(roundTrip)
        .assertNext(actual ->
            assertEquals(
                newProduct.getProductId(),
                actual.getProductId()
            )
        )
        .verifyComplete();
}
~~~

Fixture `repository`, `testProduct`, keyspace và schema cần triển khai trong test suite thật. Đừng chạy với keyspace production; nên dùng ID ngẫu nhiên và cleanup có kiểm soát.

### 16.5. Test pagination và keyset

Chuẩn bị ít nhất 25 row trong một partition:

- Hai row có cùng `created_at` nhưng `order_id` khác.
- Các row được sắp `DESC` theo cặp clustering.
- Trang đầu lấy 21, chỉ hiển thị 20.
- Cursor lấy từ **row cuối được hiển thị**, không phải row lookahead.
- Trang sau không lặp/bỏ sót khi dữ liệu đứng yên.
- Khi ghi/xóa giữa các trang, xác minh contract live-feed được ghi rõ.
- Cursor customer A không dùng để đọc customer B.

Reactive `Flux` không làm mất yêu cầu test sort/seek. Nếu driver paging state được dùng, phải test cùng query/filter/bind values và token hết hạn hoặc bị sửa.

### 16.6. Test hủy subscription và unknown write outcome

Một test fault injection có thể mô phỏng:

~~~text
1. Service phát mutation lên driver.
2. Cassandra đã áp dụng mutation.
3. HTTP client hủy request / response lỗi.
4. Client gửi lại cùng business request.
5. Kiểm tra idempotency và trạng thái cuối.
~~~

Nếu nghiệp vụ dùng counter increment hoặc phát email, đây là một test quan trọng. Mock ném lỗi **trước khi phát mutation** không tương đương server đã commit nhưng response mất.

## 17. Quan sát trong production

### 17.1. Nên đo gì?

| Nhóm | Chỉ số/câu hỏi |
| --- | --- |
| HTTP/WebFlux | Request rate, p50/p95/p99, cancel rate, 5xx, bytes streamed |
| Reactor | Số subscription, timeout, retry, upstream errors, scheduler saturation |
| Driver | Request latency, in-flight, pool usage, retry/speculation, page fetches |
| Cassandra | Read/write latency, timeout, unavailable, CPU, disk I/O, compaction |
| Data model | Partition size, hot keys, tombstone warnings, read amplification |
| Paging | Số row/page, số lần fetch, cursor invalid/expired, payload size |
| Consistency | CL theo đường truy vấn, remote DC lag, quorum errors |
| Business | Duplication, event loss, outbox/projector lag, LWT conflicts |

Nếu một reactive endpoint có p99 cao, đừng chỉ xem thread count. Truy vấn có thể **thiếu partition key, đọc quá nhiều row hoặc chạm hot partition**, những điều reactive không sửa.

### 17.2. Logging và Reactor Context

Reactor `Context` giúp truyền metadata theo subscription, khác ThreadLocal. Trong WebFlux, correlation ID/tracing cần được triển khai tương thích reactive; không dựa vào ThreadLocal tự truyền xuyên mọi scheduler/operator.

~~~java
Mono<ProductById> read = repository.findById(productId)
    .contextWrite(ctx -> ctx.put("traceId", traceId));
~~~

Đây là ví dụ lưu metadata trong Reactor Context, **không** tự ghi trace vào log hay driver span. Muốn end-to-end tracing, cần instrumentation/observability đã cấu hình đúng.

### 17.3. Lỗi khi debug reactive

Một stack trace có thể chỉ chứa các bước callback/assembly khác với call stack đồng bộ. Có thể dùng Reactor checkpoints/logging có chọn lọc trong môi trường phù hợp, nhưng không bật debug toàn bộ pipeline không giới hạn ở production nếu nó tạo overhead hoặc log dữ liệu nhạy cảm.

## 18. Runbook hiệu năng cho Reactive Cassandra

Khi một endpoint trả `Flux` đang chậm:

1. **Đọc CQL thực tế**: có đầy đủ partition key, `LIMIT` và clustering order phù hợp chưa?
2. **Xem số row và kích thước row**: `SELECT *` có lấy collection/blob lớn không?
3. **Kiểm tra code Reactor**: có `collectList()` toàn bảng, `flatMap` concurrency không giới hạn hay `block()` không?
4. **Kiểm tra driver request options**: timeout, page size, consistency, retry/speculative policies.
5. **Xem replica**: hot partition, tombstone, compaction, CPU/IO, unavailable.
6. **Đo dòng HTTP**: serializer/proxy có buffer NDJSON/SSE không? Client đọc nhanh hay chậm?
7. **Xem cancellation**: request đã hủy có tiếp tục chạy query hoặc mutation không?
8. **Kiểm tra retry storm**: timeout ở HTTP, Reactor, driver và gateway có cộng dồn không?
9. **Giảm fan-out**: tránh gửi nhiều truy vấn một cách không giới hạn.
10. **So sánh baseline**: p95/p99 và throughput trước/sau, không chỉ response đầu tiên trong local dev.

Nếu `Mono<Product>` theo ID vẫn chậm, vấn đề có thể là replica health hoặc networking, không phải thiếu một operator Reactor.

## 19. Bài thực hành: API lịch sử đơn hàng không chặn

### 19.1. Yêu cầu

Xây một API cho khách hàng:

- Tra chi tiết sản phẩm theo `product_id` bằng `ReactiveCassandraRepository`.
- Xem 20 đơn mới nhất của **một khách trong một tháng** bằng `ReactiveCassandraTemplate` hoặc repository `@Query`.
- Dùng `Flux` / `Mono` xuyên từ Cassandra đến Spring WebFlux; không dùng `block()` trong request path.
- Không quét toàn bảng hoặc dùng `ALLOW FILTERING`.
- Không hứa tổng trang/nhảy trang; hỗ trợ next cursor khi cần.
- Có error mapping: không tìm thấy, query timeout, dữ liệu invalid, không đủ quyền.
- Có test giới hạn 20/21 row, timestamp trùng, client disconnect và concurrency.

### 19.2. Bước 1 — Chốt CQL schema

Sử dụng hai bảng ở phần 4:

~~~sql
SELECT product_id, sku, name, price, status, updated_at
FROM shop.products_by_id
WHERE product_id = ?;
~~~

~~~sql
SELECT customer_id, month_bucket, created_at, order_id,
       status, total_amount
FROM shop.orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Bảo đảm `(customer_id, month_bucket)` là partition key ghép và clustering theo `created_at DESC, order_id DESC`. Đừng query chỉ `customer_id` mà thiếu `month_bucket` nếu schema không hỗ trợ đường đọc đó.

### 19.3. Bước 2 — Dựng repository và template

Tạo:

- `ProductRepository extends ReactiveCassandraRepository<ProductById, UUID>`.
- `CustomerOrderRepository` có `findLatestInMonth(...)` trả `Flux<OrderByCustomerMonth>`.
- `CustomerOrderTemplateReader` tạo `Query` theo cả hai thành phần partition key, `limit(20)`.
- `ProductService` trả `Mono`, `CustomerOrderService` trả `Flux` hoặc `Mono<OrderPageResponse>`.

Không làm cả repository và template chạy hai truy vấn giống nhau cho mỗi request chỉ để “tận dụng hai công nghệ”. Chọn đường truy cập phù hợp và giữ code dễ quan sát.

### 19.4. Bước 3 — Controller WebFlux

Một endpoint đơn giản:

~~~java
import java.util.UUID;

import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/customers")
public class CustomerOrderController {

    private final CustomerOrderRepository orders;

    public CustomerOrderController(
            CustomerOrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping("/{customerId}/orders")
    public Flux<OrderByCustomerMonth> latest(
            @PathVariable UUID customerId,
            @RequestParam String month) {

        return orders.findLatestInMonth(customerId, month);
    }
}
~~~

Đoạn mã chỉ minh họa routing. Production phải lấy customerId từ authorization/scope đúng và kiểm tra người gọi có quyền xem, validate `month` theo `YYYY-MM`, áp giới hạn request rate, có DTO không để lộ trường nội bộ.

### 19.5. Bước 4 — Thêm hasMore và cursor

Nếu muốn button “Xem thêm”:

1. Chuyển query đầu sang `LIMIT 21`.
2. Chỉ hiển thị 20 item.
3. Đặt `hasMore=true` nếu lấy được item thứ 21.
4. Lấy cursor từ **clustering key của item thứ 20** đã hiển thị.
5. Request sau truy vấn theo điều kiện seek có đầy đủ partition key.
6. Ký/bảo vệ cursor và kiểm tra lại quyền của user.

Đừng gắn `PageRequest.of(100,20)` rồi kỳ vọng Cassandra nhảy đến phần tử 2.000. Nếu nhu cầu thật là tìm theo khoảng thời gian, cho phép user chọn tháng/ngày là hợp lý hơn.

### 19.6. Bước 5 — Kiểm thử với dữ liệu cụ thể

Chuẩn bị các case:

| Dữ liệu | Kỳ vọng |
| --- | --- |
| Không có đơn trong tháng | Flux trống, API trả danh sách rỗng |
| Có đúng 20 đơn | Không thông báo có trang tiếp nếu đã hết |
| Có 21 đơn | Trang đầu hiển thị 20; trang sau có một |
| Hai đơn cùng timestamp | Tie-breaker `order_id` đảm bảo không mất row |
| Sai/thiếu month bucket | Trả lỗi validation, không chạy full scan |
| Customer khác tenant | Bị từ chối trước khi query và khi dùng cursor |
| Driver timeout | Được ánh xạ thành lỗi hạ tầng có trace ID |
| Client hủy request giữa chừng | Không để service leak subscription/đọc vô hạn |
| Flux bị subscribe hai lần | Biết nguồn cold có thể query hai lần |
| Query không có LIMIT | Thử nghiệm nhận biết nguy cơ memory/latency |
| Tăng fan-out từ 8 lên 1.000 | Quan sát pool/in-flight và p99 trước khi chọn cấu hình |

### 19.7. Bước 6 — Đo hiệu năng

Đo ít nhất:

- p50/p95/p99 của GET product và GET orders.
- Rows read, bytes per page, page fetches, number of subscriptions.
- Số request đồng thời và driver pool in-flight.
- CPU/GC của service, CPU/IO/compaction của Cassandra.
- Lỗi timeout, unavailable, query cancel và retry.
- Latency ở bucket lớn/hot customer và khách thường.
- Ảnh hưởng tới API khác khi tăng concurrency.

Nếu API chỉ trả 20 row nhưng p99 cao, hãy kiểm tra hot partitions và tombstone thay vì lập tức tăng số thread hoặc `flatMap` concurrency.

## 20. Những lỗi phổ biến khi dùng reactive Cassandra

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `block()` trong controller WebFlux | Chiếm event-loop thread, giảm throughput | Return `Mono` / `Flux` |
| Dùng `Mono.just(blockingCall())` | Blocking call chạy ngay khi assembly | Dùng API reactive thực, hoặc cô lập blocking I/O |
| Tự `subscribe()` trong service | Mất lifecycle/error/cancellation của request | Return publisher lên framework |
| Subscribe hai lần vào mutation cold | Write có thể xảy ra hai lần | Chỉ subscribe ở biên; thiết kế idempotency |
| `repository.findAll().collectList()` trên bảng lớn | Quét toàn bảng và giữ toàn bộ row trong RAM | Query theo partition + LIMIT/stream bounded |
| `take(20)` thay cho CQL `LIMIT 20` | Server/driver vẫn có thể đọc/fetch dư | Limit tại tầng truy vấn |
| Truy vấn thiếu partition key | Query bị từ chối hoặc hiệu năng tệ | Thiết kế bảng đúng access pattern |
| Dùng `ALLOW FILTERING` để “chạy được” | Chi phí quét không dự đoán được | Bảng theo truy vấn hoặc index phù hợp |
| `flatMap` không giới hạn fan-out | Overload pool/coordinator/replicas | Đặt concurrency, đo p99, rate limit |
| `flatMap` nhiều write cùng key | Không bảo đảm thứ tự business | `concatMap`, CAS hoặc writer coordination |
| `onErrorResume(ex -> Mono.empty())` | Giấu sự cố database thành “không có row” | Phân loại lỗi, giữ signal lỗi hạ tầng |
| `retryWhen` mọi mutation | Double writes, TTL refresh, counter drift | Retry chỉ khi idempotent thật, có dedup |
| Cho rằng cancellation rollback write | Trạng thái thực tế khác response HTTP | Idempotency, state verification và reconciliation |
| Cho rằng reactive cung cấp ACID nhiều bảng | Side effects bị lệch khi bước sau lỗi | Outbox/workflow, ranh giới giao dịch rõ |
| Cho rằng Flux tạo Page với totalPages | Không có total hoặc random offset | Cursor/keyset, report snapshot nếu cần |
| Dùng Reactor timeout thay driver deadline | Outcome không rõ và trùng nhiều layers | Thiết kế deadline end-to-end |
| Dùng `zip(writeA,writeB)` như transaction | Hai mutation có thể chỉ một thành công | Tách workflow/compensation |
| Test chỉ với mock Mono.just | Không phát hiện lỗi schema/CQL/replication | Integration test trên Cassandra thật |
| Map toàn entity có blob lớn vào list | Tốn memory/network/serialization | Projection/chọn cột và payload phù hợp |
| Nghĩ reactive luôn tăng tốc mỗi query | Bỏ qua latency mạng, RF, hot partitions | So sánh số liệu trước/sau theo SLA |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `Mono<T>` và `Flux<T>` khác nhau thế nào?

*Đáp án:* Mono phát tối đa một phần tử; Flux có thể phát nhiều phần tử.

**Câu 2.** ReactiveCassandraRepository phù hợp nhất với loại API nào?

*Gợi ý:* CRUD/query methods theo entity và access pattern tương đối cố định.

**Câu 3.** Khi nào nên chọn ReactiveCassandraTemplate?

*Gợi ý:* Cần dựng `Query/Criteria` linh hoạt, chọn cột/limit hoặc tùy biến data access.

**Câu 4.** Vì sao `repository.findAll().take(20)` không tương đương một CQL query có partition key và `LIMIT 20`?

*Gợi ý:* Query nguồn có thể là full scan và driver có thể đọc/fetch nhiều hơn 20.

**Câu 5.** Gọi `block()` trong controller WebFlux nguy hiểm ở điểm nào?

*Gợi ý:* Chặn thread xử lý non-blocking, giảm concurrency.

**Câu 6.** Vì sao hai lần subscribe có thể sinh hai truy vấn Cassandra?

*Gợi ý:* Nhiều nguồn reactive là cold publishers.

**Câu 7.** `flatMap(..., 8)` có tác dụng gì và không đảm bảo điều gì?

*Gợi ý:* Giới hạn concurrency của inner publishers, không tự giữ order hoặc bảo vệ CAS.

**Câu 8.** `Flux.collectList()` có phù hợp cho một truy vấn trả hàng triệu row?

*Đáp án:* Không; nó giữ toàn bộ kết quả trong bộ nhớ.

**Câu 9.** Reactive driver paging state có cho phép nhảy thẳng đến page 100 không?

*Đáp án:* Không; state dùng để tiếp tục, không phải offset tổng quát.

**Câu 10.** Vì sao `LOCAL_QUORUM` không sửa projection lag giữa hai bảng read model?

*Gợi ý:* Replica consistency và đồng bộ dữ liệu giữa hai bảng nghiệp vụ khác nhau.

**Câu 11.** `retryWhen` có thể gây vấn đề gì với counter increment?

*Gợi ý:* Subscribe lại và thực thi mutation thêm lần nữa khi outcome lần đầu không rõ.

**Câu 12.** `@Version` trong Spring Data Cassandra dựa trên cơ chế gì?

*Đáp án:* Optimistic locking bằng conditional CQL/LWT theo entity/version hỗ trợ.

**Câu 13.** `Mono.zip(writeA, writeB)` có phải transaction atomic không?

*Đáp án:* Không; nó chỉ phối hợp publisher, không tạo atomicity đa bảng/hệ thống.

**Câu 14.** Khi một `Mono` không phát dữ liệu, có phải Cassandra đang lỗi?

*Đáp án:* Không. `Mono.empty()` khác `Mono.error()`.

**Câu 15.** Khi streaming HTTP, tại sao cần đo proxy/serializer?

*Gợi ý:* Buffering và tốc độ tiêu thụ downstream có thể làm thực tế khác kỳ vọng streaming.

**Câu 16.** Vì sao query theo `customer_id` nhưng thiếu `month_bucket` có thể không hợp lệ?

*Gợi ý:* Đầy đủ composite partition key của bảng là `(customer_id, month_bucket)`.

## 22. Checklist trước khi triển khai production

- **Dependency:** Spring Boot, Spring Data Cassandra, Java Driver, Reactor version tương thích.
- **Kết nối:** Local DC đúng, contact points/TLS/auth, RF và topology được kiểm tra.
- **Schema:** Migration kiểm soát, entity mapping đúng cột/primary key và các CQL types.
- **Query-driven:** Repository/template chỉ query theo đường truy cập được bảng/index hỗ trợ.
- **Reactive API:** Dùng `Mono/Flux` end-to-end, không gọi `block()` trong WebFlux requests.
- **Subscription:** Tránh `subscribe()` thủ công; biết cold publishers có thể thực thi lại.
- **Backpressure:** Giới hạn query, page size, concurrency; không dựa riêng `take/limitRate`.
- **Memory:** Không `collectList()` các truy vấn không giới hạn; chọn cột cần thiết.
- **Paging:** Cursor/paging state đúng query; không hứa OFFSET/totalPages khi chưa thiết kế.
- **Data consistency:** Chọn CL theo RF/DC, hiểu read model lag và replication.
- **Request options:** Định nghĩa driver timeout/consistency/page size và Reactor deadline hợp lý.
- **Retry:** Phân loại lỗi; tuyệt đối không retry mù non-idempotent mutations.
- **Transaction:** LWT/CAS cho invariant ở khóa phù hợp; workflow/outbox cho cross-table/external effects.
- **Errors:** Phân biệt not-found, invalid input, conflict, timeout/unavailable và bugs mapping.
- **Concurrency:** Có giới hạn `flatMap` và fan-out; đo hot partitions/p99.
- **Cancellation:** Không coi hủy subscription như hủy mutation đã commit.
- **Bảo mật:** Tenant/authorization trước mỗi query và mỗi trang cursor.
- **Test:** StepVerifier, integration Cassandra, duplicate subscribe, timeout response-loss và paging edge cases.
- **Observability:** HTTP metrics, Reactor errors, driver in-flight/retries, Cassandra latency/IO/compaction.
- **Vận hành:** Có SLO, rate limit, circuit breaker phù hợp, khả năng giảm tải, runbook và rollback.
- **Phạm vi bước:** Đây là knowledge STEP_4; không tự thực hiện vòng Content QA chuyên sâu của STEP_6.

## Tài liệu tham khảo

- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): reactive repositories, template, mapping và Cassandra query operations.
- [Spring Data Cassandra — API](https://docs.spring.io/spring-data/cassandra/docs/current/api/): `ReactiveCassandraRepository`, `ReactiveCassandraTemplate`, `ReactiveCassandraOperations` và các method theo phiên bản.
- [Spring Data Commons — Reactive Repositories](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): reactive CRUD/repository abstractions và query methods.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, subscription, error handling, `retryWhen`, backpressure và schedulers.
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): kiểm thử tín hiệu Publisher.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): primary key, `SELECT`, `LIMIT`, clustering order và restrictions.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/): query-driven schema design và partitioning.
- [Apache Cassandra Java Driver 4.x](https://apache.github.io/cassandra-java-driver/): request options, reactive execution, paging và retry policies.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): cách controllers trả reactive publishers và streaming response.

## Kết luận

**`ReactiveCassandraRepository`** cho phép mô tả CRUD và query methods theo entity bằng `Mono`/`Flux`; **`ReactiveCassandraTemplate`** cung cấp cách truy cập linh hoạt qua `Query`, `Criteria` và mapping, giúp triển khai những đường đọc/ghi đặc thù mà không phải tạo quá nhiều repository methods. Cả hai phù hợp với Spring WebFlux để xử lý bất đồng bộ và không chiếm thread chờ I/O khi hoạt động đúng.

Tuy nhiên, reactive **không thay đổi mô hình dữ liệu Cassandra**: truy vấn vẫn cần partition key, clustering order và CQL `LIMIT` phù hợp; paging state không phải offset; `collectList()` có thể làm cạn bộ nhớ; subscribe lại hoặc retry có thể thực thi write lần nữa; consistency và LWT vẫn có giới hạn phân tán vốn có. Khi sử dụng **SPRING_DATA_CASSANDRA**, hãy bắt đầu từ access pattern, chọn repository hay template theo mức độ linh hoạt cần thiết, giữ pipeline non-blocking, giới hạn concurrency, kiểm soát lỗi và idempotency, rồi xác minh bằng integration tests và metrics production. Đó mới là cách xây một tầng dữ liệu reactive có khả năng mở rộng, dễ quan sát và đúng ngữ nghĩa trong hệ thống Apache Cassandra phân tán.







