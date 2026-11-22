# ReactiveMongoTemplate, reactive repository và yêu cầu tránh chặn luồng

Một API WebFlux nhận hàng trăm request đồng thời có thể đáp ứng tốt với **ít event-loop threads** nếu toàn bộ chuỗi gọi I/O thực sự **non-blocking**. Nhưng chỉ cần một service gọi `MongoTemplate.find(...)` hoặc `Mono.block()` ngay trên event loop, những request khác dùng chung worker có thể bị chậm đáng kể. Việc đổi chữ ký controller từ `Order` sang `Mono<Order>` **không tự biến thao tác bên trong thành reactive**.

Bài **“ReactiveMongoTemplate, reactive repository và yêu cầu tránh chặn luồng”** thuộc chương **Spring Data MongoDB**, module *Database Engine Document MongoDB*, giúp xây ứng dụng truy vấn MongoDB bằng **Reactive Streams / Project Reactor** từ controller đến database. Hai API chính được trình bày là:

- **`ReactiveMongoTemplate`**: điều khiển truy vấn, cập nhật, aggregation, streaming và các thao tác chuyên biệt bằng API Spring Data, trả về `Mono<T>` / `Flux<T>`.
- **`ReactiveMongoRepository<T, ID>`**: khai báo CRUD/query methods theo domain model để Spring Data tạo implementation reactive.

Trọng tâm của bài không chỉ là cú pháp CRUD mà còn là **yêu cầu tránh blocking**: phân biệt async và blocking, hiểu subscription/backpressure, kiểm soát concurrency, tích hợp thư viện legacy, xử lý transaction, timeout/cancellation, testing và giám sát hiệu năng.

> **Phiên bản:** Các ví dụ nhắm đến **Spring Boot 3.x/4.x, Spring Data MongoDB 4.x/5.x, Reactor 3.x** với MongoDB Java Reactive Streams Driver tương thích do dependency management cung cấp. Một số package, builder, repository API và thuộc tính cấu hình thay đổi theo phiên bản. Hãy dùng BOM của Spring Boot đang chạy, không tự trộn Spring Data 5.x với driver/Spring Framework không tương thích. Mọi URI, collection, số lượng timeout và concurrency trong bài mang tính lab/minh họa.

