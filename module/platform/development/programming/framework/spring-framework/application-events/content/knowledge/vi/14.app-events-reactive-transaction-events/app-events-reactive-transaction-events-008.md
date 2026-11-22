# Kiểm thử reactive transaction event trong Spring Framework

## 1. Mục tiêu

Reactive transaction event là sự kiện Spring được gắn với vòng đời của **reactive transaction** do `ReactiveTransactionManager` quản lý. Khi kiểm thử, điều cần chứng minh không chỉ là listener có nhận event hay không, mà còn là **listener nhận ở phase nào, transaction commit hay rollback, và dữ liệu thật sự được lưu hay hoàn nguyên**.

Sau bài này, bạn có thể:

- Phân biệt reactive transactional event với event chạy trong imperative transaction do `PlatformTransactionManager` quản lý.
- Tạo reactive transaction bằng `TransactionalOperator`, phát event bằng `TransactionalEventPublisher` và đăng ký callback với `@TransactionalEventListener`.
- Kiểm thử `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION` bằng JUnit 5 và `StepVerifier`.
- Kết hợp kiểm tra callback với truy vấn dữ liệu R2DBC sau khi transaction kết thúc.
- Kiểm thử trường hợp phát event ngoài transaction, mất transaction context, `Mono` chưa subscribe và sai cách compose.
- Tránh test PASS giả do mock sai transaction manager, dùng publisher thường, bỏ qua terminal signal hoặc dựa vào `Thread.sleep`.

Bài tập trung vào Spring Framework 6.1+ và ví dụ Java 17+, Spring 6.2.x với R2DBC H2. Đây là kiến thức về **kiểm thử reactive transaction event**, không phải kiến trúc messaging hoặc hệ thống hàng đợi bền vững.

## 2. Reactive transactional event hoạt động như thế nào?

Spring hỗ trợ `@TransactionalEventListener` từ trước khi có reactive transaction. Từ Spring Framework 6.1, annotation này còn hỗ trợ transaction do `ReactiveTransactionManager` quản lý. Điểm khác biệt chính nằm ở **nơi lưu transaction context**:

| Cơ chế | Transaction manager | Transaction context | Cách phát event |
| --- | --- | --- | --- |
| Imperative JDBC/JPA | `PlatformTransactionManager` | ThreadLocal gắn với thread đang chạy | `ApplicationEventPublisher.publishEvent(...)` bên trong transaction |
| Reactive R2DBC | `ReactiveTransactionManager` | `Reactor Context` của luồng reactive | `TransactionalEventPublisher` để đưa `TransactionContext` vào source của event |

Trong reactive programming, một luồng xử lý có thể được thực thi qua nhiều thread. Không được suy luận transaction reactive tồn tại chỉ vì một phương thức đang chạy trên thread từng mở transaction. `ReactiveTransactionManager` và các resource reactive sử dụng ngữ cảnh được truyền qua **subscription**.

`TransactionalEventPublisher.publishEvent(payload)` trả về một `Mono<Void>`. Khi Mono này được **subscribe trong reactive transaction**, wrapper lấy `org.springframework.transaction.reactive.TransactionContext` hiện tại, tạo một `PayloadApplicationEvent` có source là TransactionContext rồi phát qua `ApplicationEventPublisher`. Phía `@TransactionalEventListener` nhận biết transaction và đăng ký callback tương ứng phase.

~~~text
StepVerifier.subscribe()
       |
       v
TransactionalOperator mở reactive transaction
       |
       v
R2DBC thao tác dữ liệu trong transaction
       |
       v
TransactionalEventPublisher.publishEvent(payload)
       |
       +--> đọc TransactionContext từ Reactor Context
       +--> tạo PayloadApplicationEvent(source=TransactionContext)
       +--> Spring phân phối event và đăng ký synchronization
       |
       v
Pipeline kết thúc
       |
       +--> onComplete -> commit:
       |    BEFORE_COMMIT -> commit -> AFTER_COMMIT -> AFTER_COMPLETION
       |
       +--> onError -> rollback:
            AFTER_ROLLBACK -> AFTER_COMPLETION
~~~

Sơ đồ mô tả **đường đi thông thường**; vẫn có những trường hợp commit thất bại hoặc transaction đã rollback-only, khiến outcome khác với tín hiệu thành công từ phần nghiệp vụ.

## 3. Hiểu chính xác bốn transaction phase

`@TransactionalEventListener` dùng `TransactionPhase`. Nếu không khai báo `phase`, mặc định là `AFTER_COMMIT`.

