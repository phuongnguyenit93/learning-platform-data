# TransactionalOperator, @Transactional reactive và cùng một chuỗi thực thi

## 1. Bài toán: nhiều thao tác, một transaction

Một nghiệp vụ có thể cần cập nhật nhiều bản ghi theo nguyên tắc tất cả cùng thành công hoặc tất cả cùng thất bại. Ví dụ, khi tạo đơn hàng phải ghi vào hai bảng:

1. `purchase_orders` lưu đơn hàng.
2. `audit_events` lưu lịch sử tạo đơn.

Nếu INSERT đơn hàng thành công rồi INSERT audit thất bại, ứng dụng cần **rollback cả hai**. Transaction database cung cấp ranh giới commit/rollback để giữ dữ liệu nhất quán.

Trong Spring WebFlux, Spring Data R2DBC và Project Reactor, phương thức repository thường trả `Mono<T>` hoặc `Flux<T>`. Publisher chỉ mô tả công việc; SQL thật sự bắt đầu khi Publisher được **subscribe**. Vì vậy transaction reactive phải bao quanh **subscription và reactive pipeline**, không chỉ bao quanh vài dòng Java xây dựng Publisher.

Spring hỗ trợ:

- `@Transactional`: declarative transaction bằng Spring AOP proxy cho method trả reactive Publisher.
- `TransactionalOperator`: programmatic transaction, bọc `Mono/Flux` hoặc dùng callback `execute`.

**Nguyên tắc trung tâm:** tất cả thao tác muốn cùng transaction phải thuộc một chuỗi Publisher được trả về, cùng Reactor subscriber Context và cùng resource manager (ví dụ một R2DBC ConnectionFactory).

### Mục tiêu học tập

Sau bài này, bạn sẽ:

- Phân biệt `ReactiveTransactionManager` và `PlatformTransactionManager`.
- Hiểu transaction reactive dùng **Reactor Context** thay vì ThreadLocal.
- Viết `@Transactional` cho method trả `Mono` hoặc `Flux` đúng cách.
- Dùng `TransactionalOperator.create(...)`, `.as(operator::transactional)` và `execute(...)`.
- Đặt transaction boundary để các bước INSERT, UPDATE cùng commit/rollback.
- Xử lý error, `onErrorResume`, cancel, `take`, timeout và retry đúng.
- Triển khai và kiểm thử trên Spring Boot 3.5.7, Java 17, H2 R2DBC.
- Biết giới hạn của database transaction khi kết hợp HTTP, Kafka và nhiều resource khác nhau.

## 2. Cơ chế reactive transaction

### 2.1. Transaction manager và resource

| Tiêu chí | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Interface | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Ví dụ | `DataSourceTransactionManager`, `JpaTransactionManager` | `R2dbcTransactionManager` |
| State | Thread-bound, thường dùng ThreadLocal | Subscriber-bound, dùng Reactor Context |
| Công nghệ truy cập | JDBC/JPA | R2DBC, reactive driver tương thích |
| Cách khai báo | `@Transactional`/`TransactionTemplate` | `@Transactional`/`TransactionalOperator` |
| Kích hoạt | Khi method imperative chạy | Khi Publisher được subscribe |

`R2dbcTransactionManager` quản lý R2DBC `Connection` lấy từ `ConnectionFactory`. Spring bind connection transaction-bound vào subscriber Context; `DatabaseClient` và Spring Data R2DBC có thể dùng đúng connection đó trong chuỗi reactive.

Nếu một phương thức tự dùng `ConnectionFactories.get(...)` để mở connection khác, hoặc gọi `JdbcTemplate`, thao tác ấy **không tự tham gia** transaction R2DBC hiện tại.

### 2.2. Transaction dùng Reactor Context, không phải ThreadLocal

~~~text
Caller subscribes
       |
       v
  TransactionInterceptor / TransactionalOperator
       |
       +-- begin transaction
       |      |
       |      v
       |  R2DBC Connection bound in Reactor Context
       |      |
       |      +--> INSERT purchase_orders
       |      |
       |      +--> INSERT audit_events
       |
       +-- onComplete --> COMMIT
       |
       +-- onError ----> ROLLBACK
       |
       +-- cancel -----> ROLLBACK
       |
       v
   cleanup resource
~~~

Reactor Context đi theo subscriber và được truyền qua các operator tương thích. Đổi thread bằng `publishOn` hoặc `subscribeOn` **không tự làm mất** Context nếu vẫn ở cùng pipeline. Tuy nhiên, gọi `subscribe()` nội bộ tạo một subscriber độc lập, có thể chạy ngoài transaction của caller.

Không thể kiểm tra transaction reactive bằng cách chỉ nhìn một biến ThreadLocal ở cùng thread.

### 2.3. Transaction bắt đầu khi subscribe

