# Reactor Context và transaction context trong Spring Reactive Transaction Events

## 1. Vì sao bài học này quan trọng?

Trong ứng dụng Java theo kiểu imperative, Spring thường gắn trạng thái giao dịch với luồng thực thi bằng `ThreadLocal`. Nhưng trong ứng dụng reactive dùng Project Reactor, một pipeline có thể đi qua nhiều luồng, bị tạm dừng và tiếp tục khi dữ liệu sẵn sàng. Vì vậy, **reactive transaction không dựa vào ThreadLocal để xác định giao dịch đang hoạt động**. Spring liên kết giao dịch với **Reactor Context của subscription**.

Khác biệt đó ảnh hưởng trực tiếp đến application events: một `@TransactionalEventListener` chỉ có thể đăng ký xử lý theo pha `AFTER_COMMIT` hoặc `AFTER_ROLLBACK` của reactive transaction khi nó biết **TransactionContext** của giao dịch phát sự kiện. Từ Spring Framework 6.1, Spring hỗ trợ điều này thông qua việc **đặt TransactionContext làm source của ApplicationEvent**, thường bằng `TransactionalEventPublisher`.

Mục tiêu bài học:

- Hiểu `Context`/`ContextView` trong Reactor, `TransactionContext` của Spring và quan hệ giữa chúng.
- Biết cách `ReactiveTransactionManager` và `TransactionalOperator` gắn trạng thái transaction vào subscriber context.
- Phân biệt event phát thông thường với event có source chứa transaction context.
- Viết và kiểm tra `@TransactionalEventListener` cho cả commit và rollback trong R2DBC.
- Hiểu vì sao đổi thread, tạo subscription riêng, dùng `block()` hoặc `@Async` thiếu kiểm soát có thể làm mất các giả định về transaction.
- Phân biệt phạm vi event nội bộ JVM với cơ chế giao hàng bền vững của message broker.

## 2. Ba khái niệm dễ bị nhầm

| Khái niệm | Định nghĩa | Phạm vi |
|---|---|---|
| `ThreadLocal` | Giá trị gắn với một Java thread | Thread hiện tại; không tự theo logic khi đổi thread |
| Reactor `Context` / `ContextView` | Bộ dữ liệu key–value gắn với **subscriber**, được truyền qua các operator Reactor | Một chuỗi subscription, tùy vị trí `contextWrite` và ranh giới subscribe |
| Spring `TransactionContext` | Đối tượng lưu các thông tin tài nguyên và đồng bộ hóa transaction reactive do Spring quản lý | Transaction reactive cụ thể trong Reactor Context |

**Reactor Context không đồng nghĩa TransactionContext.** Reactor `Context` là cơ chế tổng quát: có thể chứa trace ID, tenant ID, thông tin bảo mật hoặc các khóa do framework quản lý. Spring `TransactionContext` là dữ liệu chuyên biệt mà transaction infrastructure đặt vào luồng ngữ cảnh này.

Đừng dùng `Reactor Context` như một biến toàn cục. Một subscription khác không được mặc định chia sẻ cùng context, dù hai subscription chạy trên cùng thread.

### Dữ liệu chạy theo subscription thay vì theo thread

Một pipeline minh họa:

~~~text
HTTP/WebFlux handler
   |
   | tạo Mono/Flux (assembly, chưa thực thi)
   v
Subscriber đăng ký (subscription)
   |
   | Reactor Context có các key của subscriber
   v
TransactionalOperator / @Transactional reactive
   |
   | TransactionContext được Spring gắn vào subscription
   v
DatabaseClient / R2DBC
   |
   | tra transaction state qua Reactor Context
   | sử dụng connection thích hợp với transaction
   v
Commit / Rollback khi publisher kết thúc
~~~

Thread có thể thay đổi trong quá trình thực thi, nhưng ngữ cảnh của cùng subscription được truyền qua các operator tuân thủ hợp đồng Reactor. Điều này **không có nghĩa** mọi thư viện, callback ngoài Reactor hoặc task tự tạo sẽ tự nhận ngữ cảnh.

## 3. Reactor Context hoạt động ra sao?

`reactor.util.context.Context` là cấu trúc key–value có ngữ nghĩa bất biến (*immutable API*): các thao tác `put`/`delete` tạo ra context mới. `ContextView` là giao diện chỉ đọc để truy xuất dữ liệu.