## 1. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích **Reactive Streams Publisher/Subscriber/Subscription**, tính lazy, request demand, cancel và non-blocking I/O.
2. Phân biệt `MongoTemplate`/`MongoRepository` (imperative) với `ReactiveMongoTemplate`/`ReactiveMongoRepository` (reactive).
3. Cấu hình `spring-boot-starter-data-mongodb-reactive` và WebFlux, tạo domain `@Document`/`@Id`/`@Indexed`.
4. Viết CRUD, query, update, aggregation bằng `ReactiveMongoTemplate` và derived/annotated methods bằng reactive repository.
5. Xây controller nhận/trả `Mono`/`Flux`, truyền errors/empty/not-found và validation đúng semantics.
6. Nhận diện anti-pattern **`block()`, `blockFirst()`, `toIterable()`, `Thread.sleep()`, JDBC, blocking HTTP clients** trong event-loop chain.
7. Dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` khi bắt buộc tích hợp blocking legacy, đồng thời giới hạn lượng task.
8. Kiểm soát `flatMap` concurrency, `buffer`/`collectList`, pagination, batch size và downstream backpressure.
9. Hiểu `ReactiveMongoTransactionManager`/`TransactionalOperator`, Reactor Context và các ranh giới session.
10. Test publishers bằng `StepVerifier`, WebFlux bằng `WebTestClient`, giám sát latency/cancellation/connection pool và rollback khi deploy.

## 2. Tại sao reactive? Mô hình threads và I/O

### 2.1. Imperative blocking model

~~~text
HTTP request A
   |
   v
Servlet thread #1
   |
   v
MongoTemplate.findOne() -----> MongoDB
   |    (thread #1 WAITING for response)
   |
   v
HTTP response A
~~~

Khi một Java thread chờ kết quả socket blocking, nó vẫn chiếm một worker slot/thread stack và có thể khiến service cần nhiều threads để xử lý lượng requests lớn.

### 2.2. Reactive non-blocking model

~~~text
HTTP request A          HTTP request B
      |                       |
      +------ event loop -----+
                 |
                 v
          WebFlux Controller
                 |
                 v
         Mono/Flux pipeline
                 |
                 v
      Reactive MongoDB Driver
                 |
            async network I/O
                 |
             (no event-loop
              thread blocked)
                 |
                 v
          signal onNext/onComplete
                 |
                 v
          HTTP response stream
~~~

Khi MongoDB chưa phản hồi, event loop có thể tiếp tục xử lý các kết nối khác. Khi dữ liệu tới, reactive publisher phát **signals** để pipeline tiếp tục.

**Reactive không biến MongoDB nhanh hơn** hay giảm CPU/index cost của query. Nó chủ yếu giúp **không giữ một Java thread chờ mỗi socket operation**, kết hợp backpressure và composition để quản lý luồng dữ liệu.

### 2.3. Non-blocking khác với parallel

- **Non-blocking:** thread không bị giữ khi chờ I/O; không nhất thiết có nhiều operation chạy song song.
- **Concurrency:** nhiều operations đang tồn tại/chờ phản hồi trong cùng khoảng thời gian.
- **Parallelism:** thực thi công việc đồng thời trên nhiều CPU cores/threads.
- **Asynchronous:** kết quả đến sau; nếu bên trong async wrapper gọi JDBC blocking trên event loop thì chuỗi vẫn có thể chặn.

Một `Flux` có thể chạy từng operation nối tiếp qua `concatMap`, hoặc nhiều operation đồng thời qua `flatMap`. Phải chọn theo dependency ordering và capacity, không vì “reactive” mà cho unlimited concurrency.

### 2.4. Khi nào reactive thực sự có lợi?

| Tình huống | Lợi ích có thể có | Điều cần cân nhắc |
|---|---|---|
| HTTP API I/O-heavy, nhiều requests đồng thời | Ít blocked threads, I/O efficiency. | All-in non-blocking chain cần được giữ. |
| Query trả nhiều records theo stream | `Flux` hỗ trợ demand/cancellation, giảm nhu cầu buffer toàn bộ. | DB cursor, HTTP serializer, memory, timeout vẫn có giới hạn. |
| Service gọi MongoDB + nhiều HTTP APIs | Reactive composition tự nhiên. | Tất cả clients nên non-blocking. |
| Long-lived change stream | Subscribe/cancel và processing theo signals. | Resume token, retry, lifecycle, retention. |
| CPU-bound aggregation trong app | Không tự giảm CPU work. | Phải giới hạn/tách scheduling. |
| MVC app nhỏ, blocking stack đã đủ | Reactive có thể không tạo lợi ích ròng. | Không bắt buộc migrate vì “mới hơn”. |
| Hệ thống dùng JDBC/blocking SDK bắt buộc | Cần isolation threads hoặc chọn stack imperative. | Reactive wrapper không xóa blocking. |

### 2.5. Reactive không thay thế database optimization

Nếu MongoDB query `COLLSCAN` 10 triệu documents vì thiếu index, chuyển `MongoTemplate` sang `ReactiveMongoTemplate` không sửa vấn đề. Cần:

- `explain("executionStats")` và indexes phù hợp.
- Projection/bounded limit.
- Sử dụng shard key filter nếu sharded.
- Giảm N+1 queries, batching và caching có policy.
- Giám sát CPU/IOPS/cache/connection pool ở server.

## 3. Reactive Streams và Reactor: những khái niệm cần nhớ

### 3.1. Publisher, Subscriber, Subscription

Theo Reactive Streams:

- **Publisher** phát dữ liệu/signal khi có subscription.
- **Subscriber** nhận `onSubscribe`, `onNext`, `onError` và `onComplete`.
- **Subscription** cho subscriber gửi `request(n)` (demand) và `cancel()`.
- Publisher chỉ phát dữ liệu theo demand hợp lệ và phải tuân thủ terminal signal semantics.

~~~text
Subscriber                  Publisher
    |---- subscribe --------->|
    |<--- onSubscribe --------|
    |---- request(2) -------->|
    |<--- onNext(value1) -----|
    |<--- onNext(value2) -----|
    |---- request(1) -------->|
    |<--- onNext(value3) -----|
    |<--- onComplete ---------|
~~~

Trong thực tế, Reactor operators có **prefetch, buffering và operator fusion**, nên con số request tới upstream có thể khác demand do HTTP downstream phát ra. Đừng xem sơ đồ này là một cam kết rằng MongoDB luôn lấy **chính xác n documents mỗi socket request**.

### 3.2. Mono và Flux

| Kiểu | Số giá trị `onNext` tối đa | Dùng cho |
|---|---:|---|
| `Mono<T>` | 0 hoặc 1 | `findById`, `save`, `count`, `exists`, delete/update result. |
| `Mono<Void>` | 0 | Một workflow chỉ cần completion/error. |
| `Flux<T>` | 0 đến N | `findAll`, search results, aggregation rows, change streams. |

**Empty không tự là error**: `repository.findById("missing")` thường cho `Mono.empty()`. Controller phải quyết định chuyển empty thành HTTP 404, không lấy null làm “document tìm thấy”.

### 3.3. Pipeline lazy: xây không đồng nghĩa chạy

~~~java
Mono<Order> workflow = repository.save(order);

// Chỉ tạo Publisher; ở đây chưa có downstream subscription.
~~~

Khi WebFlux controller **return** `Mono<Order>`, framework subscribe để thực thi và gửi response. Trong một batch/job độc lập, phải có owner subscription/lifecycle rõ ràng.

### 3.4. Mỗi subscription có thể kích hoạt lại I/O

~~~java
Mono<Order> lookup = repository.findById("O-100");

// Hai subscriptions có thể tạo hai lần DB read.
lookup.subscribe();
lookup.subscribe();
~~~

Không mặc định publisher reactive là một `CompletableFuture` đã chạy một lần và giữ kết quả. Các repository/template publishers thường **cold**; multiple subscriptions có thể thực hiện lại operation. Điều này đặc biệt nguy hiểm với **writes** nếu tự `subscribe()` nhiều lần:

~~~java
Mono<Order> saveOncePerSubscription = repository.save(order);
~~~

`saveOncePerSubscription` **không** nghĩa save có “exactly once” semantics toàn hệ thống. Giữ business idempotency keys và không tự repeat/retry writes thiếu kiểm soát.

### 3.5. Ba signals: dữ liệu, lỗi, hoàn tất

~~~text
Mono.just(value):        onNext(value), onComplete
Mono.empty():            onComplete
Mono.error(exception):   onError(exception)
Flux.just(a,b):          onNext(a), onNext(b), onComplete
~~~

Sau `onError` hoặc `onComplete`, subscription kết thúc. Operators như `onErrorResume` chuyển lỗi sang fallback Publisher; không “nuốt” lỗi một cách không có chủ đích.

### 3.6. `map`, `flatMap`, `then` và `switchIfEmpty`

~~~java
Mono<OrderDto> result = repository.findById("O-100")
    .map(OrderDto::fromEntity)
    .switchIfEmpty(Mono.error(
        new OrderNotFoundException("O-100")));
~~~

- `map`: biến đổi giá trị **đồng bộ/nhanh** không phát sinh publisher.
- `flatMap`: kết hợp thao tác **trả Mono/Publisher**, ví dụ một truy vấn DB tiếp theo.
- `then`: chờ completion của upstream nhưng **bỏ đi giá trị** upstream và chuyển sang tác vụ kế tiếp.
- `switchIfEmpty`: thay một publisher **empty**, không xử lý error.

**Đặc biệt:** `map(order -> repository.save(order))` tạo ra `Mono<Mono<Order>>` nếu không flatten; thường cần `flatMap(order -> repository.save(order))`.

### 3.7. `defer` để tính thao tác khi subscribe

~~~java
Mono<Instant> nowAtSubscribe =
    Mono.defer(() -> Mono.just(Instant.now()));
~~~

`Mono.just(Instant.now())` tính thời gian lúc **lắp pipeline**; `defer` trì hoãn việc tạo publisher/tính side effect đến subscription. Hữu ích khi cần lấy request context, timestamp hoặc tạo resource đúng thời điểm, nhưng không thay `ReactiveMongoTemplate` hay tự tạo transaction.

### 3.8. `subscribe()` không phải “lệnh chạy nền miễn phí”

Gọi `subscribe()` trong service rồi trả `Mono.just("OK")` ngay có thể làm HTTP response báo thành công **trước khi DB write hoàn tất**; lỗi write không đi đúng kênh đến caller, cancellation và transaction boundaries bị tách. Trong request path, **return composition** thay vì manual subscribe.

## 4. Dependency và cấu hình Spring Boot

### 4.1. Gradle dependencies

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Các tokens `<boot-version>` và `<compatible-version>` là placeholders để chọn từ BOM/Gradle của dự án, không phải file chạy nguyên xi. Nếu dùng Spring Boot plugin có BOM management tích hợp, tuân thủ đúng bản Boot thay vì phối các dependencies thủ công. Bài này **không chạy Gradle**; đây là ví dụ hướng dẫn người học.

### 4.2. Maven dependencies

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
  </dependency>
  <dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Spring Boot BOM/parent cần quản lý versions. **Không tự thêm starter imperative `spring-boot-starter-data-mongodb`** nếu mục tiêu chỉ cần reactive data access; hai starters cùng tồn tại có thể dẫn đến auto-configuration/bean choices cần quản lý rõ.

### 4.3. MongoDB URI

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

Trong real deployment, URI từ secret manager/env có thể là:

~~~text
mongodb+srv://<user>:<password>@cluster.example.mongodb.net/shop
~~~

Không commit username/password thật trong repository. Với local replica set, URI phải có replicaSet/topology đúng, hostname reachable; không dùng `directConnection=true` chỉ để vô tình che lỗi cấu hình HA.

### 4.4. Boot auto-configuration

Với reactive MongoDB starter và properties hợp lệ, Spring Boot thường tạo reactive Mongo client/database factory, `ReactiveMongoTemplate` và hỗ trợ repository scanning theo auto-config. Cần **một context configuration rõ ràng** nếu dự án có nhiều MongoDB databases/clients, profiles hoặc đồng thời imperative/reactive.

### 4.5. Cấu hình thủ công khi cần

~~~java
@Configuration
@EnableReactiveMongoRepositories(basePackages = "com.example.orders")
class ReactiveMongoConfig {
    // Để Boot auto-config MongoClient và ReactiveMongoTemplate,
    // hoặc khai bean tùy chỉnh với ReactiveMongoDatabaseFactory
    // khi thực sự có yêu cầu nhiều databases/clients.
}
~~~

**Không nên** vừa khai báo một `@Bean ReactiveMongoTemplate` tùy chỉnh vừa giả định AutoConfig tự lựa đúng mọi repository/transaction manager. Kiểm bean graph và context integration ở project thực.

### 4.6. Reactive Java driver khác Sync Java driver

Reactive Spring Data MongoDB sử dụng **MongoDB Reactive Streams driver** bên dưới, không phải `MongoClient` của Java Sync Driver được nhúng trong `Mono.fromCallable`. Sử dụng reactive driver giúp MongoDB I/O non-blocking theo pipeline. Một DAO sử dụng `MongoTemplate` blocking rồi bọc `Mono.just(...)` **vẫn block thread**.

## 5. Domain model và các quy tắc mapping

Ta xây hệ thống quản lý đơn hàng đơn giản:

~~~json
{
  "_id": "ORD-1001",
  "tenantId": "tenant-a",
  "customerId": "C-100",
  "status": "OPEN",
  "amountMinor": 250000,
  "createdAt": "2026-11-14T00:00:00Z",
  "version": 0
}
~~~

Sử dụng số nguyên `amountMinor` để tránh sai số floating-point trong các phép tính tiền. Trong MongoDB thực tế, `createdAt` là BSON Date, JSON trên chỉ để minh họa; `@Version` của Spring Data quản lý optimistic locking.

### 5.1. Entity

~~~java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
    name = "tenant_status_created_id",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1}")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private long amountMinor;
    private Instant createdAt;
    @Version
    private Long version;

    // Getters/setters hoặc constructor phù hợp cho Spring Data mapping.
}
~~~

Đoạn class rút gọn có chú thích phần getters/setters; khi dùng trong dự án cần tạo đủ constructors/accessors hoặc dùng immutable mapping theo Spring Data version. Định nghĩa `@CompoundIndex` **không đồng nghĩa index đã được tạo trong production**: auto-index creation trong Spring Data MongoDB hiện cần được chủ động bật/theo migration policy; production thường quản lý indexes có kiểm soát.

### 5.2. Vì sao index vẫn quan trọng với reactive?

Khi query:

~~~text
tenantId = "tenant-a"
status = "OPEN"
sort createdAt descending
limit 20
~~~

index dạng `{tenantId:1,status:1,createdAt:-1,_id:1}` có thể giúp filter/sort, phụ thuộc query shape và cardinality. Reactive driver không thể biến `COLLSCAN` thành `IXSCAN`. Khi request đông, query chậm làm tăng **in-flight operations** và connection pool pressure dù app không block threads.

### 5.3. Multi-tenant fields và bảo mật

Repository method `findById(id)` **không tự áp tenant authorization**. Nếu biết ID đơn hàng tenant khác, user có thể truy cập sai data trừ khi ứng dụng kiểm tra quyền/tenant.

Ưu tiên:

~~~java
Mono<Order> findByTenantIdAndId(String tenantId, String id);
~~~

`tenantId` phải lấy từ **server-validated auth context**, không tin query parameter do client tự khai. Reactive context propagation cần giữ auth identity đúng xuyên các operators/threads, không dựa vào `ThreadLocal` thay thế.

### 5.4. Mapping và null

MongoDB documents có thể thiếu fields; Java primitive `long amountMinor` sẽ có default 0 khi không có field trong nhiều mapping settings, gây nhầm “0 đồng” với “không có dữ liệu”. Với schema evolution, kiểm `@Field`, validation, nullable wrappers/records, default values và migration; không dựa vào reactive stream để chữa dữ liệu schema thiếu.

## 6. Reactive repository: khai báo CRUD/query theo domain

### 6.1. Interface cơ bản

~~~java
package com.example.orders;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<Order, String> {

    Mono<Order> findByTenantIdAndId(String tenantId, String id);

    Flux<Order> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status);

    Mono<Long> countByTenantIdAndStatus(String tenantId, String status);

    Mono<Boolean> existsByTenantIdAndCustomerId(
        String tenantId, String customerId);
}
~~~

Spring Data tạo implementation dựa trên **tên phương thức** và metadata của domain class. Chữ ký trả **Publisher** (`Mono`/`Flux`) không block khi method được gọi để tạo pipeline. Nhưng execution cần subscription; service/controller nên **return** publisher.

### 6.2. Các phương thức CRUD kế thừa

| Phương thức | Kết quả reactive | Ghi chú |
|---|---|---|
| `findById(id)` | `Mono<Order>` | Có thể `empty` nếu không tồn tại. |
| `findAll()` | `Flux<Order>` | Có thể phát nhiều documents; tránh trả không giới hạn qua API. |
| `save(order)` | `Mono<Order>` | Insert hoặc update theo entity state/version; không mặc định là patch từng field. |
| `deleteById(id)` | `Mono<Void>` | Hoàn tất không chứa số docs đã xóa; tenant authorization phải kiểm riêng. |
| `count()` | `Mono<Long>` | Có thể tốn tài nguyên nếu filter/corpus lớn. |
| `existsById(id)` | `Mono<Boolean>` | Là separate read, không loại bỏ race trước write. |

Đối với reactive MongoDB, `ReactiveMongoRepository` kế thừa những reactive CRUD APIs thông dụng, nhưng **không phải mọi method trong `MongoRepository` imperative có cùng signature**. Khi cần API như pagination tùy biến, chọn đúng reactive repository interfaces/version.

### 6.3. Derived queries

~~~java
Flux<Order> findByTenantIdAndStatus(String tenantId, String status);

Flux<Order> findByTenantIdAndAmountMinorGreaterThan(
    String tenantId, long amountMinor);

Mono<Order> findFirstByTenantIdAndCustomerIdOrderByCreatedAtDesc(
    String tenantId, String customerId);
~~~

Tên method đọc tiện nhưng có thể **rất dài** hoặc không diễn đạt được aggregation phức tạp. Dùng `@Query`/`ReactiveMongoTemplate` khi filter/sort/update phức tạp hoặc muốn kiểm soát rõ hành vi.

### 6.4. Dùng `@Query` và bind parameters

~~~java
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends ReactiveMongoRepository<Order, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        sort = "{ 'createdAt': -1, '_id': 1 }")
    Flux<Order> findVisibleByState(String tenantId, String status);
}
~~~

`?0`, `?1` được Spring Data bind theo thứ tự argument. Không nối JSON query strings bằng user-supplied fragments; hãy dùng parameter binding/`Criteria` để giảm injection/malformed query risk. Không đưa tenantId do client kiểm soát vào filter mà không xác thực server-side.

### 6.5. Reactive query nhận parameter là Publisher

Một số Spring Data repository methods có thể nhận **reactive parameters** (ví dụ `Mono<String>`) để resolve giá trị trước query, tùy API/version. Tuy nhiên, đừng dùng hình thức đó để giấu một blocking call: `Mono.just(blockingLookup())` vẫn thực hiện blockingLookup **ngay khi tạo Mono**.

### 6.6. Reactive repository và pagination

Trong reactive world, đừng vội khai `Page<Order> findAll(Pageable p)` như trong imperative stack. Xây:

~~~java
Flux<Order> findByTenantId(String tenantId, Pageable pageable);
~~~

Và nếu UI thực sự cần total count:

~~~java
Mono<Long> countByTenantId(String tenantId);
~~~

`Flux` cung cấp nội dung trang; `count` là **một truy vấn khác**, không nhất thiết là snapshot timestamp giống query list khi writes đang chạy. Có thể dùng `Mono.zip(...)` để kết hợp 2 calls và tạo response có total (hoặc bỏ count cho infinite scrolling).

### 6.7. Tại sao `findAll().collectList()` có thể nguy hiểm?

~~~java
Mono<List<Order>> everyOrder =
    repository.findAll().collectList();
~~~

Đây là non-blocking ở tầng chờ I/O nhưng **đưa toàn bộ kết quả vào RAM**. Với hàng triệu documents, heap/OOM/GC vẫn xảy ra. Reactive không có nghĩa không dùng memory. Áp tenant filter, indexed query, `limit`/pagination, projection hoặc streaming output có giới hạn.

### 6.8. Repository không phải giải pháp cho mọi operation

Nếu cần conditional atomic update, complex aggregation, index hints, sort/limit tùy runtime, write concern/read preference hoặc change streams, thường **`ReactiveMongoTemplate`** giúp biểu đạt rõ hơn. Có thể dùng cả repository lẫn template **trong cùng service** trên một reactive MongoDB connection infrastructure.

## 7. ReactiveMongoTemplate: truy vấn linh hoạt

### 7.1. Inject reactive template

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final ReactiveMongoTemplate template;

    public OrderQueryService(ReactiveMongoTemplate template) {
        this.template = template;
    }
}
~~~

`ReactiveMongoTemplate` là implementation chính của `ReactiveMongoOperations`. Nó cung cấp mapping, conversion, update/aggregation helpers và giao tiếp với reactive driver. Dùng dependency injection thay vì tự tạo `ReactiveMongoClient`/template trên từng request.

### 7.2. `findOne` và `find`

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

public Mono<Order> findOne(String tenantId, String orderId) {
    Query q = query(where("tenantId").is(tenantId)
        .and("_id").is(orderId));
    return template.findOne(q, Order.class);
}

public Flux<Order> listOpen(String tenantId) {
    Query q = query(where("tenantId").is(tenantId)
        .and("status").is("OPEN"))
        .with(Sort.by(Sort.Direction.DESC, "createdAt"))
        .limit(20);
    return template.find(q, Order.class);
}
~~~

`findOne` trả `Mono<Order>` và `find` trả `Flux<Order>`. Phần mapping giữa Java field name và MongoDB field name do Spring Data mapping context xử lý; trong các trường hợp `@Field("...")`, dùng Java property path trong DSL và xác minh BSON query nếu tự lắp raw JSON.

### 7.3. Fluent API

~~~java
Flux<Order> openOrders = template.query(Order.class)
    .matching(query(where("tenantId").is(tenantId)
        .and("status").is("OPEN")))
    .all();

Mono<Order> first = template.query(Order.class)
    .matching(query(where("tenantId").is(tenantId)))
    .one();
~~~

Fluent `template.query(Order.class)` giúp tách entity type, filter, projection và terminal operator. Tên terminal có thể là `one()`/`first()`/`all()` theo API/version; `one()` không nên bị nhầm với “đếm đúng một document” nếu query match nhiều docs. Khi nghiệp vụ bắt buộc unique match, áp **unique index** và kiểm semantics.

### 7.4. Projection giảm network và heap

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("status").is("OPEN"));
q.fields().include("_id").include("status").include("amountMinor");
q.limit(30);

Flux<Order> partial = template.find(q, Order.class);
~~~

Khi map projection vào entity đầy đủ, fields không trả về có thể mang null/default values; nếu vô tình `save(partialEntity)`, dễ ghi đè dữ liệu. Ưu tiên DTO projection `template.query(...).as(OrderSummary.class)` hoặc class riêng, và **không save projection như một full entity**.

### 7.5. Query parameters và index

~~~javascript
// MongoDB index tương ứng với ví dụ filter + sort:
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
})
~~~

Tránh regex `.*keyword.*` trên trường không phù hợp hoặc `skip` sâu khiến query chậm. Với API tìm kiếm text nâng cao, cân nhắc MongoDB Search index khi deployment hỗ trợ, nhưng đây là một capability khác với reactive execution.

## 8. ReactiveMongoTemplate: ghi, sửa và xóa

### 8.1. Insert và save

~~~java
public Mono<Order> create(Order order) {
    return template.insert(order);
}

public Mono<Order> save(Order order) {
    return template.save(order);
}
~~~

`insert` dành cho document mới; duplicate `_id`/unique key có thể tạo error (Spring Data chuyển thành data-access exceptions phù hợp). `save` có thể upsert/update theo identity/version/mapping; không nên xem nó như **patch only changed fields** trong mọi tình huống.

### 8.2. Atomic update theo filter

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

public Mono<UpdateResult> markPaid(
        String tenantId, String orderId) {

    Query q = query(where("_id").is(orderId)
        .and("tenantId").is(tenantId)
        .and("status").is("OPEN"));

    Update update = new Update().set("status", "PAID");
    return template.updateFirst(q, update, Order.class);
}
~~~

Đây là **một write atomic trên một document**, chống race tốt hơn `findById -> sửa object -> save` khi chỉ cần conditional transition. `UpdateResult.getMatchedCount()`/`getModifiedCount()` giúp phân biệt không match với đã match nhưng không thay đổi; nếu update idempotent, giá trị matched và modified có thể khác.

### 8.3. Kiểm kết quả update đúng cách

~~~java
public Mono<Void> pay(String tenantId, String orderId) {
    return markPaid(tenantId, orderId)
        .flatMap(result -> {
            if (result.getMatchedCount() == 0) {
                return Mono.error(
                    new OrderConflictException("not OPEN or not found"));
            }
            return Mono.<Void>empty();
        });
}
~~~

`OrderConflictException` là application exception giả định cần khai báo. Trong multi-tenant API, trả lời 404 hay 409 phụ thuộc policy: không tiết lộ sự tồn tại order ở tenant khác. Không dùng `flatMap` làm Java method chạy tức thì; code bên trong chỉ chạy khi publisher được subscribe.

### 8.4. Update nhiều documents và resource cost

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("status").is("EXPIRED"));

Mono<UpdateResult> updated = template.updateMulti(
    q, new Update().set("status", "ARCHIVED"), Order.class);
~~~

`updateMulti` có thể tác động nhiều documents và tiêu tốn server resources; không chuyển sang reactive rồi coi có thể chạy hàng trăm large updates vô hạn. Bounded concurrency, indexes và scheduling vẫn cần thiết. Khi nhiều collections cần atomicity, cân nhắc transaction đúng điều kiện.

### 8.5. Delete với filter tenant

~~~java
import com.mongodb.client.result.DeleteResult;

Mono<DeleteResult> deleted = template.remove(
    query(where("_id").is(orderId).and("tenantId").is(tenantId)),
    Order.class);
~~~

Kiểm `deleted.getDeletedCount()` để biết số rows bị xóa. Không dùng `repository.deleteById(orderId)` trong endpoint đa tenant nếu chưa xác minh authorization.

### 8.6. Find-and-modify atomic

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query q = query(where("_id").is(orderId)
    .and("tenantId").is(tenantId)
    .and("status").is("OPEN"));

Update u = new Update().set("status", "PAID");

Mono<Order> after = template.findAndModify(
    q, u,
    FindAndModifyOptions.options().returnNew(true),
    Order.class);
~~~

`findAndModify` có thể update và trả document trong **một thao tác atomic trên document**, tránh race giữa update và read riêng biệt. Nếu không match thì `Mono.empty()`. Không có multi-document transaction ngầm chỉ vì API này dùng tên “findAndModify”.

### 8.7. Optimistic locking với `@Version`

Khi entity có `@Version`, Spring Data có thể phát hiện một số stale-save conflicts và ném `OptimisticLockingFailureException`. Nhưng guarantee cụ thể phụ thuộc entity update path, version field, write concern, server capabilities và API:

- Nếu cần optimistic locking, giữ `@Version` và kiểm exception semantics.
- Không dùng `findById` rồi `save` thiếu version khi có concurrent updates.
- Với conditional updates dùng `Query` có version predicate khi cần CAS rõ ràng.
- Có retry bounded + idempotency cho transient failures.

**Không** cho rằng mọi custom `updateMulti` tự thực hiện version check giống `save(entity)`.

## 9. Service WebFlux end-to-end: trả Publisher, không tự subscribe

Một kiến trúc reactive có đường đi:

~~~text
HTTP client
   |
   v
WebFlux Router/Controller
   |
   v
Reactive Service (Mono/Flux)
   |
   +--> ReactiveMongoRepository
   |           |
   |           +--> Reactive MongoDB Driver
   |
   +--> ReactiveMongoTemplate
   |           |
   |           +--> Reactive MongoDB Driver
   |
   v
WebFlux subscribes/serializes with demand
   |
   v
HTTP response
~~~

**Nguyên tắc:** Controller và service **trả pipeline**, framework subscribe và quản lý lifecycle/cancellation. Một service không nên gọi `subscribe()` để “chạy rồi” và cũng không `block()` để “chờ xong” khi xử lý request.

### 9.1. Service truy xuất theo tenant

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderService {
    private final OrderRepository repo;
    private final ReactiveMongoTemplate template;

    public OrderService(
            OrderRepository repo,
            ReactiveMongoTemplate template) {
        this.repo = repo;
        this.template = template;
    }

    public Mono<Order> get(String tenantId, String id) {
        return repo.findByTenantIdAndId(tenantId, id);
    }

    public Flux<Order> listOpen(String tenantId) {
        return repo.findByTenantIdAndStatusOrderByCreatedAtDesc(
            tenantId, "OPEN");
    }

    public Mono<Order> create(Order order) {
        return template.insert(order);
    }
}
~~~

Các đoạn Java trong tài liệu được rút gọn imports/DTO validation để tập trung vào reactive patterns; production cần constructors, exception mapping, tenant authorization, input validation và idempotency.

### 9.2. Controller trả `Mono<ResponseEntity<...>>`

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Order>> get(
            @PathVariable String id,
            @RequestHeader("X-Verified-Tenant") String tenantId) {
        return service.get(tenantId, id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping
    public Flux<Order> list(
            @RequestHeader("X-Verified-Tenant") String tenantId) {
        return service.listOpen(tenantId).take(50);
    }
}
~~~

**Cảnh báo bảo mật:** `X-Verified-Tenant` chỉ là placeholder cho **identity đã được API gateway/security filter xác thực và ký/xóa headers giả**. Đừng tin HTTP header tenant do client tùy ý gửi. Trong ứng dụng thật nên lấy principal/tenant từ **Spring Security reactive context** (`ReactiveSecurityContextHolder`/authentication) và lọc DB theo tenant ở mọi query.

### 9.3. HTTP 404 cho empty

`findById` khi không tìm thấy thường `Mono.empty()`, không tự sinh exception. Với:

~~~java
return repo.findById(id)
    .map(ResponseEntity::ok)
    .defaultIfEmpty(ResponseEntity.notFound().build());
~~~

WebFlux nhận `Mono<ResponseEntity<Order>>` và trả đúng 404 nếu empty. Nếu thay bằng `repo.findById(id).block()`, ta đã làm mất mô hình event-loop non-blocking.

### 9.4. Validation và response types

Khi tạo order:

~~~java
@PostMapping
public Mono<ResponseEntity<Order>> create(
        @Valid @RequestBody Mono<CreateOrderRequest> request) {
    return request
        .map(dto -> toEntity(dto)) // CPU work nhỏ, không block
        .flatMap(service::create)
        .map(saved -> ResponseEntity
            .status(HttpStatus.CREATED)
            .body(saved));
}
~~~

`toEntity` là hàm mapping giả định; cần validate ở boundary, tenant context từ authentication, unique key, status initial và business rules. Nếu phiên bản WebFlux/Bean Validation config yêu cầu khác biệt về `@Valid` và reactive body binding, kiểm Spring Framework docs; test endpoint bằng `WebTestClient`.

### 9.5. Không tự subscribe trong controller

**Sai:**

~~~java
@PostMapping("/bad")
public Mono<String> bad(@RequestBody Mono<Order> body) {
    body.flatMap(repo::save).subscribe();
    return Mono.just("Saved");
}
~~~

Controller trả `Saved` trước khi DB write có thể hoàn tất, lỗi write không vào HTTP response đúng cách; cancellation và transaction scope tách khỏi caller.

**Đúng:**

~~~java
@PostMapping("/good")
public Mono<Order> good(@RequestBody Mono<Order> body) {
    return body.flatMap(repo::save);
}
~~~

Từ `Mono<Order>` framework sẽ subscribe một lần theo HTTP lifecycle. Tuy nhiên **at-least-once request retries từ client** vẫn có thể khiến API bị gọi lại, nên business cần stable idempotency key.

### 9.6. Service chaining `flatMap`

Giả sử tạo order rồi ghi audit record ở MongoDB:

~~~java
public Mono<Order> createWithAudit(Order input) {
    return repo.save(input)
        .flatMap(saved ->
            auditRepo.save(new AuditEvent(saved.getId(), "CREATED"))
                .thenReturn(saved));
}
~~~

Code này đảm bảo **thứ tự** “save order trước, save audit sau” trong một subscription, **không** biến hai writes thành một atomic transaction. Nếu audit thất bại, order có thể đã được lưu. Khi business cần all-or-nothing, dùng **ReactiveMongoTransactionManager** trên replica set/sharded cluster hỗ trợ hoặc transactional outbox với semantics phù hợp.

### 9.7. `Mono.zip` cho independent reads

~~~java
public Mono<OrderDetailsDto> getDetails(String tenantId, String id) {
    Mono<Order> order = repo.findByTenantIdAndId(tenantId, id);
    Mono<Long> activeCount = repo.countByTenantIdAndStatus(
        tenantId, "OPEN");

    return Mono.zip(order, activeCount)
        .map(tuple -> new OrderDetailsDto(
            tuple.getT1(), tuple.getT2()));
}
~~~

`Mono.zip` kết hợp hai publishers, có thể subscribe đồng thời và tạo **2 DB operations cùng lúc**. Nếu `order` empty thì zip có thể complete empty/cancel nhánh còn lại; nếu cần trả 404, xử lý empty trước hoặc thiết kế dùng `flatMap` để chỉ count sau khi có order. Khi concurrent writes, count và order có thể phản ánh **hai read points khác nhau**; `zip` không tự tạo transaction/snapshot.

### 9.8. Khi nào nên `concatMap` thay vì `flatMap`?

~~~java
Flux<Order> savedInOrder = Flux.fromIterable(inputs)
    .concatMap(repo::save);
~~~

`concatMap` giữ thứ tự hoàn tất/đăng ký tuần tự theo semantics; phù hợp khi các writes có dependency/order requirement. `flatMap(repo::save, 8)` cho concurrency cao hơn nhưng thứ tự completion có thể khác. **Không** dùng `flatMap` không giới hạn với hàng chục nghìn documents khi DB đang chịu tải.

## 10. Cấm blocking trên WebFlux event loop

### 10.1. `block()` là ranh giới chuyển reactive sang blocking

**Anti-pattern nghiêm trọng:**

~~~java
@GetMapping("/{id}/bad")
public Order bad(@PathVariable String id) {
    return repo.findById(id).block();
}
~~~

`block()` sẽ chờ đồng bộ đến khi `Mono` hoàn thành; nếu chạy trên Reactor Netty event loop hoặc Scheduler đánh dấu non-blocking, Reactor có thể ném:

~~~text
IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Ngay cả khi framework không ném exception trong một thread cụ thể, call blocking vẫn có thể **chiếm thread** và giảm khả năng phục vụ. Không lấy việc “code chạy được” làm bằng chứng nó non-blocking.

### 10.2. Những thao tác có thể block

| Thao tác | Nguy cơ | Thay thế |
|---|---|---|
| `Mono.block()` / `Flux.blockFirst()` | Giữ thread chờ Publisher. | Return/compose `Mono`, `Flux`. |
| `Flux.toIterable()` / `toStream()` | Kéo dữ liệu đồng bộ theo iterator/stream. | `map`/`flatMap`/streaming response. |
| `Thread.sleep(...)` | Block thread đang chạy. | `Mono.delay(...)`/`delayElement(...)`. |
| `MongoTemplate.find(...)` | Java Sync MongoDB I/O. | `ReactiveMongoTemplate.find(...)`. |
| `JdbcTemplate` / JDBC driver blocking | Giữ worker khi chờ DB. | R2DBC driver nếu hệ sinh thái hỗ trợ, hoặc isolate blocking calls. |
| `RestTemplate` / Apache blocking HTTP | Network blocking. | `WebClient`. |
| `Files.readAllBytes(...)` lớn, sync disk I/O | Chặn thread, peak memory. | Async-capable API hoặc boundedElastic + size limits. |
| SDK S3/payment blocking | Network blocking. | Async SDK hoặc boundedElastic có bounded concurrency. |
| `synchronized`/locks dài | Thread contention/block, serialization. | Tránh critical section dài; immutable state/async design. |
| CPU-heavy JSON/crypto/image processing | Chặn event loop dù không I/O. | CPU-specific bounded scheduler/worker, limit concurrency. |

Chú ý: **CPU-heavy không đồng nghĩa blocking I/O**; `Schedulers.boundedElastic()` dành cho blocking tasks, còn CPU-bound pure work thường hợp `parallel()` hoặc worker pool có giới hạn. Dù offload sang scheduler nào, số tasks phải được quản lý.

### 10.3. `Mono.just(blockingCall())` vẫn block trước subscription

**Sai:**

~~~java
Mono<User> user = Mono.just(legacyDao.loadUser(id));
~~~

Java đánh giá argument `legacyDao.loadUser(id)` **ngay khi xây Mono**, nên blocking xảy ra ở caller thread. Đổi thành `Mono.defer` chỉ trì hoãn call; nếu defer vẫn chạy trên event loop thì **vẫn block**.

**Khi bắt buộc dùng legacy blocking API:**

~~~java
Mono<User> user = Mono.fromCallable(() -> legacyDao.loadUser(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` trì hoãn việc gọi blocking DAO tới subscription, `subscribeOn` lên scheduler có threads dành cho blocking. Đây là **giải pháp tương thích tạm**, không thay thế việc chuyển sang ReactiveMongoRepository/ReactiveMongoTemplate.