~~~java
Mono<Void> work = store.insertOrder(1L, "Linh")
    .then(store.insertAudit(1L, "CREATED"));

Mono<Void> transactional =
    work.as(operator::transactional);
~~~

Code trên mới tạo Publisher. Khi caller subscribe `transactional`, manager begin transaction; các câu SQL được thực thi; khi Publisher kết thúc, manager commit hoặc rollback.

Hệ quả:

- Gọi method tạo Mono chưa đồng nghĩa SQL đã chạy.
- Mỗi subscription mới có thể tạo transaction mới và thực thi lại side effect.
- `retry` và `repeat` có thể gây INSERT trùng nếu thiếu idempotency.
- Transaction cần nguồn hoàn tất; không nên giữ một transaction quanh `Flux` vô hạn.
- Khi Publisher phát item nhưng chưa complete, điều đó chưa chứng minh dữ liệu đã commit.

### 2.4. Phạm vi resource

Database transaction điều phối những resource của manager tương ứng. `R2dbcTransactionManager` không thể rollback một HTTP request đã gửi bằng `WebClient`, email đã phát hoặc message Kafka đã publish. Muốn đảm bảo nghiệp vụ xuyên hệ thống, cân nhắc transactional outbox, saga, retry và idempotency.

## 3. @Transactional reactive

### 3.1. Cú pháp phổ biến

~~~java
@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    @Transactional
    public Mono<Long> create(long id, String customer) {
        return store.insertOrder(id, customer)
            .then(store.insertAudit(id, "CREATED"))
            .thenReturn(id);
    }
}
~~~

Spring `TransactionInterceptor` kiểm tra kiểu trả về. Nếu method được gọi qua proxy và cấu hình một `ReactiveTransactionManager`, Spring decorate Publisher với transaction boundary. Một subscriber sau đó mới kích hoạt logic bên trong transaction.

### 3.2. Return type phải reactive

Với manager reactive, method nên trả `Mono<T>`, `Flux<T>`, `Mono<Void>` hoặc một reactive type tương thích. Method `void` hay return DTO đồng bộ không cung cấp reactive pipeline để Spring quản lý; kiểu đó yêu cầu nhánh imperative và `PlatformTransactionManager` phù hợp.

Ví dụ sai:

~~~java
@Transactional
public void createWrong(long id) {
    store.insertOrder(id, "Linh").subscribe();
}
~~~

Method trả `void` và subscribe nội bộ. Nó không thiết lập reactive transaction như mong đợi. Cách đúng là trả Publisher cho caller hoặc framework.

### 3.3. Spring AOP proxy và self-invocation

`@Transactional` trong proxy mode chỉ intercept lời gọi **đi qua Spring proxy**. Nếu một bean gọi chính method annotated của nó, annotation trên method đích có thể không có tác dụng:

~~~java
@Service
public class BadService {

    public Mono<Void> outer() {
        return inner(); // this.inner(): bypasses proxy
    }

    @Transactional
    public Mono<Void> inner() {
        return doReactiveDatabaseWork();
    }
}
~~~

Khắc phục bằng cách đặt transaction trên public service method được bean khác gọi, tách transactional method sang service bean riêng, hoặc dùng `TransactionalOperator` tại nơi kết hợp Publisher. Không kỳ vọng private method được Spring AOP intercept.

### 3.4. Default và rollback rules

Mặc định `@Transactional` có `Propagation.REQUIRED`, `Isolation.DEFAULT`, read-write, timeout theo transaction system và rollback đối với `RuntimeException`/`Error`. Checked exception không mặc định kích hoạt rollback; có thể chỉ định `rollbackFor`.

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    rollbackFor = IOException.class
)
public Mono<Void> update(...) {
    return store.update(...);
}
~~~

Đây là đoạn minh họa một method khác, không phải file độc lập chạy ngay. Isolation, timeout và propagation phải được driver/manager hỗ trợ. Spring Framework 6.2 có tùy chọn toàn cục `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` nếu ứng dụng chủ động cấu hình.

`@Transactional(readOnly = true)` là hint/setting; khả năng cấm thao tác ghi phụ thuộc backend, không thay thế authorization.

## 4. TransactionalOperator: programmatic transaction

### 4.1. Tạo bean

~~~java
@Configuration(proxyBeanMethods = false)
public class TxConfig {

