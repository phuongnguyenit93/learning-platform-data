# Đưa transaction context vào event source

Trong **Spring Framework Application Events**, annotation `@TransactionalEventListener` có thể ràng buộc việc xử lý một sự kiện với pha `AFTER_COMMIT`, `AFTER_ROLLBACK`, `BEFORE_COMMIT` hoặc `AFTER_COMPLETION`. Tuy nhiên, khi ứng dụng dùng **reactive transaction**, Spring cần biết event thuộc về transaction nào, dù Reactor pipeline có thể chuyển thread. Từ **Spring Framework 6.1**, giải pháp chính thức là đặt **`TransactionContext` của transaction reactive hiện hành vào `source` của `ApplicationEvent`**.

Bài này giải thích lý do, cách dùng `TransactionalEventPublisher` và `TransactionContextManager`, cách tổ chức một Reactor pipeline đúng, và kiểm thử commit/rollback với Java 17+, Spring Test, R2DBC và JUnit 5.

## 1. Vì sao ReactiveTransactionManager cần event source đặc biệt?

Giao dịch JDBC/JPA thông thường gắn trạng thái transaction với thread; trong giới hạn thực thi đồng bộ, Spring có thể tra transaction ở `ThreadLocal`. Với `ReactiveTransactionManager`, trạng thái giao dịch nằm trong **Reactor subscriber Context**; các operator có thể thực thi trên các thread khác nhau mà vẫn cùng một subscriber context.

`ApplicationEventPublisher` chỉ chịu trách nhiệm chuyển event cho multicaster. Bản thân lời gọi `publishEvent(...)` không tự biến một đối tượng bất kỳ thành event đã mang transaction context reactive. Để `@TransactionalEventListener` đăng ký callback vào đúng transaction, Spring đọc `TransactionContext` được truyền qua **`ApplicationEvent.getSource()`**.

~~~text
Subscriber
  -> TransactionalOperator / reactive @Transactional
      -> Reactor Context: TransactionContext
      -> R2DBC INSERT/UPDATE
      -> publish ApplicationEvent
           source  = TransactionContext hiện hành
           payload = dữ liệu nghiệp vụ, ví dụ orderId
      -> transaction kết thúc
           commit   -> listener AFTER_COMMIT
           rollback -> listener AFTER_ROLLBACK
~~~

| Thành phần | Vai trò | Không nên hiểu thành |
| --- | --- | --- |
| `TransactionContext` | Ngữ cảnh của một reactive transaction, nằm trong Reactor Context | ID nghiệp vụ hoặc transaction serializable để gửi qua Kafka |
| `ApplicationEvent.source` | Cung cấp cho Spring context cần thiết để liên kết event với reactive transaction | Nơi tùy ý đặt một `String` hoặc `ApplicationContext` khi muốn xử lý sau commit |
| Payload/event field | Mang dữ liệu nghiệp vụ như order ID, loại tác vụ, correlation ID | Công cụ thay cho transaction synchronization |
| `TransactionalEventPublisher` | Lấy context khi publisher được subscribe, tạo event có `source` đúng | Một message broker hoặc bảo đảm giao nhận durable |

**Phân biệt:** mang `TransactionContext` trong source cho phép Spring quyết định **khi nào** gọi listener theo kết cục transaction. Nó không lưu event ra database, không bảo đảm chạy được nếu tiến trình sập sau commit, và không tự tạo transaction mới cho listener.

## 2. Cách ưu tiên: TransactionalEventPublisher

API `org.springframework.transaction.reactive.TransactionalEventPublisher` (Spring Framework 6.1+) là một delegate nhận `ApplicationEventPublisher`. Khai báo bean trong cấu hình Spring:

~~~java
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher publisher) {
    return new TransactionalEventPublisher(publisher);
}
~~~

Đây là trích đoạn bên trong lớp `@Configuration`. API có hai overload:

1. `Mono<Void> publishEvent(Object payload)`: Spring tự tạo `PayloadApplicationEvent` dùng `TransactionContext` hiện hành làm source.
2. `Mono<Void> publishEvent(Function<TransactionContext, ApplicationEvent> factory)`: truyền context vào factory để ứng dụng tạo một `ApplicationEvent` riêng.

### 2.1. Dùng payload record

~~~java
record OrderCreated(String orderId) { }

// transactionalEventPublisher là bean đã được inject:
Mono<Void> send = transactionalEventPublisher.publishEvent(
    new OrderCreated("O-42")
);
~~~