### 10.4. BoundedElastic không có nghĩa queue vô hạn an toàn

Reactor `Schedulers.boundedElastic()` có **giới hạn số backing threads**, nhưng cũng có **hàng đợi scheduled tasks có sức chứa riêng** (Reactor docs mô tả một mặc định lớn, version-dependent). Nếu 20.000 HTTP requests đồng loạt gọi legacy blocking API, bạn vẫn có thể:

- Xếp hàng rất lâu trên boundedElastic.
- Hết HTTP deadline khi task còn chờ.
- Tăng heap/queue pressure.
- Gây overload cho hệ thống legacy/DB.

Nên có **bounded admission, global/per-tenant concurrency, timeout, retry policy** phía trước. Với một workload blocking lớn, tạo scheduler riêng bằng `Schedulers.newBoundedElastic(...)` có giới hạn rõ và **dispose khi application shutdown**, nếu cần bulkhead tách biệt.

### 10.5. `publishOn` và `subscribeOn` khác nhau

~~~java
Mono.fromCallable(() -> legacyDao.loadUser(id))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::mapToDto);
~~~

`subscribeOn` ảnh hưởng nơi upstream subscription/source chạy; phù hợp khi **nguồn là blocking call**.

~~~java
repository.findById(id)
    .publishOn(Schedulers.parallel())
    .map(this::cpuHeavyTransformation);
~~~

`publishOn` đổi nơi downstream operators được thực thi từ vị trí đó; hữu ích khi một bước CPU-bound nên chạy ngoài event loop. Nếu `cpuHeavyTransformation` thực sự rất nặng, cần giới hạn concurrency/cost, tránh gọi parallel scheduling như phép nhân CPU vô hạn.

**Sai lầm:** gắn `publishOn(boundedElastic())` **sau** một `map(x -> legacyBlocking())` không “dịch chuyển ngược thời gian” để ngăn `map` trước đó block.

### 10.6. `Thread.sleep` thay bằng timer publisher

**Sai:**

~~~java
return repo.findById(id)
    .map(order -> {
        Thread.sleep(1000); // không hợp lệ nếu chưa catch; vẫn block
        return order;
    });
~~~

**Đúng theo nhu cầu delay signal:**

~~~java
return repo.findById(id)
    .delayElement(Duration.ofSeconds(1));
~~~

`delayElement` trì hoãn signal mà không giữ một event-loop thread `sleep()` trong một giây. Nếu mục tiêu là retry backoff, dùng `retryWhen(Retry.backoff(...))` có cap và chọn lỗi retryable, **không** tùy tiện delay mọi request một giây.

### 10.7. Blocking trong mapper vẫn là blocking

~~~java
return repo.findById(id)
    .map(order -> blockingPaymentGateway.check(order));
~~~

`map` chạy theo thread đang phát signal, có thể là I/O/event loop. Dù signature trả `Mono<Result>`, blocking bên trong `map` vẫn giữ worker. Nếu có async gateway:

~~~java
return repo.findById(id)
    .flatMap(order -> asyncPaymentGateway.check(order));
~~~

Nếu gateway chỉ có blocking API, áp `fromCallable + subscribeOn(boundedElastic())` **và admission cap**, nhưng phải tách side effects/idempotency và timeout.

### 10.8. Test với BlockHound

Trong môi trường test/diagnostics, **BlockHound** có thể phát hiện các blocking calls trên non-blocking schedulers. Tuy nhiên hỗ trợ BlockHound phụ thuộc JDK/Reactor/framework version và instrumentation compatibility. Một số blocking hành vi không bị nhận diện hoặc library có allowlist; **không** coi “BlockHound không báo” là bằng chứng end-to-end hoàn toàn non-blocking.

Nên phối hợp với Reactor event-loop lag metrics, thread dumps, CPU profiles và load tests.

### 10.9. Khi gọi `block()` có thể hợp lệ?

Ở **ranh giới imperative** như application command-line, một unit test hoặc startup script chủ động chạy ngoài event loop, `block()` có thể được dùng có kiểm soát (thường với timeout). Nhưng **không** dùng `block()` ở giữa WebFlux request pipeline; không giả định `block()` là một phương pháp “ép publisher chạy nhanh hơn”.

## 11. Backpressure và giới hạn concurrency: reactive không phải vô hạn

### 11.1. Subscriber demand và MongoDB cursor

Khi HTTP client đọc chậm hơn khả năng MongoDB trả documents, Reactor có thể truyền demand/cancellation qua các operators. Tuy nhiên, MongoDB driver/server có thể lấy dữ liệu theo **cursor batches** và operators có **prefetch**; do vậy không có cam kết “HTTP request 1 item thì chỉ 1 BSON document được đọc từ disk”.

~~~text
MongoDB cursor -> Reactive Driver -> Flux<Order> -> JSON encoder -> HTTP socket
                         ^                        |
                         |        demand/backpressure
                         +------------------------+
~~~

**Backpressure là cơ chế phối hợp**, không phải miễn phí RAM, không thay query `limit` và không bảo đảm service không overload nếu cùng lúc có 10.000 subscriptions.

### 11.2. `flatMap` có giới hạn

**Rủi ro:**

~~~java
Flux<Order> all = Flux.fromIterable(ids)
    .flatMap(id -> repo.findById(id));
~~~

`flatMap` có concurrency/prefetch defaults theo Reactor version. Với danh sách lớn, có thể tạo nhiều concurrent MongoDB calls hơn cần thiết.

**Tường minh:**

~~~java
Flux<Order> bounded = Flux.fromIterable(ids)
    .flatMap(id -> repo.findById(id), 8);
~~~

`8` giới hạn số **inner publishers được subscribe đồng thời trong pipeline đó**, không phải “MongoDB global max 8 operations”. Nếu 100 HTTP requests chạy cùng pipeline, có thể lên tới ~800 in-flight calls theo các điều kiện. Dùng global gate/limits ở tầng service/gateway khi cần bảo vệ cluster.

### 11.3. `concatMap`, `flatMapSequential` và thứ tự

| Operator | Concurrency | Ordering | Dùng khi |
|---|---|---|---|
| `concatMap` | Tuần tự theo source. | Giữ thứ tự results. | Writes phụ thuộc thứ tự; side effects cần sequence. |
| `flatMap(fn, n)` | Tối đa n inner publishers. | Completion có thể đảo thứ tự. | Independent reads/updates có giới hạn. |
| `flatMapSequential(fn, n)` | Subscribe đồng thời, phát kết quả theo source order. | Giữ output order nhưng có thể buffer kết quả đến sớm. | Cần order output và concurrency, budget memory. |

`flatMapSequential` không có nghĩa operations thực thi tuần tự; chỉ **sắp thứ tự phát**, có thể giữ các kết quả hoàn tất sớm trong buffer, nên vẫn cần n và output size giới hạn.

### 11.4. Batch thay N+1

**Kém hiệu quả:**

~~~java
return Flux.fromIterable(ids)
    .flatMap(repo::findById, 16);
~~~

Nếu `ids` có 1.000 phần tử, dù concurrency=16 vẫn có tới 1.000 MongoDB requests.

**Cân nhắc query theo `$in` có giới hạn:**

~~~java
Query q = query(where("_id").in(ids));
q.limit(200); // ví dụ; kiểm policy của API
return template.find(q, Order.class);
~~~

Không đưa `ids` hàng triệu phần tử vào `$in`, không quên tenant filter và giới hạn response. Nếu muốn bảo toàn thứ tự danh sách `ids`, MongoDB query `$in` **không tự bảo đảm thứ tự theo input**; cần sort/map kết quả theo policy.

### 11.5. `buffer` và `window`

~~~java
Flux<List<Order>> batches = ordersFlux.buffer(100);
~~~

`buffer(100)` tạo danh sách tối đa 100 items mỗi batch theo count, nhưng có thể nhiều batches in-flight nếu downstream/operators tiếp tục yêu cầu. `window(100)` chia thành sub-publishers, không materialize một List ngay; cả hai cần kế hoạch release/error/cancellation.

Đừng lấy `buffer(100)` rồi `collectList()` trên toàn bộ batches và coi memory đã bounded — toàn stream vẫn có thể bị gom lại.

### 11.6. `onBackpressureBuffer` không phải phép chữa mặc định

~~~java
flux.onBackpressureBuffer(10_000);
~~~

Operator này **lưu thêm dữ liệu trong bộ nhớ**, có thể che vấn đề downstream chậm và tạo heap pressure. Dùng version có capacity/overflow policy phù hợp nếu business thật sự cần, cân nhắc:

- Backpressure-aware sources.
- Bounded memory queue + reject/degrade.
- Durable message broker cho job queue dài.
- `onBackpressureLatest`/`onBackpressureDrop` chỉ khi **được phép mất dữ liệu** (telemetry/live UI), không dùng cho payments/orders.

### 11.7. Reactive stack vẫn dùng MongoDB connection pools

MongoDB Reactive Streams driver dùng asynchronous connections, nhưng vẫn có **pool theo server** và giới hạn như `maxPoolSize`/`maxConnecting` tùy driver version. Một subscription không đồng nhất 1 socket được giữ suốt đời, và event-loop thread count không bằng DB concurrent operations. Nếu hàng nghìn `flatMap` queries cùng bắt đầu, driver vẫn có **checkout wait và server resource contention**.

### 11.8. Giới hạn ở nhiều tầng

~~~text
API Gateway quota
        |
        v
Request concurrency / tenant admission
        |
        v
Reactor flatMap(..., maxConcurrency)
        |
        v
Reactive MongoDB Driver pool
        |
        v
mongos/mongod CPU, I/O and locks
~~~