| Phase | Lúc được gọi | Ca kiểm thử cần có |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit tài nguyên thực tế, khi transaction đang hoàn tất theo nhánh commit | Có mặt trên nhánh commit; thường không chạy nếu pipeline đã lỗi và transaction rollback |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Có mặt khi commit; không có khi rollback |
| `AFTER_ROLLBACK` | Sau rollback | Có mặt khi rollback; không có khi commit |
| `AFTER_COMPLETION` | Khi transaction đã hoàn tất, bất kể commit hay rollback | Có mặt ở cả hai trường hợp |

Các sự kiện ở phase sau hoàn tất transaction vẫn có thể nhìn thấy tài nguyên cũ trong một số trường hợp, nhưng **không được tự giả định ghi dữ liệu mới ở `AFTER_COMMIT` sẽ được commit**. Nếu cần thao tác dữ liệu mới sau commit, nên khởi tạo transaction mới phù hợp.

Điểm dễ nhầm: **đã chạy `BEFORE_COMMIT` không chứng minh commit thành công**. Một lỗi database xảy ra ở bước commit vẫn có thể dẫn tới thất bại. Vì thế, test phải xác nhận outcome của transaction và trạng thái dữ liệu sau khi commit, thay vì chỉ xác nhận listener `BEFORE_COMMIT` được gọi.

Nếu event được phát ngoài transaction, `@TransactionalEventListener` theo mặc định **không xử lý** vì không có phase nào để gắn callback. Tùy chọn `fallbackExecution = true` là cơ chế dự phòng riêng; test cần tách nó khỏi các test transaction thực sự.

## 4. Thiết kế ma trận kiểm thử

Trước khi viết code, hãy xác định đầu vào, tín hiệu kết thúc và bằng chứng mong đợi:

| Test case | Phát event | Tín hiệu pipeline | Callback mong đợi | Trạng thái DB |
| --- | --- | --- | --- | --- |
| Commit thành công | Trong `TransactionalOperator`, wrapper reactive | `onComplete` | BEFORE, AFTER_COMMIT, AFTER_COMPLETION | Insert tồn tại |
| Rollback do lỗi | Sau insert, trong transaction, rồi `onError` | `onError` có nguyên nhân rõ ràng | AFTER_ROLLBACK, AFTER_COMPLETION | Insert bị rollback |
| Ngoài transaction | `ApplicationEventPublisher` thường | Lời gọi đồng bộ trả về | Không listener transaction nào chạy | Không đổi |
| Wrapper ngoài transaction | `TransactionalEventPublisher` nhưng thiếu context | Mono phát lỗi khi subscribe | Không callback nào | Không đổi |
| Chưa subscribe | Chỉ xây dựng `Mono` | Không có terminal signal | Không callback nào | Không đổi |
| Publisher thường trong reactive transaction | Có transaction nhưng event không mang transaction source | Transaction có thể commit | Không callback reactive transaction | Nếu có dữ liệu, cần kiểm tra riêng |

Mỗi ca commit/rollback cần **hai loại oracle**:

1. **Oracle callback:** dấu vết trong một collector thread-safe cho biết phương thức nào được gọi.
2. **Oracle database:** truy vấn từ subscription **ngoài transaction** sau khi publisher đã kết thúc để biết thay đổi có được commit/rollback thật.

Chỉ mock `EventPublisher` rồi kiểm tra `publishEvent(...)` được gọi không kiểm chứng được phase. Chỉ gọi trực tiếp phương thức listener cũng không kiểm chứng cơ chế Spring đăng ký synchronization.

## 5. Môi trường, dependency và cấu trúc

Ví dụ có thể chạy với **JDK 17+, Gradle, Spring Framework 6.2.x, JUnit 5, Reactor Test và R2DBC H2**. Không cần Spring Boot hoặc HTTP server. Database H2 trong bộ nhớ có transaction thật để kiểm chứng commit/rollback.

Cấu trúc:

~~~text
reactive-event-test/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/
            └── example/
                └── ReactiveTransactionEventTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-event-test'
~~~

`build.gradle`:

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
    testImplementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.springframework:spring-r2dbc:6.2.15'
    testImplementation 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
    testImplementation 'io.projectreactor:reactor-test:3.7.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

Các phụ thuộc chính:

- `spring-context` cung cấp Spring context, event publisher và listener.
- `spring-r2dbc` cung cấp `DatabaseClient` và `R2dbcTransactionManager`, đồng thời kéo theo hạ tầng transaction cần thiết.
- `r2dbc-h2` cung cấp **R2DBC ConnectionFactory**; không thay bằng driver JDBC `com.h2database:h2` rồi dùng `DataSourceTransactionManager`.
- `reactor-test` chứa `StepVerifier` để subscribe vào pipeline, xác nhận signal và gắn timeout kiểm thử.
- `junit-jupiter` cùng JUnit Platform dùng để chạy test.

