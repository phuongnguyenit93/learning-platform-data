# Giới hạn khi trộn imperative và reactive trong Spring transaction events

Spring Framework hỗ trợ hai mô hình transaction khác nhau:

- **Imperative transaction** thường được quản lý bởi `PlatformTransactionManager`, chẳng hạn `DataSourceTransactionManager` hoặc `JpaTransactionManager`; ngữ cảnh transaction được gắn với **thread hiện tại** qua `ThreadLocal`.
- **Reactive transaction** được quản lý bởi `ReactiveTransactionManager`, chẳng hạn `R2dbcTransactionManager`; ngữ cảnh transaction nằm trong **Reactor Context của subscription** và đi theo một reactive pipeline thích hợp.

Cả hai đều có thể sử dụng `@TransactionalEventListener` từ **Spring Framework 6.1**, nhưng chúng **không chia sẻ cùng một ngữ cảnh transaction**. Vì vậy, khi trộn JDBC/JPA với R2DBC/Project Reactor hoặc gọi API phát event kiểu imperative từ một reactive flow, rất dễ hiểu sai lúc event được xử lý, bỏ lỡ listener `AFTER_COMMIT`, hoặc tạo ra những thao tác không nằm trong transaction như mong muốn.

Phạm vi bài này là **ranh giới và giới hạn khi phối hợp hai mô hình trong Spring Application Events**, không phải đánh giá tốc độ hay đề xuất thay thế toàn bộ ứng dụng sang reactive.

## 1. Hai mô hình transaction khác nhau ở đâu?

| Khía cạnh | Imperative | Reactive |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Nơi giữ transaction context | `ThreadLocal` của thread đang thực thi | `Reactor Context` gắn với subscription |
| API dữ liệu thường gặp | JDBC, JPA/Hibernate | R2DBC |
| Mã công việc | Phương thức thực thi trực tiếp, trả về kết quả bình thường | `Mono`/`Flux` mô tả công việc chỉ chạy khi có subscription |
| Công cụ transaction tường minh | `TransactionTemplate` | `TransactionalOperator` |
| Cách phát transactional event thường dùng | `ApplicationEventPublisher.publishEvent(...)` ngay trong transaction | `TransactionalEventPublisher.publishEvent(...)` bên trong reactive pipeline |
| Cách listener nhận ra transaction nguồn | Spring nhìn thấy transaction được bind ở thread lúc phát event | Event cần mang `TransactionContext` làm **source** để Spring liên kết với transaction reactive |

Với imperative:

```text
Thread hiện tại
  +-- TransactionTemplate / @Transactional (JDBC, JPA)
        +-- transaction context trong ThreadLocal
        +-- publishEvent(OrderCreated)
              +-- đăng ký callback AFTER_COMMIT
        +-- COMMIT
              +-- listener AFTER_COMMIT được gọi
```

Với reactive:

```text
Subscription của Mono/Flux
  +-- TransactionalOperator / @Transactional (R2DBC)
        +-- transaction context trong Reactor Context
        +-- TransactionalEventPublisher.publishEvent(OrderCreated)
              +-- đưa TransactionContext vào event.source
              +-- đăng ký callback AFTER_COMMIT cho transaction reactive
        +-- COMMIT khi publisher kết thúc thành công
              +-- listener AFTER_COMMIT được gọi
```

**Không có phép chuyển đổi tự động** biến một transaction JDBC gắn với `ThreadLocal` thành transaction R2DBC trong `Reactor Context`, hoặc ngược lại. Việc đặt một đoạn JDBC bên trong `Mono.fromCallable(...)` cũng không làm cho JDBC tham gia R2DBC transaction.

## 2. Vì sao `@TransactionalEventListener` hoạt động khác ở reactive?

Theo hợp đồng của Spring, `@TransactionalEventListener` hỗ trợ các pha:

- `BEFORE_COMMIT`: trước khi transaction nguồn commit.
- `AFTER_COMMIT`: sau khi transaction nguồn commit thành công; **mặc định**.
- `AFTER_ROLLBACK`: sau khi nguồn rollback.
- `AFTER_COMPLETION`: sau khi nguồn kết thúc, bất kể kết quả.

Nếu không có transaction phù hợp, listener **mặc định không chạy** (`fallbackExecution = false`).

### 2.1. Đường imperative: có thể phát trực tiếp

Trong một service JDBC/JPA đang chạy trên thread chứa transaction imperative, việc gọi:

```java
eventPublisher.publishEvent(new OrderCreated(42L));
```

cho phép Spring nhận biết transaction thread-bound ở thời điểm event được publish. Listener `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` sẽ được gắn với commit của transaction đó.

### 2.2. Đường reactive: event phải mang transaction context đúng cách

Trong một reactive transaction, việc chỉ gọi:

```java
Mono.fromRunnable(() ->
    eventPublisher.publishEvent(new OrderCreated(42L))
);
```

**không phải** cách đáng tin cậy để gắn transactional listener với transaction reactive. Khi callback publish thực thi, reactive transaction nằm trong `Reactor Context`, còn cơ chế tìm transaction kiểu imperative qua `ThreadLocal` không nhìn thấy nó. Event payload thông thường được phát bởi `ApplicationEventPublisher` cũng không tự chứa `TransactionContext` cần thiết.

Spring cung cấp `org.springframework.transaction.reactive.TransactionalEventPublisher`:

```java
TransactionalEventPublisher publisher =
        new TransactionalEventPublisher(applicationEventPublisher);

Mono<Void> publish = publisher.publishEvent(new OrderCreated(42L));
```

`publishEvent(...)` ở đây trả về **`Mono<Void>`**, có nhiệm vụ lấy `TransactionContext` của pipeline đang chạy và dùng ngữ cảnh đó làm **source** của event. Để thực sự publish và ràng buộc callback với transaction, phải **đưa Mono này vào cùng reactive chain** và subscribe từ luồng có transaction hợp lệ.

Ví dụ ý tưởng chính:

```java
Mono<Void> businessFlow =
        repository.save(order)
                  .then(transactionalEventPublisher.publishEvent(
                          new OrderCreated(order.id())));

return businessFlow.as(transactionalOperator::transactional);
```

Đây là **đoạn tích hợp minh họa**, giả định `repository.save(...)` trả về reactive publisher phù hợp, `transactionalOperator` dùng đúng `ReactiveTransactionManager` và `order` là đối tượng nghiệp vụ. `then(...)` bảo đảm bước publish được ghép theo sau bước lưu **trong cùng pipeline**. Transaction chỉ thật sự được mở khi chuỗi trả về được subscribe.

### 2.3. Không nhầm `event.source` với payload nghiệp vụ