Một local `flatMap(..., 8)` không thay global cap. Nếu app autoscale từ 5 lên 50 pods, lượng operations tối đa có thể tăng 10 lần dù code không đổi. Tính budget theo **max pods × per-pod DB in-flight × query fanout** và đo với workload thật.

## 12. Streaming, pagination và đọc tập kết quả lớn

### 12.1. Flux không tự giới hạn số documents

~~~java
@GetMapping("/all")
public Flux<Order> all() {
    return repository.findAll();
}
~~~

Kỹ thuật này có thể serialize một stream rất lớn, giữ HTTP connection lâu và tạo pressure ở MongoDB. Production endpoint nên có:

- Tenant/status filters.
- Max page size hoặc `limit`.
- Index phù hợp filter/sort.
- HTTP output size/time budget.
- Cancellation khi client disconnect.

### 12.2. Offset pagination với repository

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Flux<Order> listPage(
        String tenantId, int page, int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    int safePage = Math.max(page, 0);

    Pageable pageable = PageRequest.of(
        safePage,
        safeSize,
        Sort.by(Sort.Direction.DESC, "createdAt")
            .and(Sort.by("_id")));

    return repo.findByTenantId(tenantId, pageable);
}
~~~

Repository cần khai báo `Flux<Order> findByTenantId(String tenantId, Pageable pageable);`. **Không trả `Mono<Page<Order>>` từ derived reactive finder** như imperative: Spring Data MongoDB reactive docs nêu `Page` wrapper không được hỗ trợ theo cách đó; tự tạo DTO với `Flux` + `count` nếu UI cần total.

### 12.3. Count là query thứ hai

~~~java
record OrderPage(List<Order> items, long total) { }

Mono<OrderPage> page = repo.findByTenantId(tenantId, pageable)
    .collectList()
    .zipWith(repo.countByTenantId(tenantId))
    .map(t -> new OrderPage(t.getT1(), t.getT2()));
~~~

Ở đây `collectList()` **chỉ** gom một page đã được bounded, không phải toàn collection. `zipWith` có thể cho hai queries chạy gần đồng thời, nhưng list/count **không nhất thiết là một snapshot consistent** khi concurrent writes; nếu cần chính xác cùng một snapshot phải thiết kế transactional/snapshot read phù hợp và cân nhắc chi phí.

### 12.4. Keyset pagination

Offset `skip(page*size)` ngày càng đắt nếu page sâu và dữ liệu có insert/delete xen giữa. Với sorted `createdAt DESC, _id DESC`, có thể dùng seek:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-14T00:00:00Z") } },
    { createdAt: ISODate("2026-11-14T00:00:00Z"),
      _id: { $lt: "ORD-1000" } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(50)
~~~

Ứng dụng gửi **cursor token** chứa last createdAt/ID đã ký và giới hạn page size; filter tenant phải giữ nguyên. Composite index có cùng thứ tự phục vụ query. Nếu ID dùng ObjectId/UUID/string khác nhau, điều kiện comparator phải tương thích BSON type/collation.

Spring Data mới có abstractions scroll/keyset tùy repository API version, nhưng ví dụ query `$or` giúp hiểu cơ chế không phụ thuộc một interface đặc biệt.

### 12.5. Cursor batch size

~~~java
Query q = query(where("tenantId").is(tenantId))
    .cursorBatchSize(100)
    .limit(500);

Flux<Order> stream = template.find(q, Order.class);
~~~

`cursorBatchSize(100)` điều chỉnh số documents *tối đa dự kiến mỗi batch* từ server theo MongoDB cursor semantics; không phải `Flux.request(100)` tuyệt đối và không giới hạn tổng documents nếu không có `limit`. Chọn batch size cân bằng network overhead, memory và latency đến phần tử đầu.

### 12.6. Streaming JSON và NDJSON

Đối với nhiều kết quả, một số HTTP endpoints có thể dùng `application/x-ndjson` để truyền từng document theo dòng:

~~~java
@GetMapping(
    value = "/stream",
    produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<OrderSummary> stream() {
    return service.streamSummaries();
}
~~~

`streamSummaries()` là service giả định phải có tenant filter, bounded query và projection. Việc server hỗ trợ streaming/backpressure phụ thuộc HTTP stack/codec/proxy/client: CDN/proxy có thể buffer, không phải cứ chọn NDJSON là cuối đường truyền thật sự xử lý từng item ngay.

### 12.7. HTTP client disconnect và cancellation

Khi client hủy HTTP request, WebFlux thường propagate `cancel` vào publisher. Reactive MongoDB driver có thể đóng/kill cursor hoặc ngừng nhận thêm data theo semantics, nhưng **không mặc định rằng một server write đã gửi sẽ bị rollback**. Cần:

- Đóng subscriptions/cursors/resources đúng lifecycle.
- Không để long-running tasks sống vô hạn sau cancel.
- Stable idempotency keys cho writes.
- Timeouts/tracing để phát hiện operation vẫn hoạt động.

### 12.8. Backpressure khác durability

Một client nhận SSE/NDJSON chậm không có nghĩa MongoDB sẽ “ghi nhớ mãi” mọi event để client resume. Nếu yêu cầu không mất event, dùng **change stream resume token + durable checkpoint** hoặc durable message broker thích hợp. `Flux` là abstraction về signal/demand, không phải permanent event log.

## 13. Aggregation bằng ReactiveMongoTemplate

### 13.1. Ví dụ thống kê trạng thái đơn hàng

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

record StatusSummary(String status, long total) { }

public Flux<StatusSummary> countByStatus(String tenantId) {
    Aggregation pipeline = newAggregation(
        match(where("tenantId").is(tenantId)),
        group("status").count().as("total"),
        project("total").and("_id").as("status")
    );

    return template.aggregate(
        pipeline, Order.class, StatusSummary.class);
}
~~~

Code giả định có Spring Data mapping phù hợp giữa `_id` và `status`/record constructor, cần kiểm mapping nếu production dùng custom field names/`@Field`. Query lọc tenant sớm để giảm docs scan, index phù hợp; aggregation chạy **phía MongoDB server**, reactive ở client không làm `$group` rẻ hơn.

### 13.2. Khác với `Mono<List<...>>`

`Flux<StatusSummary>` có thể phát từng nhóm kết quả, trong khi:

~~~java
Mono<List<StatusSummary>> all = countByStatus(tenantId).collectList();
~~~

gom toàn bộ rows vào memory. Nếu số nhóm bounded nhỏ và UI cần tất cả, việc gom List có thể hợp lý. Nếu group theo customerId cho hàng triệu customers, phải giới hạn/stream/paginate hoặc export async.

### 13.3. Update với aggregation pipeline

MongoDB hỗ trợ update pipeline trong các phiên bản nhất định; Spring Data có `AggregationUpdate` để biểu diễn cập nhật. Khi kết hợp với reactive template, cần xét:

- Atomicity theo document, không mặc định multi-document transaction.
- Mapping version fields.
- Update filter có tenant predicate và index.
- `UpdateResult`/`onError` semantics.
- Server CPU/IOPS và timeout khi update nhiều.

Không áp dụng các stages được phép trong read aggregation vào update aggregation một cách máy móc; MongoDB giới hạn các update pipeline stages được hỗ trợ.

### 13.4. Mẫu “aggregate rồi ghi”

~~~java
return template.aggregate(pipeline, Order.class, StatusSummary.class)
    .flatMap(summary -> statsRepository.save(
        toStatsDocument(summary)), 4)
    .then();
~~~

Một aggregation tạo hàng nghìn records rồi `flatMap` ghi mỗi record tạo N writes; concurrency 4 là giới hạn **local pipeline**, không bảo đảm atomic transaction và không làm hai collections snapshot consistent. Nếu muốn cùng một atomic workflow, cần transactional design; với analytics materialization, có thể chọn job idempotent/periodic backfill.

### 13.5. Spring Data mapping không thay manual `explain`

Để tối ưu performance, dùng MongoDB `explain("executionStats")` trên query shape thực, xem `IXSCAN/COLLSCAN`, sort, stages và visited docs. Reactive pipeline chậm có thể do MongoDB server execution, không phải Reactor scheduling; hãy đo cả **command duration** và **event-loop lag**.

## 14. Transaction reactive: Reactor Context thay cho ThreadLocal

Một giao dịch cần update hai collections atomically. Reactive execution có thể nhảy giữa threads, nên transaction/session association **không thể chỉ dựa vào ThreadLocal** như nhiều imperative frameworks.

### 14.1. `ReactiveMongoTransactionManager`

Spring Data MongoDB hỗ trợ `ReactiveMongoTransactionManager` trên `ReactiveMongoDatabaseFactory`, bind MongoDB `ClientSession` vào **Reactor subscriber Context**. Các operations qua Spring Data reactive template có thể tham gia transaction dựa trên context đó.

MongoDB deployment phải hỗ trợ transactions (replica set hoặc sharded cluster đủ điều kiện), user có quyền và Spring context phải có transaction manager. Transaction support **không tự bật chỉ bằng reactive Mongo starter** trong mọi cấu hình.

### 14.2. Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;

@Configuration
public class MongoTransactionsConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Đảm bảo template/repositories tham gia transaction dùng đúng **ReactiveMongoDatabaseFactory**/manager được cấu hình, không tạo nhiều clients/factories rồi giả định mọi operation nằm trong cùng transaction.

### 14.3. `TransactionalOperator`

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.ReactiveTransactionManager;

@Bean
TransactionalOperator mongoTxOperator(
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
~~~

Sau đó compose:

~~~java
public Mono<Order> createWithAudit(
        Order order, TransactionalOperator tx) {
    return template.insert(order)
        .flatMap(saved ->
            template.insert(new AuditEvent(saved.getId(), "CREATED"))
                .thenReturn(saved))
        .as(tx::transactional);
}
~~~

`as(tx::transactional)` áp transaction cho **upstream pipeline**. Cả hai inserts phải được subscribe **bên trong** cùng scope; không `subscribe()` audit bên cạnh, không `block()` rồi tách transaction. Nếu một write lỗi, transaction manager abort theo semantics, với chi phí/giới hạn transactions của MongoDB.

### 14.4. `@Transactional` với Publisher

~~~java
@Service
public class OrderWorkflow {
    private final ReactiveMongoTemplate template;

    @Transactional
    public Mono<Order> createAndRecord(Order order) {
        return template.insert(order)
            .flatMap(saved ->
                template.insert(new AuditEvent(saved.getId(), "CREATED"))
                    .thenReturn(saved));
    }
}
~~~

Phải có **reactive transaction manager** và Spring AOP proxy đi qua method; **self-invocation** có thể bypass proxy, method phải trả reactive type để transaction được điều phối theo subscription. `@Transactional` trên một method trả `void` có manual `subscribe()` không tạo scope mong muốn.

### 14.5. Đừng nhầm Reactor Context với ThreadLocal

~~~text
Subscriber Context:
   ClientSession / transaction metadata
          |
          v
 Reactor operators
          |
     [thread switches]
          |
          v
 ReactiveMongoTemplate operations
          |
          v
  Same transaction context
~~~

`ThreadLocal<Session>` do ứng dụng tự đặt có thể biến mất/sai khi `publishOn` đổi scheduler. Dùng Spring transaction manager/repository/template context integration. Khi cần truyền correlationId/tenantId, dùng **Reactor Context**/Spring Security reactive context thay vì `ThreadLocal` tùy ý.

### 14.6. Reactive repository và explicit ClientSession

Spring Data MongoDB docs phân biệt **ReactiveMongoTemplate explicit session support** với reactive repository APIs: không nên giả định một repository method tùy ý nhận `ClientSession` làm argument giống native driver. Đối với explicit session handling/transactions phức tạp, dùng `ReactiveMongoTemplate.withSession(...)` và callback theo docs; với declarative reactive transactions, đảm bảo đúng transaction manager/context.

### 14.7. Transaction và parallel operations

Đừng dùng:

~~~java
Flux.fromIterable(steps)
    .flatMap(step -> template.save(step), 64)
    .as(tx::transactional);
~~~

rồi kỳ vọng **64 operations concurrent trên cùng MongoDB ClientSession** luôn an toàn. MongoDB Java Driver/session không hỗ trợ concurrent operations trên cùng session một cách tùy ý; transaction cũng có giới hạn và có thể phát sinh errors/conflicts. Trong transaction, **điều phối tuần tự** nếu các operations phụ thuộc nhau:

~~~java
Flux.fromIterable(steps)
    .concatMap(template::save)
    .then()
    .as(tx::transactional);
~~~

Thực tế production còn cần retry transaction với backoff, giới hạn độ dài/lifetime và tránh gọi external blocking services bên trong transaction.

### 14.8. Commit ambiguous và external effects

Nếu client timeout/mất network sau commit request, transaction **có thể đã commit** dù app chưa nhận ACK. Không phát lại toàn bộ business operation với ID mới. Dùng stable idempotency keys, error labels/transaction retry helpers và verification. Nếu phải gửi email/call payment gateway, cân nhắc transactional outbox thay vì thực thi external side effect không-idempotent trong một retryable transaction callback.

## 15. Tailable cursor và change streams: Publisher sống lâu

Đối với nguồn dữ liệu liên tục, `Flux` đặc biệt hữu ích, nhưng cần phân biệt **tailable cursor của capped collection** với **MongoDB change streams**.

### 15.1. Tailable cursor dùng capped collection

Một capped collection giới hạn kích thước và giữ thứ tự insertion, hỗ trợ tailable cursor để chờ documents mới:

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;

Flux<LogEvent> events = template.tail(
    query(where("level").is("WARN")),
    LogEvent.class);
~~~

Điều kiện quan trọng:

- Collection phải **capped**, không dùng cursor tailable tùy tiện trên regular collection.
- Stream có thể vô hạn cho đến cancellation/failure.
- Tailable cursor có thể chết khi cursor position không hợp lệ hoặc query không có matching data trong tình huống nhất định.
- Capped collection tự overwrite old documents; **không đảm bảo durable event replay vô hạn**.

### 15.2. Reactive repository `@Tailable`

~~~java
import org.springframework.data.mongodb.repository.Tailable;

public interface LogEventRepository
        extends ReactiveMongoRepository<LogEvent, String> {

    @Tailable
    Flux<LogEvent> findByLevel(String level);
}
~~~

`@Tailable` chỉ phù hợp với methods trả **multi-element reactive type** như `Flux`. Với event log quan trọng cần retention/replay/ordering, cân nhắc change streams hoặc message broker phù hợp thay vì một capped collection không có checkpoint.

### 15.3. Change stream trên replica set/sharded cluster

MongoDB change streams cung cấp sự kiện thay đổi cho collections/databases được hỗ trợ, cần **replica set hoặc sharded cluster** phù hợp (không dùng trên standalone mongod kiểu đơn giản). Spring Data MongoDB reactive API:

~~~java
import org.springframework.data.mongodb.core.ChangeStreamEvent;

Flux<ChangeStreamEvent<Order>> changes = template
    .changeStream(Order.class)
    .watchCollection("orders")
    .listen();
~~~

Source phù hợp để triển khai CQRS projection, cache invalidation, notification; không mặc định **tất cả events đều được giữ vĩnh viễn**. Oplog/history window, resume tokens, namespace change và deployment version ảnh hưởng khả năng resume.

### 15.4. Xử lý và lưu resume token

~~~java
Flux<Void> processing = template.changeStream(Order.class)
    .watchCollection("orders")
    .listen()
    .concatMap(event ->
        projectionService.applyIdempotently(event)
            .then(checkpointStore.save(event.getResumeToken()))
    );
~~~

Các hàm `projectionService.applyIdempotently`/`checkpointStore.save` là APIs của ứng dụng cần tự viết **reactive**. Mẫu dùng `concatMap` để lưu thứ tự processing/checkpoint trong một subscription.

**Không có exactly-once end-to-end tự động**: nếu xử lý external side effect đã xong nhưng crash trước khi checkpoint, event có thể được xử lý lại. Phải thiết kế **idempotent consumer, dedupe theo event/document version** và checkpoint sau khi side effect durable.

### 15.5. Không `subscribe()` rồi quên `Disposable`

Nếu job nền chủ động subscribe:

~~~java
Disposable handle = changes.subscribe(
    event -> handleEvent(event),
    error -> logFailure(error));
~~~

Lúc application shutdown cần `handle.dispose()`, xử lý retry/backoff/resume và giới hạn số events đang xử lý; trong production nên quản lý lifecycle bằng Spring bean/`SmartLifecycle`/supervised service, không tạo một subscription mỗi HTTP request.

### 15.6. Stream qua Server-Sent Events

~~~java
@GetMapping(
    value = "/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<OrderDto>> events() {
    return changeService.eventsForAuthenticatedTenant()
        .map(order -> ServerSentEvent.builder(order).build());
}
~~~

Client HTTP có thể disconnect bất cứ lúc nào. Cần tenant filtering, auth, throttling, rate limits, resume/reconnect protocol và bảo vệ khỏi quá nhiều concurrent change stream subscriptions. Một stream dài hạn có thể tiêu thụ cursors/socket resources dù dùng ít Java threads.

### 15.7. `Flux` không tự tạo durable queue

Một subscriber quá chậm khiến MongoDB history window trôi qua có thể không resume được. Để đảm bảo replay dài hạn, dùng Kafka/RabbitMQ/SQS hoặc log/retention chuyên biệt; change stream là nguồn thay đổi DB với window có giới hạn, không là data warehouse lưu trữ mãi mãi.

## 16. Error handling: phân biệt empty, failure và retry

### 16.1. Empty document không phải exception

~~~java
return repo.findByTenantIdAndId(tenantId, id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
~~~

`switchIfEmpty` chỉ chạy khi upstream **hoàn tất mà không phát giá trị**, không chạy khi query lỗi network. Nếu business muốn 404, controller có thể map `OrderNotFoundException` qua `@ControllerAdvice` hoặc trả `ResponseEntity.notFound`.

### 16.2. `onErrorReturn` có thể che dữ liệu sai

~~~java
// ANTI-PATTERN cho dữ liệu tiền/đơn hàng:
repo.countByTenantId(tenantId)
    .onErrorReturn(0L);
~~~

Nếu MongoDB timeout, trả count=0 có thể khiến UI hiểu “không có đơn hàng” thay vì “không tải được”. Với các nghiệp vụ quan trọng, **propagate error** hoặc trả DTO chứa trạng thái degraded rõ ràng.

### 16.3. `onErrorResume` có điều kiện

~~~java
Mono<OrderSummary> summary = template.findOne(q, Order.class)
    .map(OrderSummary::from)
    .onErrorResume(
        MongoException.class,
        ex -> cachedSummaryService.getIfFresh(tenantId, id));
~~~

Fallback chỉ hợp lý khi cache được **ủy quyền/đủ mới theo business policy**. `cachedSummaryService.getIfFresh` là reactive helper giả định. Nếu cache không có, nên trả error rõ; đừng dùng fallback để che tất cả bugs/permission failures.

### 16.4. `retryWhen` phải có cap

~~~java
Mono<Order> read = repo.findByTenantIdAndId(tenantId, id)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isTransientMongoError));
~~~

`isTransientMongoError` là predicate do ứng dụng định nghĩa theo exception/error labels/version; **không retry mọi `RuntimeException`** (validation, duplicate key, auth failure...). Hạn chế tổng attempts và **remaining deadline**; Java driver có thể đã retry nội bộ nên đo actual command attempts.

### 16.5. Retry writes có thể nhân đôi nghiệp vụ

~~~text
Attempt 1: insert order _id=ORD-101
Server writes document
Network response lost
Client retries request
Attempt 2: generates new _id=ORD-102
=> duplicate business order
~~~

`retryWhen` trên toàn reactive create workflow **không an toàn** nếu mỗi subscription tạo ID mới hoặc gửi external payment/email. Dùng stable idempotency key, unique index và retryable writes/transaction outcome handling.

### 16.6. Timeout từ Reactor operator

~~~java
Mono<Order> result = repo.findByTenantIdAndId(tenantId, id)
    .timeout(Duration.ofMillis(500));
~~~

Reactor `timeout` phát error/cancel khi upstream không phát/completion theo điều kiện. Nhưng:

- Đây là **Reactor operator-level timeout**, không phải MongoDB server-side `maxTimeMS`.
- Cancellation không đồng nghĩa server write rollback nếu đã gửi.
- Một timeout 500ms có thể bắt đầu sau khi request chờ HTTP queue lâu.
- MongoDB driver/server có timeout/CSOT riêng; chúng có thể tương tác.

Để giới hạn server query execution dùng `Query.maxTime(...)`/driver-supported options, và dùng HTTP deadline/CSOT ở nơi phù hợp theo version. **Không lấy một `Mono.timeout` làm thay thế cho toàn bộ resource admission/cancellation semantics**.

### 16.7. `doOnError` không nuốt error

~~~java
return repo.findById(id)
    .doOnError(ex -> metrics.increment("mongo.read.error"))
    .onErrorMap(ex -> new OrderDataAccessException(ex));
~~~

`doOnError` là side effect quan sát, không chuyển error thành success. Nếu `metrics.increment(...)` throw exception mới, nó có thể che nguyên nhân gốc; instrumentation phải không làm hỏng request pipeline.

### 16.8. `doFinally` để cleanup/metrics

~~~java
return repo.findById(id)
    .doFinally(signalType ->
        metrics.recordTermination(signalType.name()));
~~~

`doFinally` được gọi khi complete, error hoặc cancel theo Reactor lifecycle; phù hợp recording cleanup metrics. Không đặt **blocking DB/network calls** trong `doFinally` trên event loop; nếu cần cleanup async, dùng `usingWhen`/transaction manager/resource lifecycle.

## 17. Timeout và connection pool trong reactive MongoDB

### 17.1. Reactive không “bỏ qua” connection pool

Reactive Streams driver vẫn kết nối tới `mongod`/`mongos` với các pools/limits; nhiều reactive subscriptions có thể đòi connections cùng lúc. Bởi vậy cần monitor:

- Pool in-use/size, checkout wait/failed.
- Server selection failures.
- Command execution latency.
- Created/closed/cleared connection rate.
- MongoDB server CPU/IOPS/cache/lock queues.
- Reactor event-loop lag và HTTP p95/p99.

### 17.2. Những loại thời gian chờ

| Timeout | Tầng | Điều không đảm bảo |
|---|---|---|
| HTTP/API deadline | Gateway/WebFlux application | Không tự rollback MongoDB write. |
| Reactor `timeout(Duration)` | Publisher pipeline | Không tự hủy command server đã commit. |
| MongoDB server selection timeout | Reactive driver topology | Không giải quyết thiếu pooled connection sau khi chọn server. |
| Connection checkout/wait timeout | Reactive driver pool | Không thay server command timeout. |
| Connect/socket timeout | Network/driver | Không bảo đảm HTTP response trước deadline. |
| `maxTimeMS` | MongoDB server execution | Không tính queue/selection/checkout. |
| Driver CSOT nếu phiên bản reactive driver hỗ trợ | MongoDB operation | Không tính toàn bộ HTTP pipeline trước MongoDB operation. |

**Đừng lấy Java Sync Driver defaults áp mù lên MongoDB Reactive Streams Driver bản khác**. Các connection string options có tên quen thuộc nhưng behavior/default và CSOT support/version cần tra driver tương ứng.

### 17.3. Pool size không phải parallelism of `Flux`

~~~text
100 HTTP requests
  each does flatMap(..., 10)
       |
  up to ~1,000 inner subscriptions
       |
Reactive MongoDB Driver pool maxSize=100/server
       |
  queued/checked-out operations
       |
MongoDB server CPU/IOPS
~~~

Ví dụ định lượng có điều kiện; `flatMap` và driver scheduling có thể làm con số thực khác. Nếu command execution tăng mạnh khi concurrency tăng, chỉ tăng pool có thể làm tail latency tệ hơn. Dùng bounded concurrency/admission và tối ưu query.

### 17.4. Lifecycle client trong reactive stack

Spring Boot reactive MongoDB starter quản lý reactive MongoClient dưới bean lifecycle nếu auto-config đúng. Đừng tạo client mới trong mỗi subscription:

~~~java
Mono.defer(() -> {
    // ANTI-PATTERN:
    // MongoClients.create(uri) each subscription
    // -> new topology monitor and pool.
    return somePublisher;
});
~~~

Client phải reusable, close khi application shutdown. Với nhiều database clusters hoặc bulkhead workloads, có thể tạo nhiều clients **có chủ đích** nhưng tính tổng connections/pod count.

### 17.5. Netty event-loop và driver threads

WebFlux/Reactor Netty event-loop workers và MongoDB Reactive Streams driver’s I/O/callback execution có thể dùng threads/schedulers khác nhau theo version. **Không mặc định một callback luôn chạy trên Reactor Netty thread**; nhưng mọi callback thread có thể được dùng bởi nhiều requests, do đó code blocking trong `map`/`doOnNext` vẫn tạo contention. Đo thread names/traces khi debug, đừng phụ thuộc tên thread cứng trong logic business.

### 17.6. Connection storms khi deploy/failover

Khi 30 pods restart đồng thời, mỗi pod có reactive MongoClient riêng và `minPoolSize` đáng kể, cluster có thể nhận hàng trăm TLS/auth handshakes trong thời gian ngắn. Strategies:

- Rolling/canary deploy.
- Min pool vừa đủ.
- `maxConnecting` có tính toán.
- Warmup theo readiness/controlled rate.
- Retry với cap và jitter khi primary election.
- Giới hạn request concurrency khi MongoDB chưa ready.

Reactive code **không loại bỏ** SDAM/server selection/pool clearing behavior khi primary thay đổi.

## 18. Logging, tracing và Reactor Context

### 18.1. Vì sao ThreadLocal/MDC có thể không theo pipeline?

~~~java
MDC.put("tenantId", tenantId);
return repo.findById(id)
    .publishOn(Schedulers.parallel())
    .doOnNext(order -> log.info("Found {}", order.getId()));
~~~

`MDC` thường dựa trên `ThreadLocal`; khi Reactor chuyển threads, MDC có thể **không còn tenantId** hoặc giữ giá trị của request khác nếu không được cleanup/propagate đúng. Không dùng MDC giá trị stale làm **authorization decision**.

### 18.2. Reactor Context

~~~java
Mono<Order> pipeline = repo.findById(id)
    .flatMap(order ->
        Mono.deferContextual(ctx -> {
            String tenant = ctx.get("tenantId");
            return auditRepo.save(
                new AuditEvent(tenant, order.getId()))
                .thenReturn(order);
        }))
    .contextWrite(ctx -> ctx.put("tenantId", tenantId));
~~~

`Reactor Context` đi cùng **subscriber** thay vì phụ thuộc một physical thread. Tuy nhiên tenantId nên đến từ **trusted authenticated context**; ví dụ chỉ minh họa cách lưu/đọc metadata, không là giải pháp authorization hoàn chỉnh.

### 18.3. Spring Security reactive context

`ReactiveSecurityContextHolder.getContext()` cung cấp SecurityContext dưới dạng reactive:

~~~java
Mono<String> trustedTenant = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(auth -> extractTenantFromValidatedPrincipal(auth));
~~~

`extractTenantFromValidatedPrincipal` là logic ứng dụng cần kiểm security model. **Không chuyển auth context sang global static variable** hoặc lấy tenant từ `ThreadLocal` rồi hy vọng đúng khi reactive pipeline đổi thread.

### 18.4. OpenTelemetry/Micrometer

Trong production nên theo dõi:

- HTTP route + request latency p50/p95/p99.
- Reactor event-loop lag và scheduler queue depth.
- MongoDB command duration, errors/command names.
- Driver pool checked-out/checkout wait, server selection failures.
- DB-side query plans/CPU/IOPS.
- Retry/cancellation counters và pending subscriptions.

Traces cần có correlation giữa HTTP span và MongoDB command spans. Không log nguyên query BSON chứa PII/secrets; tránh labels `userId`/`requestId` gây cardinality cao trong Prometheus.

### 18.5. Tracing với `doOnEach` không được block

~~~java
return repo.findById(id)
    .doOnEach(signal -> telemetry.observe(signal));
~~~

`telemetry.observe` phải nhanh, thread-safe, không gọi network blocking đồng bộ ở event-loop; nếu export telemetry ra backend, instrumentation SDK thường có async buffer/queue riêng và sampling. Không bật logging body mỗi document trong stream hàng triệu records.

### 18.6. Cách nhận ra event-loop bị chặn

Những dấu hiệu:

- Reactor Netty event-loop lag cao trong traffic bình thường.
- Thread dump thấy `reactor-http-nio-*` ở `WAITING` trong JDBC/Sync MongoDB/HTTP client/`Thread.sleep`.
- Request p99 tăng nhưng MongoDB command latency thấp.
- CPU app/GC tăng do `collectList()` trên hàng triệu docs.
- BlockHound test báo blocking call trên non-blocking thread.

Khi đó ưu tiên sửa **blocking call hoặc unbounded buffering**, không mặc định tăng MongoDB connection pool.

## 19. Kiểm thử reactive code: `StepVerifier` và `WebTestClient`

Reactive code có ba trường hợp cần test: **onNext**, **onComplete empty**, **onError**. Ngoài ra, cần kiểm thứ tự signals, cancellation, concurrency và không có side effects trước subscription.

### 19.1. `StepVerifier` kiểm một Mono thành công

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void monoEmitsOneValueThenCompletes() {
    Mono<String> source = Mono.just("OPEN");

    StepVerifier.create(source)
        .expectNext("OPEN")
        .verifyComplete();
}
~~~

`StepVerifier` **subscribe** để kiểm signals; không cần `.block()` bên trong unit test cho một test reactive đơn thuần.

### 19.2. Test empty/no-document

~~~java
@Test
void missingOrderCompletesEmpty() {
    Mono<Order> lookup = Mono.empty();

    StepVerifier.create(lookup)
        .verifyComplete();
}
~~~

Nếu service chuyển empty sang business error bằng `switchIfEmpty`:

~~~java
@Test
void missingOrderBecomesNotFoundError() {
    Mono<Order> lookup = Mono.<Order>empty()
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException("O-404")));

    StepVerifier.create(lookup)
        .expectError(OrderNotFoundException.class)
        .verify();
}
~~~

