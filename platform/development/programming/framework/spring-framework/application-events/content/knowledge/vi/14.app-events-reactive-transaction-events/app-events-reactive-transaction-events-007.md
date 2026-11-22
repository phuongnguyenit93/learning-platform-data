# Listener transaction-bound trong reactive flow

## 1. Bài toán: event chỉ được xử lý khi reactive transaction đạt đúng trạng thái

Trong ứng dụng Spring dùng Reactor và R2DBC, một luồng có thể ghi đơn hàng, phát `OrderCreated` rồi commit. Listener chỉ nên gửi thông báo hoặc cập nhật trạng thái phụ **sau khi commit thành công**; nếu thao tác ghi rollback, listener `AFTER_COMMIT` không được thực hiện.

Công cụ Spring là `@TransactionalEventListener`, nhưng việc đăng ký listener trong reactive transaction có một khác biệt quan trọng so với JDBC/JPA truyền thống: **reactive transaction nằm trong Reactor `Context` của subscriber, không nằm trong `ThreadLocal` của thread**. Vì thế, event phải mang ngữ cảnh giao dịch thích hợp để Spring liên kết callback với lần commit/rollback của đúng subscription.

Từ **Spring Framework 6.1**, `@TransactionalEventListener` hỗ trợ cả transaction thông thường do `PlatformTransactionManager` quản lý và reactive transaction do `ReactiveTransactionManager` quản lý. Với reactive transaction, Spring yêu cầu **`TransactionContext` nằm trong `source` của `ApplicationEvent`**. `TransactionalEventPublisher` là tiện ích thực hiện việc này.

### Luồng mong muốn

~~~text
Client subscribe
    |
    v
TransactionalOperator / @Transactional trên Mono hoặc Flux
    |
    +-- BEGIN reactive transaction T1
    |
    +-- INSERT orders qua R2DBC (cùng Reactor Context)
    |
    +-- TransactionalEventPublisher.publishEvent(orderCreated)
    |      |
    |      +-- lấy TransactionContext của subscription hiện tại
    |      +-- tạo ApplicationEvent với source = TransactionContext
    |      +-- multicaster thông báo listener để đăng ký synchronization
    |
    +-- pipeline complete ----------------------------> COMMIT T1
    |                                                     |
    |                                                     +-- AFTER_COMMIT listener
    |
    +-- pipeline error -------------------------------> ROLLBACK T1
                                                          |
                                                          +-- AFTER_ROLLBACK listener
~~~

**Giới hạn của mô hình:** việc phát event qua `ApplicationEventPublisher` chỉ là giao event cho hệ thống listener nội bộ. Nó không tự tạo một message broker, không bảo đảm xử lý lại sau crash và không bảo đảm chính xác một lần.

## 2. Reactive transaction khác gì transaction gắn với thread?

