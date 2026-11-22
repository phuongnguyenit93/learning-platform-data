# Phân biệt JDBC, JPA chặn với driver dữ liệu reactive trong Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Tích hợp hệ sinh thái  
> **Trọng tâm:** phân biệt bản chất truy cập SQL của JDBC/JPA (imperative, blocking) và R2DBC (Reactive Relational Database Connectivity); tác động lên event loop, thread, connection pool, transaction và thiết kế API; cách tích hợp tạm thời hệ thống cũ; ví dụ Java 17+ với Spring Boot 4.0.9, H2, WebFlux, Spring Data R2DBC và HTTP integration tests.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích JDBC, JPA, Hibernate, Spring Data JDBC, Spring Data JPA, R2DBC và Spring Data R2DBC nằm ở tầng nào.
2. Phân biệt lời gọi **chặn thread** với xử lý **không chặn thread trong thời gian chờ I/O**.
3. Nhận ra vì sao `Mono.just(jpaRepository.findById(...))` vẫn chặn event-loop và vì sao `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` chỉ là cầu nối.
4. Viết repository reactive trả `Mono<T>`/`Flux<T>` dùng driver R2DBC thay vì dùng JDBC bên trong operator.
5. Hiểu sự khác nhau giữa `DataSource`/`java.sql.Connection` và `ConnectionFactory`/`io.r2dbc.spi.Connection`.
6. Phân biệt transaction của `PlatformTransactionManager` gắn với thread và `ReactiveTransactionManager` gắn với Reactor Context.
7. Biết các đặc điểm JPA như persistence context, dirty checking, lazy loading không tự xuất hiện khi đổi sang R2DBC.
8. Chọn stack theo workload, sự sẵn có của driver và độ phức tạp nghiệp vụ thay vì mặc định “reactive luôn nhanh hơn”.
9. Giới hạn concurrency và quan sát JDBC pool, R2DBC pool, event-loop, latency và timeout.
10. Chạy một REST API không chặn bằng Spring WebFlux + Spring Data R2DBC + H2 và kiểm thử hành vi thực.

**Kết luận nền tảng:** WebFlux là web runtime reactive; nó không tự biến lời gọi JDBC/JPA thành non-blocking. Muốn có đường truy cập SQL reactive từ đầu tới cuối, phải dùng driver/API reactive thực sự (ví dụ R2DBC) và xây dựng pipeline không chứa thao tác blocking không được cô lập. Ngược lại, khi hệ thống JPA đang ổn định và cần ORM mạnh, Spring MVC + JDBC/JPA hoặc một boundary blocking được kiểm soát vẫn có thể là lựa chọn hợp lý.

## 2. Xác định đúng các khái niệm

### 2.1. JDBC

**JDBC** (Java Database Connectivity) là API chuẩn `java.sql` cho SQL database. Các lời gọi như `DataSource.getConnection()`, `PreparedStatement.executeQuery()` và `ResultSet.next()` được sử dụng theo mô hình đồng bộ. Khi database chậm, thread thực hiện lời gọi phải chờ nó hoàn tất hoặc lỗi/timeout.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, name FROM items WHERE id = ?")) {

    statement.setLong(1, id);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            return new ItemView(
                rows.getLong("id"),
                rows.getString("name")
            );
        }
        return null;
    }
}
~~~

Đây là **fragment minh họa JDBC thuần**, giả định có biến `DataSource dataSource`, `long id` và DTO `ItemView`. Các lệnh JDBC chặn thread trong thời gian chờ driver/database; `try-with-resources` đảm bảo connection/statement/result set được đóng theo lifecycle.

**Spring JDBC** như `JdbcTemplate` hoặc `JdbcClient` giảm boilerplate SQL và quản lý resource, nhưng vẫn dựa trên JDBC blocking. **Spring Data JDBC** thêm aggregate mapping/repository nhưng cũng dựa vào JDBC. Đừng nhầm Spring Data JDBC với Spring Data R2DBC chỉ vì cả hai đều là Spring Data.

### 2.2. JPA, Hibernate và Spring Data JPA

**JPA** (Jakarta Persistence) là specification về ORM và persistence lifecycle. **Hibernate ORM** là implementation JPA phổ biến; **Spring Data JPA** cung cấp repository abstraction trên JPA/Hibernate.

~~~java
public interface ItemJpaRepository
        extends JpaRepository<LegacyItemEntity, Long> {
}
~~~

`findById(id)`, `save(entity)`, `flush()` và lazy relation loading của Spring Data JPA/Hibernate thông thường cuối cùng sử dụng JDBC và là blocking. JPA bổ sung entity state, persistence context, dirty checking, cascade, relationship mapping và query language; điều này **không** làm database I/O trở thành reactive.

Có một số công nghệ “reactive ORM” riêng trong hệ sinh thái, nhưng không được đánh đồng chúng với Spring Data JPA mặc định. Bài này so sánh Spring Data JPA/Hibernate ORM dựa trên JDBC với Spring Data R2DBC.

### 2.3. R2DBC

**R2DBC** (Reactive Relational Database Connectivity) là specification truy cập SQL qua reactive stream. Nó sử dụng:

- `io.r2dbc.spi.ConnectionFactory` thay cho `javax.sql.DataSource`.
- `io.r2dbc.spi.Connection` thay cho `java.sql.Connection`.
- `Publisher` cho kết quả kết nối, thực thi statement và lấy rows.
- Hỗ trợ composition, cancellation và demand theo reactive contract.

`ConnectionFactory.create()` trả Publisher; kết nối và thực thi không bị buộc phải block thread gọi trong khi chờ network I/O. Hiệu quả thực tế phụ thuộc driver, server và cách bạn sử dụng API.

**Spring Data R2DBC** thêm `ReactiveCrudRepository`, `R2dbcEntityTemplate`, object mapping và repository query methods trên driver R2DBC. **Spring Framework R2DBC** có `DatabaseClient`, `R2dbcTransactionManager` và `ConnectionFactoryUtils`.

### 2.4. Không so sánh nhầm tầng

~~~text
              Imperative SQL                 Reactive SQL

HTTP layer    Spring MVC                     Spring WebFlux
                     |                               |
Data API      Spring Data JPA/JDBC            Spring Data R2DBC
                     |                               |
Mapper/SQL    Hibernate ORM, JdbcTemplate    R2dbcEntityTemplate, DatabaseClient
                     |                               |
Driver SPI    JDBC / java.sql                R2DBC / io.r2dbc.spi
                     |                               |
Network       DB connection                  DB connection
                     |                               |