### 19.3. Test fallback chỉ cho lỗi thích hợp

~~~java
Mono<String> source = Mono.<String>error(
        new IllegalStateException("temporary"))
    .onErrorResume(IllegalStateException.class,
        ex -> Mono.just("FALLBACK"));

StepVerifier.create(source)
    .expectNext("FALLBACK")
    .verifyComplete();
~~~

Unit test phải phân biệt **temporary MongoDB error** với validation/auth/duplicate-key error; đừng catch mọi `Throwable` rồi trả fallback “thành công”.

### 19.4. Test không có eager side effect trước subscription

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.just(42);
});

assertEquals(0, calls.get());

StepVerifier.create(source)
    .expectNext(42)
    .verifyComplete();

assertEquals(1, calls.get());
~~~

Test này giúp nhận ra khi service vô tình dùng `Mono.just(legacyDao.load())` khiến blocking function chạy **trước khi subscription**.

### 19.5. `StepVerifier.withVirtualTime`

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Virtual time phù hợp với **Reactor timers/delays** và logic thuần Reactor, không tự biến MongoDB network I/O thành virtual-time-controlled. Không dùng unit test virtual time để khẳng định server query thực luôn chạy nhanh.

### 19.6. Mock reactive repository

~~~java
when(repo.findByTenantIdAndId("tenant-a", "O-100"))
    .thenReturn(Mono.just(orderFixture));

Mono<Order> result = service.get("tenant-a", "O-100");

StepVerifier.create(result)
    .expectNext(orderFixture)
    .verifyComplete();
~~~

Đây là snippet JUnit/Mockito; cần `repo`, `service` và `orderFixture` được khởi tạo. Mock test kiểm **composition/control flow**, không xác nhận query mapping, MongoDB indexes hoặc server failover behavior.

### 19.7. `WebTestClient` cho controller

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", "O-100")
    .header("X-Verified-Tenant", "tenant-a")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("O-100");
~~~

Đây là ví dụ WebFlux controller test với security/gateway/header policy **mocked hợp lệ**. Trong production không tin header tenant từ client. Với HTTP 404 test:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", "O-missing")
    .header("X-Verified-Tenant", "tenant-a")
    .exchange()
    .expectStatus().isNotFound();
~~~

### 19.8. MongoDB integration test

Mock không đủ để xác minh:

- MongoDB JSON query/Criteria thực.
- Data mapping `@Document`/`@Field`/`@Version`.
- Unique/compound indexes và optimistic locking.
- Transaction support.
- Change streams/capped collections.
- Driver connections/read preference/timeouts.

Nên dùng **Testcontainers MongoDB replica set** hoặc dedicated Atlas test cluster với version tương thích; test cần cleanup, fixture isolation và không connect production. Testcontainers module/API và replica-set startup syntax thay đổi theo phiên bản nên tham khảo docs trước khi thêm container configuration.