    @Bean
    TransactionalOperator transactionalOperator(
        ReactiveTransactionManager manager
    ) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Package đúng là `org.springframework.transaction.reactive.TransactionalOperator`. Spring khuyến nghị `TransactionTemplate` cho imperative code và `TransactionalOperator` cho reactive code.

### 4.2. Operator style: đặt boundary đúng vị trí

~~~java
Mono<Long> businessWork = store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .thenReturn(id);

return businessWork.as(operator::transactional);
~~~

`.as(operator::transactional)` bọc Publisher phía upstream. Cả hai INSERT đều chạy bên trong transaction.

Sai:

~~~java
return store.insertOrder(id, customer)
    .as(operator::transactional)
    .then(store.insertAudit(id, "CREATED"));
~~~

Trong ví dụ sai, transaction chỉ bao quanh INSERT đầu; audit nằm sau transactional Publisher và không tham gia ranh giới đó. Nếu audit thất bại, đơn hàng có thể đã commit.

Đúng:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);
~~~

### 4.3. Callback style: execute

`execute` cho phép dùng `ReactiveTransaction` để kiểm soát trạng thái transaction:

~~~java
Flux<Long> result = operator.execute(status ->
    store.insertOrder(id, customer)
        .then(store.insertAudit(id, "CREATED"))
        .thenReturn(id)
);
~~~

`execute` trả `Flux<T>` kể cả khi callback chỉ phát một item. Nếu chắc chắn chỉ có một item, có thể chuyển thành Mono bằng:

~~~java
Mono<Long> result = operator.execute(status ->
    store.insertOrder(id, customer).thenReturn(id)
).single();
~~~

Không dùng `single()` nếu Publisher có thể hoàn tất rỗng. Cẩn thận với `next()` vì nó có thể cancel sau item đầu, kích hoạt rollback thay vì commit.

### 4.4. Đánh dấu rollback-only

~~~java
Flux<String> outcome = operator.execute(status ->
    store.insertOrder(id, customer)
        .then(Mono.fromSupplier(() -> {
            status.setRollbackOnly();
            return "không commit vì chính sách nghiệp vụ";
        }))
);
~~~

`status.setRollbackOnly()` yêu cầu rollback dù callback không phát lỗi. Với business error thông thường, phát `Mono.error(new BusinessException(...))` có thể làm luồng xử lý rõ ràng hơn.

### 4.5. TransactionDefinition

~~~java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(10);

TransactionalOperator operator =
    TransactionalOperator.create(manager, definition);
~~~

Không phải mọi R2DBC driver hỗ trợ mọi isolation/propagation như nhau. Cần kiểm thử trên đúng database production.

### 4.6. Chọn annotation hay operator?

| Tiêu chí | `@Transactional` | `TransactionalOperator` |
| --- | --- | --- |
| Cấu hình | Declarative | Programmatic |
| Cần proxy | Có, ở proxy mode | Không |
| Boundary | Bao quanh Publisher trả từ method | Bọc rõ một đoạn Publisher |
| Rollback-only callback | Không trực tiếp qua annotation | Có `execute(status -> ...)` |
| Hữu ích khi | Service method nghiệp vụ | Workflow compose nhiều đoạn và cần kiểm soát boundary |
| Dễ mắc lỗi | Self-invocation và sai return type | Đặt `.as(...)` quá sớm |

Tránh bọc cùng một đoạn bằng cả annotation và operator chỉ vì “muốn an toàn hơn”; nested transaction boundaries có thể làm propagation và rollback-only khó hiểu hơn.

## 5. Cùng một chuỗi thực thi: đúng và sai

### 5.1. Dùng then để ghép Mono<Void>

~~~java
public Mono<Void> create(long id, String customer) {
    return store.insertOrder(id, customer)
        .then(store.insertAudit(id, "CREATED"))
        .as(operator::transactional);
}
~~~

`then` đợi INSERT đầu hoàn tất rồi mới bắt đầu INSERT thứ hai. Cả hai publisher được ghép trong cùng subscriber transaction context.

Sai:

~~~java
public Mono<Void> createWrong(long id, String customer) {
    store.insertOrder(id, customer).subscribe(); // detached subscriber
    return store.insertAudit(id, "CREATED")
        .as(operator::transactional);
}
~~~

Lệnh đầu chạy trên subscription độc lập; lỗi/rollback của audit không rollback được nó.

### 5.2. Mono<Void>.flatMap không chạy callback

~~~java
// SAI: Mono<Void> hoàn tất không có onNext
return store.insertOrder(id, customer)
    .flatMap(ignored -> store.insertAudit(id, "CREATED"));
~~~

`flatMap` chỉ chạy trên onNext, trong khi `Mono<Void>` hoàn tất rỗng. Vì vậy audit không chạy. Dùng `then`:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"));
~~~

Khi bước đầu trả một ID thực tế, `flatMap` lại phù hợp:

~~~java
return store.createAndReturnId(customer)
    .flatMap(id -> store.insertAudit(id, "CREATED")
        .thenReturn(id))
    .as(operator::transactional);
~~~

### 5.3. Nhiều thao tác tuần tự

Một R2DBC connection transaction-bound thường không nên chạy nhiều SQL statement đồng thời khi driver/connection không hỗ trợ. Với các command có thứ tự, dùng `concatMap`:

~~~java
return Flux.fromIterable(commands)
    .concatMap(store::applyCommand)
    .then()
    .as(operator::transactional);
~~~

`flatMap` có thể chạy đồng thời và đảo thứ tự. Với thao tác phụ thuộc, hãy bảo đảm thứ tự hoặc giảm concurrency phù hợp.

### 5.4. Publisher phải là lazy

~~~java
return Mono.defer(() -> store.insertOrder(id, customer))
    .then(Mono.defer(() -> store.insertAudit(id, "CREATED")))
    .as(operator::transactional);
~~~

`Mono.defer` tạo source tại lúc subscription; không chạy code tạo side effect từ trước rồi mới bọc transaction. Không lấy một hot Publisher đã chạy bên ngoài để kỳ vọng operator “quay lại” bao quanh tác vụ đã xảy ra.

### 5.5. Đổi scheduler không tự làm mất Context

~~~java
return store.insertOrder(id, customer)
    .publishOn(Schedulers.parallel())
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);
~~~

Trong cùng Reactor chain, subscriber Context có thể được truyền qua scheduler. Nhưng việc gọi JDBC blocking trên scheduler này không biến JDBC thành resource của R2DBC transaction. Không dùng ThreadLocal để kiểm tra transaction reactive.

### 5.6. Subscribe hai lần là hai lần thực thi

~~~java
Mono<Void> operation = store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);

operation.subscribe();
operation.subscribe(); // potentially duplicate INSERT
~~~

Đây là code **không nên dùng** trong service. Mỗi subscription có thể tạo transaction mới. Để framework/caller quản lý subscription và thiết kế idempotency khi retry hoặc restart.

## 6. Error, recovery, cancel và retry

### 6.1. Error signal làm rollback

~~~java
return store.insertOrder(id, customer)
    .then(Mono.error(
        new IllegalStateException("audit failed")))
    .as(operator::transactional);
~~~

Sau khi insert đầu complete, onError xảy ra bên trong boundary. Manager rollback transaction; caller nhận error signal.

### 6.2. onErrorResume bên trong boundary có thể commit

~~~java
// SAI: nuốt lỗi trước khi TransactionalOperator nhìn thấy nó
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .onErrorResume(ex -> Mono.empty())
    .as(operator::transactional);
~~~

Lỗi được biến thành onComplete bên trong transaction. Operator có thể commit phần INSERT đã chạy.

Nếu muốn rollback rồi mới trả fallback:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional)
    .onErrorResume(ex -> {
        // Transaction has already observed the error.
        return Mono.empty();
    });
~~~

Hoặc phát lại `Mono.error(ex)` từ nhánh xử lý bên trong. Nếu chủ động muốn rollback mà vẫn trả một kết quả, dùng callback `execute` và `setRollbackOnly()`.

### 6.3. Cancel signal cũng rollback

Spring Framework 5.3+ rollback reactive transaction khi subscription bị cancel. Các operator downstream như `take(n)`, `next()`, `timeout(Duration)` hoặc caller dispose có thể phát cancellation.

~~~java
Flux<Event> transactionalStream =
    store.findAndUpdateAll()
        .as(operator::transactional);

Mono<Event> first = transactionalStream.next();
~~~

`next()` có thể cancel Flux sau item đầu, khiến transaction rollback. Một item đã emit không chứng minh commit. Với Flux transaction, thường phải để source **complete hoàn toàn** để commit.

### 6.4. Không giữ transaction quanh stream vô hạn

~~~java
// Anti-pattern: không nên dùng transaction dài hạn này
@Transactional
public Flux<Event> forever() {
    return eventSource.events();
}
~~~

Nếu stream không complete, transaction giữ connection và có thể giữ lock lâu; cuối cùng bị cancel rồi rollback. Đúng hơn là chia transaction hữu hạn cho từng item hoặc batch:

~~~java
return eventSource.events()
    .concatMap(event ->
        store.persist(event).as(operator::transactional));
~~~

Đây là đoạn minh họa, yêu cầu `store.persist` trả Publisher tương ứng. Trong production, giới hạn throughput và xác định semantics nhận trùng.

### 6.5. Retry đặt ngoài boundary

~~~java
return performWork()
    .as(operator::transactional)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    );
~~~

Đặt retry ngoài boundary có thể tạo transaction mới cho từng attempt. Nếu retry bên trong transaction, một phần công việc có thể chạy lại khi transaction/connection đã bị lỗi. Chỉ retry lỗi transient, giới hạn attempts, deadline và bảo đảm idempotency.

### 6.6. Timeout và side effect