- `contextWrite(...)` tạo context hiệu lực cho các operator ở **phía upstream** tại thời điểm subscription.
- `Mono.deferContextual(...)` hoặc `Flux.deferContextual(...)` đọc context ở thời điểm subscribe, khi có subscriber thật.
- Context được truyền qua chuỗi Reactor theo hướng **downstream → upstream** ở giai đoạn subscription; vị trí đặt `contextWrite` vì vậy quan trọng.
- `publishOn(...)` có thể đổi thread xử lý tín hiệu, nhưng Reactor Context tiếp tục là ngữ cảnh subscriber; điều đó khác với `ThreadLocal`.
- Mỗi lời gọi `subscribe()`/`block()` có thể tạo subscription mới. Nếu tự tách một publisher ra khỏi chuỗi giao dịch hiện tại, không được giả định nó kế thừa transaction context.

Ví dụ Reactor thuần có thể đưa vào một class Java 17:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public class ReactorContextExample {
    public static void main(String[] args) {
        String result = Mono.deferContextual(view ->
                Mono.just("trace=" + view.get("traceId")))
            .contextWrite(Context.of("traceId", "REQ-123"))
            .block();

        System.out.println(result);
    }
}
~~~

Với dependency `io.projectreactor:reactor-core`, kết quả:

~~~text
trace=REQ-123
~~~

**Giải thích:** `deferContextual` truy xuất `traceId` khi Mono được subscribe bởi `block()`. `contextWrite` cấp dữ liệu cho đoạn phía upstream. Đặt `contextWrite` ở một nhánh khác không làm mọi publisher trên toàn ứng dụng nhìn thấy khóa đó.

Để thấy điều ngược lại, xét:

~~~java
Mono<String> source = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("traceId", "missing").toString()));

Mono<String> first = source.contextWrite(Context.of("traceId", "A"));
Mono<String> second = source.contextWrite(Context.of("traceId", "B"));
// first và second là hai publisher được cấu hình khác nhau.
// Khi subscribe riêng, chúng nhận A và B tương ứng.
~~~

Đoạn này minh họa; dùng các class/import Reactor trong dự án thực. Nó giúp tránh suy nghĩ rằng `Context` là biến được lưu toàn cục trên `source`.

## 4. Spring quản lý reactive transaction bằng Reactor Context

Trong mô hình imperative:

~~~text
PlatformTransactionManager
    -> ThreadLocal / TransactionSynchronizationManager (imperative)
    -> cùng thread thường cùng transaction
~~~

Trong mô hình reactive:

~~~text
ReactiveTransactionManager
    -> Reactor subscriber Context
    -> Spring TransactionContext / TransactionSynchronizationManager (reactive)
    -> những thao tác nằm trong cùng reactive chain có thể cùng transaction
~~~

Hai loại transaction manager khác nhau:

- `PlatformTransactionManager` dùng cho JDBC/JPA và các giao dịch truyền thống ràng buộc với thread.
- `ReactiveTransactionManager` dùng cho các driver reactive như R2DBC, với trạng thái giao dịch trong Reactor Context.
- `R2dbcTransactionManager` là một implementation của `ReactiveTransactionManager` dành cho `ConnectionFactory` R2DBC.
- `TransactionalOperator` cung cấp API khai báo ranh giới transaction *theo publisher*. Khi một subscriber đăng ký, Spring bắt đầu transaction, đặt ngữ cảnh thích hợp, rồi commit nếu hoàn tất thành công hoặc rollback khi lỗi/hủy theo hợp đồng cụ thể.

Ví dụ cấu hình:

~~~java
@Bean
ReactiveTransactionManager reactiveTransactionManager(ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Đây là **đoạn cấu hình**, cần import các class Spring và R2DBC, cùng một bean `ConnectionFactory`. Để giao dịch thực sự diễn ra, phải **subscribe** vào publisher đã được áp dụng operator:

~~~java
Mono<Void> operation = repository.save(order)
    .then()
    .as(transactionalOperator::transactional);

// Chỉ tạo Mono chưa thực thi DB, chưa commit.
return operation; // WebFlux sẽ subscribe để xử lý request.
~~~

Đoạn trên minh họa với một repository reactive giả định có phương thức `save`. Trong ứng dụng WebFlux thực, ưu tiên **trả Mono/Flux cho framework**; trong ví dụ dòng lệnh hoặc test có thể dùng `block()` tại điểm biên. Không sử dụng `block()` ở giữa logic đang chạy trên event loop WebFlux.

### TransactionContextManager.currentContext()

Spring cung cấp `org.springframework.transaction.reactive.TransactionContextManager.currentContext()` để lấy `Mono<TransactionContext>` của subscription hiện hành. API này đọc ngữ cảnh do Spring quản lý, gồm trường hợp transaction được giữ qua context holder, nên thích hợp hơn việc tự phỏng đoán khóa lưu trong `ContextView`.

Ví dụ minh họa bên trong một reactive transaction:

~~~java
Mono<Boolean> hasReactiveContext =
    TransactionContextManager.currentContext()
        .map(context -> context != null);
~~~

Đây là publisher chưa subscribe. Khi đặt nó trong cùng pipeline có reactive transaction, kết quả có thể là `true`; nếu không có transaction context, Spring báo lỗi thiếu context thay vì ngầm tạo transaction. Việc có `TransactionContext` không có nghĩa tại mọi thời điểm đều có một transaction đang *active*; khi cần kiểm tra trạng thái cụ thể, dùng contract của reactive transaction manager/synchronization manager.

**Không dùng** `org.springframework.transaction.support.TransactionSynchronizationManager` (phiên bản thread-bound) để kết luận có/không có reactive transaction. Spring có lớp tên tương tự trong package `org.springframework.transaction.reactive` với hợp đồng Mono/Context riêng.

## 5. Tại sao @TransactionalEventListener cần transaction context trong event source?

`ApplicationEventPublisher.publishEvent(...)` bản thân không phải API tạo transaction và cũng không tự chuyển toàn bộ Reactor Context cho một callback Java đồng bộ. Một listener giao dịch cần biết nó phải gắn callback vào **transaction nào**.

Với transaction JDBC thông thường, listener có thể lấy trạng thái transaction thông qua ThreadLocal lúc `publishEvent` chạy. Nhưng trong pipeline reactive, listener có thể được gọi ở bất kỳ thread nào và transaction state thuộc **subscriber Context**. Vì vậy, với reactive transaction, Spring cần `TransactionContext` nằm trong **source** của `ApplicationEvent`.

Luồng đúng về mặt ý tưởng:

~~~text
Mono/Flux đang nằm trong reactive transaction T1
       |
       | TransactionalEventPublisher.publishEvent(payload)
       v
TransactionContextManager.currentContext()
       |
       | lấy TransactionContext của T1
       v
PayloadApplicationEvent(source=TransactionContext, payload)
       |
       | delegate cho ApplicationEventPublisher.publishEvent
       v
@TransactionalEventListener
       |
       | dùng source để đăng ký transaction synchronization vào T1
       v
T1 COMMIT  ---> listener AFTER_COMMIT được gọi
T1 ROLLBACK ---> listener AFTER_ROLLBACK được gọi
~~~

Nếu phát một event POJO bằng `applicationEventPublisher.publishEvent(payload)` trực tiếp từ pipeline reactive mà không gắn transaction source, `@TransactionalEventListener` có thể không tìm thấy đúng reactive transaction và không thực thi như mong đợi. Với `fallbackExecution=false` (mặc định), sự kiện không có giao dịch phù hợp sẽ bị bỏ qua ở listener giao dịch.

Spring Framework 6.1+ cung cấp:

~~~java
import org.springframework.transaction.reactive.TransactionalEventPublisher;

// Thường khai báo thành bean:
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher publisher) {
    return new TransactionalEventPublisher(publisher);
}
~~~

Hai overload chính:

| API | Sử dụng khi |
|---|---|
| `publishEvent(Object payload)` | Có POJO/record payload; Spring tự tạo `PayloadApplicationEvent` với source là `TransactionContext` |
| `publishEvent(Function<TransactionContext, ApplicationEvent>)` | Cần tự tạo lớp sự kiện kế thừa `ApplicationEvent` và đặt source là `TransactionContext` |

Chú ý: `publishEvent(Object payload)` **không nhận một `ApplicationEvent` có sẵn** để tùy tiện thay source; với custom `ApplicationEvent`, dùng overload nhận function và tạo event mới bằng transaction context được cung cấp.

## 6. Phát event đúng bên trong transactional publisher

Ví dụ record payload:

~~~java
public record OrderPlaced(long orderId) {}
~~~

Service reactive:

~~~java
public Mono<Void> createOrder(long id) {
    return database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(transactionalEvents.publishEvent(new OrderPlaced(id)))
        .as(transactionalOperator::transactional);
}
~~~

Mã này là **đoạn tích hợp**: cần bean `database` kiểu `DatabaseClient`, `transactionalEvents` kiểu `TransactionalEventPublisher` và `transactionalOperator`. Việc `then(...)` rất quan trọng: đảm bảo publisher phát sự kiện nằm trong **cùng reactive chain** được điều hành bởi transaction operator, sau khi câu lệnh INSERT đã hoàn thành ở mức publisher. INSERT chưa được commit tại thời điểm event được phát; listener `AFTER_COMMIT` mới đợi commit thành công.

Không tự gọi:

~~~java
@Transactional // Giả sử đây là reactive transaction.
public Mono<Void> incorrect(long id) {
    database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .subscribe(); // Tạo subscription riêng, không còn ranh giới mong muốn.

    return Mono.empty();
}
~~~