### 19.9. Test transaction atomicity

Trong integration test trên replica set lab:

1. Ghi order và audit event trong cùng `TransactionalOperator` scope.
2. Cố tình tạo một lỗi **sau write thứ nhất, trước write thứ hai**.
3. Verify publisher phát error.
4. Query lại DB để xác nhận cả hai records được rollback như mong đợi.
5. Test riêng retry/unknown commit ambiguity, không coi một forced exception unit test là đủ.

Nếu dùng standalone MongoDB local không hỗ trợ transactions, test có thể fail không vì reactive code mà vì topology.

### 19.10. Test detection of blocking behavior

Nếu BlockHound hỗ trợ JDK/Reactor của project, bật trong môi trường test phù hợp và chạy đoạn blocking anti-pattern để xác nhận instrumentation detect được. Kết hợp:

- Thread dumps ở traffic peak.
- Event-loop latency metrics.
- CPU/GC profiles.
- Load test có số clients/queries đại diện.

**Không QA code bằng việc “không thấy exception”**: nhiều blocking APIs không phát `IllegalStateException` nếu chạy trên thread chưa đánh dấu non-blocking.

## 20. Tối ưu performance reactive MongoDB: vấn đề ở đâu?

### 20.1. Tách từng giai đoạn latency

~~~text
HTTP request accepted
     |
     v
Auth/validation/context extraction
     |
     v
Reactive pipeline subscription
     |
     v
Driver server selection / pool checkout
     |
     v
MongoDB server executes command
     |
     v
Publisher emits BSON / Spring mapping
     |
     v
JSON encoder / HTTP send
     |
     v
Client receives response
~~~

Không suy “command p95 chỉ 5 ms” thì HTTP p95 cũng 5 ms: queue/cancellation, mapper CPU, JSON serialization, network, scheduler saturation và MongoDB pool wait có thể cộng thêm.

### 20.2. Little's Law và concurrency

Trong hệ thống tương đối ổn định:

\[
L = \lambda W
\]

Với 800 MongoDB operations/s, trung bình mỗi operation mất 25 ms **từ lúc chiếm connection đến lúc trả connection**:

\[
L \approx 800 \times 0.025 = 20
\]

Ước tính có trung bình ~20 operations đang sử dụng connection. **Không** đặt `maxPoolSize=20` như chân lý: burst, p99 latency, retry, transactions và pod count cần headroom. Reactive giảm threads bị block nhưng **không xóa định luật queueing**.

### 20.3. Khi DB saturated

Nếu MongoDB server CPU=98%, IOPS gần giới hạn, command p99 tăng dù WebFlux event loops rảnh, nút thắt là **DB**. Tăng `flatMap` concurrency từ 8 lên 256 có thể làm chậm hơn, tăng pool checkout/server queues. Cân nhắc:

- Tối ưu index/query/projection.
- Giảm concurrency của batch/report.
- Cache có TTL/authorization/freshness policy.
- Denormalization/materialized summaries đúng nghiệp vụ.
- Sharding hoặc tăng capacity server khi cần.

### 20.4. Khi event loop bị block

Nếu MongoDB command p95 thấp nhưng HTTP p95 tăng mạnh, thread dump cho thấy event-loop chạy JDBC/`Thread.sleep`/large JSON parse, cần:

- Thay blocking library bằng async/reactive.
- Offload legacy call đúng `fromCallable + subscribeOn`.
- Tách CPU-heavy work.
- Giới hạn buffer/concurrency.
- Theo dõi event-loop lag.

**Không tăng MongoDB pool** để chữa event-loop stalls.

### 20.5. Khi pool checkout wait cao

Nếu reactive driver pool checked-out sát `maxPoolSize` nhưng DB CPU còn thấp, kiểm:

- Long-held cursors/transactions.
- Too many concurrent `flatMap` calls.
- Pool ramp-up `maxConnecting` sau cold start/failover.
- Connection churn/TLS/auth.
- Number of MongoClients/pods.

Nếu server có headroom, có thể thử tăng pool từng bước **và giữ admission gate**, đo p95/p99/throughput. Không nới trần vô hạn.

### 20.6. Tránh N+1 queries

~~~java
return customerRepo.findByTenantId(tenantId)
    .flatMap(c ->
        orderRepo.findByTenantIdAndCustomerId(tenantId, c.getId())
            .collectList()
            .map(orders -> new CustomerWithOrders(c, orders)),
        16);
~~~

Đây là N+1 pattern: 1 query customers rồi N queries orders. Với N lớn có thể tốn network/DB. Thay bằng batch by customer IDs, aggregation `$lookup` phù hợp, materialized view hoặc document model theo MongoDB access patterns. `flatMap(16)` giảm concurrency peak chứ **không giảm tổng N queries**.

### 20.7. Reactive memory traps

| Operator/code | Rủi ro |
|---|---|
| `findAll().collectList()` | Gom toàn collection. |
| `buffer(Integer.MAX_VALUE)` | Bộ nhớ không bị giới hạn thực tế. |
| `groupBy` trên key cardinality rất cao | Tạo nhiều groups, memory/consumption complexity. |
| `cache()` trên infinite/large Flux | Retain emitted elements lâu, có thể OOM. |
| `replay().autoConnect()` trên event stream | Giữ lịch sử dài nếu không giới hạn. |
| `flatMap` concurrency cao | Many pending DB operations và buffers. |
| JSON encode item rất lớn | Peak heap/network frame pressure. |

**Không block thread** và **không dùng nhiều memory** là hai mục tiêu độc lập. Reactive code có thể thỏa mục tiêu đầu nhưng vi phạm mục tiêu thứ hai.

### 20.8. Connection pool theo ứng dụng và pods

Giả sử 24 pods, mỗi pod có reactive MongoClient maxPoolSize=80 cho primary:

\[
24 \times 80 = 1{,}920
\]

Đây là **trần pooled application connections tiềm năng** tới primary, không phải số chắc chắn đang dùng. Nếu tạo 3 clients/pod, trần tăng theo. HPA tăng pods có thể làm DB overload dù event loop của từng pod nhẹ.

### 20.9. Adaptive admission và overload shedding

Một API có SLO p95 300 ms nên tránh queue dài hàng giây trong client pool. Có thể đặt:

~~~text
API per-pod in-flight MongoDB operations: 40
HTTP queue capacity: 80
Admission wait: at most 30ms
MongoDB operation timeout: based on remaining deadline
Reports: separate gate and async jobs
~~~

Đây là **cấu hình giả định**; chọn bằng load test. Khi full, trả 429/503 hoặc giảm chức năng theo policy, không để mọi request vô hạn đợi trong pool. Ngay cả reactive async tasks cũng chiếm memory, request context và DB resources.

### 20.10. Load test cả overload và recovery

Một bài test tốt tăng arrival rate theo stages, đo:

1. Incoming vs completed throughput.
2. HTTP p50/p95/p99 latency.
3. DB command p50/p95/p99, pool checkout wait.
4. Event-loop lag, CPU/GC/heap, scheduler queue.
5. Error/timeout/retry/rejection rates.
6. Queue drains khi traffic giảm.
7. Failover/connection reconnection và resume behavior.

**Reactive service tốt không nhất thiết đạt QPS cao nhất trên một benchmark đơn lẻ**; nó cần **throughput bền vững, predictable latency và error handling đúng** khi MongoDB hoặc downstream chậm.

## 21. Security, resource lifecycle và testing edge cases

### 21.1. Trusted tenant context

Trong WebFlux, user/tenant data có thể nằm trong `SecurityContext` của Reactor. Mọi DB query phải lọc theo tenant từ **validated principal/permissions**, không tin client-supplied IDs:

~~~java
return trustedTenant()
    .flatMap(tenantId -> repository.findByTenantIdAndId(
        tenantId, orderId));
~~~

Không đặt tenant context vào global mutable singleton/shared `ThreadLocal` rồi dùng nó khi Reactor chuyển threads; dữ liệu có thể chéo requests. `ReactiveMongoRepository.findById(id)` không có tenant isolation tự động.

### 21.2. SQL-like authorization không đủ

Chỉ kiểm tenant ở controller rồi service dùng raw `repository.findById` có thể gây lỗ hổng nếu endpoint khác gọi service trực tiếp. Đặt authorization constraints ở **data access/service boundary**; có integration tests cho cross-tenant IDs và background jobs.

### 21.3. MongoDB data mapping và field-level access

Projection không phải ACL. Khi API trả `Order` đầy đủ, nó có thể chứa fields nhạy cảm như internal notes/payment references. Dùng response DTO/projection phù hợp, không serialize raw MongoDB document từ bất kỳ collection nào. Với encryption/CSFLE, kiểm driver compatibility và tránh blocking crypto/key resolver trong event-loop workflow.

### 21.4. Resource lifecycle

Reactive MongoClient là shared resource; không tạo/đóng trong mỗi request/subscription. Change streams/cursors cần cancellation/lifecycle. Background subscriptions phải có owner, error handling và shutdown cleanup.

### 21.5. HTTP client disconnect giữa write

Khi HTTP client bỏ kết nối, subscription có thể bị cancel, nhưng DB write đã gửi có thể hoàn tất. Đừng suy rằng cancel event tương đương **database rollback**. API write cần stable idempotency key và cách kiểm trạng thái khi client retry.

### 21.6. Operational readiness

Readiness/liveness cần phân biệt **MongoDB tạm election** với **JVM process chết**. Nếu mỗi failover vài giây khiến Kubernetes restart tất cả WebFlux pods, chính lần restart đồng loạt có thể gây connection storm lớn hơn. Dùng phù hợp:

- Liveness: process còn hoạt động.
- Readiness: service có thể phục vụ traffic hiện tại.
- Dependency health/SDAM: connectivity/eligible server state.
- Graceful shutdown: drain requests, close clients/cursors.

### 21.7. Logging và PII

Không log raw MongoDB connection string có credentials, BSON user data, auth headers hoặc resume tokens không cần thiết. Traces/metrics nên dùng low-cardinality labels: `route`, `commandName`, `operationClass`, `outcome`, `cluster`; requestId ở trace context/log có retention policy, không là Prometheus metric label.

### 21.8. Test race conditions

`Mono.zip(read1, read2)` có thể chạy reads ở hai timestamps; `findById(...).flatMap(save)` có thể gặp concurrent update races; `@Version` giúp một số cases nhưng không thay **atomic conditional update** hoặc transaction. Viết tests simulate concurrent writes, duplicate key, optimistic locking failures và disconnect/retry.

## 22. Những hiểu lầm và lỗi thường gặp

| Hiểu lầm/anti-pattern | Vì sao sai | Cách làm |
|---|---|---|
| “Trả `Mono` là non-blocking dù bên trong gọi `MongoTemplate`.” | Sync I/O vẫn block worker. | Dùng `ReactiveMongoTemplate`/reactive repository. |
| “`Mono.just(blockingCall())` dời call sang subscription.” | Argument được evaluate trước khi Mono được tạo. | `fromCallable + subscribeOn(boundedElastic)`. |
| “`Mono.defer(blockingCall)` tự không block.” | Chỉ trì hoãn; vẫn chạy trên thread subscribe nếu không offload. | Scheduler phù hợp và bounded admission. |
| “`block()` cần để thực thi query trong controller.” | WebFlux subscribe publisher sau khi controller return. | Return `Mono/Flux`. |
| “Manual `subscribe()` luôn tốt cho fire-and-forget.” | Lỗi không về HTTP, mất lifecycle/transaction. | Compose/return; nền phải có owner/durable queue. |
| “`doOnNext` là nơi chạy một DB write thứ hai.” | Side effect async không compose, có thể thất bại/lặp. | `flatMap` với returned Mono, transactional/outbox khi cần. |
| “Reactive làm MongoDB query chạy nhanh hơn.” | Server vẫn dùng cùng indexes/CPU/IOPS. | `explain` và tối ưu query/data model. |
| “`Flux` chỉ phát 1 doc mỗi lần driver chạm DB.” | Cursor batches/prefetch tồn tại. | Limit/batch size, demand metrics. |
| “`findAll().collectList()` có memory bounded.” | Gom toàn bộ docs trong RAM. | Filter/limit/paginate/stream. |
| “`flatMap(repo::save)` có concurrency vô hạn là nhanh nhất.” | Có thể saturate pool/server, reorder writes. | Bounded concurrency hoặc `concatMap`. |
| “`flatMap(...,8)` là global limit.” | Mỗi subscription/request có 8 slots. | Global/per-tenant gate và pod budget. |
| “`Schedulers.boundedElastic` làm legacy call an toàn vô điều kiện.” | Scheduler vẫn có queue, timeout/overload. | Cap task count, timeout, async migration. |
| “`publishOn` sau blocking mapper sẽ sửa mapper trước nó.” | Scheduler switch chỉ ảnh hưởng downstream. | `subscribeOn` cho blocking source hoặc move `publishOn` trước step. |
| “`Schedulers.parallel` dành cho blocking JDBC.” | CPU-focused scheduler, có thể chặn số ít threads. | boundedElastic cho blocking; R2DBC/reactive API nếu có. |
| “WebFlux event loop thread count bằng MongoDB pool size.” | Hai tài nguyên khác nhau. | Driver CMAP metrics + event loop lag riêng. |
| “Reactive repository `findById` tự xác thực tenant.” | ID lookup không có tenant filter mặc định. | Derived finder/Template query gồm tenant from security context. |
| “HTTP header tenant do client gửi là trusted.” | Có thể giả mạo. | Reactive SecurityContext/verified principal. |
| “`@Transactional` trên method void có `subscribe()` sẽ mở transaction.” | Reactive transaction theo Publisher subscription/proxy. | Return publisher và cấu hình reactive tx manager. |
| “Chỉ thêm `@Transactional` là đủ.” | Cần `ReactiveMongoTransactionManager` đúng factory/topology. | Configuration/integration test trên replica set. |
| “`flatMap` 100 writes cùng transaction luôn được phép.” | Concurrent operations trên same ClientSession không được hỗ trợ tùy ý. | `concatMap`/sequential compose. |
| “Reactive transaction dùng ThreadLocal giống imperative.” | Transaction binding qua Reactor subscriber Context. | Spring reactive manager/context. |
| “`Mono.zip` làm hai reads cùng snapshot.” | Đó là composition, không transaction/snapshot tự động. | Transaction/snapshot policy khi business cần. |
| “`save(entity)` chỉ ghi các fields đã sửa.” | Có thể ghi entity state, optimistic locking semantics khác patch. | Atomic `updateFirst/findAndModify` cho field-level updates. |
| “`@Version` áp dụng hết mọi updateMulti.” | Custom update path có semantics khác save entity. | Kiểm version predicate/mapping/version update. |
| “`onErrorReturn(0)` là fallback tốt cho mọi query.” | Timeout bị giả thành kết quả nghiệp vụ hợp lệ. | Error rõ ràng/cached verified fallback. |
| “`retryWhen` mọi lỗi là an toàn.” | Có thể retry validation/auth/duplicate hoặc tạo writes lặp. | Chỉ transient + capped retries + stable ID. |
| “`Mono.timeout` rollback write khi HTTP cancel.” | Server có thể đã commit. | Idempotency/verify outcome. |
| “`StepVerifier.withVirtualTime` benchmark MongoDB I/O.” | Chỉ ảo hóa Reactor scheduler time, không network DB. | Integration/load test thật. |
| “`@Tailable` chạy trên regular collection.” | Tailable cursor yêu cầu capped collection. | Capped collection hoặc change stream. |
| “Change stream bảo đảm replay vô hạn.” | Oplog/history/resume window có giới hạn. | Durable checkpoint + retention/broker khi cần. |
| “Change stream cùng callback tự exactly once.” | Crash giữa side effect/checkpoint có thể replay. | Idempotent processing. |
| “No BlockHound errors => code non-blocking 100%.” | Instrumentation/version coverage không tuyệt đối. | Metrics/thread dumps/load test. |
| “Reactive response `Flux` luôn streaming qua mọi proxy.” | Proxy/client có thể buffer. | Kiểm end-to-end codecs/proxies/NDJSON. |
| “Reactive driver bỏ connection pool.” | Vẫn có per-server connections, checkout/SDAM. | CMAP/pool/server monitoring. |
| “HPA thêm pods sẽ tự làm DB có thêm năng lực.” | Pool requests tăng, DB CPU/IOPS không tăng theo. | Global admission và DB scaling strategy. |
| “`@Document`/`@CompoundIndex` luôn tự tạo index.” | Auto-index creation có config/version; migration policy. | Quản lý index có kiểm soát, verify. |
| “Projection có thể `save` như full entity.” | Missing fields có thể bị ghi đè. | DTO riêng, không save partial projection. |

