# Transaction reactive trong Spring 6.1: TransactionalEventPublisher và sự kiện gắn transaction

## 1. Bối cảnh: reactive transaction events trong Spring Framework Application Events

Khi một ứng dụng WebFlux dùng R2DBC ghi dữ liệu, một sự kiện nghiệp vụ như `OrderCreated` thường phải được xử lý **sau khi transaction commit**. Chẳng hạn, nếu tạo đơn hàng thành công thì ghi nhận một thông báo; nếu thao tác database rollback thì không được thông báo rằng đơn hàng đã được tạo.

Trong Spring Framework trước 6.1, `@TransactionalEventListener` chủ yếu gắn với transaction do `PlatformTransactionManager` quản lý, dựa vào trạng thái gắn với thread. **Từ Spring Framework 6.1**, cơ chế transactional listener hỗ trợ cả transaction do `ReactiveTransactionManager` quản lý. Điều kiện quan trọng là **`ApplicationEvent.source` phải mang reactive `TransactionContext`**. Lớp mới `org.springframework.transaction.reactive.TransactionalEventPublisher` giúp tạo đúng event và gửi nó trong reactive pipeline.

Mục tiêu bài học:
- Phân biệt reactive transaction với imperative transaction; hiểu Reactor `Context` và lifecycle theo subscription.
- Dùng `TransactionalOperator` hoặc `@Transactional` cho reactive pipeline.
- Phát sự kiện qua `TransactionalEventPublisher` và nối `Mono<Void>` vào pipeline.
- Sử dụng `@TransactionalEventListener` với `AFTER_COMMIT`, `AFTER_ROLLBACK` và các phase khác.
- Kiểm thử commit, rollback, mất context, thiếu subscription, xử lý lỗi hậu commit và độ bền của sự kiện.

**Điểm giới hạn:** transactional event chỉ giúp gọi listener theo phase của transaction. Nó không phải message queue bền vững, không bảo đảm exactly-once delivery, không biến các side effect bên ngoài thành một phần atomic của DB transaction.

## 2. Transaction được giữ ở đâu?

| Khía cạnh | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Ví dụ database | JDBC qua `DataSourceTransactionManager` | R2DBC qua `R2dbcTransactionManager` |
| Nơi chứa transaction state | `ThreadLocal` của thread hiện tại | Reactor `Context` gắn với chuỗi reactive/subscription |
| API quản lý phạm vi | `TransactionTemplate`, `@Transactional` đồng bộ | `TransactionalOperator`, `@Transactional` với reactive return type |
| Cách listener tìm context | Spring nhìn transaction gắn thread | Event phải mang `TransactionContext` làm source |
| Thời điểm thực thi | Thường khi gọi phương thức | `Publisher` cần được subscribe |

Trong reactive programming, code có thể đổi thread vì scheduler nhưng Reactor Context vẫn có thể đi theo chain. Ngược lại, hai thao tác chạy liên tiếp trên cùng thread **không bảo đảm** thuộc cùng transaction nếu chúng nằm trong hai subscription/context khác nhau.

Mô hình khái quát:

```text
Subscription
   |
TransactionalOperator mở reactive transaction
   |
R2DBC lưu order
   |
TransactionalEventPublisher.publishEvent(OrderCreated)
   | tạo PayloadApplicationEvent
   | source = TransactionContext hiện tại
   | payload = OrderCreated
   | đăng ký transactional listener với transaction này
   |
   +---- pipeline hoàn tất -> COMMIT
   |                         -> AFTER_COMMIT
   |
   +---- pipeline lỗi      -> ROLLBACK
                             -> AFTER_ROLLBACK
```

Sự kiện có thể được phát khi transaction **chưa commit** để đăng ký callback; còn side effect được yêu cầu ở `AFTER_COMMIT` chỉ thực hiện sau khi commit. Đó là khác biệt giữa **thời điểm publish event** và **thời điểm listener xử lý**.

## 3. API mới trong Spring 6.1