Đây là **ví dụ sai có chủ đích**: một subscription nội bộ bằng `subscribe()` tạo luồng xử lý tách khỏi transaction mà phương thức `incorrect` trả về. Lỗi tương tự có thể xảy ra khi gọi `block()` bên trong pipeline, dùng `CompletableFuture` tự tạo hoặc tự ném công việc vào thread pool mà không truyền ngữ cảnh cần thiết. Không sửa bằng cách sao chép thủ công transaction context như một ThreadLocal; hãy cấu trúc một publisher thống nhất rồi để Spring subscribe.

### Custom ApplicationEvent và source

Nếu hệ thống cần loại `ApplicationEvent` riêng thay vì payload record:

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {

    private final long orderId;

    public OrderPlacedEvent(Object source, long orderId) {
        super(source);
        this.orderId = orderId;
    }

    public long orderId() {
        return orderId;
    }
}
~~~

Phát bằng overload function để giữ transaction source:

~~~java
return transactionalEvents.publishEvent(
    transactionContext -> new OrderPlacedEvent(transactionContext, orderId)
);
~~~

Các đoạn trên cần import `org.springframework.context.ApplicationEvent` và chạy **trong reactive transaction**. Không thay transactionContext bằng `this`, `null` hoặc một chuỗi tùy ý: listener giao dịch reactive cần source đúng kiểu `TransactionContext`.

## 7. Ví dụ đầy đủ Java 17 + R2DBC H2: commit có listener, rollback không có

Ví dụ này dùng Spring Framework **6.2.8**, Reactor và H2 với R2DBC; không cần Spring Boot hoặc một database server bên ngoài. Chương trình:

1. Tạo bảng `orders` trong H2 in-memory.
2. Bật giao dịch reactive bằng `R2dbcTransactionManager` và `TransactionalOperator`.
3. Chèn một hàng rồi phát event qua `TransactionalEventPublisher`.
4. Xác nhận listener `AFTER_COMMIT` chạy sau khi transaction thành công.
5. Thử chèn hàng thứ hai và ném lỗi để rollback; listener `AFTER_COMMIT` không chạy thêm.
6. Đọc số hàng thực tế trong database và in kết quả xác định.

Cấu trúc:

~~~text
reactive-event-demo/
├── pom.xml
└── src/main/java/demo/ReactiveEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-r2dbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.8</version>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <version>1.0.0.RELEASE</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ReactiveEventDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

public final class ReactiveEventDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DatabaseClient database = context.getBean(DatabaseClient.class);
            OrderCommands orders = context.getBean(OrderCommands.class);
            CommitListener listener = context.getBean(CommitListener.class);

            database.sql(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, status VARCHAR(20))"
            ).fetch().rowsUpdated().block();

            orders.saveAndPublish(1L, false).block();
            System.out.println("after success listener calls: "
                    + listener.handledCount());

            try {
                orders.saveAndPublish(2L, true).block();
            } catch (IllegalStateException expected) {
                System.out.println("rollback: " + expected.getMessage());
            }

            Long rows = database.sql("SELECT COUNT(*) AS total FROM orders")
                .map((r, meta) -> ((Number) r.get("total")).longValue())
                .one()
                .block();

            System.out.println("after rollback listener calls: "
                    + listener.handledCount());
            System.out.println("database rows: " + rows);
        }
    }

    public record OrderPlaced(long orderId) {}

    @Configuration
    public static class Config {

        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                "r2dbc:h2:mem:///rxevents?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
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
                ReactiveTransactionManager transactionManager) {
            return TransactionalOperator.create(transactionManager);
        }

        @Bean
        TransactionalEventPublisher transactionalEventPublisher(
                ApplicationEventPublisher publisher) {
            return new TransactionalEventPublisher(publisher);
        }

        @Bean
        OrderCommands orderCommands(
                DatabaseClient database,
                TransactionalEventPublisher publisher,
                TransactionalOperator operator) {
            return new OrderCommands(database, publisher, operator);
        }

        @Bean
        CommitListener commitListener() {
            return new CommitListener();
        }
    }

    public static final class OrderCommands {

        private final DatabaseClient database;
        private final TransactionalEventPublisher publisher;
        private final TransactionalOperator operator;

        OrderCommands(DatabaseClient database,
                TransactionalEventPublisher publisher,
                TransactionalOperator operator) {
            this.database = database;
            this.publisher = publisher;
            this.operator = operator;
        }

        public Mono<Void> saveAndPublish(long id, boolean fail) {
            Mono<Void> flow = database.sql(
                    "INSERT INTO orders (id, status) VALUES (:id, :status)")
                .bind("id", id)
                .bind("status", "NEW")
                .fetch()
                .rowsUpdated()
                .then(publisher.publishEvent(new OrderPlaced(id)));

            if (fail) {
                flow = flow.then(Mono.error(
                    new IllegalStateException("simulated failure")));
            }

            return operator.transactional(flow);
        }
    }

    public static final class CommitListener {

        private final AtomicInteger handled = new AtomicInteger();

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            handled.incrementAndGet();
            System.out.println("committed event: " + event.orderId());
        }

        int handledCount() {
            return handled.get();
        }
    }
}
~~~