Listener trong một Spring bean có thể nhận payload và chỉ chạy sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
~~~

Hai đoạn trên là **trích đoạn**, cần định nghĩa/import record, bean, gateway và các annotation. `TransactionalEventPublisher` tạo `PayloadApplicationEvent<OrderCreated>` mà **source** là `TransactionContext`, nên listener theo transaction phase có đủ thông tin. Không lầm lẫn với lời gọi `ApplicationEventPublisher.publishEvent(new OrderCreated(...))` trực tiếp: publisher thường không chủ động gắn `TransactionContext` vào source.

### 2.2. Dùng ApplicationEvent tùy biến

Khi muốn event class riêng (để phân biệt loại event, mang metadata nghiệp vụ, hoặc kiểm tra source), định nghĩa:

~~~java
import org.springframework.context.ApplicationEvent;

final class OrderCreatedEvent extends ApplicationEvent {
    private final String orderId;

    OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    String orderId() {
        return orderId;
    }
}
~~~

Và publish theo factory:

~~~java
Mono<Void> send = transactionalEventPublisher.publishEvent(
    transactionContext -> new OrderCreatedEvent(
        transactionContext, "O-42"
    )
);
~~~

Khi publisher được subscribe bên trong reactive transaction, `event.getSource()` là instance của `org.springframework.transaction.reactive.TransactionContext`. Không cần tự đọc `ThreadLocal`, tự gắn source là `this`, hoặc truyền Reactor `ContextView` thay cho `TransactionContext`.

**Quan trọng:** `Mono<Void>` trả về chưa chạy khi mới được tạo. Phải nối `Mono` vào pipeline được subscribe. `TransactionalEventPublisher` không tự subscribe thay service.

## 3. Đưa publish vào đúng phạm vi transaction

Giả sử lưu đơn hàng bằng repository reactive rồi phát event. Cách đúng là ghép hai bước trong cùng pipeline và đặt **toàn bộ pipeline** vào `TransactionalOperator`:

~~~java
Mono<Void> operation = repository.save(order)
    .then(transactionalEventPublisher.publishEvent(
        ctx -> new OrderCreatedEvent(ctx, order.id())
    ));

return operation.as(transactionalOperator::transactional);
~~~

Đây là trích đoạn service, cần định nghĩa `repository`, `order`, các bean và class event. Vì cả `save()` lẫn publish nằm **bên trong** chuỗi được `TransactionalOperator` điều khiển, Spring lấy được `TransactionContext` đúng lúc publisher được subscribe. `then` bảo đảm phần lưu hoàn tất trước phần publish; listener `AFTER_COMMIT` vẫn phải đợi **commit**, không đơn thuần đợi `save()`.

Đối chiếu trường hợp sai:

~~~java
// Sai: kết thúc transaction của save trước khi thực hiện publish.
return repository.save(order)
    .as(transactionalOperator::transactional)
    .then(transactionalEventPublisher.publishEvent(
        ctx -> new OrderCreatedEvent(ctx, order.id())
    ));
~~~

Ở đây bước publish nằm **ngoài** transaction của thao tác lưu. Khi subscribe, `TransactionContextManager.currentContext()` không có transaction phù hợp; publisher có thể báo `NoTransactionException`.

Một cách khác là `@Transactional` trên service trả về `Mono` hoặc `Flux`, khi Spring dùng `ReactiveTransactionManager` và lời gọi thực sự đi qua Spring proxy:

~~~java
@Transactional
public Mono<Void> create(Order order) {
    return repository.save(order)
        .then(transactionalEventPublisher.publishEvent(
            ctx -> new OrderCreatedEvent(ctx, order.id())
        ));
}
~~~

Đoạn minh họa không phải file Java độc lập. Với reactive transaction, phương thức phải trả về kiểu reactive phù hợp; không tự gọi method `@Transactional` qua `this.create(...)` trong proxy mode mặc định rồi kỳ vọng Spring mở transaction.

### Tránh subscription lồng và side effect bị bỏ quên

~~~java
// Sai: tạo một subscription độc lập trong doOnNext.
return repository.save(order)
    .doOnNext(saved -> transactionalEventPublisher
        .publishEvent(new OrderCreated(saved.id()))
        .subscribe());
~~~

Cách này tách bước phát event khỏi pipeline cha, làm khó kiểm soát lỗi và transaction context. Gọi `publishEvent(...)` bên trong `doOnNext` mà **không subscribe/compose kết quả** còn khiến event không được phát. Dùng `flatMap`, `then`, hoặc `concatMap` phù hợp để nối các publisher và để subscriber ngoài cùng điều khiển toàn bộ tiến trình.