`timeout` có thể cancel transaction trong lúc chờ kết quả. Nếu đã gọi HTTP bên ngoài database transaction, side effect HTTP vẫn có thể đã hoàn thành dù database rollback. Không dùng timeout làm bằng chứng “chưa có gì xảy ra”.

## 7. Propagation, isolation và hệ sinh thái dữ liệu

- `REQUIRED`: tham gia transaction hiện tại khi có thể, hoặc tạo mới.
- `REQUIRES_NEW`: yêu cầu transaction độc lập, phụ thuộc manager/driver hỗ trợ.
- `SUPPORTS`: tham gia nếu có transaction.
- `MANDATORY`: yêu cầu transaction đang tồn tại.
- `NOT_SUPPORTED`: chạy ngoài transaction khi manager có khả năng suspend.

Các mức isolation như `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` có hành vi tùy database. Đừng sao chép assumptions từ JPA sang R2DBC mà không kiểm thử.

`DatabaseClient`, `R2dbcEntityTemplate` và `ReactiveCrudRepository` có thể tham gia R2DBC transaction khi dùng cùng ConnectionFactory và framework integration phù hợp. `JdbcTemplate`, `JpaRepository` hay `ReactiveMongoTransactionManager` sử dụng resource khác, không tự được gộp vào một R2DBC transaction.

Một transaction R2DBC không bao phủ `WebClient`, Kafka, email, object storage hay database khác. Nếu cần đồng bộ dữ liệu DB và message, hãy dùng **transactional outbox**: ghi record nghiệp vụ và outbox trong cùng transaction, rồi worker publish sau commit; consumer xử lý idempotent. Với workflow nhiều dịch vụ, cân nhắc **saga/compensation** thay vì giả định distributed ACID.

## 8. Ví dụ hoàn chỉnh: Spring Boot 3.5.7 + Java 17 + R2DBC H2

Project tạo đơn hàng và audit trong cùng transaction. Hai cách gọi được kiểm thử: `@Transactional` và `TransactionalOperator`. Khi bước audit phát lỗi, order đầu tiên phải rollback.

### 8.1. Cấu trúc project

~~~text
reactive-tx-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── schema.sql
├── src/main/java/example/tx/
│   ├── ReactiveTxApplication.java
│   ├── ReactiveTxConfig.java
│   ├── PurchaseStore.java
│   └── PurchaseService.java
└── src/test/java/example/tx/
    └── PurchaseTransactionTest.java
~~~

### 8.2. pom.xml

~~~xml
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

    <groupId>example</groupId>
    <artifactId>reactive-tx-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Starter R2DBC cung cấp Spring Data R2DBC và DatabaseClient. `r2dbc-h2` cung cấp driver in-memory. Starter AOP cho thấy rõ dependency proxy cần thiết cho ví dụ annotation.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.sql.init.mode=always
~~~

`spring.sql.init.mode=always` chạy `schema.sql` khi Boot khởi động; H2 options giữ database in-memory khi các connection ngắn hạn đóng. Đây là ví dụ học tập, không phải cấu hình database production.

### 8.4. schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS purchase_orders (
    id BIGINT PRIMARY KEY,
    customer VARCHAR(160) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    order_id BIGINT PRIMARY KEY,
    action VARCHAR(80) NOT NULL
);
~~~

### 8.5. ReactiveTxApplication.java

~~~java
package example.tx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
~~~

### 8.6. ReactiveTxConfig.java

~~~java
package example.tx;

import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration(proxyBeanMethods = false)
public class ReactiveTxConfig {

    @Bean
    public ReactiveTransactionManager transactionManager(
        ConnectionFactory connectionFactory
    ) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    public TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager
    ) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring Boot có thể auto-configure R2DBC manager khi ứng dụng chưa khai báo; ví dụ tạo bean tường minh để dễ thấy manager sử dụng cùng ConnectionFactory. `TransactionalOperator` là bean có thể được chia sẻ giữa nhiều service.

### 8.7. PurchaseStore.java

~~~java
package example.tx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class PurchaseStore {

    private final DatabaseClient db;

    public PurchaseStore(DatabaseClient db) {
        this.db = db;
    }

    public Mono<Void> insertOrder(long id, String customer) {
        return db.sql(
                "INSERT INTO purchase_orders(id, customer) " +
                "VALUES (:id, :customer)"
            )
            .bind("id", id)
            .bind("customer", customer)
            .fetch().rowsUpdated().then();
    }

    public Mono<Void> insertAudit(long id, String action) {
        return db.sql(
                "INSERT INTO audit_events(order_id, action) " +
                "VALUES (:id, :action)"
            )
            .bind("id", id)
            .bind("action", action)
            .fetch().rowsUpdated().then();
    }

    public Mono<Long> countOrders(long id) {
        return db.sql(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = :id"
            )
            .bind("id", id)
            .map((row, metadata) ->
                ((Number) row.get(0)).longValue())
            .one();
    }

    public Mono<Long> countAudits(long id) {
        return db.sql(
                "SELECT COUNT(*) FROM audit_events WHERE order_id = :id"
            )
            .bind("id", id)
            .map((row, metadata) ->
                ((Number) row.get(0)).longValue())
            .one();
    }
}
~~~