### 22.1. Năm dấu hiệu trong một review reactive pull request

1. Controller/service có `.block()`, `.subscribe()` hoặc `Thread.sleep()` không?
2. Có thư viện **blocking** ẩn trong `map`/`doOnNext`/mapper/validator không?
3. `flatMap` concurrency, page size và buffer memory đã có giới hạn chưa?
4. Reactive transaction, tenant security context, errors/retries có được **compose** đúng không?
5. Integration tests và metrics có chứng minh không block event loop, không leak cursor và không làm DB overload không?

## 23. Tình huống thực tế: chọn đúng cách sửa

### 23.1. Case A — API WebFlux p99 cao nhưng MongoDB rất nhanh

~~~text
HTTP p99:          1,400 ms
MongoDB command:      15 ms
Driver checkout:       3 ms
Event-loop lag:      900 ms
Thread dump:
  reactor-http-nio-X -> Thread.sleep(...)
~~~

Các số giả định. Nút thắt ở **event-loop blocking**, không phải MongoDB query/pool. Sửa `Thread.sleep` bằng timer publisher, loại blocking SDK hoặc offload có giới hạn. Tăng `maxPoolSize` sẽ không chữa event loop bị chặn.

### 23.2. Case B — `flatMap` đọc 10.000 IDs làm DB bão hòa

~~~text
One HTTP request:
  10,000 IDs -> flatMap(repo.findById)
  many concurrent DB operations

Driver checkout wait p99: 500 ms
MongoDB CPU:            98%
HTTP requests timeout/retry
~~~

**Hướng sửa:**

1. Chặn input list size, áp tenant/ACL validation.
2. Batch IDs bằng `$in` trong limits cho phép hoặc data-access pattern khác.
3. Dùng `flatMap(..., n)` với n có đo.
4. Bounded admission và short HTTP deadline.
5. Tối ưu MongoDB indexes, đọc đúng query shape.
6. Không tự tăng `maxPoolSize` 10 lần khi CPU 98%.

### 23.3. Case C — Controller trả “Saved” nhưng DB không có record

~~~java
public Mono<String> saveBad(Order o) {
    repository.save(o).subscribe();
    return Mono.just("Saved");
}
~~~

Nếu write lỗi duplicate key hoặc primary election, HTTP đã báo success. **Sửa** bằng:

~~~java
public Mono<Order> saveGood(Order o) {
    return repository.save(o);
}
~~~

Kết quả được propagate theo subscription của framework, errors đúng kênh. Với client retries, business vẫn cần idempotency key.

### 23.4. Case D — Transaction không rollback hai writes

~~~java
@Transactional
public Mono<Void> bad(Order order) {
    repo.save(order).subscribe();
    auditRepo.save(new AuditEvent(order.getId(), "NEW")).subscribe();
    return Mono.empty();
}
~~~

Hai `subscribe()` tạo subscriptions riêng; transaction scope của returned publisher có thể không bao gồm chúng. **Sửa**:

~~~java
@Transactional
public Mono<Void> good(Order order) {
    return repo.save(order)
        .flatMap(saved ->
            auditRepo.save(
                new AuditEvent(saved.getId(), "NEW")))
        .then();
}
~~~

Vẫn cần reactive transaction manager, topology replica set/sharded support và integration test rollback.

### 23.5. Case E — `Mono.zip` trả empty bất ngờ

~~~java
Mono<Order> order = repo.findById("missing");
Mono<Long> count = repo.count();
return Mono.zip(order, count);
~~~

Nếu `order` empty, `zip` có thể complete empty/cancel other. **Sửa** theo business:

~~~java
return repo.findById("missing")
    .switchIfEmpty(Mono.error(new OrderNotFoundException("missing")))
    .flatMap(order -> repo.count()
        .map(count -> new OrderAndCount(order, count)));
~~~

Nếu muốn ghi count khi order thiếu để analytics, thiết kế riêng; không dùng `zip` mặc định rồi ngạc nhiên vì một nhánh empty làm không có tuple.

### 23.6. Case F — Change stream bị mất kết nối rồi xử lý trùng event

~~~text
Consume event E101
Apply projection in S3
Crash before resume-token checkpoint
Restart from E100
Receive E101 again
~~~

Đây là **at-least-once** processing. Dùng event ID/resume token, idempotent projection update và checkpoint sau khi side effect durable; nếu cần exactly-once semantics qua systems khác nhau, cần protocol/transactional design cụ thể chứ không chỉ Reactor operators.

### 23.7. Case G — High memory dù threads rảnh

~~~java
Mono<List<Order>> response = repo.findAll().collectList();
~~~

Với vài triệu orders, bộ nhớ đủ lớn có thể bị dùng hết. **Sửa** bằng indexed tenant filter + `Pageable`/seek pagination, projection DTO và max response size. “Reactive” không xóa chi phí lưu một List hàng triệu objects.

### 23.8. Case H — Blocking payment SDK trong `map`

~~~java
return repo.findById(orderId)
    .map(order -> paymentSdk.charge(order)); // blocking call
~~~

Nếu SDK blocking, event loop/callback threads bị giữ. Không đủ để thêm `.publishOn(boundedElastic())` **sau** mapper. Nên ưu tiên async payment SDK. Nếu chưa có:

~~~java
return repo.findById(orderId)
    .flatMap(order ->
        Mono.fromCallable(() -> paymentSdk.charge(order))
            .subscribeOn(Schedulers.boundedElastic()));
~~~

**Đặc biệt:** Charge payment là side effect không-idempotent. Cần idempotency key từ payment provider, timeout/retry policy riêng và không mặc định retry toàn `Mono`.

### 23.9. Case I — Reactive repository được dùng trong Spring MVC

Spring MVC và WebFlux là hai programming models. Một MVC controller có thể trả một reactive type theo những hỗ trợ nhất định của Spring MVC, nhưng **Servlet request handling không tự trở thành toàn bộ WebFlux event-loop runtime** chỉ vì DAO reactive. Ngược lại, WebFlux app dùng JDBC vẫn có đoạn blocking. Chọn stack có chủ đích và kiểm framework auto-config (khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có, Boot có precedence theo version).

### 23.10. Case J — Dự án lẫn imperative và reactive transaction managers

Một ứng dụng có cả `MongoTransactionManager` và `ReactiveMongoTransactionManager` hoặc JDBC transaction manager. Nếu `@Transactional` resolution chọn sai manager, code có thể không bind reactive ClientSession đúng context. Đặt bean names/transactionManager qualifier rõ, viết integration test cho workflow, không cho rằng “có một annotation” là đủ atomicity.

### 23.11. Case K — Retry storm sau primary election

Nếu primary mới được bầu, MongoDB driver reconnection/SDAM chọn server mới trong khi 20 pods đồng loạt `retryWhen` không jitter, tất cả queries có thể dồn vào primary mới. Dùng capped retries, backoff/jitter, global admission và phân biệt read vs write idempotency.

### 23.12. Case L — Tối ưu sai vì nhìn metric sai

~~~text
HTTP p99 = 1,000ms
MongoDB command p99 = 30ms
Pool checkout wait p99 = 500ms
Event-loop lag p99 = 10ms
~~~

Các số giả định. Khả năng cao pressure tại **pool checkout/concurrency**, không phải event loop blocking. Xem pool checked-out/max, `maxConnecting`, long cursor/transaction, created/closed rates, server headroom và số MongoClients/pods trước khi tăng pool nhỏ có kiểm soát.

## 24. Bài tập thực hành và đáp án

Các bài độc lập; code minh họa dùng Spring Data MongoDB reactive + Reactor, không tuyên bố đã chạy test thật trên cluster. Với bài liên quan giao dịch/change streams, cần replica set/sharded lab hỗ trợ và được phép. Trước khi áp dụng production, xác minh Spring Boot/Spring Data/Reactor/driver versions và security config.

### Bài 1 — Reactive repository là gì?

**Đề:** So sánh `MongoRepository<Order,String>` và `ReactiveMongoRepository<Order,String>`.

**Đáp án:** `MongoRepository` là imperative CRUD abstraction, các method thường trả entity/collection đồng bộ. `ReactiveMongoRepository` dùng **reactive publishers** (`Mono`/`Flux`), MongoDB Reactive Streams driver và pipeline được subscribe mới chạy. Đổi interface không biến blocking logic bên ngoài thành non-blocking.

### Bài 2 — `Mono` và `Flux`

**Đề:** API tìm một order theo ID nên trả kiểu nào? API tìm mọi orders của tenant có thể trả kiểu nào?

**Đáp án:** `Mono<Order>` cho 0 hoặc 1 result; `Flux<Order>` cho nhiều results. Trả về `Flux` phải có tenant filter, pagination/limit hoặc streaming design để không phát toàn bộ collection vô hạn.

### Bài 3 — Empty khác error

**Đề:** `repo.findById("missing")` không thấy document. Nó mặc định phát `MongoException` không?

**Đáp án:** Thông thường không: trả `Mono.empty()`, kết thúc bằng `onComplete`. Controller chuyển sang 404 bằng `defaultIfEmpty(ResponseEntity.notFound().build())` hoặc `switchIfEmpty(Mono.error(...))` khi business cần.

### Bài 4 — Cold publisher

**Đề:** Gọi `Mono<Order> m = repo.save(order);` mà không subscribe/return cho WebFlux. Write đã xảy ra chưa?

**Đáp án:** Publisher repository thường **cold**; chưa có subscription thì chưa bắt đầu I/O. Return `m` cho WebFlux hoặc để owner job subscribe/lifecycle rõ ràng, không gọi `m.block()` chỉ để khởi động request.

### Bài 5 — Hai subscriptions

**Đề:** `Mono<Order> m = repo.save(order); m.subscribe(); m.subscribe();`. Có exactly-once write guarantee không?

**Đáp án:** Không. Hai subscriptions có thể kích hoạt hai attempts; nếu save với cùng stable `_id` có thể update hoặc lỗi/version conflict theo state, nhưng không được xem là exactly once. Tránh manual subscribe duplicate, dùng idempotency keys.

### Bài 6 — `map` hay `flatMap`?

**Đề:** `repo.findById(id).map(repo::save)` trả kiểu gì và sửa ra sao?

**Đáp án:** Tạo nested `Mono<Mono<Order>>` (nếu lambda nhận đúng Order). Dùng `flatMap(repo::save)` để flatten Publisher, hoặc dùng `map` chỉ khi hàm biến đổi trả DTO/value đồng bộ.

### Bài 7 — `Mono.just(blocking())`

**Đề:** `Mono.just(legacyDao.load())` có hoãn blocking I/O đến subscription không?

**Đáp án:** Không. Java chạy `legacyDao.load()` trước rồi mới gọi `just`. Dùng `Mono.fromCallable(legacyDao::load).subscribeOn(Schedulers.boundedElastic())` nếu bắt buộc dùng legacy blocking API.

### Bài 8 — `Mono.defer` có tự non-blocking?

**Đề:** `Mono.defer(() -> Mono.just(legacyDao.load()))` đã đủ an toàn trên event loop chưa?

**Đáp án:** Chưa. Call được trì hoãn nhưng vẫn blocking trên thread subscription. Cần offload scheduler phù hợp, bounded queue/concurrency, hoặc dùng reactive DAO gốc.

### Bài 9 — `block()` trong WebFlux

**Đề:** Controller trả `Order` bằng `repo.findById(id).block()`. Điều gì xảy ra?

**Đáp án:** Có thể ném `IllegalStateException` trên Reactor non-blocking thread hoặc block event loop, giảm throughput/tăng p99. Return `Mono<Order>` hoặc `Mono<ResponseEntity<Order>>`, để WebFlux subscribe.

### Bài 10 — `Thread.sleep`

**Đề:** Trong `map` có `Thread.sleep(500)`. Thay bằng gì nếu chỉ muốn delay phát response?

**Đáp án:** Dùng `delayElement(Duration.ofMillis(500))` hoặc `Mono.delay`; không giữ event-loop thread sleep. Nếu muốn retry backoff, dùng `Retry.backoff` theo transient-error policy, không delay tất cả queries vô cớ.

### Bài 11 — `subscribe()` trong controller

**Đề:** Controller gọi `repo.save(o).subscribe()` rồi trả `Mono.just("OK")`. Vì sao nguy hiểm?

**Đáp án:** Trả OK trước khi DB write hoàn tất; errors không propagate vào HTTP lifecycle, cancellation và transaction context bị tách. Return `repo.save(o)` và map response sau completion.

### Bài 12 — Derived query

**Đề:** Viết repository method lấy orders của một tenant với trạng thái OPEN.

**Đáp án:**

~~~java
Flux<Order> findByTenantIdAndStatus(
    String tenantId, String status);
~~~

Tenant lấy từ authenticated principal/server-side authorization, không tin client request parameter.

### Bài 13 — Query annotation

**Đề:** Làm sao tìm trạng thái theo parameter mà không nối raw JSON với user input?

**Đáp án:** Dùng `@Query("{ 'tenantId': ?0, 'status': ?1 }")` hoặc `Query/Criteria`; Spring Data bind parameter. Giữ filter tenant và kiểm index/schema.

### Bài 14 — `ReactiveMongoTemplate.findOne`

**Đề:** Viết truy vấn tenant + order ID.

**Đáp án:**

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("_id").is(orderId));
Mono<Order> result = template.findOne(q, Order.class);
~~~

`Mono.empty()` khi không match, không cần `block()`.

### Bài 15 — Atomic transition

**Đề:** Hai API requests cùng muốn chuyển order từ OPEN sang PAID. Nên dùng `findById -> setStatus -> save` hay conditional update?

**Đáp án:** Ưu tiên **atomic conditional update**:

~~~java
Query q = query(where("_id").is(id)
    .and("tenantId").is(tenantId)
    .and("status").is("OPEN"));
Mono<UpdateResult> result = template.updateFirst(
    q, new Update().set("status", "PAID"), Order.class);
~~~

Kiểm `matchedCount`; nếu không match, xử lý conflict/not-found theo policy. Với nhiều docs/collections cần transaction.

### Bài 16 — `save` partial projection

**Đề:** `template.find` chỉ project `_id`/`status` vào Order, sau đó `repo.save(order)`. Rủi ro?

**Đáp án:** Những fields không load có thể null/default, bị ghi đè khi save entity state tùy mapping. Dùng DTO projection riêng, không save partial entity; dùng `updateFirst` để sửa đúng field.

### Bài 17 — `@Version`

**Đề:** Vì sao dùng `@Version` trên Order?

**Đáp án:** Hỗ trợ optimistic locking cho những save/update paths tương thích, giúp phát hiện một số concurrent stale writes. Không mặc định mọi custom bulk update có cùng version check; kiểm exceptions và integration tests.

### Bài 18 — Reactive pagination

**Đề:** Có thể dùng derived reactive repository method trả `Mono<Page<Order>>` như Spring Data imperative không?

**Đáp án:** Spring Data MongoDB reactive repository docs không hỗ trợ trả `Mono<Page>` theo cách đó. Dùng `Flux<Order>` có `Pageable`, và nếu cần total count thì gọi `Mono<Long>` riêng và kết hợp thành DTO; count/list không mặc nhiên một snapshot.

### Bài 19 — Không giới hạn `findAll`

**Đề:** `repo.findAll().collectList()` trên 2 triệu documents có an toàn vì reactive không?

**Đáp án:** Không. Dù I/O non-blocking, `collectList` materialize toàn bộ vào heap, có nguy cơ OOM/GC. Dùng filter/limit/pagination/streaming và DTO projection.

### Bài 20 — `flatMap` concurrency

**Đề:** `Flux.fromIterable(ids).flatMap(repo::findById,8)` được gọi bởi 100 concurrent requests. Global concurrency tối đa chỉ 8?

**Đáp án:** Không. `8` là limit **mỗi subscription/pipeline**; tổng có thể gần 800 inner subscriptions với nhiều requests, chưa kể operations khác. Cần global/per-tenant admission và server capacity budget.

### Bài 21 — `concatMap`

**Đề:** Một batch tạo order B trước rồi order C phụ thuộc business state của B. Nên dùng `flatMap(repo::save, 32)` không?

**Đáp án:** Không nếu thứ tự/side effects phụ thuộc nhau. Dùng `concatMap(repo::save)` hoặc compose tuần tự rõ ràng. `flatMapSequential` chỉ giữ thứ tự **output**, các inner operations vẫn có thể chạy đồng thời.

### Bài 22 — `buffer`