`TransactionalEventPublisher` nhận một `ApplicationEventPublisher` (thường chính là Spring application context):

```java
TransactionalEventPublisher publisher =
    new TransactionalEventPublisher(applicationEventPublisher);
```

Đây là đoạn minh họa tích hợp; `applicationEventPublisher` được inject hoặc lấy từ application context.

### 3.1. Phát payload

```java
Mono<Void> publish = publisher.publishEvent(
    new OrderCreated(101L)
);
```

Overload `publishEvent(Object payload)` tạo event với `TransactionContext` của Reactor Context làm **source**, đồng thời giữ `OrderCreated` làm payload. Listener có thể khai báo phương thức nhận `OrderCreated`.

### 3.2. Chủ động dựng ApplicationEvent

Nếu cần tùy chỉnh event, dùng overload `publishEvent(Function<TransactionContext, ApplicationEvent>)`:

```java
Mono<Void> publish = publisher.publishEvent(
    transactionContext -> new PayloadApplicationEvent<>(
        transactionContext,
        new OrderCreated(101L)
    )
);
```

Đoạn này cần `org.springframework.context.PayloadApplicationEvent` và các kiểu phù hợp. Cũng có thể dùng một lớp `ApplicationEvent` tự định nghĩa, miễn event source chính là reactive `TransactionContext`.

Hai overload đều trả về `Mono<Void>`. Cần ghép `Mono` vào chuỗi đang có transaction. Việc viết:

```java
publisher.publishEvent(new OrderCreated(101L)); // BỎ QUA Publisher
```

không khiến event tự được phát. `Mono` mặc định là lazy: nếu không có subscription bao trùm, nó không thực thi.

### 3.3. Tự tạo event từ TransactionContext

Để hiểu cơ chế, cách thủ công tương đương là:

```java
Mono<Void> publication = TransactionContextManager.currentContext()
    .map(source -> new PayloadApplicationEvent<>(
        source,
        new OrderCreated(101L)
    ))
    .doOnNext(applicationEventPublisher::publishEvent)
    .then();
```

Đây là đoạn minh họa tích hợp, với `TransactionContextManager` thuộc package `org.springframework.transaction.reactive`. Thông thường ưu tiên `TransactionalEventPublisher` vì nó gói sẵn thao tác lấy context và tạo event, hạn chế lỗi cấu hình.

## 4. Vì sao ApplicationEventPublisher.publishEvent(payload) chưa đủ?

Trong một method reactive, code sau trông như có phát sự kiện bên trong transaction:

```java
return database.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .doOnNext(count ->
        applicationEventPublisher.publishEvent(
            new OrderCreated(orderId)
        )
    )
    .then();
```

Đây là **mẫu minh họa có lỗi ngữ nghĩa**. `ApplicationEventPublisher.publishEvent(Object)` có thể bọc payload thành `PayloadApplicationEvent` nhưng không tự đặt reactive `TransactionContext` làm event source. Vì `@TransactionalEventListener` nhận context qua event source trong mô hình reactive, listener có thể không đăng ký được đúng phase và mặc định bị bỏ qua khi không có transaction tương thích.

Mẫu đúng để lưu và đăng ký event trong một chain:

```java
Mono<Void> workflow = database
    .sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated()
    .then()
    .then(transactionalEventPublisher.publishEvent(
        new OrderCreated(orderId)
    ));
```

Đây là đoạn tích hợp, cần một reactive transaction bao quanh workflow. `then(publisherMono)` bảo đảm publication được thực thi **sau** thao tác R2DBC và trong cùng subscription/context. Không gọi `subscribe()` riêng trên publication; làm thế có thể tạo subscription khác, không có transaction phù hợp.

## 5. Ví dụ Java 17+ chạy được với Spring Context, R2DBC và H2

Chương trình dưới đây có transaction DB thật và hai listener:
- `AFTER_COMMIT` cho đơn hàng đã được commit.
- `AFTER_ROLLBACK` cho đơn hàng bị rollback.