`rowsUpdated().then()` tạo Mono<Void> hoàn tất khi câu INSERT thực hiện xong. `DatabaseClient` do Boot tạo sẽ dùng ConnectionFactory tương ứng với transaction manager. SQL sử dụng bind parameters thay vì nối input trực tiếp vào chuỗi.

### 8.8. PurchaseService.java

~~~java
package example.tx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PurchaseService {

    private final PurchaseStore store;
    private final TransactionalOperator tx;

    public PurchaseService(
        PurchaseStore store,
        TransactionalOperator tx
    ) {
        this.store = store;
        this.tx = tx;
    }

    @Transactional
    public Mono<Long> createAnnotated(
        long id, String customer, boolean failAudit
    ) {
        return savePair(id, customer, failAudit);
    }

    public Mono<Long> createProgrammatic(
        long id, String customer, boolean failAudit
    ) {
        return savePair(id, customer, failAudit)
            .as(tx::transactional);
    }

    private Mono<Long> savePair(
        long id, String customer, boolean failAudit
    ) {
        return store.insertOrder(id, customer)
            .then(Mono.defer(() ->
                failAudit
                    ? Mono.<Void>error(new IllegalStateException(
                        "simulated audit failure"))
                    : store.insertAudit(id, "CREATED")
            ))
            .thenReturn(id);
    }
}
~~~

`savePair` chỉ là helper lắp ráp Publisher. Trong case fail, nó INSERT order rồi phát error; annotation/operator ở method bên ngoài phải rollback. Không có `subscribe()` hay `block()` nội bộ.

### 8.9. PurchaseTransactionTest.java

~~~java
package example.tx;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class PurchaseTransactionTest {

    @Autowired
    PurchaseService service;

    @Autowired
    PurchaseStore store;

    @Test
    void annotationCommitsBothWrites() {
        StepVerifier.create(
                service.createAnnotated(1001L, "Linh", false))
            .expectNext(1001L)
            .verifyComplete();

        assertCounts(1001L, 1L, 1L);
    }

    @Test
    void annotationRollsBackBothWritesOnError() {
        StepVerifier.create(
                service.createAnnotated(1002L, "An", true))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException &&
                error.getMessage().contains("simulated audit failure"))
            .verify();

        assertCounts(1002L, 0L, 0L);
    }

    @Test
    void operatorCommitsBothWrites() {
        StepVerifier.create(
                service.createProgrammatic(2001L, "Binh", false))
            .expectNext(2001L)
            .verifyComplete();

        assertCounts(2001L, 1L, 1L);
    }

    @Test
    void operatorRollsBackBothWritesOnError() {
        StepVerifier.create(
                service.createProgrammatic(2002L, "Hoa", true))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException &&
                error.getMessage().contains("simulated audit failure"))
            .verify();

        assertCounts(2002L, 0L, 0L);
    }

    private void assertCounts(
        long id, long expectedOrders, long expectedAudits
    ) {
        StepVerifier.create(store.countOrders(id))
            .expectNext(expectedOrders)
            .verifyComplete();

        StepVerifier.create(store.countAudits(id))
            .expectNext(expectedAudits)
            .verifyComplete();
    }
}
~~~

Test gọi service Spring bean để proxy `@Transactional` có cơ hội intercept. Mỗi test dùng ID riêng tránh xung đột. Sau khi Publisher kết thúc, test query DB **ngoài transaction** và so sánh số bản ghi: commit = 1/1, rollback = 0/0.

### 8.10. Cách chạy

Cài JDK 17+ và Maven, sau đó:

~~~bash
mvn test
~~~

Kết quả dự kiến: 4 integration tests pass và Maven in `BUILD SUCCESS`. Đây là kỳ vọng từ cấu trúc project, **không phải output đã thực thi trong bài viết**.

Có thể chạy process Spring:

~~~bash
mvn spring-boot:run
~~~

Do `spring.main.web-application-type=none`, project không tạo HTTP endpoint. Muốn thử luồng nghiệp vụ, dùng integration tests hoặc runner thích hợp; không sử dụng curl tới URL chưa tồn tại.

## 9. Kiểm thử transaction và tình huống nâng cao

### 9.1. Error không đủ chứng minh rollback

Một rollback test phải chứng minh cả error signal lẫn database state. Thứ tự kiểm tra:

1. Publisher phát lỗi như dự kiến.
2. Boundary đã hoàn tất xử lý rollback.
3. Query mới ngoài transaction không thấy order đã insert.
4. Không thấy audit bị ghi dở.