Phiên bản `1.0.0.RELEASE` của R2DBC H2 thuộc dòng tương thích với H2 2.1–2.3. Trong Spring Boot, hãy ưu tiên dependency management/BOM do Boot quản lý thay cho việc ghim độc lập nhiều phiên bản Spring và Reactor.

## 6. Bộ kiểm thử Java 17+ hoàn chỉnh

Tạo `src/test/java/example/ReactiveTransactionEventTest.java` với toàn bộ mã nguồn sau:

~~~java
package example;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Timeout(15)
class ReactiveTransactionEventTest {

    // Payload là record Java, không kế thừa ApplicationEvent.
    record OrderRecorded(String id) {}

    public static class EventLog {
        private final CopyOnWriteArrayList<String> entries =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(OrderRecorded event) {
            entries.add("before:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderRecorded event) {
            entries.add("commit:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderRecorded event) {
            entries.add("rollback:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void completed(OrderRecorded event) {
            entries.add("complete:" + event.id());
        }

        List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                    "r2dbc:h2:mem:///reactive_event_test"
                    + "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE");
        }

        @Bean
        DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
            return DatabaseClient.create(connectionFactory);
        }

        @Bean
        ReactiveTransactionManager transactionManager(
                ConnectionFactory connectionFactory) {
            return new R2dbcTransactionManager(connectionFactory);
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
        EventLog eventLog() {
            return new EventLog();
        }
    }

    private AnnotationConfigApplicationContext context;
    private DatabaseClient db;
    private TransactionalOperator tx;
    private TransactionalEventPublisher publisher;
    private EventLog log;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(Config.class);
        db = context.getBean(DatabaseClient.class);
        tx = context.getBean(TransactionalOperator.class);
        publisher = context.getBean(TransactionalEventPublisher.class);
        log = context.getBean(EventLog.class);

        // Tạo schema và xóa dữ liệu trước mỗi test.
        StepVerifier.create(db.sql(
                "CREATE TABLE IF NOT EXISTS tx_orders "
                + "(id VARCHAR(40) PRIMARY KEY)")
                .fetch().rowsUpdated().then())
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        StepVerifier.create(db.sql("DELETE FROM tx_orders")
                .fetch().rowsUpdated().then())
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @AfterEach
    void tearDown() {
        if (context != null) {
            context.close();
        }
    }