Ví dụ dùng **Spring Framework 6.1.21**, H2 in-memory và `TransactionalOperator`. Không yêu cầu Spring Boot hoặc database ngoài. Việc dùng `block()` chỉ nằm ở `main` để ứng dụng console đợi kết quả; không dùng `block()` như vậy trên luồng xử lý WebFlux production.

Cấu trúc:

```text
reactive-transaction-events/
├── build.gradle
└── src/main/java/demo/ReactiveTransactionEventsDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.springframework:spring-r2dbc:6.1.21'
    runtimeOnly 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

application {
    mainClass = 'demo.ReactiveTransactionEventsDemo'
}
```

Nội dung `src/main/java/demo/ReactiveTransactionEventsDemo.java`:

```java
package demo;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class ReactiveTransactionEventsDemo {

    public record OrderCreated(long orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderEventListener orderEventListener() {
            return new OrderEventListener();
        }
    }

    public static final class OrderEventListener {
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void whenCommitted(OrderCreated event) {
            System.out.println("AFTER_COMMIT order=" + event.orderId());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void whenRolledBack(OrderCreated event) {
            System.out.println("AFTER_ROLLBACK order=" + event.orderId());
        }
    }

    public static void main(String[] args) {
        ConnectionFactory factory = ConnectionFactories.get(
            "r2dbc:h2:mem:///reactive_events" +
            "?options=DB_CLOSE_DELAY=-1"
        );

        DatabaseClient database = DatabaseClient.create(factory);
        database.sql(
            "CREATE TABLE orders (id BIGINT PRIMARY KEY)"
        ).fetch().rowsUpdated().then().block();

        R2dbcTransactionManager manager =
            new R2dbcTransactionManager(factory);
        TransactionalOperator transactions =
            TransactionalOperator.create(manager);

        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransactionalEventPublisher events =
                new TransactionalEventPublisher(context);

            Mono<Void> successFlow = database
                .sql("INSERT INTO orders (id) VALUES (1)")
                .fetch()
                .rowsUpdated()
                .then()
                .then(events.publishEvent(new OrderCreated(1L)));

            transactions.transactional(successFlow).block();

            Mono<Void> rollbackFlow = database
                .sql("INSERT INTO orders (id) VALUES (2)")
                .fetch()
                .rowsUpdated()
                .then()
                .then(events.publishEvent(new OrderCreated(2L)))
                .then(Mono.<Void>error(
                    new IllegalStateException("rollback requested")
                ));

            try {
                transactions.transactional(rollbackFlow).block();
            } catch (IllegalStateException expected) {
                System.out.println("rollback requested");
            }

            Long persistedRows = database
                .sql("SELECT COUNT(*) FROM orders")
                .map((row, metadata) ->
                    ((Number) row.get(0)).longValue()
                )
                .one()
                .block();

            System.out.println("rows persisted=" + persistedRows);
        }
    }
}
```

Lệnh chạy (JDK 17+ và Gradle có sẵn):

```bash
gradle run --quiet
```

**Các dòng stdout nghiệp vụ kỳ vọng:**

```text
AFTER_COMMIT order=1
AFTER_ROLLBACK order=2
rollback requested
rows persisted=1
```

Giải thích:
1. Tạo bảng xảy ra trước hai transaction demo. `DB_CLOSE_DELAY=-1` giữ database H2 in-memory giữa các kết nối trong cùng tiến trình.
2. `transactions.transactional(successFlow).block()` subscribe vào workflow, mở reactive transaction và đưa connection vào Reactor Context. `INSERT 1` chạy, rồi `events.publishEvent(OrderCreated(1))` đăng ký sự kiện đúng transaction.
3. Workflow hoàn tất nên transaction commit. Listener `AFTER_COMMIT` in thông báo cho id 1.
4. Workflow thứ hai phát sự kiện sau `INSERT 2`, rồi ném `IllegalStateException` bên **trong** transaction scope. Transaction manager rollback; listener `AFTER_ROLLBACK` in thông báo cho id 2.
5. `catch` được đặt **ngoài** operator; nó chỉ xử lý exception sau khi transaction đã rollback. Nếu dùng `onErrorResume` để nuốt lỗi trước khi transaction manager thấy lỗi, có thể dẫn tới commit ngoài ý muốn.
6. Câu lệnh `COUNT(*)` được thực thi sau cả hai transaction nên chỉ tìm thấy id 1.