Trong ví dụ, `assertCounts(id, 0L, 0L)` là hậu điều kiện quan trọng. Nếu chỉ assert `expectError`, transaction có thể đã thiết kế sai nhưng test vẫn xanh.

### 9.2. Lỗi SQL thật

Có thể viết thêm test tạo duplicate primary key của `audit_events.order_id` để driver phát data-access exception. Sau lỗi thứ hai, transaction phải rollback cả INSERT đầu. Khi dùng H2/PostgreSQL, exception message và class wrapper có thể khác nhau; tránh assert chuỗi thông báo driver quá cụ thể.

### 9.3. @DataR2dbcTest không tự transactional

Khác với nhiều test JDBC/JPA, Spring Boot `@DataR2dbcTest` mặc định **không transactional**. Để test transaction service thực tế, dùng `@SpringBootTest` hoặc tự cấu hình đúng service, manager và Publisher, rồi truy vấn kết quả sau khi hoàn tất.

Không đặt `@Transactional` trên test chỉ để mặc nhiên có rollback và xem đó là bằng chứng rằng transaction tại service hoạt động.

### 9.4. Reactive TransactionSynchronizationManager

`org.springframework.transaction.reactive.TransactionSynchronizationManager` khác với class imperative `org.springframework.transaction.support.TransactionSynchronizationManager`. Có thể dùng nó để debug transaction state của subscriber khi thực sự cần. Không nhúng transaction internals vào business code nếu annotation/operator đã đủ.

## 10. Lỗi phổ biến

**1. Dùng PlatformTransactionManager cho R2DBC.** Reactive pipeline cần `ReactiveTransactionManager`.

**2. Nghĩ gọi method trả Mono đã chạy transaction.** Transaction chỉ kích hoạt khi subscribe.

**3. Self-invocation @Transactional.** Lời gọi không đi qua Spring proxy thì annotation có thể không được áp dụng.

**4. Đánh dấu @Transactional trên private/void method.** Proxy và return type không phù hợp reactive transaction.

**5. Gọi subscribe() trong service.** Subscription độc lập có thể tách khỏi transaction và che giấu lỗi.

**6. Gọi block() trong event loop.** Có nguy cơ blocking và làm sai cách compose reactive.

**7. Bọc .as(...) trước thao tác cuối.** Thao tác sau boundary không được rollback cùng phần trước.

**8. flatMap sau Mono<Void>.** Mono<Void> không emit onNext; dùng then.

**9. Nuốt lỗi bằng onErrorResume trong transaction.** Operator có thể thấy complete và commit phần trước.

**10. Dùng next()/take(n) trên Flux transactional và kỳ vọng commit.** Cancel có thể gây rollback.

**11. Transaction bao quanh Flux vô hạn.** Connection/lock giữ quá lâu; chia transaction hữu hạn.

**12. Concurrent flatMap chạy SQL trên một connection.** Có thể gây lỗi driver hoặc sai thứ tự; dùng concatMap khi cần.

**13. Trộn JDBC/JPA và R2DBC.** Chúng không tự tham gia cùng một transaction context.

**14. Dùng hai ConnectionFactory khác nhau.** Resource manager không tự điều phối chung.

**15. Retry không có idempotency.** Re-subscription có thể gây side effect trùng.

**16. Cho rằng readOnly là lệnh cấm ghi.** Hành vi phụ thuộc database và driver.

**17. Cho rằng R2DBC rollback được WebClient/Kafka.** Cần outbox, saga hoặc consistency policy khác.

**18. Test chỉ nhìn error mà không query DB.** Không chứng minh atomicity.

**19. Không kiểm tra isolation/propagation thực tế.** Driver/manager có thể không hỗ trợ đầy đủ.

**20. Bọc cả annotation và operator không có chủ đích.** Nested boundary gây khó hiểu rollbackOnly/propagation.

**21. Dùng hot Publisher chạy trước boundary.** Side effect có thể đã xảy ra trước subscribe transaction.

**22. Giữ DB transaction chờ HTTP lâu.** Tăng contention và connection pool pressure.

## 11. Checklist production

1. Repository là R2DBC hay JDBC? Manager có đúng loại không?
2. Annotation được gọi qua proxy không?
3. Method trả Mono/Flux thay vì void/DTO đồng bộ?
4. Các thao tác DB nằm trong cùng returned Publisher?
5. Có subscribe() nội bộ tạo subscriber độc lập không?
6. Các repository dùng cùng ConnectionFactory/transaction manager không?
7. then/concatMap có đảm bảo trình tự khi cần không?
8. TransactionalOperator đặt sau toàn bộ công việc cần atomicity?
9. onErrorResume có thể chuyển error thành commit ngoài ý muốn không?
10. Có quản lý cancel/timeout và hiểu rollback do cancel không?
11. Flux transactional có hữu hạn và hoàn tất không?
12. Retry có giới hạn, phân loại transient và idempotency?
13. Isolation/propagation/readOnly có được test trên DB production không?
14. Có remote side effect nào nằm ngoài transaction cần outbox không?
15. Integration tests có xác minh DB state sau commit/rollback không?
16. Đã giám sát transaction duration, rollback rate, connection pool và lock contention chưa?
17. Có migration schema, timeout và pool sizing phù hợp chưa?