Chạy trong thư mục `reactive-event-demo` bằng Java 17 và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReactiveEventDemo
~~~

Đầu ra do **chính chương trình** in (bỏ qua log phụ của Maven, nếu có):

~~~text
committed event: 1
after success listener calls: 1
rollback: simulated failure
after rollback listener calls: 1
database rows: 1
~~~

### Phân tích kết quả

- `AnnotationConfigApplicationContext` đăng ký bean listener và các thành phần reactive transaction.
- Lệnh INSERT vào H2 được chạy khi `saveAndPublish(...).block()` subscribe. `TransactionalOperator` bắt đầu transaction và thiết lập context của subscription.
- `TransactionalEventPublisher.publishEvent(new OrderPlaced(id))` lấy TransactionContext trong cùng chain, tạo `PayloadApplicationEvent` có source là TransactionContext, rồi chuyển cho `ApplicationEventPublisher`.
- `@TransactionalEventListener(AFTER_COMMIT)` đăng ký synchronization với transaction đó. Vì listener không có `@Async`, việc tăng bộ đếm và in thông báo diễn ra trong quá trình hoàn tất transaction trước khi Mono thành công trả tín hiệu cuối.
- Nhánh `fail = true` phát event trước khi trả về `Mono.error(...)`, nhưng transaction rollback nên callback `AFTER_COMMIT` không chạy.
- H2 dùng `DB_CLOSE_DELAY=-1` để giữ database in-memory khi các connection kết thúc; câu COUNT xác nhận chỉ hàng ID 1 được commit.

Ví dụ chủ động dùng `TransactionalOperator` nên không cần `@EnableTransactionManagement`. Nếu thay bằng `@Transactional` trên phương thức trả `Mono`, cần cấu hình reactive transaction manager và gọi qua Spring proxy.

**Giới hạn minh họa:** listener chỉ tăng bộ đếm trong bộ nhớ. Trong ứng dụng thực tế, việc gửi message hoặc thao tác I/O ở callback sau commit cần thiết kế riêng về publisher, retry, async và quan sát lỗi; không được tự nhận rằng callback đảm bảo delivery bền vững.

## 8. @Transactional reactive khác @Transactional imperative như thế nào?

Giả sử một phương thức trả `Mono<Void>` và được quản lý bởi `ReactiveTransactionManager`:

~~~java
@Transactional
public Mono<Void> createOrder(long id) {
    return database.sql("INSERT INTO orders(id) VALUES (:id)")
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(transactionalEvents.publishEvent(new OrderPlaced(id)));
}
~~~

Đây là mã tích hợp, cần được gọi qua transaction proxy, dùng `DatabaseClient` và publisher tương ứng. Spring transaction interceptor áp dụng transaction khi reactive publisher **được subscribe**, không chỉ khi method Java trả về `Mono`.

Phương thức imperative:

~~~java
@Transactional
public void createOrderImperative(long id) {
    jdbcTemplate.update("INSERT INTO orders(id) VALUES (?)", id);
    applicationEventPublisher.publishEvent(new OrderPlaced(id));
}
~~~

được quản lý theo `PlatformTransactionManager`/ThreadLocal. Hai đoạn dùng cùng annotation nhưng khác loại resource và cách lưu transaction context. Với application vừa có JDBC/JPA vừa có R2DBC, phải chọn transaction manager đúng cho từng operation và không mặc định một transaction sẽ bao trùm cả hai công nghệ.

Các điểm phân biệt:

| Đặc điểm | Imperative transaction | Reactive transaction |
|---|---|---|
| Manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Ngữ cảnh | Thread-bound state | Reactor subscriber Context |
| Ranh giới bắt đầu | Thường khi proxy gọi method | Khi publisher được subscribe |
| Đổi thread | ThreadLocal không tự theo | Context theo subscription qua Reactor operators |
| Data access | JDBC / JPA | R2DBC hoặc API reactive có tích hợp |
| Publish event cho transactional listener | Event thông thường có thể dùng ThreadLocal | Cần source mang `TransactionContext` |
| Tham chiếu đúng API đồng bộ hóa | `org.springframework.transaction.support` | `org.springframework.transaction.reactive` |