Mỗi subscription có thể thực thi lại side effect. Trong production, nếu retry toàn bộ workflow hoặc re-subscribe một Publisher, phải kiểm soát idempotency, khóa duy nhất và trạng thái DB.

## 6. Các phase của @TransactionalEventListener

`@TransactionalEventListener` có cùng các phase cho cả imperative và reactive transaction:

| Phase | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `BEFORE_COMMIT` | Gọi trước khi commit | Transaction vẫn có thể lỗi/rollback sau callback |
| `AFTER_COMMIT` | Gọi sau commit thành công; **mặc định** | Lỗi hậu commit không rollback được transaction gốc |
| `AFTER_ROLLBACK` | Gọi sau rollback | Dùng cho cleanup, logging hay xử lý nhánh thất bại |
| `AFTER_COMPLETION` | Gọi khi transaction đã kết thúc (commit/rollback) | Không được tự suy ra luôn là thành công |

Ví dụ dạng method trong bean Spring:

```java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Nghiệp vụ cần chạy trước commit.
}

@TransactionalEventListener
public void afterSuccess(OrderCreated event) {
    // Mặc định AFTER_COMMIT.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void afterFailure(OrderCreated event) {
    // Chỉ chạy với rollback.
}
```

Các method trên mang tính minh họa, không phải chương trình độc lập. Listener không chỉ vì được gọi “sau commit” mà tự nhiên có một transaction mới. Tại thời điểm completion, một số tài nguyên transaction cũ có thể còn khả dụng, nhưng thao tác ghi DB mới cần transaction riêng nếu phải commit tiếp.

Nếu không có transaction thích hợp, `@TransactionalEventListener` mặc định **không xử lý event** vì `fallbackExecution=false`. Đặt `fallbackExecution=true` cho phép listener chạy cả khi không có transaction, nhưng trường hợp ấy không có commit thật để chờ. Chỉ bật khi nghiệp vụ chấp nhận ngữ nghĩa fallback.

## 7. @Transactional với reactive return type

Một service reactive có thể dùng `@Transactional` thay cho `TransactionalOperator`, nếu bean transaction manager và transaction advice được cấu hình đúng.

Ví dụ tích hợp (cần `@Service`, `@Transactional`, Spring bean `DatabaseClient` và `TransactionalEventPublisher`):

```java
@Service
public class OrderService {
    private final DatabaseClient database;
    private final TransactionalEventPublisher events;

    public OrderService(DatabaseClient database,
                        TransactionalEventPublisher events) {
        this.database = database;
        this.events = events;
    }

    @Transactional
    public Mono<Void> createOrder(long id) {
        return database
            .sql("INSERT INTO orders (id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then()
            .then(events.publishEvent(new OrderCreated(id)));
    }
}
```

Đoạn này **không phải file chạy độc lập**; ứng dụng cần khai báo `OrderCreated`, transaction manager reactive và listener của mình. Trong cấu hình proxy mặc định, lời gọi service phải đi qua Spring proxy; gọi nội bộ trong cùng bean thường không áp dụng `@Transactional`.

Với `ReactiveTransactionManager`, transaction gắn vào publisher được **subscribe**, không phải lúc phương thức Java chỉ tạo một `Mono`. Phương thức trả về kiểu bình thường hoặc `void` không mang contract reactive transaction như `Mono`/`Flux`. Bên trong cùng reactive chain, các thao tác truy cập dữ liệu phải dùng tài nguyên reactive-aware như `DatabaseClient` để tham gia transaction.