DB            PostgreSQL/H2/...              PostgreSQL/H2/...
~~~

**Spring MVC vẫn có thể dùng R2DBC**, **WebFlux vẫn có thể gọi JPA**, nhưng cách trộn phải có chủ ý. Một lớp trả `Mono` không chứng minh tầng bên dưới đã non-blocking.

## 3. Bảng so sánh tổng thể

| Tiêu chí | JDBC / Spring JDBC | JPA / Spring Data JPA | R2DBC / Spring Data R2DBC |
| --- | --- | --- | --- |
| Giao diện I/O | Đồng bộ, blocking | Đồng bộ, qua JDBC, blocking | Reactive Publisher |
| Kết quả thường gặp | `List<T>`, `T`, `Optional<T>` | Entity, `Optional<T>`, `List<T>`, `Page<T>` | `Mono<T>`, `Flux<T>` |
| Connection | `DataSource`, `java.sql.Connection` | JDBC connection qua ORM | `ConnectionFactory`, R2DBC connection |
| Mapping | Thủ công hoặc mapper | ORM/entity graph mạnh | Row/aggregate mapping, không phải JPA |
| Lazy loading | Do code tự quyết định | Hỗ trợ quan hệ lazy theo Hibernate | Không có JPA-style lazy entity proxy mặc định |
| Persistence context / dirty checking | Không | Có | Không có JPA persistence context |
| Transaction | `PlatformTransactionManager`, thường ThreadLocal | `JpaTransactionManager`, ThreadLocal | `ReactiveTransactionManager`, Reactor Context |
| Dùng trên Netty event-loop | Không trực tiếp | Không trực tiếp | Phù hợp khi toàn pipeline non-blocking |
| Backpressure phía client | Không có theo JDBC API | Không có theo JPA API | Reactive stream, nhưng còn phụ thuộc driver/DB |
| Mức độ ORM | Thấp đến vừa | Cao | Khác JPA, mapping đơn giản hơn |
| Điểm mạnh | Trưởng thành, API dễ hiểu | Domain model phức tạp, ecosystem lớn | Tối ưu concurrency cho I/O-bound reactive services |
| Chi phí đổi stack | Thấp với code cũ | Thấp nếu đã dùng JPA | Cần xem lại repository, transaction, mapping, query và test |

Không suy ra “R2DBC nhanh hơn JDBC trong mọi benchmark”. Với truy vấn đơn giản, concurrency thấp hoặc ứng dụng có nhiều business logic blocking, hệ thống JDBC/JPA được cấu hình tốt có thể đơn giản và có throughput tương đương hoặc tốt hơn. R2DBC chủ yếu giúp giảm chi phí giữ **thread chờ I/O**, chứ không làm SQL hoặc database thực thi nhanh hơn.

## 4. Điều gì bị chặn khi dùng JDBC trong WebFlux?

Giả sử Netty event-loop chỉ có một số lượng thread nhỏ để xử lý rất nhiều socket. Nếu một request dùng thread đó gọi JDBC và chờ database 300 ms, thread không thể xử lý các request/socket khác trong cùng thời gian.

~~~text
Sai: blocking JDBC ngay trên event-loop

reactor-http-nio-1:
  accept request A -> JDBC query [đợi DB 300ms] -> response A
  accept request B -> bị chậm vì thread đang bị chiếm
  accept request C -> bị chậm vì thread đang bị chiếm

Đúng khi còn dùng JDBC:
  reactor-http-nio-1:
    request A -> schedule blocking task -> quay về phục vụ socket
  boundedElastic-1:
    JDBC query [đợi DB 300ms] -> gửi kết quả về pipeline

Đúng khi truy cập DB reactive:
  reactor-http-nio-1:
    request A -> subscribe vào R2DBC publisher -> chờ I/O không giữ thread
  DB/driver callback:
    phát row -> tiếp tục pipeline -> response
~~~

### 4.1. Ví dụ sai: `Mono.just()` không làm lời gọi bất đồng bộ

~~~java
@GetMapping("/bad/{id}")
Mono<ItemView> bad(@PathVariable long id) {
    ItemView item = legacyJpaService.load(id); // JDBC đã chạy và chặn.
    return Mono.just(item);
}
~~~

Kể cả viết một dòng vẫn sai:

~~~java
return Mono.just(legacyJpaService.load(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

**Vì sao?** Java phải đánh giá đối số của `Mono.just(...)` ngay khi tạo Mono. `legacyJpaService.load(id)` đã chạy trên thread hiện tại trước khi `subscribeOn()` có cơ hội tác động.

### 4.2. Ví dụ đúng khi chưa thể bỏ JDBC/JPA

~~~java
Mono<ItemView> loadViaLegacy(long id) {
    return Mono.fromCallable(() -> legacyJpaService.load(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` trì hoãn việc gọi `legacyJpaService.load(id)` cho tới khi có subscription; `subscribeOn(boundedElastic())` chuyển việc thực thi nguồn blocking sang scheduler dành cho blocking work.

`boundedElastic` có giới hạn số thread và các task chờ. Đây là **cách cô lập blocking**, không biến JDBC thành non-blocking. Mỗi truy vấn JDBC vẫn chiếm một worker thread và một JDBC connection trong lúc chờ.

Nếu `legacyJpaService.load()` có thể trả `null`, `Mono.fromCallable` hoàn tất rỗng khi trả null; nên dùng `switchIfEmpty` hoặc map thành 404 theo API contract.

### 4.3. Giữ JPA transaction ở boundary đồng bộ

Một lỗi tinh vi là gắn `@Transactional` vào method trả `Mono` trong khi bên trong là Spring Data JPA, rồi hy vọng transaction JPA tự băng qua các Reactor operator.

Đúng hơn là để transaction blocking nằm ở một service đồng bộ riêng:

~~~java
@Service
public class LegacyJpaService {

    private final ItemJpaRepository repository;

    public LegacyJpaService(ItemJpaRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ItemView load(long id) {
        return repository.findById(id)
            .map(item -> new ItemView(item.getId(), item.getName()))
            .orElse(null);
    }
}
~~~

Đây là **fragment dành cho module JPA riêng**; cần có entity/repository tương ứng và dependency `spring-boot-starter-data-jpa`. Lớp bọc reactive nằm bên ngoài và gọi qua Spring proxy:

~~~java
@Service
public class LegacyBridge {

    private final LegacyJpaService legacyJpaService;

    public LegacyBridge(LegacyJpaService legacyJpaService) {
        this.legacyJpaService = legacyJpaService;
    }

    public Mono<ItemView> load(long id) {
        return Mono.fromCallable(() -> legacyJpaService.load(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Điều quan trọng là `@Transactional` đồng bộ mở, dùng và đóng transaction **bên trong cùng một lời gọi trên worker thread**. Không đưa entity JPA chưa tải đủ lazy association ra khỏi boundary rồi cố đọc lazy property ở một reactive thread khác. Map DTO trước khi đóng transaction.

### 4.4. Khi nào không cần WebFlux?

Nếu phần lớn các operation đều JDBC/JPA blocking, hệ thống MVC với thread-per-request có thể đơn giản hơn: cấu hình servlet thread pool, HikariCP, timeout và database capacity. Không bắt buộc đổi sang WebFlux chỉ vì muốn trả `Mono` trong controller.

Java virtual threads ở các phiên bản JDK hỗ trợ chúng có thể làm chi phí thread blocking thấp hơn, nhưng **không biến JDBC thành API non-blocking** và không giải phóng capacity của database. Ví dụ runnable trong bài dùng Java 17.

## 5. R2DBC thực hiện truy vấn như thế nào?

Ví dụ dùng Spring Framework `DatabaseClient`:

~~~java
public Mono<ItemView> findOne(DatabaseClient db, long id) {
    return db.sql("""
            SELECT id, name
            FROM items
            WHERE id = :id
            """)
        .bind("id", id)
        .map((row, metadata) ->
            new ItemView(
                row.get("id", Long.class),
                row.get("name", String.class)))
        .one();
}
~~~

Đây là **fragment minh họa** dùng `DatabaseClient`, giả định có bảng `items` và record `ItemView(Long id, String name)` tương ứng. `sql(...).bind(...).map(...).one()` tạo `Mono` reactive, không thực hiện SQL một cách eager trên event-loop.

`DatabaseClient` quản lý việc lấy/trả connection, thực thi statement và ánh xạ lỗi sang nhóm `DataAccessException` thích hợp. Khi dùng Spring Data R2DBC ở tầng cao hơn, bạn thường không cần tự viết mọi câu SQL.

### 5.1. ReactiveCrudRepository

~~~java
public interface ItemRepository
        extends ReactiveCrudRepository<ItemEntity, Long> {
}
~~~

Các method thường dùng:

| Method | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `findById(id)` | `Mono<ItemEntity>` | Có một row hoặc empty |
| `findAll()` | `Flux<ItemEntity>` | Luồng kết quả |
| `save(entity)` | `Mono<ItemEntity>` | Insert hoặc update |
| `deleteById(id)` | `Mono<Void>` | Hoàn tất thao tác xóa |
| `existsById(id)` | `Mono<Boolean>` | Có tồn tại hay không |
| `count()` | `Mono<Long>` | Đếm số row |

**`Flux` không có nghĩa DB streaming vô hạn.** Kết quả phụ thuộc query, fetch strategy và driver. Không sử dụng `findAll().collectList()` cho bảng rất lớn; dùng phân trang/keyset pagination hoặc streaming có giới hạn theo nghiệp vụ.

### 5.2. API R2DBC không dùng JPA EntityManager

Không có việc:
- Gọi `EntityManager.flush()` để “đẩy các thay đổi R2DBC”.
- Tự động dirty checking như persistence context của Hibernate.
- Giữ entity graph lazy rồi truy cập property để phát sinh SQL ngầm.
- Đem annotation `@ManyToOne` của JPA vào R2DBC và kỳ vọng lazy ORM giống Hibernate.

Spring Data R2DBC hỗ trợ mapping entity/aggregate, repository, template và một số relationship/aggregate semantics của Spring Data Relational. Với quan hệ phức tạp, hãy chủ động thiết kế query/join, mapping DTO, multiple queries hoặc boundary aggregate thích hợp.

## 6. `DataSource` khác `ConnectionFactory`

| JDBC | R2DBC |
| --- | --- |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| `PreparedStatement.executeQuery()` | `Statement.execute()` phát Publisher |
| `ResultSet.next()` | Publisher của `Result`/row |
| `HikariDataSource` thường dùng pool JDBC | `r2dbc-pool` có thể quản lý R2DBC connections |
| `spring.datasource.*` | `spring.r2dbc.*` |

Ví dụ cấu hình:

~~~properties
# JDBC (khi dùng module JDBC/JPA)
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
~~~

~~~properties
# R2DBC (khi dùng module R2DBC)
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=shop_user
spring.r2dbc.password=${DB_PASSWORD}
~~~

`jdbc:` và `r2dbc:` là hai protocol URL khác nhau. Không thể trỏ JDBC repository vào R2DBC URL rồi mong nó tự thành reactive.

Driver production phải hỗ trợ đúng database/dialect và các tính năng thực sự cần như transaction, cancellation, generated keys, parameter binding và TLS. Xác minh tính tương thích của driver, server và framework trước khi triển khai.

### 6.1. Pool và giới hạn tài nguyên

Reactive không có nghĩa không cần connection pool:

- JDBC: connection pool như HikariCP; thread chờ khi JDBC call đang chạy.
- R2DBC: connection pool như `r2dbc-pool` khi được cấu hình; request có thể chờ connection theo reactive publisher.
- Cả hai đều bị giới hạn bởi max connections, DB CPU/IOPS, row lock và transaction duration.

Với R2DBC Pool, khi dependency `io.r2dbc:r2dbc-pool` có mặt và pooling được bật theo cấu hình Boot, có thể cấu hình:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=2
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-idle-time=30m
~~~

Đây là **ví dụ cấu hình production**, không cần thêm vào demo H2. Số connection phải được tính theo số replica và khả năng chấp nhận connection của database; 50 instance x 20 connection có thể mở tới khoảng 1.000 kết nối.

## 7. Transactions: hai mô hình khác nhau

### 7.1. JDBC/JPA: transaction gắn với thread

Ở imperative stack, `PlatformTransactionManager` (thường `DataSourceTransactionManager` hoặc `JpaTransactionManager`) gắn transaction resource với thread trong thời gian chạy method.

~~~java
@Transactional
public Receipt placeOrderBlocking(Command command) {
    inventoryRepository.reserve(command.productId());
    return orderJpaRepository.save(mapToEntity(command)).toReceipt();
}
~~~

Đây là **fragment khái niệm** trong service JPA/JDBC đồng bộ, không phải file thuộc demo R2DBC. Cả hai lời gọi nằm trong transaction sync được Spring AOP proxy mở/đóng.

Không tự tạo `subscribe()` hoặc nhảy thread bên trong transaction JPA rồi cho rằng cùng ThreadLocal transaction được truyền sang thread mới.

### 7.2. R2DBC: transaction gắn với Reactor Context

Reactive transaction dùng `ReactiveTransactionManager` (ví dụ `R2dbcTransactionManager`) và lưu transaction-bound connection vào subscriber `Context`, không dựa vào thread cố định.

~~~java
public Mono<Receipt> placeOrderReactive(Command command) {
    return inventoryRepository.reserve(command.productId())
        .then(orderRepository.save(mapToEntity(command)))
        .map(this::toReceipt)
        .as(transactionalOperator::transactional);
}
~~~

Đây là **fragment minh họa**: giả định các repository là reactive và `transactionalOperator` là một bean được tạo từ `ReactiveTransactionManager`. Các operation phải nằm trong cùng reactive chain/Context; đừng `.block()` hoặc tự `.subscribe()` giữa transaction.

Bean tối thiểu khi đã có `ReactiveTransactionManager`:

~~~java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Với một `ConnectionFactory`, Spring cung cấp `R2dbcTransactionManager`; trong ứng dụng Boot tương thích, transaction manager có thể được auto-configure theo dependency và bean hiện hữu.

### 7.3. `@Transactional` reactive và các bẫy

Method trả reactive type có thể dùng `@Transactional` nếu Spring chọn đúng `ReactiveTransactionManager`:

~~~java
@Transactional
public Mono<ItemEntity> createReactive(ItemEntity item) {
    return repository.save(item);
}
~~~

- Transaction được bắt đầu khi Publisher được subscribe, không phải chỉ khi method được gọi để tạo Mono.
- Mọi thao tác DB trong transaction phải đi qua pipeline có Reactor Context của transaction.
- Không dùng JDBC operation trực tiếp bên trong reactive transaction rồi nghĩ rằng nó tự enlist vào R2DBC connection.
- `@Transactional` qua Spring proxy; self-invocation thường không được interceptor áp dụng.
- Cancellation có thể làm reactive transaction rollback; cần xác định semantics của transaction khi stream bị hủy sớm.
- Khi app có cả transaction manager JDBC/JPA và R2DBC, phải chọn manager rõ ràng cho mỗi boundary; không để Spring tùy đoán.

### 7.4. Không có distributed transaction tự động giữa JDBC và R2DBC

Một method vừa cập nhật JPA vừa cập nhật R2DBC **không tạo atomic transaction** chỉ nhờ thêm `@Transactional`. Các manager quản lý những connection/resource và execution context khác nhau.

Nếu phải phối hợp nhiều hệ thống, cân nhắc:
- Outbox pattern.
- Idempotency key.
- Saga/compensating actions.
- Ranh giới transaction rõ ràng.
- Eventual consistency nếu nghiệp vụ cho phép.

Không tạo ảo giác “một transaction” bằng `Mono.zip(jpaWrite, r2dbcWrite)`. Chạy song song cũng không có nghĩa atomicity.

## 8. Backpressure, scheduler và nguồn blocking

### 8.1. Backpressure hữu ích ở đâu?

`Flux` có demand: downstream có thể yêu cầu từng phần tử thay vì ứng dụng giữ toàn bộ kết quả trong RAM. Đó là lợi thế cho những truy vấn trả nhiều hàng.

~~~java
Flux<ItemEntity> items = repository.findAll();

return items
    .filter(item -> item.priceCents() > 0)
    .map(this::toView);
~~~

Tuy vậy, cơ sở dữ liệu có thể không hỗ trợ mọi kiểu demand ở cùng granularity; driver có thể prefetch hoặc buffer dữ liệu. Backpressure không thay thế `LIMIT`, keyset pagination, index và query tuning.

### 8.2. `subscribeOn` khác `publishOn`

- `subscribeOn(scheduler)` chọn execution context lúc subscribe nguồn.
- `publishOn(scheduler)` chuyển execution context cho các operator **phía sau nó** trong pipeline.
- Với nguồn blocking JDBC/JPA, pattern chuẩn là `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- Đặt `publishOn(boundedElastic())` sau khi `Mono.just(jdbcCall())` không sửa được việc JDBC đã chạy eager.

~~~java
// Sai: blocking operation chạy trước khi dựng Publisher.
Mono<ItemView> wrong = Mono.just(legacyJpaService.load(id))
    .publishOn(Schedulers.boundedElastic());

// Đúng: trì hoãn operation, chạy nguồn trên scheduler riêng.
Mono<ItemView> correct = Mono.fromCallable(
        () -> legacyJpaService.load(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 8.3. `boundedElastic` có giới hạn, không phải vô hạn

Với batch gọi JDBC:

~~~java
Flux<ItemView> loadBatch(Flux<Long> ids) {
    return ids.flatMap(
        id -> Mono.fromCallable(
                () -> legacyJpaService.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

`flatMap(..., 8)` chỉ giới hạn concurrency **trong subscription của batch này**. Nó không đặt giới hạn global cho mọi request trong service. Nếu 100 request mỗi request chạy 8 JDBC call, tổng in-flight vẫn có thể cao. Dùng bulkhead/semaphore, Hikari pool và request limit phù hợp.

Khi boundedElastic queue đầy, tác vụ có thể bị reject. Khi DB đã quá tải, tăng thread/connections vô hạn chỉ làm tăng queue và tail latency.

### 8.4. Đừng làm blocking trong R2DBC mapping callback

Đây là code sai dù repository là reactive:

~~~java
return reactiveRepository.findAll()
    .map(row -> blockingRestClient.fetch(row.id()));
~~~

Operator `map` chạy trên thread đang phát tín hiệu và `blockingRestClient.fetch` có thể chặn event-loop. Hoặc dùng WebClient reactive trong `flatMap`, hoặc cô lập operation blocking bằng `fromCallable(...).subscribeOn(boundedElastic())`.

Một pipeline thật sự non-blocking cần kiểm soát **tất cả** các dependency, không chỉ database.

## 9. Ví dụ runnable: Spring WebFlux + Spring Data R2DBC + H2

Demo sử dụng H2 in-memory để không cần Docker/PostgreSQL. H2 phù hợp để học mapping, repository và HTTP contract; benchmark performance phải dùng database/driver production tương ứng vì H2 không phản ánh chính xác network I/O của PostgreSQL.

API minh họa:
- `POST /api/items` tạo item.
- `GET /api/items/{id}` tìm một item, trả 404 khi không thấy.
- `GET /api/items` trả JSON list nhỏ để học semantics; production cần pagination.
- Data access hoàn toàn qua `ReactiveCrudRepository`, không dùng JDBC/JPA.

### 9.1. Cấu trúc project

~~~text
reactive-sql-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/resources/schema.sql
├── src/main/java/com/example/reactivesql/
│   ├── ReactiveSqlApplication.java
│   ├── ItemEntity.java
│   ├── ItemRepository.java
│   ├── CreateItemRequest.java
│   ├── ItemView.java
│   ├── ItemService.java
│   └── ItemController.java
└── src/test/java/com/example/reactivesql/
    └── ItemApiIntegrationTest.java
~~~

### 9.2. pom.xml

Spring Boot `4.0.9` đã phát hành; Boot 4 dùng các starter WebFlux và Data R2DBC riêng. Maven parent quản lý phiên bản Spring, Reactor và `r2dbc-h2`.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-sql-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

Dự án demo **không** thêm `spring-boot-starter-data-jpa` hoặc JDBC driver. Điều này giúp tránh vô tình dùng repository blocking.

### 9.3. application.properties

~~~properties
spring.application.name=reactive-sql-demo

spring.r2dbc.url=r2dbc:h2:mem:///reactive_demo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=

spring.sql.init.mode=always
~~~

`spring.r2dbc.url` khai báo R2DBC ConnectionFactory. `spring.sql.init.mode=always` cho phép Spring Boot chạy `schema.sql` ở startup. Với H2 in-memory, DB được tạo cho mỗi process. Đối với production, dùng migration tool phù hợp; không dùng demo DDL như chiến lược quản lý schema sản xuất.

### 9.4. schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_cents BIGINT NOT NULL
);
~~~

`id` được database sinh tự động. `price_cents` dùng số nguyên để tránh sai số nhị phân khi biểu diễn đơn vị tiền nhỏ nhất; trong nghiệp vụ thực, cần xét đơn vị tiền và currency.

### 9.5. ReactiveSqlApplication.java

~~~java
package com.example.reactivesql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSqlApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSqlApplication.class, args);
    }
}
~~~

### 9.6. ItemEntity.java

~~~java
package com.example.reactivesql;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("items")
public record ItemEntity(
    @Id Long id,
    String name,
    long priceCents
) {}
~~~

Chú ý import `org.springframework.data.annotation.Id`, không phải `jakarta.persistence.Id`. Với Spring Data Relational, property `priceCents` theo mặc định được ánh xạ tới cột `price_cents` qua naming strategy; có thể thêm `@Column("price_cents")` nếu muốn tường minh.

`record` là object immutable. Khi `save(new ItemEntity(null, ...))` thành công, repository phát entity kết quả với `id` mới; dùng object được phát ra thay vì giả định input record bị mutate.

### 9.7. ItemRepository.java

~~~java
package com.example.reactivesql;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ItemRepository
        extends ReactiveCrudRepository<ItemEntity, Long> {
}
~~~

Không có `JpaRepository` hay `CrudRepository` blocking ở đây. Interface này trả các reactive publisher và được Spring Data R2DBC triển khai trên R2DBC driver.

### 9.8. CreateItemRequest.java và ItemView.java

`CreateItemRequest.java`:

~~~java
package com.example.reactivesql;

public record CreateItemRequest(
    String name,
    long priceCents
) {}
~~~

`ItemView.java`:

~~~java
package com.example.reactivesql;

public record ItemView(
    Long id,
    String name,
    long priceCents
) {
    public static ItemView from(ItemEntity entity) {
        return new ItemView(
            entity.id(),
            entity.name(),
            entity.priceCents());
    }
}
~~~

API DTO được tách khỏi persistence entity để schema DB không tự trở thành public contract.

### 9.9. ItemService.java

~~~java
package com.example.reactivesql;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ItemService {

    private final ItemRepository repository;

    public ItemService(ItemRepository repository) {
        this.repository = repository;
    }

    public Mono<ItemView> create(CreateItemRequest request) {
        if (request == null ||
                request.name() == null ||
                request.name().isBlank() ||
                request.priceCents() < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid item"));
        }

        ItemEntity entity = new ItemEntity(
            null, request.name().trim(), request.priceCents());

        return repository.save(entity)
            .map(ItemView::from);
    }

    public Mono<ItemView> find(long id) {
        return repository.findById(id)
            .map(ItemView::from);
    }

    public Flux<ItemView> all() {
        return repository.findAll()
            .map(ItemView::from);
    }
}
~~~

`repository.save` trả `Mono`, còn `findAll` trả `Flux`. Không có `.block()` hoặc `.subscribe()` thủ công. `Mono.error` vẫn là reactive error signal và được WebFlux xử lý thành HTTP 400 khi service được subscribe.

Validation được giữ đơn giản cho demo; production có thể dùng Bean Validation, giới hạn input, error code ổn định và exception handling tập trung.

### 9.10. ItemController.java

~~~java
package com.example.reactivesql;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @RequestBody Mono<CreateItemRequest> request) {

        return request.flatMap(service::create)
            .map(item -> ResponseEntity
                .created(URI.create("/api/items/" + item.id()))
                .body(item));
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> find(
            @PathVariable long id) {

        return service.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<ItemView> all() {
        return service.all();
    }
}
~~~

Controller không thực hiện JDBC và không tự quyết định scheduler. Nó trả `Mono`/`Flux` cho WebFlux để request lifecycle quản lý subscription và cancellation. Với `application/json`, `Flux<ItemView>` có thể được encode thành JSON array; response không nhất thiết flush từng row. Nếu cần stream row theo record, dùng media type hỗ trợ streaming và giới hạn query phù hợp.

### 9.11. ItemApiIntegrationTest.java

Test dùng HTTP server thật (random port), H2 R2DBC và `WebTestClient`. Một test repository riêng dùng `StepVerifier` để xác minh insert rồi query hoàn tất.

~~~java
package com.example.reactivesql;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ItemApiIntegrationTest {

    @Value("${local.server.port}")
    int port;

    @Autowired
    ItemRepository repository;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void createThenReadItemOverHttp() {
        String name = "Book-" + UUID.randomUUID();

        ItemView created = client().post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest(name, 1250))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueMatches(
                "Location", "/api/items/[0-9]+")
            .expectBody(ItemView.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(created);
        assertNotNull(created.id());
        assertEquals(name, created.name());
        assertEquals(1250, created.priceCents());

        client().get()
            .uri("/api/items/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemView.class)
            .value(item -> {
                assertEquals(created.id(), item.id());
                assertEquals(name, item.name());
            });
    }

    @Test
    void missingItemReturnsNotFound() {
        client().get()
            .uri("/api/items/{id}", Long.MAX_VALUE)
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void invalidInputReturnsBadRequest() {
        client().post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest("  ", -1))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void repositoryPublisherPersistsAndReadsReactively() {
        String name = "Repo-" + UUID.randomUUID();

        StepVerifier.create(
            repository.save(new ItemEntity(null, name, 99))
                .flatMap(saved -> repository.findById(saved.id()))
        )
            .assertNext(found -> {
                assertNotNull(found.id());
                assertEquals(name, found.name());
                assertEquals(99, found.priceCents());
            })
            .verifyComplete();
    }
}
~~~

Test dùng kết quả HTTP chứ không giả định database có ID cố định. `StepVerifier` subscribe vào pipeline reactive và kiểm tra phần tử/terminal signal; không có `.block()` trong production classes.

### 9.12. Chạy project

Yêu cầu JDK 17+, Maven 3.6.3+ và network để tải dependency Maven lần đầu.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Tạo item (Windows CMD; dùng dấu `^` nối dòng):

~~~bat
curl -i -X POST http://localhost:8080/api/items ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Notebook\",\"priceCents\":12900}"
~~~

Response minh họa (ID được DB sinh):

~~~http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json

{"id":1,"name":"Notebook","priceCents":12900}
~~~

Đọc item:

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

Danh sách:

~~~bash
curl -i http://localhost:8080/api/items
~~~

Test trạng thái lỗi:

~~~bash
curl -i http://localhost:8080/api/items/999999
~~~

Kết quả kỳ vọng: HTTP 404 cho ID chưa tồn tại. Với dữ liệu không hợp lệ (`name` trống hoặc `priceCents` âm), HTTP 400. Đầu ra và thứ tự ID phụ thuộc dữ liệu đang có; các test không phụ thuộc ID cố định.

### 9.13. Vì sao demo minh chứng R2DBC chứ không chỉ reactive return type?

Kiểm tra dependency:
- Có `spring-boot-starter-data-r2dbc`.
- Có `io.r2dbc:r2dbc-h2`.
- URL bắt đầu bằng `r2dbc:`.
- Repository kế thừa `ReactiveCrudRepository`.
- Method của repository trả `Mono` hoặc `Flux`.
- Không có `JpaRepository`, `JdbcTemplate`, `EntityManager`, `java.sql.Connection` hoặc `.block()` trong code production.

Test chứng minh đường HTTP và persistence hoạt động. Để **đo tính non-blocking/performance thực tế**, cần thêm load test trên database/driver production, thread profiler, database pool metrics và kiểm tra toàn bộ các dependency khác không blocking.

## 10. So sánh cùng một nghiệp vụ ở JDBC, JPA và R2DBC

Giả sử cần tìm item theo ID.

### 10.1. Spring JDBC (blocking)

~~~java
public ItemView findWithJdbc(JdbcClient jdbc, long id) {
    return jdbc.sql("""
            SELECT id, name
            FROM items
            WHERE id = :id
            """)
        .param("id", id)
        .query((rs, rowNum) -> new ItemView(
            rs.getLong("id"),
            rs.getString("name")))
        .optional()
        .orElse(null);
}
~~~

Đây là **fragment minh họa**, dùng kiểu `ItemView(Long id, String name)` của ví dụ so sánh hai field. Cần `spring-boot-starter-jdbc`, JDBC driver và `DataSource`. Lời gọi `query` vẫn chặn.

### 10.2. Spring Data JPA (blocking)

~~~java
public ItemView findWithJpa(ItemJpaRepository repository, long id) {
    return repository.findById(id)
        .map(entity -> new ItemView(
            entity.getId(),
            entity.getName()))
        .orElse(null);
}
~~~

Đây là **fragment minh họa**, dùng `JpaRepository`/entity và transaction phù hợp. JPA mapping/ORM không làm lời gọi `findById` non-blocking.

### 10.3. Spring Data R2DBC (reactive)

~~~java
public Mono<ItemView> findWithR2dbc(
        ItemRepository repository, long id) {

    return repository.findById(id)
        .map(entity -> new ItemView(
            entity.id(), entity.name()));
}
~~~

Đây là **fragment minh họa** hai-field `ItemView` để so sánh cú pháp; demo runnable ở mục 9 dùng `ItemView(Long id, String name, long priceCents)`. Sự khác biệt không chỉ là kiểu trả về: `ItemRepository` phải được backed bởi R2DBC driver, không phải JPA.

### 10.4. Chi phí không tự biến mất

| Bối cảnh | JDBC/JPA | R2DBC |
| --- | --- | --- |
| Query mất 500 ms tại database | Thread blocking đợi I/O | Thread không phải chờ I/O theo mô hình reactive |
| DB chỉ cho 20 connection | Vẫn chỉ 20 connection | Vẫn chỉ 20 connection |
| SQL thiếu index | Vẫn chậm | Vẫn chậm |
| Transaction giữ row lock lâu | Vẫn chặn transaction khác ở DB | Vẫn chặn transaction khác ở DB |
| CPU mapping/JSON lớn | Tốn CPU | Vẫn tốn CPU |
| Repository bị gọi 100.000 lần không giới hạn | Pool/DB quá tải | Pool/DB vẫn quá tải |
| Code có blocking HTTP client khác | Thêm blocking | Pipeline tổng thể vẫn bị blocking |

R2DBC tối ưu việc **sử dụng thread khi chờ kết quả**, không thay thế thiết kế query, index, pool, timeout hoặc giới hạn concurrency.

## 11. Khi migrate từ JPA sang R2DBC

### 11.1. Kiểm kê hiện trạng

Trước khi đổi dependency, liệt kê:
- Những repository nào đang dùng `JpaRepository`/`EntityManager`.
- Entity graph, relationship, lazy loading, cascade, dirty checking.
- JPQL/HQL, Criteria API, query hints và database-specific SQL.
- Transaction boundary và propagation/isolation cần có.
- Auditing, optimistic locking/version column.
- Batch update, pagination, fetch joins, N+1 queries.
- Số request đồng thời, DB connection pool, p95/p99 latency và timeouts.

Không chuyển đổi bằng cách thay `JpaRepository` thành `ReactiveCrudRepository` rồi giữ nguyên entity lifecycle.

### 11.2. Thiết kế lại persistence contract

1. Xác định aggregate root và ranh giới transaction.
2. Chuyển dữ liệu truy cập sang reactive repository/template.
3. Kiểm tra driver có hỗ trợ các loại column/SQL và transaction cần dùng.
4. Tách REST DTO khỏi DB record.
5. Viết explicit query hoặc nhiều operation có composition khi thiếu lazy ORM.
6. Chọn cách tải association một cách rõ ràng.
7. Thay `Page<T>` blocking bằng chiến lược paging phù hợp; dùng LIMIT/keyset để giới hạn bộ nhớ.
8. Thay transaction manager và kiểm tra rollback/cancellation.
9. Thêm integration tests trên DB thật cho critical query.
10. Load test so sánh hiệu quả, không chỉ thời gian một request.

### 11.3. Lộ trình chuyển đổi tăng dần

| Giai đoạn | Làm gì | Rủi ro cần kiểm tra |
| --- | --- | --- |
| 1. Đo baseline | JDBC/JPA latency, Hikari pool, thread dump, CPU | Hiểu nghẽn thật |
| 2. Cô lập legacy | `Mono.fromCallable` + boundedElastic + bulkhead | Không block Netty event-loop |
| 3. Chọn một vertical slice | Một endpoint/query ít quan hệ ORM | Contract và transaction rõ |
| 4. Viết repository R2DBC | Driver, `ReactiveCrudRepository`, `R2dbcEntityTemplate` | Mapping và SQL semantics |
| 5. Chuyển service chain | `Mono`/`Flux`, error và cancellation | Không `.block()`/`.subscribe()` |
| 6. Kiểm tra transaction | `ReactiveTransactionManager`/operator | Rollback và context |
| 7. Kiểm tra production DB | Migrations, indexes, locks, pool | Khác biệt H2 với DB thực |
| 8. Canary và quan sát | p95/p99, throughput, pool, errors | Fail-fast và rollback plan |

Có thể duy trì JDBC/JPA cho một số bounded context và dùng R2DBC cho luồng I/O lớn. Việc trộn stack cần tách bean/transaction và đảm bảo không dùng cùng một transaction giả định xuyên hai công nghệ.

## 12. Những cạm bẫy thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `Mono.just(jpaRepo.findById(id))` | JDBC đã chạy eager | `fromCallable` + `subscribeOn(boundedElastic)` |
| Cho JDBC chạy ngay trong `map`/`flatMap` | Có thể chặn thread xử lý tín hiệu | Offload ở boundary hoặc dùng driver R2DBC |
| Đổi method return type sang `Mono` rồi gọi JPA bên dưới | Reactive wrapper không đổi I/O | Phân biệt bridge với non-blocking end-to-end |
| Dùng `publishOn` sau lời gọi blocking eager | Chuyển thread quá muộn | Dùng lazy source và `subscribeOn` |
| `.block()` trong WebFlux controller | Chặn event-loop | Return publisher |
| `.subscribe()` riêng trong service | Tách lỗi, cancel, transaction khỏi request | Compose và return publisher |
| Dùng `@Transactional` JPA quanh `Mono` | Sai execution/context boundary | Đóng transaction trong service sync hoặc chuyển reactive manager |
| Dùng chung transaction giữa JPA và R2DBC | Không atomic tự động | Tách boundary, outbox/saga |
| Mang lazy JPA entity ra khỏi method | Có thể lỗi lazy initialization/thread | Map DTO trong transaction sync |
| Mong R2DBC có dirty checking/cascade JPA | Khác mapping model | Explicit repository/template operations |
| Không phân trang `findAll()` | Có thể stream lượng dữ liệu khổng lồ | Limit/keyset/paging |
| Tạo connection mới cho mọi item | Pool/DB saturation | Tái sử dụng ConnectionFactory/pool |
| Tăng pool không giới hạn | DB overload, lock contention | Load test và giới hạn tổng connections |
| Retry transaction write vô hạn | Duplicate writes và DB overload | Idempotency và retry budget |
| Kiểm thử chỉ với H2 | Che khác biệt dialect/locking/index | Integration test với production-like DB |
| Log SQL parameters/PII tràn lan | Rò rỉ thông tin | Redact và cấu hình logging an toàn |
| Đánh giá reactive bằng thread name đơn lẻ | Thread có thể thay đổi | Profile/block detector/metrics và end-to-end tests |

## 13. Quan sát và hiệu năng

### 13.1. JDBC/JPA

Theo dõi:
- `hikaricp.connections.active`, `idle`, `pending`, `max` (theo meter registry).
- Thread pool đang chạy các JDBC calls và queue.
- JDBC query duration, transaction duration và connection acquisition time.
- Deadlock/lock wait, slow SQL, DB CPU/IOPS.
- WebFlux/Netty event-loop blocking hoặc latency tăng bất thường.

Thread dump với nhiều `reactor-http-nio-*` đang ở stack `java.sql`/Hibernate là dấu hiệu nguy hiểm.

### 13.2. R2DBC

Theo dõi:
- Active/idle/pending/max connections từ R2DBC pool nếu pool metrics được bật và exporter hỗ trợ.
- R2DBC driver/DB query duration, p95/p99.
- In-flight reactive DB operations và cancellation/timeout.
- Database CPU/IOPS, connection limit, lock wait và slow queries.
- Netty event-loop latency và số blocking call ngoài DB.

Một dịch vụ R2DBC vẫn có thể làm cạn database connections khi concurrency quá cao. Reactive không loại bỏ nhu cầu bulkhead và backpressure.

### 13.3. Chọn workload để benchmark

Chạy ít nhất:
1. **Single request latency:** độ trễ truy vấn đơn.
2. **Steady concurrency:** số request đồng thời vừa phải, p95/p99.
3. **High concurrency:** khi DB wait time tăng; theo dõi thread/connection pools.
4. **Slow query:** mô phỏng DB chậm, xem event-loop còn phản hồi không.
5. **Cancellation:** client hủy request; quan sát connection/transaction cleanup.
6. **Memory and CPU:** heap, direct memory, GC, context switching.

So sánh trong cùng điều kiện SQL, index, DB capacity, số replica và HTTP workload. Nếu R2DBC có throughput cao hơn nhưng DB error/lock wait tăng, đó chưa phải kết quả cải thiện tổng thể.

## 14. Cách lựa chọn trong kiến trúc thực tế

Chọn JDBC/JPA khi:
- Ứng dụng chủ yếu là CRUD nghiệp vụ với ORM relationships/dirty checking phức tạp.
- Đội ngũ đã có nhiều JPA entity và transaction ổn định.
- Concurrency được đáp ứng tốt bằng Spring MVC/HikariCP hoặc boundary blocking có giới hạn.
- Driver reactive của database chưa có hoặc chưa hỗ trợ tính năng quan trọng.

Chọn R2DBC khi:
- WebFlux xử lý nhiều request I/O-bound đồng thời.
- Cần pipeline non-blocking đến relational database.
- Database/driver R2DBC đã được hỗ trợ, vận hành và kiểm thử đầy đủ.
- Mapping/transaction semantics không cần các tính năng JPA ORM hoặc có thể thiết kế lại.
- Team đủ năng lực quản lý publisher, backpressure, cancellation và reactive transaction.

Chọn mô hình lai khi:
- Có một legacy JPA module cần giữ lại.
- Một số endpoint cần reactive DB streaming và scale concurrency.
- Ranh giới transaction, connection pool và scheduler được tách rõ.
- Có kế hoạch loại dần blocking I/O khỏi các critical WebFlux request path.

**Nguyên tắc ra quyết định:** đo bottleneck, chọn đúng abstraction, giữ transaction correctness và test production-like. Không chuyển sang R2DBC chỉ để đổi chữ `Optional` thành `Mono`.

## 15. Bài tập thực hành

1. **Định vị blocking:** trong một WebFlux endpoint, gọi `JpaRepository.findById` trực tiếp và quan sát thread. Chuyển sang `fromCallable(...).subscribeOn(boundedElastic())`, đo sự khác biệt của event-loop responsiveness.
2. **Tìm lỗi Mono.just:** tạo unit test với counter tăng trong blocking method; chứng minh `Mono.just(fn())` gọi ngay nhưng `Mono.fromCallable(fn)` gọi khi subscribe.
3. **R2DBC CRUD:** chạy demo mục 9, POST item mới, GET item vừa tạo, GET ID không có.
4. **Reactive query:** thêm `findByName(String name)` vào `ReactiveCrudRepository`, dùng `Flux`/`Mono` đúng cardinality.
5. **Transaction rollback:** tạo hai thao tác R2DBC liên tiếp trong `TransactionalOperator`, cố tình phát lỗi sau thao tác đầu và kiểm tra rollback.
6. **Lazy loading migration:** chọn một JPA entity có `@ManyToOne`; thiết kế explicit query/DTO R2DBC thay vì kỳ vọng JPA lazy loading tự hoạt động.
7. **Pool saturation:** giới hạn R2DBC pool nhỏ, tăng concurrency và quan sát pending acquire/timeout ở client cùng CPU/connection count ở DB.
8. **Pagination:** thay `findAll()` toàn bảng bằng query có LIMIT và keyset pagination; kiểm tra memory khi bảng có nhiều row.
9. **Mixed stack:** xây `LegacyJpaService` transaction đồng bộ, bọc bằng `LegacyBridge` và giới hạn concurrency. Không tạo transaction giả xuyên JPA + R2DBC.
10. **Benchmark:** so sánh Spring MVC + JPA, WebFlux + JPA offload và WebFlux + R2DBC trên cùng SQL/index/DB, báo cáo p50/p95/p99, throughput, errors, CPU, threads và DB connections.

## 16. Checklist production

- [ ] Đã xác định toàn bộ blocking sources trong WebFlux request path.
- [ ] JDBC/JPA không chạy trực tiếp trên Netty event-loop.
- [ ] Nếu còn blocking DB, dùng lazy Publisher + bounded scheduler và bulkhead hữu hạn.
- [ ] Không gọi `.block()` hoặc `.subscribe()` tùy tiện trong service/controller.
- [ ] Phân biệt `spring.datasource.*` và `spring.r2dbc.*`.
- [ ] Chọn driver R2DBC phù hợp với database và feature cần dùng.
- [ ] Spring Data R2DBC repository thực sự backed by `ConnectionFactory`.
- [ ] Mapping, generated IDs, joins, lazy associations và transaction semantics đã được kiểm tra.
- [ ] JDBC/JPA transaction chỉ ở synchronous boundary; R2DBC transaction ở Reactor Context.
- [ ] Không mặc định transaction atomic giữa JDBC/JPA và R2DBC.
- [ ] Cấu hình DB connection pool, timeout và max concurrent operations.
- [ ] Query lớn có LIMIT/keyset pagination hoặc streaming có giới hạn.
- [ ] SQL migration được quản lý bằng quy trình phù hợp; không phụ thuộc demo schema init.
- [ ] Có integration tests trên production-like database cho critical queries.
- [ ] Có test rollback, cancellation, timeout và data integrity.
- [ ] Observability theo dõi event loop, thread pool, DB pool, DB latency và error rate.
- [ ] Không log PII, credentials hoặc raw SQL parameters thiếu kiểm soát.
- [ ] Có canary/rollback plan nếu migrate từ JPA sang R2DBC.

## 17. Tài liệu tham khảo

1. Spring Framework – R2DBC Data Access, `DatabaseClient`, `R2dbcTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
2. Spring Framework – Transaction management và `TransactionalOperator`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
3. Spring Framework – Declarative transactions (thread-bound vs Reactor Context): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
4. Spring Data Relational – R2DBC reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
5. Spring Data Relational – R2DBC mapping conventions: https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html
6. Spring Boot 4.0 – R2DBC configuration: https://docs.spring.io/spring-boot/4.0/reference/data/sql.html
7. Spring Boot – Schema initialization for `ConnectionFactory`: https://docs.spring.io/spring-boot/how-to/data-initialization.html
8. Spring Boot – Managed dependencies, including R2DBC and WebFlux starters: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
9. Reactor Core – Blocking call bridge with `Mono.fromCallable` and `Schedulers.boundedElastic`: https://projectreactor.io/docs/core/release/reference/
10. R2DBC specification and drivers: https://r2dbc.io/
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Tự kiểm tra:** `Mono.just(jpaRepo.findById(...))` chặn ở thời điểm nào? `boundedElastic` thay đổi chỗ chạy của blocking call hay biến JDBC thành non-blocking? Vì sao transaction JPA dùng ThreadLocal còn transaction R2DBC dùng Reactor Context? Vì sao một entity R2DBC không tự có dirty checking/lazy loading như Hibernate? Khi nào nên giữ Spring MVC + JPA? Nếu bạn trả lời chính xác và chạy được demo R2DBC cùng integration tests, bạn đã hiểu khác biệt thực sự giữa JDBC/JPA blocking và driver dữ liệu reactive.