Chú ý trong Spring transaction abstraction, phương thức `@Transactional` dùng reactive manager thường cần trả về reactive publisher (hoặc dạng hỗ trợ tương ứng). Phương thức `void`/trả object thông thường không tự biến thành reactive transaction chỉ vì được gọi từ reactive controller.

## 9. Thời điểm transaction phase và sự kiện reactive

Bốn pha chính của `@TransactionalEventListener`:

| Phase | Khi listener được gọi | Ý nghĩa |
|---|---|---|
| `BEFORE_COMMIT` | Trước khi commit | Chưa được khẳng định dữ liệu đã commit |
| `AFTER_COMMIT` | Transaction commit thành công | Phù hợp để kích hoạt xử lý hậu commit |
| `AFTER_ROLLBACK` | Transaction rollback | Phù hợp phản ứng với hủy giao dịch |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Hành vi không phân biệt hai kết quả nếu không tự kiểm tra |

`AFTER_COMMIT` là giá trị mặc định của annotation. Nếu không có transaction phù hợp, listener mặc định không chạy; chỉ bật `fallbackExecution = true` khi có ý định xử lý cả trường hợp không có transaction. **`fallbackExecution` không khiến `TransactionalEventPublisher` tự tạo transaction:** helper này vẫn cần current `TransactionContext` để tạo đúng event source.

Ngay cả sau `AFTER_COMMIT`, tài nguyên gắn với transaction cũ có thể còn khả dụng khi callback chạy; gọi I/O hoặc cập nhật database trong callback không đồng nghĩa nó tự có transaction mới. Với thao tác hậu commit cần ghi bền, mở ranh giới giao dịch mới phù hợp, hoặc dùng outbox. Điều này áp dụng ở cả mô hình imperative và reactive, nhưng cách tạo pipeline/transaction mới khác nhau.

### Có nên dùng @Async cùng @TransactionalEventListener?

Có thể có mục tiêu chuyển phần xử lý nặng sang executor, nhưng cần phân biệt **đăng ký transaction synchronization** (phải diễn ra trong ngữ cảnh transaction của event) với **thực hiện công việc sau khi transaction hoàn tất**.

Một số điểm cần nhớ:

- Từ Spring 6.1, các transactional application listener yêu cầu thực thi phần xử lý đăng ký theo ngữ cảnh gốc, không bị tùy tiện chuyển sang executor của multicaster.
- Nếu phần thân listener sau commit có `@Async`, công việc có thể chạy ở thread khác, nơi không có ThreadLocal của publisher; đừng giả định có thể truy cập transaction cũ.
- Với Reactor, callback đồng bộ không tự trở thành một subscriber có transaction context chỉ vì event source chứa `TransactionContext`.
- Nếu phải chạy reactive I/O sau commit, cần thiết kế subscription độc lập có quản lý lỗi và trạng thái hoặc queue/outbox, **không lồng `subscribe()` tùy tiện** trong pipeline nghiệp vụ.

Hãy giữ listener giao dịch gọn, dành những side effect quan trọng cho cơ chế có thể theo dõi và khôi phục khi thất bại.

## 10. Các lỗi thường gặp khi chuyển từ ThreadLocal sang Reactor Context

### Lỗi 1: Dựa vào Thread.currentThread() để xác định transaction

Một reactive publisher có thể bắt đầu trên thread A, tiếp tục trên B sau `publishOn` hoặc khi R2DBC phát tín hiệu. Tên thread hay việc truy vấn ThreadLocal imperative không chứng minh transaction reactive nào đang hoạt động.

**Cách đúng:** giữ công việc trong cùng reactive chain, dùng `TransactionalOperator`/reactive `@Transactional` và API reactive transaction context của Spring.

### Lỗi 2: Gọi publishEvent(Object) trực tiếp rồi chờ AFTER_COMMIT

~~~java
Mono<Void> wrong = database.sql("INSERT INTO orders(id) VALUES (123)")
    .fetch().rowsUpdated()
    .doOnSuccess(ignored -> applicationEventPublisher.publishEvent(
        new OrderPlaced(123)))
    .then()
    .as(transactionalOperator::transactional);
~~~

Dù callback phát xảy ra trong pipeline, `ApplicationEventPublisher` thông thường không tự đóng gói source thành `TransactionContext`. Với reactive transaction, listener `@TransactionalEventListener` thiếu nguồn cần thiết.

**Cách đúng:** dùng `TransactionalEventPublisher.publishEvent(new OrderPlaced(123))` làm một bước trong chuỗi thay vì `doOnSuccess` gọi publisher thông thường.