**Không trộn `TransactionTemplate` và `TransactionalOperator`** chỉ vì tên gần nhau: `TransactionTemplate` dành cho imperative `PlatformTransactionManager`, `TransactionalOperator` dành cho reactive `ReactiveTransactionManager`.

## 8. Reactor Context và những lỗi dễ bỏ sót

### 8.1. Gọi publisher ngoài transaction

`TransactionalEventPublisher` sử dụng transaction context hiện tại. Khi subscribe ngoài reactive transaction, nó không thể lấy một transaction context đang thiếu để đưa vào event source, nên phép phát có thể lỗi. `fallbackExecution=true` ở listener không tự tạo context cho publisher này.

Nếu event **không** cần phụ thuộc commit/rollback, hãy dùng `ApplicationEventPublisher` hoặc một pipeline khác với hợp đồng rõ ràng.

### 8.2. Thiếu subscription

```java
Mono<Void> neverRuns =
    transactionalEventPublisher.publishEvent(new OrderCreated(1L));
```

Đoạn này chỉ khởi tạo Mono; không có subscription nên event chưa được phát. Trong ứng dụng WebFlux, framework thường subscribe vào publisher mà handler trả về. Trong CLI/test, `block()` hoặc `StepVerifier` có thể là ranh giới subscription thích hợp.

### 8.3. Gọi subscribe tách rời

```java
database.sql("INSERT ...").fetch().rowsUpdated().then().subscribe();
events.publishEvent(new OrderCreated(1L)).subscribe();
```

Đây là **mẫu sai cho nghiệp vụ có tính transaction**: hai subscription không mặc nhiên chia sẻ cùng Reactor Context/transaction. Ngoài việc mất phase, lỗi còn khó gom và retry. Hãy compose một publisher duy nhất rồi bọc transaction ở lớp ngoài.

### 8.4. Dùng ThreadLocal để kiểm tra reactive transaction

Có hai lớp cùng tên nhưng khác mô hình:
- `org.springframework.transaction.support.TransactionSynchronizationManager`: hỗ trợ imperative, gắn thread.
- `org.springframework.transaction.reactive.TransactionSynchronizationManager`: hỗ trợ reactive, gắn subscriber context.

Không gọi API ThreadLocal imperative để quyết định rằng pipeline reactive “không có transaction”. Nếu cần đọc ngữ cảnh reactive trực tiếp, dùng các API reactive được thiết kế cho Reactor Context.

### 8.5. Nhầm thứ tự thực thi

Việc tạo `Mono` không đảm bảo đã có transaction. Trình tự đúng là **subscribe → transaction bắt đầu → thao tác R2DBC → phát event → commit/rollback → listener phase**. `flatMap` có thể làm công việc chồng lấn; nếu thứ tự ghi rồi publish là điều kiện quan trọng, dùng `then(...)` hoặc cách kết hợp bảo đảm trình tự completion mong muốn.

`map(...)` trên `Mono<Void>` không giúp gọi side effect sau khi hoàn tất vì `Mono<Void>` không có phần tử `onNext`. Dùng `then(...)` cho tác vụ nối tiếp.

## 9. Có nên xử lý I/O reactive trong listener sau commit?

`@TransactionalEventListener` giúp **chọn thời điểm gọi handler**, không tự quản lý một reactive chain bất kỳ được tạo bên trong handler. Ví dụ:

```java
@TransactionalEventListener
public void onCreated(OrderCreated event) {
    remoteClient.sendNotification(event.orderId()).subscribe();
}
```

Đây là **anti-pattern minh họa**: `remoteClient` giả định đã được inject. Lời gọi `subscribe()` tự tạo tác vụ không có cơ chế quản lý hoàn tất, retry, backpressure hay shutdown đáng tin cậy. Lỗi có thể không tới nơi caller mong đợi, còn transaction gốc đã commit.