## 4. Cách thủ công với TransactionContextManager

`TransactionalEventPublisher` là tiện ích, không phải cách duy nhất. Spring cho phép lấy current context rồi trực tiếp đặt nó vào source của một event:

~~~java
Mono<Void> publication = TransactionContextManager.currentContext()
    .map(ctx -> new OrderCreatedEvent(ctx, orderId))
    .doOnNext(applicationEventPublisher::publishEvent)
    .then();

return publication.as(transactionalOperator::transactional);
~~~

Đây là trích đoạn, với `OrderCreatedEvent`, publisher và operator do ứng dụng cung cấp. Import `org.springframework.transaction.reactive.TransactionContextManager`. `currentContext()` trả về `Mono<TransactionContext>` từ Reactor subscriber context/holder; khi không tìm thấy context, nó phát lỗi `NoTransactionException`.

Dùng cách này khi phải tự kiểm soát việc dựng event. Đối với đa số nghiệp vụ, dùng `TransactionalEventPublisher.publishEvent(...) ` là gọn hơn và giảm nguy cơ quên source.

### Một event cần hai thông tin khác nhau

~~~text
OrderCreatedEvent
  source = TransactionContext  [chỉ sử dụng nội bộ Spring]
  orderId = "O-42"             [dữ liệu nghiệp vụ]
~~~

Không serialize `TransactionContext` vào payload HTTP, outbox, Kafka hoặc log. Nếu cần đẩy event ra bên ngoài, tạo message DTO riêng gồm thông tin nghiệp vụ cần dùng (ví dụ eventId, orderId, createdAt). Transaction context là trạng thái runtime trong JVM; nó không phải transaction ID có thể “khôi phục” ở tiến trình khác.

## 5. Ví dụ integration test với R2DBC và Spring Test

Bộ test sau dùng Java 17+, Spring Framework 6.2, R2DBC H2, `TransactionalOperator` và JUnit 5. Nó kiểm tra ba điều: event có source đúng; callback chạy ở pha commit/rollback thích hợp; và chưa subscribe thì chưa có side effect. Test không bị bọc trong test-managed JDBC transaction.

### 5.1. `build.gradle`

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.19')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-r2dbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dự án có Spring Boot nên dùng bộ phiên bản tương thích do BOM của Boot quản lý. H2 chỉ là database test, còn yêu cầu chính để xử lý reactive event là Spring Context, Spring Transaction và Reactor.

### 5.2. `src/test/java/example/events/ReactiveEventSourceTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionContext;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@SpringJUnitConfig(ReactiveEventSourceTest.Config.class)
class ReactiveEventSourceTest {

    @Autowired DatabaseClient client;
    @Autowired OrderService service;
    @Autowired Trace trace;

    @BeforeEach
    void reset() {
        client.sql("CREATE TABLE IF NOT EXISTS orders (" +
                "id VARCHAR(64) PRIMARY KEY)")
            .fetch().rowsUpdated().block();

        client.sql("DELETE FROM orders")
            .fetch().rowsUpdated().block();
        trace.clear();
    }

    @Test
    void commitInvokesListenerWithTransactionSource() {
        service.create("O-100", false).block();

        assertEquals(
            List.of("published:O-100:true", "commit:O-100"),
            trace.snapshot()
        );
        assertEquals(1, rowCount("O-100"));
    }

    @Test
    void rollbackSkipsAfterCommit() {
        assertThrows(IllegalStateException.class,
            () -> service.create("O-200", true).block());

        assertEquals(
            List.of("published:O-200:true", "rollback:O-200"),
            trace.snapshot()
        );
        assertEquals(0, rowCount("O-200"));
    }

    @Test
    void monoWithoutSubscriptionDoesNothing() {
        Mono<Void> notSubscribed = service.create("O-300", false);

        assertEquals(List.of(), trace.snapshot());
        assertEquals(0, rowCount("O-300"));
    }

    private int rowCount(String id) {
        return client.sql("SELECT COUNT(*) FROM orders WHERE id = :id")
            .bind("id", id)
            .map((row, meta) -> ((Number) row.get(0)).intValue())
            .one()
            .block();
    }

    static final class OrderCreatedEvent extends ApplicationEvent {
        private final String orderId;

        OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class Trace {
        private final List<String> values = new CopyOnWriteArrayList<>();

        void add(String value) {
            values.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        void clear() {
            values.clear();
        }
    }

    static final class OrderService {
        private final DatabaseClient client;
        private final TransactionalEventPublisher events;
        private final TransactionalOperator transaction;

        OrderService(DatabaseClient client,
                     TransactionalEventPublisher events,
                     TransactionalOperator transaction) {
            this.client = client;
            this.events = events;
            this.transaction = transaction;
        }

        Mono<Void> create(String id, boolean forceRollback) {
            Mono<Void> operation = client.sql(
                    "INSERT INTO orders(id) VALUES (:id)")
                .bind("id", id)
                .fetch()
                .rowsUpdated()
                .flatMap(affected -> {
                    if (affected != 1) {
                        return Mono.error(
                            new IllegalStateException("Insert failed"));
                    }
                    return events.publishEvent(
                        source -> new OrderCreatedEvent(source, id)
                    );
                })
                .then();

            if (forceRollback) {
                operation = operation.then(Mono.error(
                    new IllegalStateException("force rollback")));
            }
            return transaction.transactional(operation);
        }
    }

    static final class OrderListener {
        private final Trace trace;

        OrderListener(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public void onPublication(OrderCreatedEvent event) {
            boolean hasContext =
                event.getSource() instanceof TransactionContext;
            trace.add("published:" + event.orderId() + ":" + hasContext);
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onCommit(OrderCreatedEvent event) {
            trace.add("commit:" + event.orderId());
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRollback(OrderCreatedEvent event) {
            trace.add("rollback:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class Config {
        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                "r2dbc:h2:mem:///event_source_test" +
                "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
            );
        }

        @Bean
        DatabaseClient databaseClient(ConnectionFactory factory) {
            return DatabaseClient.create(factory);
        }

        @Bean
        ReactiveTransactionManager transactionManager(
                ConnectionFactory factory) {
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

        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        OrderListener orderListener(Trace trace) {
            return new OrderListener(trace);
        }

        @Bean
        OrderService orderService(DatabaseClient client,
                TransactionalEventPublisher events,
                TransactionalOperator transaction) {
            return new OrderService(client, events, transaction);
        }
    }
}
~~~

Chạy từ project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.ReactiveEventSourceTest"
~~~

Trên Windows PowerShell có thể dùng `./gradlew.bat` thay `./gradlew`. Test không in bản ghi event ra stdout; các dấu vết `published`, `commit`, `rollback` nằm trong `Trace` và được kiểm tra bằng assertion.

**Vì sao ba test này có ý nghĩa?**

- Test commit khẳng định listener thường nhận event có source `TransactionContext` và listener `AFTER_COMMIT` chỉ chạy khi giao dịch hoàn tất thành công. DB còn một bản ghi `O-100`.
- Test rollback khẳng định publish event không đồng nghĩa với đã commit: listener `AFTER_ROLLBACK` ghi nhận sự kiện, không xuất hiện `commit:O-200` và database không còn bản ghi.
- Test chưa subscribe khẳng định chỉ *tạo* `Mono` không thực hiện SQL hay publish. Điều này quan trọng vì nhiều lỗi reactive bắt nguồn từ việc quên compose publisher.

Ví dụ dùng cơ chế synchronous listener mặc định của context, còn transaction thì chạy bằng `ReactiveTransactionManager`. Nếu ứng dụng thay đổi cách dispatch sang async, cần kiểm thử thêm completion và lỗi bất đồng bộ, tránh suy từ lệnh `block()` ngoài cùng rằng mọi nhiệm vụ fire-and-forget đều đã hoàn thành.

## 6. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `new OrderCreatedEvent("myService", id)` | `source` không phải `TransactionContext` | Dùng factory của `TransactionalEventPublisher`, truyền `ctx` cho `super(ctx)` |
| Dùng `ApplicationEventPublisher.publishEvent(payload)` thường | Event không tự gắn Reactor transaction context | Dùng `TransactionalEventPublisher.publishEvent(payload)` |
| Đặt publish sau `.as(transactionalOperator::transactional)` | Transaction đã kết thúc trước publish | Bọc cả save và publish trong một transaction pipeline |
| Gọi `subscribe()` trong `doOnNext` | Tạo subscription khác và không kiểm soát được lỗi/context | Compose bằng `then` hoặc `flatMap` |
| Chỉ tạo `Mono<Void>` rồi bỏ đó | Không publish event | Bảo đảm publisher được subscribe trong pipeline chính |
| Dùng `ThreadLocal` để đọc reactive transaction | Không bền trước thay đổi thread | Dùng Reactor Context và `TransactionalEventPublisher` |
| `fallbackExecution = true` để “chữa” việc mất context | Listener có thể chạy dù không có transaction đúng | Giữ context/source đúng; chỉ bật fallback khi nghiệp vụ cho phép |
| Ghi DB trong listener `AFTER_COMMIT` mà không mở transaction mới | Không thể giả định có lần commit tiếp theo cho thay đổi đó | Bắt đầu transaction mới phù hợp và test readback |
| Gửi event vào Kafka kèm `TransactionContext` | Chuyển state nội bộ không có giá trị ngoài JVM | Tách business DTO, dùng outbox nếu cần giao nhận bền vững |

### Khi không có reactive transaction

Nếu subscription không có `TransactionContext` hiện hành, `TransactionContextManager.currentContext()` báo `NoTransactionException`. Với `@TransactionalEventListener` mặc định, event phát bên ngoài transaction thích hợp sẽ không được xử lý theo pha. `fallbackExecution = true` cho phép chạy cả khi không có transaction, nhưng đây là thay đổi **hợp đồng nghiệp vụ** chứ không phải cách khôi phục context bị thất lạc.

### Khi kết hợp với phương thức bất đồng bộ và các hệ thống khác

Context trong source giúp **đăng ký transaction synchronization** tại lúc phát event. Nó không bảo đảm listener tự thừa hưởng context để tiếp tục truy cập DB ở transaction đã hoàn tất, không cung cấp retry, và không tự biến một publisher được return từ listener thành công việc đã await.

Nếu sau commit phải gửi thông báo có độ bền cao, cân nhắc **transactional outbox**: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng database transaction; một worker đọc bản ghi đã commit và giao nhận với retry/idempotency. Event source nội bộ Spring vẫn không phải payload để giao cho broker.

## 7. Checklist và bài tập tự kiểm tra

- Xác nhận đang dùng Spring Framework **6.1+** và `ReactiveTransactionManager`.
- Xác nhận `TransactionalEventPublisher.publishEvent` được subscribe **bên trong** transaction pipeline.
- Với custom `ApplicationEvent`, truyền đúng context vào `super(source)`; giữ `orderId` trong field nghiệp vụ.
- Kiểm thử `AFTER_COMMIT` bằng transaction commit thật; kiểm thử rollback độc lập với nó.
- Nếu code sử dụng `@Transactional`, bảo đảm reactive return type và lời gọi đi qua Spring proxy.
- Nếu có async, broker hoặc cập nhật dữ liệu sau commit, thêm test cho ranh giới transaction và cơ chế giao nhận riêng.

**Câu hỏi 1:** Vì sao một `ApplicationEvent` có `source` là bean service chưa đủ cho reactive `AFTER_COMMIT`? Vì source đó không chứa `TransactionContext` của subscriber, nên Spring không thể liên kết callback với reactive transaction hiện hành.

**Câu hỏi 2:** `TransactionalEventPublisher.publishEvent(Object payload)` có tự dùng source đúng không? Có: nó tạo `PayloadApplicationEvent` mang `TransactionContext` hiện hành nếu được subscribe trong reactive transaction.

**Câu hỏi 3:** Có thể dùng `Mono` được tạo ngoài transaction nhưng subscribe nó bên trong không? Có, nếu quá trình lấy context và thực thi publish diễn ra **khi subscribe** trong pipeline transaction; điểm cần xem là phạm vi subscription thực tế.

**Câu hỏi 4:** Event đã được publish rồi mà transaction rollback thì listener `AFTER_COMMIT` có được gọi không? Không. Listener `AFTER_ROLLBACK` sẽ xử lý nếu đã đăng ký đúng pha và event được gắn transaction.

**Câu hỏi 5:** Đưa transaction context vào source có đồng nghĩa với giao nhận message exactly-once không? Không. Đây là cơ chế điều phối listener theo transaction nội bộ Spring, không phải cơ chế tin cậy xuyên tiến trình.

**Điểm cần nhớ:** `TransactionContext` trong `ApplicationEvent.source` là cầu nối giữa sự kiện Spring và **Reactor transaction context**. Dùng `TransactionalEventPublisher` để truyền nguồn chính xác; đặt publisher trong cùng reactive transaction chain để callback nhận đúng kết cục commit/rollback.

## Tài liệu tham khảo

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework – TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework – TransactionContextManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [Spring Framework – Reactive TransactionalOperator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html)
- [Spring Framework – R2DBC Data Access](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