## 12. Câu hỏi ôn tập

1. Reactive transaction bắt đầu lúc tạo Mono hay subscribe? **Lúc subscribe.**
2. Manager reactive dùng ThreadLocal hay Reactor Context? **Reactor Context.**
3. R2dbcTransactionManager quản lý resource nào? **R2DBC Connection.**
4. Vì sao @Transactional cần Spring proxy? **AOP interceptor quản lý boundary qua proxy.**
5. Self-invocation xảy ra khi nào? **Method trong cùng object gọi method annotated mà bỏ qua proxy.**
6. Return type phù hợp reactive manager? **Mono/Flux hoặc Publisher tương thích.**
7. Dùng operator style thế nào? **`publisher.as(operator::transactional)`.**
8. `execute` trả loại Publisher nào? **Flux<T>.**
9. Cách đánh dấu rollback-only trong callback? **`status.setRollbackOnly()`.**
10. Đặt `as` trước audit gây gì? **Audit nằm ngoài transaction đã bọc.**
11. Vì sao Mono<Void>.flatMap không chạy? **Mono<Void> không emit onNext.**
12. Khi nào dùng then? **Khi đợi một Publisher hoàn tất rồi mới thực hiện bước tiếp.**
13. publishOn có tự xóa Reactor Context không? **Không khi vẫn nằm trong cùng chain.**
14. Subscribe() nội bộ nguy hiểm vì sao? **Tạo subscription tách lifecycle/context.**
15. onErrorResume trước operator có thể gây gì? **Biến error thành completion và commit phần trước.**
16. Cancel transaction reactive Spring 5.3+ dẫn đến gì? **Rollback.**
17. Nên giữ transaction trên Flux vô hạn không? **Không.**
18. Retry ngoài boundary có thể làm gì? **Tạo transaction mới cho mỗi attempt.**
19. R2DBC transaction có rollback HTTP request không? **Không.**
20. Mẫu phổ biến để liên kết DB commit và message publication? **Transactional outbox + idempotent consumer.**
21. Test rollback có cần đọc DB sau transaction không? **Có, để xác minh state đã rollback.**
22. @DataR2dbcTest mặc định có transactional không? **Không.**

## 13. Kết luận và tài liệu tham khảo

- `@Transactional` reactive và `TransactionalOperator` đều quản lý transaction trên Publisher, không phải trên những dòng code lắp ráp Publisher.
- Transaction nằm trong **Reactor subscriber Context**, không được truyền qua ThreadLocal theo mô hình imperative.
- Tất cả thao tác DB phải nằm trong cùng reactive chain/subscription và resource manager nếu cần atomicity.
- `@Transactional` cần gọi qua proxy; `TransactionalOperator` cần đặt boundary đúng vị trí.
- `then` phù hợp khi ghép sau Mono<Void>; dùng `concatMap` cho chuỗi SQL có thứ tự.
- `onError` thường làm rollback; nuốt lỗi trong boundary có thể gây commit; cancel cũng rollback.
- Flux vô hạn, retry không idempotent, subscribe nội bộ và HTTP side effect bên trong transaction là các rủi ro lớn.
- Hãy kiểm thử commit/rollback bằng truy vấn DB ngoài transaction sau khi Publisher hoàn tất.
- Với Kafka/HTTP/đa hệ thống, dùng outbox hoặc saga thay vì kỳ vọng một R2DBC transaction quản lý tất cả.

**Tài liệu chính thức**

1. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): TransactionalOperator, operator/callback style, rollback trên cancellation, TransactionDefinition.
2. [Spring Framework 6.2 — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html): AOP proxy, ReactiveTransactionManager và Reactor Context.
3. [Spring Framework 6.2 — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): annotation, return type, rollback rules, proxy mode.
4. [Spring Framework 6.2 — R2DBC Data Access](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html): DatabaseClient, R2dbcTransactionManager và ConnectionFactoryUtils.
5. [Spring Boot 3.5 — SQL Databases / R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): ConnectionFactory, embedded H2, DatabaseClient.
6. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql và spring.sql.init.mode.
7. [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @DataR2dbcTest không tự transactional.
8. [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, Context, then, retry, concatMap, cancellation, StepVerifier.