Nếu chỉ là tác vụ phụ có thể mất, cần ghi nhận lỗi và giới hạn tài nguyên. Nếu cần độ tin cậy, cân nhắc:
- Lưu **outbox record** trong cùng reactive DB transaction với bản ghi nghiệp vụ; worker độc lập đọc và gửi sau commit.
- Consumer idempotent theo business key hoặc `eventId` ổn định, có retry và giám sát.
- Khi bắt buộc tạo bản ghi mới sau commit, mở **reactive transaction mới** ở service phù hợp (thông qua `TransactionalOperator`/`@Transactional`) và điều phối chính sách lỗi rõ ràng.

**Không có exactly-once mặc định:** listener `AFTER_COMMIT` có thể chưa kịp chạy nếu tiến trình bị dừng sau DB commit. Event nội bộ Spring không tự bền vững qua restart. Transactional outbox giúp thu hẹp khoảng trống mất sự kiện bằng cách lưu ý định gửi trong cùng transaction.

## 10. Kiểm thử commit, rollback và lỗi context

Đừng chỉ test rằng một listener được đăng ký. Integration test cần xác minh cả **trạng thái DB** và **callback phase**.

| Tình huống | Thiết kế test | Kỳ vọng |
| --- | --- | --- |
| Commit thật | Insert + publish trong cùng TransactionalOperator và subscribe hoàn tất | DB có dữ liệu; gọi `AFTER_COMMIT` đúng lần |
| Rollback | Insert + publish rồi phát `Mono.error` trước commit | DB không có bản ghi; gọi `AFTER_ROLLBACK` |
| Không subscribe | Tạo Mono mà không subscribe | Không có thao tác DB hay event được thực thi |
| Publisher không có context | Subscribe `TransactionalEventPublisher` ngoài transaction | Không thể lấy reactive transaction context để publish đúng cách |
| Source không đúng | Dùng publisher thông thường trong reactive transaction | Transactional listener không có reactive source hợp lệ để liên kết phase |
| Nuốt lỗi trong transaction | `onErrorResume` bên trong operator biến lỗi thành hoàn tất | Cần kiểm tra nguy cơ commit không mong muốn |
| Phát lại/retry | Subscribe lại pipeline hoặc retry khi có lỗi | Side effect không bị trùng bất hợp lệ |
| Hậu commit thất bại | Mô phỏng API hoặc job fail trong after-commit | Transaction DB gốc vẫn đã commit; lỗi cần cơ chế quan sát/phục hồi riêng |

Nếu dùng `reactor-test`, có thể kiểm tra tín hiệu của pipeline:

```java
StepVerifier.create(transactions.transactional(successFlow))
    .verifyComplete();

StepVerifier.create(transactions.transactional(rollbackFlow))
    .expectError(IllegalStateException.class)
    .verify();
```

Đây là **đoạn test minh họa**, giả định các biến từ ví dụ đã có và bổ sung dependency `io.projectreactor:reactor-test`. Mỗi `StepVerifier` tạo subscription thực, do đó pipeline có thể thao tác DB. Tránh tái dùng cùng ID hoặc cùng trạng thái test khi muốn chạy độc lập.

Kiểm thử thêm số callback thực nhận, event ID, tính bất biến payload, tên transaction manager và đường lỗi khi thiếu context. Đừng dùng `Thread.sleep` để “đợi commit”; dùng kết quả hoàn tất publisher hoặc tín hiệu kiểm thử phù hợp.

## 11. Phân biệt ba loại sự kiện dễ nhầm

| Loại | Cách sử dụng | Hệ quả |
| --- | --- | --- |
| Event thông thường | `@EventListener` + `ApplicationEventPublisher` | Xử lý theo dispatch; không gắn mặc định với commit/rollback |
| Transactional event imperative | `@TransactionalEventListener` trong `PlatformTransactionManager` | Dựa trên transaction state của thread |
| Transactional event reactive Spring 6.1 | `@TransactionalEventListener` + event source là `TransactionContext`, thường do `TransactionalEventPublisher` tạo | Đăng ký callback theo lifecycle reactive transaction |