    private Mono<Long> countRows(String id) {
        return db.sql("SELECT COUNT(*) FROM tx_orders WHERE id = :id")
                .bind("id", id)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    private void assertPhases(String... expected) {
        List<String> actual = log.snapshot();

        // Đủ số lượng, đúng nhãn; không ràng buộc thứ tự
        // nội bộ không cần thiết giữa các callbacks.
        assertEquals(expected.length, actual.size());
        assertEquals(Set.of(expected), Set.copyOf(actual));
    }

    @Test
    void commitInvokesCommitPhasesAndPersistsRow() {
        Mono<Void> operation = db.sql(
                "INSERT INTO tx_orders (id) VALUES (:id)")
                .bind("id", "A")
                .fetch().rowsUpdated()
                .then(publisher.publishEvent(new OrderRecorded("A")));

        StepVerifier.create(tx.transactional(operation))
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertPhases("before:A", "commit:A", "complete:A");

        StepVerifier.create(countRows("A"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void errorRollsBackAndInvokesRollbackPhases() {
        Mono<Void> operation = db.sql(
                "INSERT INTO tx_orders (id) VALUES (:id)")
                .bind("id", "B")
                .fetch().rowsUpdated()
                .then(publisher.publishEvent(new OrderRecorded("B")))
                .then(Mono.<Void>error(
                        new IllegalStateException("force rollback")));

        StepVerifier.create(tx.transactional(operation))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "force rollback".equals(error.getMessage()))
                .verify(Duration.ofSeconds(10));

        assertPhases("rollback:B", "complete:B");

        StepVerifier.create(countRows("B"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void eventOutsideTransactionIsIgnoredByDefault() {
        // Publisher thường phát được payload ngoài transaction,
        // nhưng transactional listeners mặc định bỏ qua.
        context.publishEvent(new OrderRecorded("outside"));
        assertTrue(log.snapshot().isEmpty());

        // Wrapper reactive không tìm thấy TransactionContext.
        StepVerifier.create(
                publisher.publishEvent(new OrderRecorded("outside")))
                .expectError()
                .verify(Duration.ofSeconds(10));

        assertTrue(log.snapshot().isEmpty());
    }

    @Test
    void nothingHappensUntilSubscription() {
        Mono<Void> cold = tx.transactional(
                publisher.publishEvent(new OrderRecorded("cold")));

        assertTrue(log.snapshot().isEmpty());

        StepVerifier.create(cold)
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertPhases("before:cold", "commit:cold", "complete:cold");
    }

    @Test
    void plainPublisherDoesNotCarryReactiveTransactionSource() {
        // Có reactive transaction nhưng source của event vẫn sai.
        Mono<Void> operation = tx.transactional(
                Mono.fromRunnable(() ->
                        context.publishEvent(new OrderRecorded("plain"))));

        StepVerifier.create(operation)
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertTrue(log.snapshot().isEmpty());
    }
}
~~~

**Các phần chính của ví dụ:**

1. `Config` tạo Spring context, `ConnectionFactory` R2DBC, `R2dbcTransactionManager` và `TransactionalOperator`. `@EnableTransactionManagement` kích hoạt hạ tầng transaction annotation cần thiết cho `@TransactionalEventListener` trong context thuần.
2. `TransactionalEventPublisher` được khai báo là bean thông qua `ApplicationEventPublisher`. Wrapper này đảm bảo event mang `TransactionContext` ở source khi sử dụng đúng.
3. `EventLog` là bean chứa bốn listener theo bốn phase; list thread-safe ghi lại nhãn có id để phân biệt các lần phát.
4. `@BeforeEach` tạo context và reset bảng `tx_orders`; `@AfterEach` đóng context. H2 được giữ sống giữa các connection bằng `DB_CLOSE_DELAY=-1`.
5. `StepVerifier` subscribe vào `Mono` và kiểm tra terminal signal. Sau đó test truy vấn database **ngoài transaction** để đối chiếu kết quả.
6. `assertPhases` kiểm tra đầy đủ số callback và tập nhãn; không biến thứ tự duyệt nội bộ của các callback cùng giai đoạn thành một giả định nghiệp vụ.

`@Timeout(15)` giúp kiểm soát test mắc kẹt. Timeout trong phép verify có vai trò giới hạn thời gian kiểm thử; không thay thế bảo đảm nghiệp vụ.

## 7. Cách chạy và kết quả dự kiến

Từ thư mục `reactive-event-test`, dùng JDK 17+ và Gradle:

~~~bash
gradle test
~~~

Nếu đã có Gradle Wrapper, dùng `./gradlew test` trên Linux/macOS hoặc `gradlew.bat test` trên Windows. Gradle sinh báo cáo HTML trong `build/reports/tests/test/index.html`.

Bộ test có **năm phương thức `@Test`**. Nếu dependency được tải đúng, môi trường hỗ trợ R2DBC H2 và hạ tầng Spring như cấu hình, kết quả mong đợi là cả năm test hoàn tất thành công.

Không nên công bố một đoạn stdout cụ thể của Gradle như bằng chứng nếu chưa chạy thật: thời gian, log dependency và thứ tự test có thể khác nhau. Ý nghĩa của từng assertion nằm ngay trong mã:

- `commitInvokesCommitPhasesAndPersistsRow`: có `before:A`, `commit:A`, `complete:A`; bảng có một hàng A.
- `errorRollsBackAndInvokesRollbackPhases`: có `rollback:B`, `complete:B`; không có `commit:B`; bảng không có hàng B.
- `eventOutsideTransactionIsIgnoredByDefault`: listener transaction không nhận event; wrapper reactive báo lỗi khi không có transaction context.
- `nothingHappensUntilSubscription`: chưa subscribe thì danh sách rỗng; subscribe xong mới có callback của transaction commit.
- `plainPublisherDoesNotCarryReactiveTransactionSource`: dùng publisher thường trong reactive transaction không tạo event source cần thiết, nên không có callback phase reactive.

**Lưu ý thực hành:** kết quả phía trên là kỳ vọng kiểm thử từ mã, không phải báo cáo đã thực thi bằng công cụ trong môi trường hiện tại. Khi đưa vào dự án, cần chạy `gradle test` để xác nhận cả compile và runtime.

## 8. Phân tích test commit thành công

Đoạn trung tâm:

~~~java
Mono<Void> operation = db.sql(
        "INSERT INTO tx_orders (id) VALUES (:id)")
        .bind("id", "A")
        .fetch().rowsUpdated()
        .then(publisher.publishEvent(new OrderRecorded("A")));

StepVerifier.create(tx.transactional(operation))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
~~~

Quá trình xảy ra khi `StepVerifier` subscribe:

1. `TransactionalOperator` mở transaction do `R2dbcTransactionManager` quản lý; ngữ cảnh được truyền qua Reactor Context.
2. `DatabaseClient` thực thi insert bằng connection tham gia transaction hiện tại.
3. `then(...)` chờ thao tác insert hoàn tất rồi chuyển sang subscribe `publisher.publishEvent(...)`.
4. `TransactionalEventPublisher` lấy `TransactionContext` từ reactive chain và tạo event có source đúng.
5. `@TransactionalEventListener` của `EventLog` đăng ký các callback theo phase; việc publish không đồng nghĩa các callback đã chạy.
6. Phần nghiệp vụ phát `onComplete`; transaction manager tiến hành commit, gọi `BEFORE_COMMIT`, rồi callback sau commit/completion.
7. Publisher bên ngoài `tx.transactional(...)` hoàn tất sau xử lý transaction; test mới assert snapshot và truy vấn bảng A.

Vì thế một phép test chỉ gọi `publisher.publishEvent(event)` nhưng không dùng `StepVerifier` hoặc subscribe sẽ chưa chứng minh điều gì. Reactive publisher là cấu trúc **lazy**; xây dựng pipeline không tương đương thực thi.

### Vì sao phải kiểm tra bảng sau commit?

Giả sử một listener ghi log `AFTER_COMMIT` nhưng transaction thực tế không tồn tại, đã bị rollback hoặc driver bị mock không đầy đủ. Một assertion trên danh sách log không thể phát hiện tất cả những vấn đề đó. Truy vấn ngoài transaction xác nhận H2 thật sự đã lưu hàng A. Khi test dữ liệu, hãy dùng truy vấn trên cùng database nhưng sau khi transaction publisher đã kết thúc để tránh đọc nhầm trạng thái chưa commit.

## 9. Phân tích test rollback

Trong test rollback, việc chèn hàng và phát event **đã xảy ra trong transaction** trước khi pipeline phát lỗi:

~~~java
Mono<Void> operation = db.sql(
        "INSERT INTO tx_orders (id) VALUES (:id)")
    .bind("id", "B")
    .fetch().rowsUpdated()
    .then(publisher.publishEvent(new OrderRecorded("B")))
    .then(Mono.<Void>error(
            new IllegalStateException("force rollback")));
~~~

`TransactionalOperator` nhận `onError` và gọi rollback. `StepVerifier.expectErrorMatches(...)` xác nhận chính xác exception nghiệp vụ, không chỉ một lỗi bất kỳ. Sau khi transaction xử lý xong, phép kiểm tra gồm:

- Có callback `AFTER_ROLLBACK` với B.
- Có callback `AFTER_COMPLETION` với B.
- Không có `AFTER_COMMIT`, không có `BEFORE_COMMIT` cho B.
- Hàng B không tồn tại trong bảng.

Ba điều kiện trên cùng cần thiết. Không có hàng B nhưng callback rollback không chạy có thể là lỗi ở event registration. Callback rollback chạy nhưng hàng B vẫn tồn tại có thể cho thấy thao tác R2DBC không tham gia transaction mà test định kiểm tra.

**Lưu ý thời điểm gây lỗi:** nếu pipeline ném lỗi **trước** `publisher.publishEvent(...)`, event chưa được phát/đăng ký nên không thể kỳ vọng một listener `AFTER_ROLLBACK` cho event đó. Tương tự, khi transaction đã được đánh dấu rollback-only trước giai đoạn commit, `BEFORE_COMMIT` không nhất thiết được gọi.

## 10. Vì sao publisher thường không đủ trong reactive transaction?

Đoạn:

~~~java
Mono<Void> operation = tx.transactional(
    Mono.fromRunnable(() ->
        context.publishEvent(new OrderRecorded("plain"))));
~~~

vẫn được subscribe bên trong reactive transaction. Nhưng `context.publishEvent(payload)` là publisher thường; event được bọc với source là object publisher, **không phải reactive `TransactionContext`**. Với reactive transaction, `@TransactionalEventListener` không thể dựa trên ThreadLocal để lấy context như imperative transaction. Vì vậy, test `plainPublisherDoesNotCarryReactiveTransactionSource` kiểm tra một lỗi wiring phổ biến.

Đường đi đúng:

~~~java
Mono<Void> operation = tx.transactional(
    transactionalPublisher.publishEvent(new OrderRecorded("ok")));
~~~

Trong code minh họa này `transactionalPublisher` là bean kiểu `TransactionalEventPublisher`, `tx` là `TransactionalOperator`. Wrapper tự lấy TransactionContext tại thời điểm subscription.

### Nếu cần custom ApplicationEvent

Overload `TransactionalEventPublisher.publishEvent(Object payload)` dành cho một **payload bình thường**; nó không nhận `ApplicationEvent` đã được tạo sẵn. Với custom `ApplicationEvent`, dùng overload có hàm tạo event từ source:

~~~java
class AuditEvent extends org.springframework.context.ApplicationEvent {
    private final String id;

    AuditEvent(Object source, String id) {
        super(source);
        this.id = id;
    }

    String id() {
        return id;
    }
}

// Minh họa bên trong reactive transaction:
Mono<Void> send = transactionalPublisher.publishEvent(
    source -> new AuditEvent(source, "A"));
~~~

Đây là **đoạn minh họa** cần các biến và Spring bean tương ứng, không phải chương trình độc lập. Source nhận từ hàm là `TransactionContext` do wrapper cung cấp; không thay bằng `this`, request hoặc entity nếu bạn muốn listener gắn với reactive transaction.

## 11. Dấu hiệu mất subscription hoặc Reactor Context

Một lỗi thường thấy là tạo Mono trong callback phụ rồi bỏ qua nó:

~~~java
// Sai: publisher.publishEvent(...) tạo Mono nhưng không được subscribe.
Mono.just("A")
    .doOnNext(id -> transactionalPublisher.publishEvent(
        new OrderRecorded(id)));
~~~

`doOnNext` phù hợp cho side effect **đồng bộ, tức thời**; ở đây side effect là một publisher reactive cần được subscribe. Tạo Mono mà không compose chỉ tạo mô tả công việc.

Đúng là dùng `flatMap` hoặc `then`:

~~~java
Mono.just("A")
    .flatMap(id -> transactionalPublisher.publishEvent(
        new OrderRecorded(id)))
    .as(tx::transactional);
~~~

Các đoạn này là minh họa với `transactionalPublisher` và `tx` đã khai báo. Khi cần kiểm thử chính xác, hãy bao kết quả bằng `StepVerifier.create(...)`.

Những nguồn làm mất context khác gồm gọi `subscribe()` riêng lẻ trong service, tự tách chuỗi làm việc sang một pipeline độc lập không chuyển context, hoặc gọi publisher bên ngoài subscription có transaction. Hãy thiết kế chuỗi reactive liền mạch và tránh xử lý giao dịch dựa vào “cùng thread” hay biến static/thread-local.

`publishEvent(...)` từ `TransactionalEventPublisher` trả `Mono<Void>`: nó không có giá trị `onNext` để chờ, nên `flatMap`, `then` và `StepVerifier.expectComplete()` phù hợp hơn việc cố `expectNext(...)` một event.

## 12. Fallback, test method @Transactional và các trường hợp đặc biệt

### 12.1. Không có transaction và fallbackExecution

Mặc định `@TransactionalEventListener` có `fallbackExecution = false`. Nếu event phát ngoài transaction, listener bị bỏ qua; đó là hành vi đúng chứ không phải lỗi Spring.

Nếu ứng dụng muốn callback chạy ngay cả khi không có transaction:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true)
public void handleWithFallback(OrderRecorded event) {
    // Chấp nhận cả xử lý khi không có transaction.
}
~~~

Đoạn này là một **phương thức minh họa**, cần nằm trong bean Spring. Test phải phân biệt hai nhánh rõ ràng: nhánh có commit thật và nhánh fallback **không hề có commit**. Không dùng một assertion `listener đã chạy` để suy ra dữ liệu đã được commit.

### 12.2. Tránh đặt @Transactional lên toàn bộ test một cách máy móc

Một test method được framework bao bởi test-managed transaction có thể bị **rollback cuối test**. Nếu bạn đặt assertion `AFTER_COMMIT` trong thân phương thức trước khi test transaction kết thúc, callback có thể chưa chạy; hoặc test runner rollback khiến callback `AFTER_COMMIT` không chạy. Với reactive transaction, việc dùng test method annotation mà không biết manager nào được chọn càng dễ gây nhầm.

Bộ test trong mục 6 **không dùng `@Transactional` trên `@Test`**. Mỗi method tạo một reactive transaction cụ thể bằng `TransactionalOperator` và chờ nó kết thúc bằng `StepVerifier`, nên ranh giới kiểm chứng rõ ràng.

### 12.3. BEFORE_COMMIT có thể ảnh hưởng commit

Có thể bổ sung listener `BEFORE_COMMIT` cố ý ném `IllegalStateException` khi nhận event nhất định, rồi test transaction rollback. Nhưng nên đặt nó trong một test/config riêng để không làm hỏng các trường hợp commit. Một exception ở callback trước commit có thể khiến transaction manager rollback; test cần xác nhận database state và error signal thực tế.

### 12.4. Xử lý công việc async sau commit

Nếu listener chỉ khởi tạo một `Mono` hoặc tự schedule tác vụ độc lập mà không gắn kết sự hoàn tất vào transaction pipeline, việc `StepVerifier` chờ transaction commit không bảo đảm tác vụ phụ đã xong. Cần tín hiệu hoàn tất riêng có timeout hoặc kiểm chứng cuối cùng ở DB/message system. Không dùng `Thread.sleep(100)` để đo một bất đồng bộ không có hợp đồng thời gian.

## 13. Khi nào cần R2DBC thật, khi nào có thể mock?

Có ba mức test:

1. **Unit test handler:** gọi trực tiếp listener method, mock service/repository và kiểm tra quyết định nghiệp vụ. Rẻ và nhanh nhưng không có transaction synchronization.
2. **Integration test Spring + R2DBC H2:** khởi tạo context, event listener factory, `ReactiveTransactionManager`, publisher, database, subscription và hai phase thật. Phù hợp bài học này.
3. **Integration test với database production qua Testcontainers:** giúp kiểm tra semantics đặc thù về isolation, constraint, locking, commit failure và driver thực tế.

Mock `ReactiveTransactionManager` chỉ trả `Mono.empty()` từ `commit(...)` hoặc `rollback(...)` thường **không tạo đúng Reactor transaction context/synchronizations**. Khi đó bạn có thể nhận được test giả: application event có mặt nhưng listener transaction không chạy, hoặc callback chạy mà database không rollback vì hoàn toàn không có tài nguyên thật.

Một H2 in-memory database chỉ phù hợp để chứng minh cơ chế chung; nếu sản phẩm dùng PostgreSQL, cần ít nhất một nhóm integration test với PostgreSQL R2DBC. Không suy luận khả năng rollback của một hệ thống ngoài (email, Kafka, REST API) từ kết quả rollback bảng H2.

## 14. Hủy subscription, timeout và lỗi khi đóng transaction

Reactive publisher có các tín hiệu `onComplete`, `onError` và **cancel**. Chúng không hoàn toàn tương đương:

- `onComplete` của phần nghiệp vụ thường khiến transaction đi tới commit nếu không rollback-only hoặc không có lỗi khác.
- `onError` khiến transaction manager xử lý rollback và truyền lỗi cho downstream subscriber.
- `cancel` là một tín hiệu riêng, có thể dẫn tới rollback/hủy tài nguyên theo semantics của operator. Spring khuyến cáo thận trọng khi dùng cancellation với transactional publisher.

Nếu luồng nghiệp vụ có `take(...)`, `timeout(...)`, disconnect của client hoặc backpressure đặc biệt, hãy tạo **test cancellation riêng**. Không mặc định `thenCancel()` trên StepVerifier giống việc tạo `Mono.error(...)`; outcome và thời điểm cleanup có thể khác nhau.

Cũng phải phân biệt hai loại timeout:

- `verify(Duration.ofSeconds(10))` trong StepVerifier giới hạn **thời gian chờ của test**; nó không cố tình thêm lỗi `timeout` vào pipeline nghiệp vụ.
- `somePublisher.timeout(Duration...)` bên trong transaction là một operator có thể biến đổi terminal signal và khiến transaction rollback.

Khi test commit, chọn timeout đủ để xác định kẹt vô lý nhưng không gắn với thời gian sleep tùy tiện. Khi test lỗi, `expectErrorMatches` nên chỉ rõ nguyên nhân mong đợi. Khi test rollback, chỉ đọc DB sau khi publisher xử lý transaction đã kết thúc.

## 15. Các lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không listener nào chạy | Event thiếu reactive TransactionContext ở source | Dùng `TransactionalEventPublisher`, giữ Mono trong transaction pipeline |
| Không thấy insert hay callback | `Mono` chưa được subscribe | `StepVerifier.create(...).verify...` |
| Listener nhận event dù không có transaction | Thiếu transaction-aware listener factory hoặc bật fallback | Kiểm tra `@EnableTransactionManagement` và `fallbackExecution` |
| `AFTER_COMMIT` không chạy | Pipeline rollback, chưa kết thúc, hoặc callback chưa được đăng ký | Assert signal, log phase và transaction outcome |
| `AFTER_ROLLBACK` không chạy | Exception xảy ra **trước publish**, hoặc không có transaction | Đảm bảo event đã publish trong transaction trước khi gây lỗi |
| `BEFORE_COMMIT` chạy nhưng hàng không tồn tại | Commit thất bại sau callback hoặc transaction bị rollback | Kiểm tra terminal signal và truy vấn DB |
| Dùng JDBC DataSource manager với R2DBC | Sai mô hình transaction manager | Dùng `R2dbcTransactionManager` và `ConnectionFactory` |
| `@EventListener` chạy ngay, transaction listener không theo phase | Annotation wiring bị cấu hình sai | Kiểm tra factory/`@EnableTransactionManagement` và loại annotation |
| Test chỉ PASS khi chạy riêng | Chia sẻ database/bảng/collector giữa các test | Xóa dữ liệu mỗi test, context độc lập, tên DB phù hợp |
| Có `@Order` nhưng thứ tự log khác | Callback cùng phase hoặc tác vụ async không bảo đảm hoàn tất theo order | Chỉ assert thứ tự khi hợp đồng yêu cầu và cơ chế bảo đảm |
| Test sử dụng `Thread.sleep` hay bị flake | Scheduler, tải máy và thread khác nhau | Chờ tín hiệu completion/latch với timeout |
| Test dùng `@Transactional` trên method nhưng chờ commit ngay | Test-managed transaction còn mở đến cuối test | Dùng `TransactionalOperator` trực tiếp trong test |
| Listener `AFTER_COMMIT` ghi dữ liệu nhưng DB không thấy | Cố dùng lại tài nguyên transaction đã hoàn tất | Mở transaction mới nếu có thao tác ghi hậu commit |
| Wrapper reactive ngoài transaction ném lỗi | Không có TransactionContext | Đưa việc publish vào chuỗi được bao bằng operator |

Khi một test thất bại, hãy kiểm tra theo thứ tự **subscription → transaction manager → event source → listener annotation/factory → terminal signal → database outcome**. Quy trình này giúp khoanh vùng lỗi mà không đoán từ thời gian chạy hoặc tên thread.

## 16. Bài tập mở rộng

**Bài tập 1 — Lỗi trong BEFORE_COMMIT.** Thêm một listener kiểm tra id bằng `"reject"` và ném `IllegalStateException` tại `BEFORE_COMMIT`. Viết test phát event sau insert, sau đó xác nhận rollback, không có callback `AFTER_COMMIT` và không có hàng trong DB. So sánh với trường hợp `onError` xuất phát ngay từ pipeline.

**Bài tập 2 — Fallback.** Thêm listener `fallbackExecution = true`. Viết test phát event ngoài transaction rồi khẳng định listener dự phòng được gọi. Giải thích vì sao callback fallback không chứng minh commit.

**Bài tập 3 — Context sai.** Đổi một phép gọi `TransactionalEventPublisher` thành `ApplicationEventPublisher` thường trong reactive transaction. Viết assertion phát hiện listener không nhận đúng phase, sau đó sửa bằng wrapper có transaction source.

**Bài tập 4 — Quên compose.** Viết một chuỗi dùng `doOnNext` nhưng bỏ qua `Mono<Void>` trả về từ publisher. Cho test thất bại có chủ đích rồi sửa bằng `flatMap` hoặc `then`. Nêu rõ khác biệt giữa “tạo publisher” và “subscribe vào publisher”.

**Bài tập 5 — Database production.** Thay H2 bằng Testcontainers PostgreSQL với R2DBC. Chạy lại ca commit/rollback và kiểm tra sự khác biệt về connection, isolation, constraint và giao dịch thực tế.

**Bài tập 6 — Cancellation.** Thiết kế test subscription cancellation với `StepVerifier.thenCancel()` và xác định outcome theo phiên bản Spring/database đang dùng. Phân biệt cancel với `onError`, tránh mặc định chúng là một.

## 17. Tài liệu tham khảo

- Spring Framework 6.2 Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Javadoc `TransactionalEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Javadoc `TransactionalEventListener`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Javadoc `TransactionalOperator`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html
- Javadoc `TransactionPhase`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — Programmatic Reactive Transactions: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework — @EnableTransactionManagement: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Project Reactor — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- R2DBC H2 README — driver and in-memory database URL: https://github.com/r2dbc/r2dbc-h2