| Khía cạnh | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager`, ví dụ `DataSourceTransactionManager` | `ReactiveTransactionManager`, ví dụ `R2dbcTransactionManager` |
| Nơi mang ngữ cảnh | Chủ yếu `ThreadLocal` của thread hiện tại | Reactor `Context` gắn với subscriber/reactive chain |
| Mã truy cập dữ liệu | JDBC/JPA đồng bộ | R2DBC/reactive repository trả `Mono` hoặc `Flux` |
| Ranh giới transaction | Transaction interceptor quanh lời gọi đồng bộ | Transaction interceptor/operator quanh quá trình **subscribe và phát tín hiệu** |
| Gắn event với transaction | Spring có thể nhìn transaction thread-bound | Event phải chứa `TransactionContext` làm `source` để listener đăng ký synchronization |
| Lỗi thường gặp | Dịch chuyển sang thread khác làm mất thread context | Tách chain hoặc `subscribe()` thủ công làm logic chạy ngoài subscription mong đợi |

`publishOn` hoặc `subscribeOn` **không mặc nhiên làm mất Reactor Context** nếu chuỗi Reactor được ghép đúng: context đi theo subscription chứ không theo một thread cố định. Rủi ro nằm ở việc tạo **subscription riêng**, giao công việc cho hệ thống không mang context hoặc dựng pipeline ngoài phạm vi transaction.

Khi dùng Spring `@Transactional` với `ReactiveTransactionManager`, phương thức giao dịch phải trả về kiểu reactive thích hợp như `Mono<T>` hoặc `Flux<T>`; phương thức trả `void` không thể áp dụng như một reactive transactional method thông thường.

## 3. TransactionalEventPublisher đưa context vào event như thế nào?

`org.springframework.transaction.reactive.TransactionalEventPublisher` được Spring cung cấp từ phiên bản 6.1. Nó nhận một `ApplicationEventPublisher` và cung cấp hai kiểu sử dụng chính:

~~~java
// Publisher trả Mono<Void>; phải nối vào reactive chain.
Mono<Void> published = transactionalEventPublisher.publishEvent(
    new OrderCreated(101L)
);
~~~

Trong ví dụ trên `OrderCreated` là payload thông thường. Spring tạo `PayloadApplicationEvent<OrderCreated>` với **source là `TransactionContext` đang hoạt động**. Listener vẫn có thể khai báo tham số nghiệp vụ `OrderCreated`.

Nếu muốn một lớp event kế thừa `ApplicationEvent`, dùng factory nhận context:

~~~java
// Đoạn minh họa cần có các biến và lớp phù hợp.
Mono<Void> published = transactionalEventPublisher.publishEvent(
    transactionContext -> new OrderCreatedApplicationEvent(
        transactionContext, 101L
    )
);
~~~

Với constructor minh họa:

~~~java
final class OrderCreatedApplicationEvent
        extends org.springframework.context.ApplicationEvent {
    private final long orderId;

    OrderCreatedApplicationEvent(Object source, long orderId) {
        super(source);
        this.orderId = orderId;
    }

    long orderId() {
        return orderId;
    }
}
~~~

Cả hai cách đều bảo đảm **event source** là transaction context khi được gọi trong một reactive transaction hợp lệ. Tùy cách biểu diễn event, listener nhận payload hoặc lớp `ApplicationEvent` cụ thể.

**Đặc biệt lưu ý:**

- `TransactionalEventPublisher` **không mở transaction**. Nó lấy ngữ cảnh hiện tại; tác vụ phát event cần được gọi trong chuỗi đang có transaction.
- Phương thức trả `Mono<Void>` là **lazy**: chỉ tạo biến `Mono` nhưng không đưa nó vào chuỗi có subscriber thì event chưa được phát.
- Đừng tạo `Mono` rồi gọi `subscribe()` độc lập trong service; subscription mới không tự thừa hưởng context của subscription giao dịch đang bao quanh.
- Chỉ thêm `TransactionContext` vào **source**, không cần đưa toàn bộ đối tượng transaction hoặc kết nối DB vào payload nghiệp vụ. Payload nên chứa dữ liệu cần thiết, chẳng hạn `orderId`.
- Không tự tạo một `TransactionContext` giả để đánh lừa listener. Context phải thuộc transaction thật do Spring quản lý.

`ApplicationEventPublisher.publishEvent(new OrderCreated(...))` trực tiếp trong reactive flow có thể thiếu source đặc biệt. Khi thiếu nguồn context và không có transaction thread-bound phù hợp, listener transaction-bound **không đăng ký được synchronization** và mặc định không chạy.

## 4. Phase của listener và ý nghĩa trong reactive flow

`@TransactionalEventListener` vẫn dùng cùng các phase như lập trình imperative:

| Phase | Khi nào callback được gọi? | Ví dụ nghiệp vụ |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit, khi synchronization chạy | Kiểm tra đồng bộ hoặc hoàn thiện công việc cùng transaction, nếu việc đó phù hợp cơ chế callback |
| `AFTER_COMMIT` (**mặc định**) | Sau khi commit thành công | Thông báo nghiệp vụ chỉ phát sau khi đơn hàng tồn tại |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận thất bại vào hệ thống độc lập |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Dọn tài nguyên/logging không phụ thuộc kết quả |

Khi **không có transaction**, listener `@TransactionalEventListener` mặc định bị bỏ qua. Bật `fallbackExecution = true` để xử lý cả event ngoài transaction nếu nghiệp vụ cho phép, nhưng lúc đó hành vi fallback **không còn bảo đảm after-commit**.

Ngoài ra, callback listener là một phần của cơ chế synchronization. Không nên hiểu "listener chạy sau commit" là "mọi publisher mà listener trả về sẽ tự được subscribe trong transaction mới". Nếu callback cần thao tác R2DBC mới, phải tổ chức một reactive pipeline độc lập với ranh giới transaction và subscription rõ ràng.

## 5. Ví dụ chạy được: H2 R2DBC + TransactionalOperator + listener theo commit/rollback

Demo dùng **Java 17+**, Spring Framework **6.2.19**, Reactor Core **3.7.19** và H2 R2DBC. Không cần Spring Boot. Nó mở giao dịch reactive T1, lưu một đơn hàng, phát event trong cùng pipeline; sau đó lần lượt thử commit và cố ý rollback.

Cấu trúc dự án:

~~~text
reactive-transaction-events/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ReactiveTxEventsDemo.java
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-transaction-events'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-tx:6.2.19'
    implementation 'org.springframework:spring-r2dbc:6.2.19'
    implementation 'io.projectreactor:reactor-core:3.7.19'
    implementation 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

application {
    mainClass = 'demo.ReactiveTxEventsDemo'
}
~~~

Tạo `src/main/java/demo/ReactiveTxEventsDemo.java`:

~~~java
package demo;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Configuration
@EnableTransactionManagement
@ComponentScan(basePackageClasses = ReactiveTxEventsDemo.class)
public class ReactiveTxEventsDemo {

    @Bean
    ConnectionFactory connectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:h2:mem:///reactive_events" +
            "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
        );
    }

    @Bean
    DatabaseClient databaseClient(ConnectionFactory factory) {
        return DatabaseClient.create(factory);
    }

    @Bean
    ReactiveTransactionManager transactionManager(ConnectionFactory factory) {
        return new R2dbcTransactionManager(factory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher publisher) {
        return new TransactionalEventPublisher(publisher);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                ReactiveTxEventsDemo.class)) {

            var db = context.getBean(DatabaseClient.class);
            db.sql("CREATE TABLE orders (id BIGINT PRIMARY KEY)")
                .then()
                .block();

            var service = context.getBean(OrderService.class);

            // T1 commit -> listener AFTER_COMMIT xử lý đơn 101.
            service.createOrder(101L, false).block();

            // T2 rollback -> listener AFTER_ROLLBACK xử lý đơn 102.
            try {
                service.createOrder(102L, true).block();
            } catch (IllegalStateException ex) {
                System.out.println("caught rollback: 102");
            }

            Long total = db.sql("SELECT COUNT(*) FROM orders")
                .map((row, metadata) ->
                    ((Number) row.get(0)).longValue())
                .one()
                .block();

            System.out.println("rows in DB: " + total);
        }
    }
}

// Payload thuần dữ liệu. TransactionContext nằm trong source
// của PayloadApplicationEvent do TransactionalEventPublisher tạo.
record OrderCreated(long orderId) {}

@Component
class OrderService {
    private final DatabaseClient db;
    private final TransactionalEventPublisher events;
    private final TransactionalOperator transaction;

    OrderService(DatabaseClient db,
                 TransactionalEventPublisher events,
                 TransactionalOperator transaction) {
        this.db = db;
        this.events = events;
        this.transaction = transaction;
    }

    Mono<Void> createOrder(long id, boolean forceRollback) {
        Mono<Void> work = db.sql(
                    "INSERT INTO orders (id) VALUES (:id)")
                .bind("id", id)
                .fetch()
                .rowsUpdated()
                .then(events.publishEvent(new OrderCreated(id)))
                .then(Mono.defer(() -> forceRollback
                    ? Mono.<Void>error(
                        new IllegalStateException("forced rollback"))
                    : Mono.<Void>empty()));

        // Reactive transaction bao trọn INSERT và publishEvent.
        // Mọi bước được thực thi khi người gọi subscribe/block.
        return transaction.transactional(work);
    }
}

@Component
class OrderEventListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void onCommit(OrderCreated event) {
        System.out.println("after commit: " + event.orderId());
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderCreated event) {
        System.out.println("after rollback: " + event.orderId());
    }
}
~~~

Chạy tại thư mục dự án bằng JDK 17+ và Gradle (hoặc Gradle Wrapper nếu dự án đã có):

~~~bash
gradle run --quiet
# Nếu có wrapper: ./gradlew run --quiet
# Windows: gradlew.bat run --quiet
~~~

Các dòng do chương trình `System.out` phát ra, theo thứ tự:

~~~text
after commit: 101
after rollback: 102
caught rollback: 102
rows in DB: 1
~~~

Giải thích:

1. `createOrder(101, false)` tạo reactive pipeline T1. Lúc `block()` subscribe, R2DBC INSERT đơn 101 rồi `TransactionalEventPublisher.publishEvent(...)` đưa `OrderCreated(101)` vào multicaster với source là `TransactionContext` của T1.
2. Listener đăng ký các transaction synchronization thích hợp. Pipeline hoàn tất không lỗi → T1 commit; callback `AFTER_COMMIT` in `after commit: 101`. Callback `AFTER_ROLLBACK` không chạy cho event này.
3. `createOrder(102, true)` cũng INSERT và publish event trong T2, nhưng phần cuối tạo lỗi. T2 rollback → callback `AFTER_ROLLBACK` in `after rollback: 102`. Lỗi được truyền tới `block()` và bị `catch` ở `main` bắt; `AFTER_COMMIT` không chạy cho đơn 102.
4. Truy vấn sau cùng cho `rows in DB: 1`: chỉ đơn 101 tồn tại. Event của đơn 102 đã được công bố trong flow nhưng listener sau commit không thực thi.

**Điểm học quan trọng:** gọi `publishEvent(...)` **trong chuỗi** bằng `.then(events.publishEvent(...))` bảo đảm nó thực thi sau INSERT và trước khi transactional operator hoàn tất. Nếu chỉ tạo `Mono` mà không ghép vào chain, event không được phát. Nếu gọi `events.publishEvent(...).subscribe()` bên trong service, rất dễ tách ra một subscription không mang transaction context hiện tại.

Lệnh `block()` trong demo chỉ dùng tại `main` để chờ chương trình console chạy xong. Trong WebFlux/reactive handler hoặc luồng xử lý non-blocking, hãy **return `Mono`/`Flux`** cho runtime subscribe; không gọi `block()` bên trong handler hay listener.

## 6. Vì sao publishEvent thông thường có thể làm listener không chạy?

So sánh hai cách trong reactive transaction:

~~~java
// KHÔNG ĐỦ CHO REACTIVE TRANSACTION-BOUND LISTENER:
// ApplicationEventPublisher thông thường không tự đưa
// Reactor TransactionContext vào event source.
return db.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .doOnSuccess(count ->
        applicationEventPublisher.publishEvent(new OrderCreated(id)))
    .then();
~~~

~~~java
// ĐÚNG: event mang TransactionContext ở source,
// và Mono<Void> phát event được nối vào cùng reactive chain.
return db.sql("INSERT INTO orders (id) VALUES (:id)")
    .bind("id", id)
    .fetch()
    .rowsUpdated()
    .then(transactionalEventPublisher.publishEvent(new OrderCreated(id)));
~~~

Hai đoạn chỉ minh họa **phần thân của một pipeline**: để thật sự transaction-bound còn cần bao toàn bộ bằng `TransactionalOperator` hoặc phương thức reactive `@Transactional` dùng `ReactiveTransactionManager`. Không ghép từng đoạn vào demo mà quên ranh giới transaction.

Việc gọi `ApplicationEventPublisher.publishEvent(...)` trực tiếp **không luôn sai**: nó hợp lệ cho event thông thường hoặc khi đang dùng transaction thread-bound. Nhưng **với reactive transaction-bound listener**, nó không tự mang `TransactionContext` theo yêu cầu Spring 6.1+.

Một cách thay thế rõ ràng khác là chủ động lấy `TransactionContextManager.currentContext()` và tạo `PayloadApplicationEvent<>(transactionContext, payload)` rồi truyền qua `ApplicationEventPublisher`. Tuy nhiên, `TransactionalEventPublisher` đã đóng gói đúng thao tác này, giúp giảm rủi ro viết sai.

## 7. Reactive context, thread và subscription: các tình huống dễ nhầm

### Tình huống A — Tạo publisher nhưng không subscribe

~~~java
Mono<Void> pending = transactionalEventPublisher.publishEvent(
    new OrderCreated(5L)
);
// Không return pending, không compose vào flow, không subscribe.
// Chưa có event nào được phát từ đoạn này.
~~~

Reactor là lazy. Đây là lý do cần `then(...)`, `flatMap(...)` hoặc cấu trúc kết hợp reactive phù hợp.

### Tình huống B — Subscribe độc lập ngay bên trong transaction

~~~java
// Anti-pattern: tự mở subscription khác rồi quên quản lý lifecycle.
transactionalEventPublisher.publishEvent(new OrderCreated(5L))
    .subscribe();
~~~

Subscription mới có thể không có `TransactionContext` của publisher ngoài; lỗi có thể xuất hiện như “không có transaction trong context”, hoặc hành vi quan sát không như mong đợi. Trả publisher về và kết hợp bằng toán tử Reactor.

### Tình huống C — Chuyển scheduler

~~~java
Mono<Void> work = transactionalEventPublisher
    .publishEvent(new OrderCreated(5L))
    .publishOn(reactor.core.scheduler.Schedulers.parallel());
~~~

Nếu `work` được subscribe **trong transaction chain tương ứng**, `publishOn` theo thông lệ Reactor giữ subscriber context. Không cần cố ghim tất cả vào cùng thread. Nhưng callback đẩy sang API chạy ngoài Reactor, tương tác với ThreadLocal bên ngoài hoặc lén gọi `subscribe()` vẫn cần xử lý truyền context/lifecycle riêng.

### Tình huống D — Event không có active transaction

Với mặc định `fallbackExecution = false`, listener không được gọi nếu event được công bố ngoài transaction có thể đăng ký synchronization. Nếu publisher yêu cầu `TransactionContext` nhưng không có context hợp lệ, việc lấy context có thể phát lỗi reactive; điều này **khác** với việc dùng một event publisher thông thường và bị listener bỏ qua. Đừng bật `fallbackExecution = true` chỉ để che lỗi tạo transaction hoặc lỗi ghép reactive chain.

## 8. Listener cần thao tác R2DBC sau commit thì sao?

Callback `AFTER_COMMIT` cho biết **T1 đã commit**. Nó **không cung cấp một transaction T2 mới** cho thao tác ghi tiếp theo. Tương tự cơ chế imperative, một số tài nguyên transaction gốc có thể vẫn đang trong giai đoạn cleanup. Với reactive transaction, càng không nên giả định một callback `void` là nơi có thể chạy an toàn `Mono` ghi DB chỉ bằng cách tạo ra rồi bỏ mặc.

Nếu thực sự cần ghi bản ghi khác **sau** commit:

- Thiết kế một pipeline ghi riêng với `ReactiveTransactionManager`/`TransactionalOperator` phù hợp, có ranh giới **transaction T2** rõ ràng, và bảo đảm pipeline đó được subscribe/quản lý vòng đời, lỗi, retry theo yêu cầu ứng dụng.
- Nếu cần `REQUIRES_NEW`, có thể tạo `TransactionalOperator` với `DefaultTransactionDefinition` và `PROPAGATION_REQUIRES_NEW`. Nó mở giao dịch mới khi pipeline được subscribe; thao tác cấu hình propagation **không tự subscribe**.
- Không gọi `block()` trong event listener chạy trên thread non-blocking; không dùng `subscribe()` “fire and forget” mà không quản lý completion/error.
- Nếu thao tác phụ phải sống sót qua process crash, cân nhắc **transactional outbox**: ghi `orders` và `outbox` trong cùng T1, rồi worker độc lập xử lý outbox với retry/idempotency.

Ví dụ cấu hình operator riêng, **đoạn minh họa nhúng**, không phải chương trình độc lập:

~~~java
var definition = new org.springframework.transaction.support
    .DefaultTransactionDefinition();
definition.setPropagationBehavior(
    org.springframework.transaction.TransactionDefinition.PROPAGATION_REQUIRES_NEW
);

var newTransaction = TransactionalOperator.create(
    reactiveTransactionManager, definition
);

// Trả Mono này cho tầng quản lý lifecycle/subscription thích hợp.
Mono<Void> saveAudit = newTransaction.transactional(
    databaseClient.sql(
        "INSERT INTO audit_log (order_id) VALUES (:orderId)")
        .bind("orderId", orderId)
        .then()
);
~~~

Đoạn trên giả định đã có `reactiveTransactionManager`, `databaseClient`, `orderId` và bảng `audit_log`. Nó minh họa **ranh giới T2**, không chỉ cách kết nối publisher đó vào callback cụ thể. Việc gọi nhầm một phương thức `@Transactional` có kiểu trả `void` cũng không tạo ra reactive transaction đúng nghĩa.

Một lưu ý nghiệp vụ: **T1 đã commit không thể bị rollback bởi lỗi ở T2**. Vì thế, với audit bắt buộc cùng tồn tại nguyên tử với đơn hàng, hãy ghi trong T1; với tích hợp tin cậy qua hệ thống ngoài, outbox thường phù hợp hơn.

## 9. Kiểm thử transaction-bound listener và xử lý sự cố

Một bộ kiểm thử hữu ích nên phân biệt ít nhất bốn tình huống:

| Ca kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Transaction commit thành công | `AFTER_COMMIT` chạy đúng một lần cho event đã phát trong phép thử; `AFTER_ROLLBACK` không chạy |
| Transaction rollback | `AFTER_ROLLBACK` chạy; `AFTER_COMMIT` không chạy; thay đổi DB trong T1 được rollback |
| Phát event ngoài transaction | Listener mặc định bị bỏ qua, hoặc `TransactionalEventPublisher` báo thiếu context khi được subscribe |
| Tách subscription bằng `subscribe()` | Không được giả định cùng transaction; thay bằng một chain duy nhất có kiểm chứng |

Chẩn đoán theo thứ tự:

1. **Kiểm tra loại transaction manager**: đang dùng `ReactiveTransactionManager` hay vô tình dùng `PlatformTransactionManager`? Với R2DBC dùng `R2dbcTransactionManager` phù hợp connection factory.
2. **Xác nhận event thực sự được phát**: publisher đã được subscribe chưa? `Mono<Void>` đã được nối đúng sau câu lệnh DB chưa?
3. **Kiểm tra source**: event dành cho reactive listener có `TransactionContext` không? Dùng `TransactionalEventPublisher` là cách chuẩn.
4. **Kiểm tra thời điểm**: `AFTER_COMMIT` chỉ chạy sau commit thành công; transaction rollback hoặc bị hủy thì không có callback after-commit. Cancellation trong reactive transaction cần được xử lý cẩn thận; đừng coi nó là commit.
5. **Tìm subscription bị tách**: `subscribe()` thủ công, callback chuyển sang hệ thống ngoài Reactor hoặc code tạo publisher nhưng không return.
6. **Kiểm tra lỗi thực thi listener**: event đã đăng ký nhưng listener có thể ném exception hoặc công việc phụ bất đồng bộ thất bại; dùng logging, metric và cơ chế retry phù hợp. Không nhầm “đã dispatch event” với “công việc phụ đã thành công”.
7. **Đọc lại dữ liệu từ connection độc lập sau khi transaction hoàn tất** để xác nhận commit/rollback, không dựa vào log “đã gọi INSERT”.

### Ghi nhớ

~~~text
ReactiveTransactionManager -> transaction trong Reactor Context
TransactionalEventPublisher -> event.source = TransactionContext
@TransactionalEventListener -> xử lý theo phase đã đăng ký
Mono/Flux -> phải nằm trong một reactive chain được subscribe
AFTER_COMMIT -> T1 đã commit; muốn ghi tiếp cần T2 rõ ràng
~~~

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionalEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework 6.2 — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionalOperator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html)
- [Spring Framework — R2DBC transaction management](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [R2DBC H2 project documentation](https://github.com/r2dbc/r2dbc-h2)