Trong cách publish reactive, `TransactionContext` được dùng làm **source** của `ApplicationEvent`, không cần thay toàn bộ payload nghiệp vụ bằng đối tượng transaction. Với `TransactionalEventPublisher.publishEvent(Object)`, Spring có thể đóng gói payload thành một `PayloadApplicationEvent` mang source là transaction context, để phương thức listener tiếp tục nhận kiểu nghiệp vụ:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // Được gọi khi transaction reactive nguồn commit thành công.
}
```

Không nên tự tạo một `ApplicationEvent` với `source = this` hoặc nguồn tùy ý rồi cho rằng Spring biết nó thuộc reactive transaction nào. Nếu cần tự xây dựng event có source, API `publishEvent(Function<TransactionContext, ApplicationEvent>)` cho phép gắn đúng context.

## 3. Ví dụ Java 17+ chạy được: cùng reactive transaction, hai cách phát event khác nhau

Ví dụ sau sử dụng **Spring Framework 6.2**, H2 qua R2DBC và `TransactionalOperator`. Chúng ta tạo ba transaction reactive:

1. **T1:** lưu đơn `42` và phát event qua `TransactionalEventPublisher` — listener `AFTER_COMMIT` chạy.
2. **T2:** lưu đơn `43` nhưng gọi thẳng `ApplicationEventPublisher` từ `Mono.fromRunnable` — không truyền transaction context trong event, nên listener transaction-bound mặc định **bỏ qua** event đó.
3. **T3:** lưu đơn `44` và publish đúng cách, nhưng ném lỗi trước commit — transaction rollback, vì vậy listener `AFTER_COMMIT` **không chạy**.

Ví dụ dùng cơ sở dữ liệu trong bộ nhớ để so sánh dữ liệu đã commit; đây không phải mã triển khai hệ thống production.

Cấu trúc dự án:

```text
mixed-transaction-events/
├── pom.xml
└── src/main/java/MixedTransactionEventsDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mixed-transaction-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-r2dbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <version>1.0.0.RELEASE</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>MixedTransactionEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/MixedTransactionEventsDemo.java`:

```java
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public class MixedTransactionEventsDemo {

    public record OrderCreated(long id) {}

    public static class OrderListeners {
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderCreated event) {
            System.out.println("AFTER_COMMIT listener: " + event.id());
        }
    }

    private static long count(DatabaseClient db, long orderId) {
        Long result = db.sql("SELECT COUNT(*) FROM orders WHERE id = :id")
                .bind("id", orderId)
                .map((row, meta) -> row.get(0, Long.class))
                .one()
                .block();

        return result == null ? 0L : result;
    }

    public static void main(String[] args) {
        var connectionFactory = ConnectionFactories.get(
                "r2dbc:h2:mem:///mixed?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
        );

        var db = DatabaseClient.create(connectionFactory);
        db.sql("CREATE TABLE orders (id BIGINT PRIMARY KEY)")
                .fetch().rowsUpdated().block();

        var txManager = new R2dbcTransactionManager(connectionFactory);
        var txOperator = TransactionalOperator.create(txManager);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(OrderListeners.class);
            context.refresh();

            var reactivePublisher = new TransactionalEventPublisher(context);

            // T1: phát event đúng cách, gắn vào transaction R2DBC.
            Mono<Void> t1 =
                    db.sql("INSERT INTO orders (id) VALUES (42)")
                            .fetch().rowsUpdated()
                            .then(reactivePublisher.publishEvent(
                                    new OrderCreated(42)));

            t1.as(txOperator::transactional).block();
            System.out.println("T1 committed rows: " + count(db, 42));

            // T2: gọi publisher imperative; event không mang
            // TransactionContext của transaction reactive.
            Mono<Void> t2 =
                    db.sql("INSERT INTO orders (id) VALUES (43)")
                            .fetch().rowsUpdated()
                            .then(Mono.fromRunnable(() -> {
                                context.publishEvent(new OrderCreated(43));
                                System.out.println("T2 raw publish: 43");
                            }));

            t2.as(txOperator::transactional).block();
            System.out.println("T2 committed rows: " + count(db, 43));

            // T3: đã đăng ký AFTER_COMMIT nhưng transaction rollback.
            Mono<Void> t3 =
                    db.sql("INSERT INTO orders (id) VALUES (44)")
                            .fetch().rowsUpdated()
                            .then(reactivePublisher.publishEvent(
                                    new OrderCreated(44)))
                            .then(Mono.<Void>error(
                                    new IllegalStateException("reject order 44")));

            try {
                t3.as(txOperator::transactional).block();
            } catch (IllegalStateException ex) {
                System.out.println("T3 rolled back: 44");
            }
            System.out.println("T3 committed rows: " + count(db, 44));
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml` (cần JDK 17+, Maven; lần đầu Maven cần tải dependencies):

```bash
mvn -q compile exec:java
```

Các dòng chính do ứng dụng in ra, theo thứ tự (không tính log từ thư viện):

```text
AFTER_COMMIT listener: 42
T1 committed rows: 1
T2 raw publish: 43
T2 committed rows: 1
T3 rolled back: 44
T3 committed rows: 0
```

Giải thích:

- Ở **T1**, `TransactionalEventPublisher` tạo event có source là `TransactionContext`; Spring đăng ký listener với transaction R2DBC và gọi listener sau commit của T1.
- Ở **T2**, phần ghi database đã commit, nhưng `context.publishEvent(...)` tạo payload event không mang context của reactive transaction. `@TransactionalEventListener` không tìm thấy transaction phù hợp từ event này, nên không in `AFTER_COMMIT listener: 43`. Đây là **event listener bị bỏ qua**, không phải database transaction rollback.
- Ở **T3**, cách publish đúng nhưng transaction rollback trước commit, nên listener `AFTER_COMMIT` không chạy. Bản ghi `44` không tồn tại sau rollback.

Việc dùng `.block()` ở đây **chỉ nằm trong chương trình dòng lệnh** để chờ từng kịch bản hoàn tất và in kết quả có thứ tự. **Không copy `.block()` vào thread xử lý non-blocking của WebFlux/Netty**. Trong ứng dụng reactive thực tế, nên trả về `Mono`/`Flux` cho tầng trên subscribe và hoàn tất.

Lưu ý quan trọng: `@TransactionalEventListener` không tự bảo đảm giao event bền vững tới broker, tính chính xác đúng một lần, hay tự động retry khi listener thất bại. Nó chỉ ràng buộc callback với kết quả của transaction mà Spring nhận diện được.

## 4. Các giới hạn thực tế khi trộn hai mô hình

### 4.1. `ThreadLocal` và `Reactor Context` không thay thế nhau

Imperative transaction được bind với **thread** hiện tại. Khi gọi `subscribeOn` hoặc chạy tác vụ trên thread khác, không thể giả định transaction imperative `ThreadLocal` có mặt ở thread mới.

Ngược lại, **Reactor Context không đồng nghĩa với ThreadLocal**. Các operator Reactor tiêu chuẩn có thể duy trì Reactor Context qua một lần thay đổi thread hợp lệ trong **cùng subscription**, nhưng một lời gọi Java thông thường chỉ tìm transaction qua `ThreadLocal` vẫn không nhìn thấy transaction reactive.

Ví dụ:

```java
Mono<Void> flow = reactiveService.saveOrder(order)
        .publishOn(Schedulers.boundedElastic())
        .then(Mono.fromRunnable(() -> {
            // Không thể suy ra JDBC transaction đang hoạt động
            // chỉ vì flow này có reactive transaction.
            jdbcAuditService.writeAudit(order.id());
        }));
```

Đây là **đoạn minh họa tích hợp**, cần ứng dụng cung cấp `reactiveService`, `jdbcAuditService`, `order` và import Reactor scheduler. Ngay cả khi JDBC chạy trên scheduler dành cho blocking I/O, nó cũng không tự tham gia transaction R2DBC trước đó.

### 4.2. Gọi `subscribe()` tách rời làm mất quan hệ hoàn tất cần thiết

Sai lầm phổ biến:

```java
public Mono<Void> saveAndPublish(Order order) {
    reactiveRepository.save(order).subscribe(); // Subscription riêng.
    return transactionalEventPublisher.publishEvent(
            new OrderCreated(order.id()));
}
```

Đây là **mã sai để minh họa**, giả định `reactiveRepository.save(...)` là một publisher reactive. `subscribe()` ở giữa làm tác vụ lưu chạy độc lập; chuỗi trả về không còn bảo đảm lưu xong trước khi publish, và transaction context không được tự động chia sẻ với subscription mới.

Mẫu đúng là **compose** các publisher:

```java
public Mono<Void> saveAndPublish(Order order) {
    return reactiveRepository.save(order)
            .then(transactionalEventPublisher.publishEvent(
                    new OrderCreated(order.id())));
}
```

Phương thức ở trên là **đoạn tích hợp minh họa**. Nó vẫn phải được thực thi trong transaction reactive thật, ví dụ bằng `@Transactional("r2dbcTransactionManager")` trên phương thức được Spring quản lý qua proxy hoặc bằng `TransactionalOperator`. Chỉ ghép chuỗi là chưa đủ để tự sinh ra transaction.

### 4.3. Trả về `Mono` từ một phương thức gắn transaction JDBC

Mã như sau dễ làm người đọc nhầm:

```java
@Transactional("jdbcTransactionManager")
public Mono<Void> saveLater() {
    return Mono.fromRunnable(() ->
            jdbcTemplate.update("INSERT INTO audit(message) VALUES (?)", "ok"));
}
```

Đây là **mã minh họa một thiết kế có lỗi**, không phải chương trình độc lập. Nếu `jdbcTransactionManager` là `PlatformTransactionManager`, transaction imperative bao quanh **lời gọi phương thức**, trong khi `Mono.fromRunnable` chỉ chạy khi có subscription sau đó. Vì vậy công việc JDBC thực tế có thể chạy **sau khi transaction của phương thức đã đóng**. Không nên dùng chữ ký trả về `Mono` như bằng chứng rằng JDBC transaction sẽ được giữ mở tới khi publisher hoàn thành.

Để xử lý JDBC, hãy để transaction imperative bao trọn lời gọi JDBC thật, ví dụ trong một service Spring tách riêng có `@Transactional("jdbcTransactionManager")` và phương thức trả về kiểu thông thường. Nếu cần gọi service blocking đó từ reactive code, chuyển sang executor/scheduler thích hợp và chấp nhận rằng đây là **ranh giới transaction riêng**.

### 4.4. `.block()` không chuyển transaction qua lại

Gọi `.block()` trên `Mono` có thể kích hoạt một subscription để đợi kết quả. Nó **không chuyển** `TransactionContext` trong reactive pipeline sang `ThreadLocal` của JDBC/JPA và cũng không biến một JDBC transaction hiện có thành reactive transaction.

Ngoài việc làm mất lợi ích non-blocking, `.block()` trên thread được Reactor đánh dấu non-blocking (thường gặp trong các luồng WebFlux) có thể ném `IllegalStateException`. Ở các thread khác, blocking vẫn có thể làm cạn tài nguyên và giảm throughput.

Nếu bất khả kháng phải gọi thư viện imperative chặn thread từ một pipeline reactive, giới hạn tác vụ đó bằng một adapter có điều phối rõ ràng, ví dụ `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, và quản lý transaction JDBC trong chính service imperative được gọi. **`boundedElastic` chỉ giúp cách ly blocking I/O, không kết hợp hai transaction thành một**.

### 4.5. Hai transaction manager không tạo ra một transaction chung

Một ứng dụng có thể có đồng thời:

```java
@Transactional("jdbcTransactionManager")
public void writeLegacyTable() {
    // JDBC/JPA transaction.
}

@Transactional("r2dbcTransactionManager")
public Mono<Void> writeReactiveTable() {
    // R2DBC transaction.
    return reactiveRepository.save(...).then();
}
```

Đây là **mã khung minh họa**, các repository và cấu hình manager là thành phần của ứng dụng. Mỗi manager có connection, ranh giới commit và rollback riêng. Việc hai phương thức được gọi trong cùng một request **không bảo đảm atomicity** giữa hai nguồn dữ liệu.

Kịch bản có thể xảy ra:

```text
JDBC transaction:  COMMIT thành công
R2DBC transaction: lỗi -> ROLLBACK

Kết quả: dữ liệu JDBC đã lưu, dữ liệu R2DBC chưa lưu.
```

Nếu nghiệp vụ đòi hỏi tất cả thay đổi phải có cùng kết quả, cần thiết kế ranh giới transaction phù hợp hoặc một giao thức phối hợp có cam kết rõ. Các thiết kế thông thường khi đi qua nhiều nguồn dữ liệu/dịch vụ gồm **Transactional Outbox**, message retry có idempotency, hoặc **Saga/compensating action**. Không thể dùng riêng `@TransactionalEventListener` để tạo atomicity giữa JDBC và R2DBC.

### 4.6. Các pha listener có tính cục bộ theo transaction nguồn

Một listener `AFTER_COMMIT` gắn với transaction R2DBC chỉ có nghĩa là **transaction R2DBC nguồn** đã commit. Nó không chứng nhận transaction JDBC khác đã commit và cũng không đảm bảo event sẽ đến Kafka/RabbitMQ. Tương tự, một `AFTER_COMMIT` của JDBC không nói gì về tiến độ của một reactive pipeline độc lập.

Nếu listener thực thi một thao tác database mới sau commit, cần tạo **transaction mới rõ ràng** trong mô hình tương ứng. Ở callback sau commit, resource transaction cũ có thể còn được truy cập trong một thời gian, nhưng thao tác ghi mới không mặc nhiên được commit thêm lần nữa. Trong imperative flow, một service `@Transactional(propagation = REQUIRES_NEW)` qua Spring proxy có thể mở transaction riêng; với reactive flow cần sử dụng operator/manager reactive tương ứng và giữ publisher trong đúng lifecycle của nó.

## 5. Chọn API phát event theo transaction nào đang sở hữu nghiệp vụ

Một quy tắc ứng dụng:

1. Nếu nghiệp vụ được quản lý bằng **`PlatformTransactionManager`** và công việc đang chạy trong phương thức imperative đã mở transaction, sử dụng `ApplicationEventPublisher.publishEvent(...)` và `@TransactionalEventListener`.
2. Nếu nghiệp vụ được quản lý bằng **`ReactiveTransactionManager`**, sử dụng `TransactionalEventPublisher`, **ghép `Mono` publish vào chính pipeline**, và để subscription quản lý toàn bộ transaction.
3. Nếu đang ở **ranh giới chuyển đổi** từ imperative sang reactive, xác định giao dịch nguồn nào quyết định event có hợp lệ. Đừng dựa vào scheduler, thread hiện tại hay việc cùng dùng annotation `@Transactional` để đoán.
4. Nếu cần phát event sang hệ thống ngoài một cách bền vững, ghi một **outbox record trong cùng transaction của dữ liệu nguồn** rồi để worker độc lập gửi và retry. Sự kiện in-memory chỉ nên là một tín hiệu phụ trợ để worker bắt đầu sớm.

Một số lưu ý:

- **Đừng bật `fallbackExecution = true` chỉ để che lỗi mất transaction context.** Cờ này cho phép callback chạy ngay cả khi không có transaction phù hợp, nên có thể phá vỡ yêu cầu “chỉ xử lý sau commit thành công”.
- **Đừng dùng `@Async` hay `@Order` để sửa bài toán transaction context.** Chúng liên quan tới thực thi và ưu tiên listener, không chuyển transaction context từ Reactor sang `ThreadLocal`.
- **Đừng đặt nội dung công việc quan trọng vào một `Mono` rồi bỏ quên subscription.** Publisher chưa subscribe thường chưa làm gì.
- **Đừng cho rằng thay đổi thread luôn làm mất Reactor Context.** Context gắn với subscription; vấn đề là rời subscription hoặc truy cập bằng API chỉ biết `ThreadLocal`.
- **Đừng xem HTTP 500 là bằng chứng rollback.** Có thể transaction nguồn đã commit và lỗi xảy ra ở callback sau commit; client retry phải có idempotency.

## 6. Kiểm thử những điểm giao nhau

Kiểm thử bằng **database thực hoặc H2/R2DBC phù hợp**, có transaction manager đúng loại. Chỉ kiểm tra log từ listener không đủ để kết luận transaction đã commit.

| Trường hợp | Điều kiểm chứng |
| --- | --- |
| Reactive transaction + `TransactionalEventPublisher` + commit | Listener `AFTER_COMMIT` chạy, dữ liệu R2DBC tồn tại |
| Reactive transaction + publisher imperative trực tiếp + payload không mang `TransactionContext` | Listener transaction-bound mặc định không chạy, dù dữ liệu có thể đã commit |
| Reactive transaction + publish đúng nhưng rollback | Listener `AFTER_COMMIT` không chạy, dữ liệu rollback |
| Reactive transaction không được subscribe | Không thể khẳng định có transaction hoặc event được xử lý; phần công việc lazy thường chưa chạy |
| Phát event ngoài transaction với `fallbackExecution = false` | Listener transaction-bound bị bỏ qua |
| Gọi JDBC từ reactive flow | Transaction JDBC và R2DBC được kiểm thử riêng; không giả định atomicity |
| Hai manager với commit/rollback lệch nhau | Quan sát trạng thái cả hai nguồn và logic khôi phục/outbox |

Với Reactor, có thể dùng `StepVerifier` để kiểm chứng completion, error và cancellation của pipeline. Khi kiểm tra `AFTER_COMMIT`, phải chắc rằng transaction đã **thực sự hoàn tất**, rồi truy vấn database từ một kết nối/transaction độc lập. Chỉ nhận giá trị `onNext` chưa chứng minh transaction đã commit: reactive publisher có thể phát dữ liệu khi transaction còn đang mở.

Không nên viết test dựa vào `Thread.sleep(...)` để “chờ event” vì tạo tính bất định; với tác vụ bất đồng bộ dùng công cụ đồng bộ hóa hoặc trạng thái lưu bền vững. Test với blocking JDBC được gọi qua scheduler cần kiểm tra thread/resources và transaction thật, không chỉ mock phương thức repository.

## 7. Câu hỏi tự đánh giá

**1. Vì sao `@TransactionalEventListener` có thể không chạy khi gọi `applicationEventPublisher.publishEvent(...)` trong reactive transaction?**

Vì transaction R2DBC nằm trong `Reactor Context`, còn event thông thường không mang `TransactionContext` làm source và không có transaction imperative phù hợp trong `ThreadLocal`. Spring không thể gắn callback với transaction nguồn.

**2. Đổi từ `Mono.fromRunnable(...publishEvent...)` sang `TransactionalEventPublisher.publishEvent(...)` đã đủ chưa?**

Chưa. `Mono` publish phải nằm trong **reactive pipeline có transaction thực sự**, được subscribe và hoàn tất. Gọi nó rồi bỏ kết quả vẫn không publish.

**3. Dùng `publishOn(Schedulers.boundedElastic())` có làm transaction R2DBC biến thành JDBC transaction không?**

Không. Scheduler có thể đổi nơi chạy, nhưng không tạo transaction manager mới và không chuyển `Reactor Context` thành `ThreadLocal`.

**4. Nếu transaction JDBC đã commit mà reactive transaction lỗi, `@TransactionalEventListener` có rollback cả hai không?**

Không. Hai transaction độc lập có thể đạt hai kết quả khác nhau. Cần thiết kế nhất quán bằng transaction boundary phù hợp, outbox, idempotency hoặc hành động bù trừ.

**5. Nếu `@TransactionalEventListener(AFTER_COMMIT)` chạy nhưng gửi webhook lỗi thì transaction nguồn có rollback không?**

Không: lỗi của tác vụ sau commit không thể đảo quyết định commit đã hoàn thành. Hãy quản lý lỗi gửi webhook độc lập và áp dụng retry/idempotency nếu nghiệp vụ cần.

## Tài liệu chính thức và tham khảo kỹ thuật

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Programmatic Transaction Management và `TransactionalOperator`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework 6.2 — `@Transactional`, lựa chọn transaction manager](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2.9 — Javadoc `TransactionalEventListener`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2.9 — Javadoc `TransactionalEventPublisher`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [R2DBC H2 — README về ConnectionFactory và in-memory database](https://github.com/r2dbc/r2dbc-h2)