Trong Spring 6.1, transactional listener có thể chạy trên luồng phát event để đăng ký synchronization ngay cả khi multicaster được cấu hình async. Không giả định `@Async` bảo toàn reactive transaction context hoặc làm cho side effect hậu commit bền vững. Nếu listener phải gọi một workflow reactive dài, tách và quản lý pipeline đó theo yêu cầu giao nhận.

## 12. Các sai lầm phổ biến

1. **Gọi publisher thông thường và mong listener transactional tự thấy Reactor Context.** Cần đưa `TransactionContext` vào event source.
2. **Bỏ qua `Mono<Void>` từ `TransactionalEventPublisher`.** Không có subscription thì chưa publish.
3. **Tự subscribe nhiều lần bên trong service.** Dễ tách khỏi transaction và gây side effect lặp.
4. **Cho rằng đổi thread nhất định làm mất Reactor Context hoặc cùng thread luôn có context.** Yếu tố quyết định là subscription/context.
5. **Dùng `TransactionSynchronizationManager` imperative để hỏi trạng thái reactive transaction.** Hai API có cơ chế state khác nhau.
6. **Gọi `block()` trong WebFlux handler/worker reactive.** Có nguy cơ chặn event-loop và giảm throughput.
7. **Dùng `onErrorResume` trước điểm manager quyết định rollback.** Lỗi bị biến thành thành công có thể dẫn đến commit.
8. **Bật `fallbackExecution=true` để che lỗi thiếu source.** Có thể xử lý event dù không có commit thật.
9. **Viết DB mới sau commit nhưng không tạo transaction mới.** Tài nguyên transaction cũ có thể còn bound nhưng không bảo đảm commit lần nữa.
10. **Coi `AFTER_COMMIT` là durable queue.** Crash sau commit vẫn có thể làm mất tác vụ chưa xử lý.
11. **Không thiết kế idempotency cho event có retry.** Một lần subscribe/retry khác có thể phát lại event.
12. **Dựa vào log hoặc thứ tự listener làm chứng cứ commit.** Cần kiểm tra outcome DB và phase thực tế.

## 13. Checklist áp dụng

- [ ] Phần lưu dữ liệu thật sự do `ReactiveTransactionManager` điều phối và dùng R2DBC/driver reactive phù hợp.
- [ ] Service có reactive return type; transaction bắt đầu khi subscribe chứ không chỉ lúc dựng Mono.
- [ ] `TransactionalEventPublisher` được tạo từ một `ApplicationEventPublisher` và publication chạy trong transaction context đúng.
- [ ] `publishEvent(...)` nằm trong cùng chain với thao tác dữ liệu, không subscribe riêng.
- [ ] Listener có `@TransactionalEventListener` với phase đúng; hiểu mặc định `AFTER_COMMIT` và `fallbackExecution=false`.
- [ ] Không nhầm Reactor Context với ThreadLocal, không mặc định async kế thừa transaction.
- [ ] Test bao phủ commit, rollback, không có transaction, không subscribe, retry và lỗi hậu commit.
- [ ] Side effect quan trọng có kế hoạch retry/idempotency, outbox khi phải bảo đảm độ bền.
- [ ] Có thể phân biệt “DB đã commit”, “event đã đăng ký callback”, “listener đã chạy” và “tác vụ ngoài hệ thống đã hoàn thành”.

**Ghi nhớ:** từ Spring Framework 6.1, transactional listener hỗ trợ reactive transaction khi event mang đúng `TransactionContext`. Hãy phát event bằng `TransactionalEventPublisher` **bên trong** reactive transaction pipeline và kiểm tra phase thực tế, thay vì dựa vào trạng thái thread.

## Tài liệu tham khảo

- [Spring 6.1.21 Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring 6.1.21 Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework Reference — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [R2DBC H2 — Connection Factory and URL](https://github.com/r2dbc/r2dbc-h2)