**Đề:** `repo.findAll().buffer(100).collectList()` có giới hạn memory ở 100 objects không?

**Đáp án:** Không. `buffer(100)` tạo các lists 100 items, sau đó `collectList()` lại gom **tất cả batches** vào một List. Với stream vô hạn nó có thể không bao giờ complete, với stream lớn có thể OOM.

### Bài 23 — `Schedulers.boundedElastic`

**Đề:** Đã bọc JDBC blocking call trong boundedElastic, nên service có thể nhận 100.000 tasks mà không cần admission gate?

**Đáp án:** Không. BoundedElastic giới hạn backing threads nhưng có **task queue**, có thể quá tải/timeout/heap pressure. Dùng bounded task/concurrency limits, prefer R2DBC/async SDK nếu phù hợp.

### Bài 24 — `publishOn` sai vị trí

**Đề:** 

~~~java
repo.findById(id)
    .map(o -> legacyBlockingCall(o))
    .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` đã dời blocking mapper ra khỏi event loop chưa?

**Đáp án:** Chưa. `publishOn` ảnh hưởng **downstream**; mapper phía trước vẫn chạy trên thread upstream. Dời scheduler switch **trước** mapper hoặc dùng `flatMap(o -> Mono.fromCallable(...).subscribeOn(boundedElastic()))`, với concurrency cap.

### Bài 25 — `Mono.zip` và empty

**Đề:** `Mono.zip(repo.findById("missing"), repo.count())` có trả tuple với giá trị null cho order không?

**Đáp án:** Không. Khi một Mono empty, `zip` thường **complete empty** (có thể cancel nhánh còn lại); không tạo null item. Dùng `switchIfEmpty` hoặc thiết kế `flatMap`, quyết định business semantics trước.

### Bài 26 — `Mono.zip` và consistency

**Đề:** Hai read publishers cùng nằm trong `Mono.zip`. Chúng có được thực thi tại một MongoDB snapshot timestamp duy nhất không?

**Đáp án:** Không. `zip` là operator composition/concurrency, không tự tạo MongoDB transaction/snapshot. Nếu cần consistency, dùng read concern/transaction phù hợp, hiểu overhead và server requirements.

### Bài 27 — Reactive transaction manager

**Đề:** Dự án có `@Transactional` trên method trả `Mono<Void>` nhưng không có `ReactiveMongoTransactionManager`. Có chắc hai MongoDB writes atomic không?

**Đáp án:** Không. Reactive MongoDB transactions cần manager/factory đúng, topology hỗ trợ, đúng Spring AOP proxy và subscription scope. Test rollback trên replica set lab.

### Bài 28 — Manual subscription trong transaction

**Đề:** Trong `@Transactional` method, service gọi `repo.save(o).subscribe()` và trả `Mono.empty()`. Write có chắc tham gia transaction không?

**Đáp án:** Không. Manual subscription tách khỏi returned publisher/transaction context được manager quản lý. Return composed Mono và không tự subscribe trong method.

### Bài 29 — Parallel trên same session

**Đề:** `flatMap(...,64)` thực thi 64 updates trên cùng reactive transaction/session. Có luôn an toàn?

**Đáp án:** Không. MongoDB ClientSession/transactions không hỗ trợ tùy ý nhiều operations concurrent trong cùng session. Dùng `concatMap`/sequential composition và giữ transaction ngắn.

### Bài 30 — Transaction + payment gateway

**Đề:** Callback transaction gọi payment SDK để charge thẻ rồi do MongoDB transient error bị retry callback. Rủi ro?

**Đáp án:** Payment có thể bị **charge nhiều lần**. Không đặt external non-idempotent side effects trong transaction retry callback thiếu bảo vệ; dùng provider idempotency key, transactional outbox và reconciler.

### Bài 31 — Change streams

**Đề:** Tạo change stream trên MongoDB standalone local với API `template.changeStream`. Có chạy như replica set không?

**Đáp án:** MongoDB change streams cần **replica set/sharded cluster** hỗ trợ; standalone deployment không cung cấp semantics tương tự. Dùng replica set lab/integration test.

### Bài 32 — `@Tailable`

**Đề:** `@Tailable Flux<Log> findByLevel(...)` dùng regular collection. Có đúng điều kiện?

**Đáp án:** Không. Tailable cursor yêu cầu **capped collection**. Với event changes trên normal collections, cân nhắc change streams; quản lý lifecycle/resume.

### Bài 33 — Resume token/checkpoint

**Đề:** Consumer áp side effect E101 xong rồi crash trước khi checkpoint resume token. Khi restart có thể nhận E101 nữa không?

**Đáp án:** Có, có thể replay. Dùng idempotent consumer/dedupe stable event ID và checkpoint **sau side effect durable**. `Flux` không bảo đảm exactly once across systems.

### Bài 34 — HTTP client disconnect

**Đề:** Client hủy POST sau 200 ms, nhưng MongoDB đã nhận insert. Có chắc insert bị rollback vì subscription cancel?

**Đáp án:** Không. Cancellation/timeout phía client **không chứng minh server write chưa commit**. Dùng stable idempotency key, verify request state và retryable write semantics.

### Bài 35 — `onErrorReturn(0)`

**Đề:** API tổng số tiền trả `0` mỗi khi MongoDB timeout. Vì sao không an toàn?

**Đáp án:** Timeout bị biến thành dữ liệu nghiệp vụ có vẻ hợp lệ, có thể gây quyết định sai. Propagate error hoặc dùng fallback có trạng thái degraded/nguồn tin cậy, không giả vờ “không có tiền/đơn hàng”.

### Bài 36 — `StepVerifier.withVirtualTime`

**Đề:** Unit test dùng virtual time cho `Mono.delay(1h)` chạy nhanh. Điều đó có chứng minh MongoDB `find` có p99 dưới 10ms không?

**Đáp án:** Không. Virtual time ảo hóa Reactor scheduler/timers, **không** benchmark MongoDB network/server. Dùng load test/integration test metrics thật.

### Bài 37 — WebTestClient và security

**Đề:** Controller đọc tenant từ HTTP header bất kỳ và repository lọc đúng header; test HTTP 200 pass. Đã bảo mật multi-tenant chưa?

**Đáp án:** Chưa. Client có thể giả header tenant khác. Tenant phải lấy từ authenticated principal/validated gateway context; test cross-tenant access denial, không chỉ happy path 200.

### Bài 38 — Command latency thấp, HTTP chậm

**Đề:** MongoDB command p99=12ms, driver checkout=3ms, HTTP p99=900ms và event-loop lag=700ms. Điều tra đâu?

**Đáp án:** Có dấu hiệu event-loop blocking/CPU-heavy mapping/serialization/GC hoặc app queue. Lấy thread dump/BlockHound/traces, kiểm blocking SDK/`block`/large buffers; tăng MongoDB pool không giải quyết.

### Bài 39 — DB CPU gần 100%, reactive app rảnh threads

**Đề:** Reactive WebFlux app còn event-loop headroom, nhưng MongoDB CPU=99%, query p99 2 giây. Có nên tăng `flatMap` concurrency từ 8 lên 200?

**Đáp án:** Thường không. DB đang saturated; thêm in-flight queries làm queue/contension tăng. Tối ưu indexes/query, giảm concurrency/bulk reports, dùng admission và scale database nếu nhu cầu bền vững vượt capacity.

### Bài 40 — Thiết kế API orders reactive end-to-end

**Đề:** Xây endpoint tạo order với tenant auth, MongoDB và audit event, yêu cầu không chặn event loop, chống duplicate do retry, p95 dưới 300ms và có khả năng rollout production. Nêu thiết kế/kiểm chứng.

**Đáp án gợi ý:**

1. Sử dụng `spring-boot-starter-webflux` + `spring-boot-starter-data-mongodb-reactive`, dependency versions theo BOM.
2. Inject singleton reactive MongoDB infrastructure; dùng `ReactiveMongoRepository` cho CRUD, `ReactiveMongoTemplate` cho atomic conditional updates/aggregation.
3. Nhận tenant từ **reactive authenticated principal**, không từ header có thể giả.
4. Validate request, gán stable `idempotencyKey` và unique index theo tenant/business.
5. Service trả `Mono<Order>`, không `block()`, không `subscribe()` trong controller/service.
6. Nếu order+audit cần atomic, dùng `ReactiveMongoTransactionManager`/`TransactionalOperator` và compose hai writes **trong cùng publisher**; test rollback trên replica set.
7. Side effects ngoài MongoDB như Kafka/payment dùng outbox hoặc idempotent workflows; không gọi blocking SDK trong transaction.
8. Nếu bắt buộc gọi blocking legacy, dùng `fromCallable(...).subscribeOn(boundedElastic())` **có concurrency cap**, ưu tiên migration sang async.
9. Limit MongoDB in-flight, request queues và timeout theo **remaining HTTP deadline**; áp retry chỉ cho transient errors, có cap/jitter.
10. Test bằng `StepVerifier`, `WebTestClient` và MongoDB integration tests: success, 404, duplicate key, transaction rollback, timeout/cancel và cross-tenant.
11. Monitor HTTP p95/p99, event-loop lag, driver pool checkout wait, MongoDB command latency/CPU/IOPS/retries/heap.
12. Canary deploy và load test open-loop với query mix thực, có rollback nếu p99/errors/correctness xấu.

Không chọn cấu hình `flatMap=16` hoặc pool=100 vì đó là default phổ biến; chọn bằng **evidence của workload, SLO và DB headroom**. Kết quả đúng là pipeline vừa non-blocking, vừa giữ business semantics và đủ giới hạn tài nguyên để phục vụ ổn định.

## 25. Tài liệu chính thức để tra cứu theo phiên bản

Tài liệu này hướng dẫn mô hình/kỹ thuật chung, **không thay thế tài liệu API của Spring Data MongoDB, Reactor và MongoDB Java Reactive Streams Driver theo đúng version dự án**. Một số tài liệu dẫn tới nhánh `current`, nội dung sẽ thay đổi khi phiên bản mới được phát hành. Khi triển khai, kiểm BOM Spring Boot, Spring Data MongoDB, Reactor, Java driver và MongoDB Server tương thích.

### 25.1. Spring Data MongoDB Reactive API

1. [Spring Data MongoDB — Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/) — danh mục tổng quan mapping, repositories, template, sessions, transactions và streaming.
2. [ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html) — các overload `find`, `findOne`, `insert`, `save`, `updateFirst`, `findAndModify`, `aggregate` và reactive operations.
3. [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Criteria`, `Query`, projection, cursorBatchSize, sort, limit và keyset/scroll patterns.
4. [Saving, Updating and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — update/filter, findAndModify, `@Version` và mapping.
5. [MongoDB-specific Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, `Flux` + `Pageable` và lưu ý `Mono<Page>` không được hỗ trợ.
6. [Spring Data Repositories — Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html) — repository abstractions, reactive repository types và lifecycle.
7. [Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking) — `@Version`, stale writes và optimistic-lock exception semantics.
8. [Mapping Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `@Document`, `@Id`, `@Field`, constructors và entity conversion.

### 25.2. Transactions và streaming

9. [Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `ReactiveMongoTransactionManager`, `TransactionalOperator`, Reactor Context, explicit ClientSession và hạn chế repository session support.
10. [Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — reactive `changeStream(...).listen()`, resume tokens, server time và long-lived streams.
11. [Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html) — capped collections, `ReactiveMongoTemplate.tail`, `@Tailable` repository methods.
12. [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — replica set/sharded prerequisites, transaction atomicity/limitations.
13. [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — oplog/history/resume semantics và deployment support.
14. [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — query planning và giảm server service time cho reactive/imperative như nhau.

### 25.3. Reactor và WebFlux

15. [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Mono`/`Flux`, publishers, operators, subscription và backpressure.
16. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — `subscribeOn`, `publishOn`, `boundedElastic` và vì sao `block()` không được phép trên non-blocking schedulers.
17. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier` và virtual time.
18. [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — `onErrorResume`, `retryWhen` và error signals.
19. [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html) — non-blocking I/O, event-loop model và Reactive Streams backpressure.
20. [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html) — `Mono/Flux` return types, request binding và HTTP responses.
21. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — kiểm thử reactive HTTP endpoints.
22. [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html) — reactive security context/authentication/authorization.

### 25.4. Boot, MongoDB driver và observability

23. [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.mongodb) — auto-configuration, configuration properties, reactive starter và MongoDB connections.
24. [MongoDB Java Reactive Streams Driver](https://www.mongodb.com/docs/drivers/reactive-streams/) — Reactive Streams driver concepts/API/version compatibility.
25. [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — server selection, TLS, pool/network timeout options theo driver/version.
26. [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP/SDAM/Command events khái niệm và instrumentation; đối chiếu listener/API của reactive driver version.
27. [MongoDB serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections, locks/queues/CPU/storage metrics.
28. [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `executionStats`, `IXSCAN/COLLSCAN`, keys/docs examined để sửa query chậm.
29. [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry/ambiguous write outcomes.
30. [Micrometer Observation](https://micrometer.io/docs/observation) — instrumentation/tracing context; kiểm Spring Boot/Actuator version khi tích hợp.

**Ghi chú:** Các URL chính thức có thể chuyển hướng khi Spring Data/Boot/Reactor đổi cấu trúc website. Nội dung `ReactiveMongoTemplate`, repositories, transactions và schedulers nên được tra ở docs **đúng release line**. Bài học không tuyên bố đã chạy các đoạn code, benchmark hay tests trên môi trường thực.

### 25.5. Checklist trước khi đưa reactive API vào production

1. **Dependency/version:** dùng đúng starter reactive, driver và Reactor qua BOM; không duplicate MongoClients.
2. **Non-blocking path:** không có `block`/`Thread.sleep`/Sync MongoTemplate/JDBC trong WebFlux event-loop path.
3. **Security:** tenant/ACL từ trusted reactive authentication context và filter mọi truy vấn.
4. **Resource bounds:** page size, batch size, `flatMap` concurrency, queue capacity, timeout, response size.
5. **Correctness:** atomic conditional updates/`@Version`/transactions đúng scope, idempotent retries, không fire-and-forget writes.
6. **Streaming:** cursor/change-stream cancellation, resume/checkpoint và không giả định exactly once.
7. **Tests:** `StepVerifier`, `WebTestClient`, integration trên MongoDB replica set, race/cancel/timeout/cross-tenant cases.
8. **Observability:** HTTP p95/p99, event-loop lag, driver pool checkout, MongoDB command latency/`explain`/CPU/IOPS, error/retry counters.
9. **Rollout:** canary, load test với mix thật, failover/recovery và rollback plan.
10. **Business SLO:** chấp nhận load shedding có kiểm soát khi capacity hết; không để hàng đợi vô hạn gây timeout dây chuyền.

## 26. Kết luận

**`ReactiveMongoTemplate` và `ReactiveMongoRepository`** là hai cách truy cập MongoDB bằng Spring Data theo mô hình non-blocking Reactive Streams. Repository phù hợp cho **domain CRUD/derived queries**, còn template phù hợp cho **criteria phức tạp, atomic updates, aggregations, projections và streaming**. Cả hai có thể cùng xuất hiện trong một ứng dụng WebFlux với reactive MongoDB driver/connection infrastructure được cấu hình đúng.

Điều quan trọng nhất không phải mọi method đều trả `Mono` hay `Flux`, mà là **không vô tình chặn luồng đang xử lý nhiều requests**. Hãy **return pipeline** thay vì `block()` hoặc `subscribe()` trong request path; thay synchronous I/O bằng reactive APIs; khi bắt buộc tương thích legacy blocking, dùng `fromCallable + boundedElastic` kèm **giới hạn concurrency và deadline**. Reactive backpressure không thay thế `limit`, pagination, bộ nhớ có giới hạn hay việc tối ưu MongoDB indexes.

Với nghiệp vụ có nhiều writes, cần hiểu **transaction/reactive subscriber Context, optimistic locking, cancellation và commit ambiguity**. Một HTTP timeout không chứng minh MongoDB write chưa hoàn tất; một change stream không đảm bảo exactly once giữa MongoDB với hệ thống khác. Chỉ khi kết hợp **non-blocking end-to-end, kiểm soát tài nguyên, data consistency, security và testing/monitoring theo tải thực**, reactive MongoDB mới mang lại lợi ích bền vững.

**Thiết kế tốt là giữ event loop rảnh để phục vụ nhiều yêu cầu, đồng thời bảo đảm MongoDB và các tài nguyên downstream chỉ nhận lượng công việc mà chúng có thể hoàn thành đúng, an toàn và trong thời gian hữu ích.**