### Lỗi 3: Gọi subscribe() bên trong một transaction

~~~java
Mono<Void> wrong = database.sql("UPDATE orders SET status='READY'")
    .fetch().rowsUpdated()
    .doOnNext(count -> otherMono.subscribe())
    .then()
    .as(transactionalOperator::transactional);
~~~

`otherMono.subscribe()` tạo subscription riêng. Nó không kế thừa transaction context theo cách mà chuỗi chính được điều hành. Nếu cần thứ tự thực thi và chung transaction, cấu trúc `flatMap`/`then`/`concatMap` để kết hợp publisher trước khi áp dụng transaction operator.

### Lỗi 4: Tạo Mono nhưng không subscribe

~~~java
Mono<Void> eventMono = transactionalEvents.publishEvent(new OrderPlaced(1));
// Chỉ assembly; không có subscribe thì chưa có publication.
~~~

Khác với `ApplicationEventPublisher.publishEvent` trả `void` và gọi trực tiếp, `TransactionalEventPublisher.publishEvent` trả `Mono<Void>`. Nó là thao tác reactive cần được subscribe như một phần của chain. Trong chương trình server, để framework subscribe; trong test dùng `StepVerifier` hoặc `block()` ở ranh giới an toàn.

### Lỗi 5: Bỏ qua rollback, cancellation, timeout

Reactive transaction có thể rollback do lỗi hoặc hủy subscription. Nếu event đã đăng ký nhưng transaction rollback thì listener `AFTER_COMMIT` không chạy. Không dựa vào “đã gọi publisher” để kết luận “sự kiện đã được xử lý”.

### Lỗi 6: Lạm dụng Context như kho dữ liệu nghiệp vụ

`Context` được thiết kế cho metadata theo subscription, không thay thế database, payload sự kiện hoặc cơ chế giao hàng bền vững. Để listener xử lý đúng, đưa các dữ liệu nghiệp vụ cần thiết vào payload (ví dụ order ID, version), còn `TransactionContext` ở source phục vụ ràng buộc với transaction.

### Lỗi 7: Đặt contextWrite sai chỗ

~~~java
Mono<String> flow = Mono.deferContextual(ctx ->
        Mono.just(ctx.get("traceId").toString()));

Mono<String> correct = flow.contextWrite(Context.of("traceId", "X"));
~~~

Ví dụ này cho `flow` thấy key. Nếu `contextWrite` nằm trên một nhánh không phải nguồn mà listener subscribe, hoặc được thêm sau một subscription đã hoàn thành, nó không cấp dữ liệu như mong đợi. Với transaction Spring, **đừng tự chèn `TransactionContext` tùy ý bằng `contextWrite`**; để transaction infrastructure quản lý lifecycle và resources.

## 11. Kiểm thử và quan sát hành vi

Một kiểm thử tích hợp tốt cần có ít nhất hai nhánh:

1. **Commit:** trong transaction reactive, INSERT/update, gọi `TransactionalEventPublisher`, rồi hoàn thành bình thường. Xác nhận `@TransactionalEventListener(AFTER_COMMIT)` chạy và database chứa dữ liệu.
2. **Rollback:** cùng chuỗi nhưng phát lỗi trước khi commit. Xác nhận listener `AFTER_COMMIT` không chạy và database rollback thay đổi.

Dùng `StepVerifier` để subscribe và kiểm tra completion/error trong test Reactor:

~~~java
StepVerifier.create(orderCommands.saveAndPublish(1L, false))
    .verifyComplete();

StepVerifier.create(orderCommands.saveAndPublish(2L, true))
    .expectError(IllegalStateException.class)
    .verify();
~~~

Đây là **đoạn test tích hợp**, cần dependency `io.projectreactor:reactor-test` và cấu hình JUnit/test data. Không thêm đoạn này vào class main của ví dụ vì sẽ cần test scope/dependencies và dữ liệu riêng.

Để quan sát đúng, có thể ghi:

- Transaction ID hoặc correlation ID của ứng dụng (không mặc định Spring cung cấp ID bền vững).
- Loại event, ID/version payload, transaction phase, listener được chọn.
- Thời điểm INSERT/update, publication, commit/rollback, callback bắt đầu/kết thúc.
- Tên executor/thread cho mục đích chẩn đoán, nhưng không dùng nó thay thế định danh transaction.
- Số event được phát, số callback thành công, số lỗi, độ dài queue/outbox nếu có.

Với ứng dụng nhiều subscriber, cần kiểm tra ranh giới context ở các operator `flatMap`, `publishOn`, `retry`, callback ngoài Reactor và những nơi tự gọi `subscribe()`. Đặc biệt, `retry` có thể dẫn đến **subscription mới** và việc thực thi lại cả thao tác database; nếu pipeline phát event và xử lý nghiệp vụ không idempotent, có thể có lặp tác dụng phụ.

## 12. Vòng đời event không phải delivery bền vững

`TransactionalEventPublisher` chỉ cung cấp phương tiện xuất bản event mang reactive transaction context để `@TransactionalEventListener` đăng ký đúng phase. Nó **không phải** một message broker:

| Nhu cầu | Event trong JVM | Cần bổ sung khi nghiêm ngặt |
|---|---|---|
| Chờ commit trước khi xử lý | `@TransactionalEventListener(AFTER_COMMIT)` | Đảm bảo publication nằm trong cùng subscription |
| Không xử lý khi rollback | Có theo transaction phase | Kiểm thử rollback/cancellation |
| Sau crash vẫn còn sự kiện | Không có bảo đảm mặc định | Transactional outbox, broker và recovery |
| Retry khi listener thất bại | Không tự động có | Retry policy, DLQ hoặc job queue |
| Truyền context qua service khác | Không tự động | Explicit headers/payload; tracing propagation |
| Đúng một lần toàn hệ thống | Không có mặc định | Thiết kế idempotency, deduplication, giao dịch liên quan |

Nếu tác vụ sau commit rất quan trọng, hãy ghi một outbox record cùng transaction business, sau đó một worker đọc outbox, gửi message và đánh dấu kết quả. Với database R2DBC, thao tác ghi outbox cần cùng transaction reactive có kiểm chứng; nếu kết hợp nhiều nguồn dữ liệu, phải xác định rõ giới hạn atomicity.

## 13. Câu hỏi ôn tập

**1. Reactor Context có phải TransactionContext không?** Không. Reactor Context là cơ chế key–value theo subscriber; TransactionContext là trạng thái giao dịch chuyên biệt do Spring quản lý ở đó.

**2. Transaction reactive có tự đi theo ThreadLocal không?** Không. Spring liên kết trạng thái reactive transaction với Reactor subscriber Context.

**3. Vì sao cần TransactionalEventPublisher?** Vì transactional listener cần `TransactionContext` nằm trong **event source** để gắn với transaction reactive. Publisher này tạo event đúng và trả Mono cho phép kết hợp vào pipeline.

**4. Có thể gọi `publishEvent(Object payload)` với một `ApplicationEvent` đã tạo không?** Không theo overload đó; nếu muốn tạo custom ApplicationEvent hãy dùng overload function nhận TransactionContext và trả về event có source đúng.

**5. Khi nào event được phát?** Khi Mono do `TransactionalEventPublisher.publishEvent` được subscribe trong chain; việc chỉ gọi method để lấy Mono chưa phát.

**6. Nếu transaction rollback thì listener AFTER_COMMIT có chạy không?** Không. Chọn `AFTER_ROLLBACK` nếu cần xử lý riêng khi rollback.

**7. Đổi thread bằng publishOn có khiến Reactor Context luôn mất?** Không; Reactor Context gắn với subscription. Nhưng ThreadLocal và callback tự tạo bên ngoài chuỗi không tự được bảo toàn.

**8. Có nên dùng raw `subscribe()` ở giữa business flow?** Thường không: nó tách subscription, làm ranh giới giao dịch và lỗi khó kiểm soát.

**9. Có nên tự đặt `TransactionContext` vào Reactor Context để giả lập transaction?** Không: transaction manager còn quản lý connection, synchronization, commit/rollback và cleanup.

**10. Sau AFTER_COMMIT có được đảm bảo message đã đến broker không?** Không. Transaction phase chỉ nói về kết quả transaction local; phải thiết kế delivery và retry riêng.

## 14. Ghi nhớ cốt lõi

**Reactor Context giữ ngữ cảnh theo subscription. Spring TransactionContext giữ trạng thái giao dịch reactive và được transaction manager quản lý qua Reactor Context.** Khi phát transaction-bound application events, event phải mang TransactionContext ở `source`. Cách thuận tiện là dùng `TransactionalEventPublisher.publishEvent(...)` và ghép Mono trả về vào cùng pipeline đang được `ReactiveTransactionManager` hoặc `TransactionalOperator` điều hành.

Đừng dùng ThreadLocal hay tên thread để suy đoán reactive transaction; đừng để một publisher tự `subscribe()` tách khỏi chain. Kiểm tra cả commit, rollback, pha xử lý và xử lý lỗi; dùng outbox/broker khi cần độ bền hoặc giao hàng liên tiến trình.

### Tài liệu đối chiếu

- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 Reference — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework Javadoc — TransactionContextManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [Spring Framework Reference — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html)
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
