# Kiểm thử @TransactionalEventListener trong Spring Framework

## 1. Mục tiêu và vấn đề cần giải quyết

`@TransactionalEventListener` cho phép Spring chạy một listener theo **giai đoạn của transaction** thay vì nhất thiết chạy ngay tại thời điểm gọi `publishEvent(...)`. Với những luồng nghiệp vụ như đặt hàng, thanh toán, cập nhật trạng thái hoặc lưu audit, sự khác biệt này quyết định một tác vụ có được thực hiện **chỉ sau khi commit**, **sau rollback** hay **trước commit**.

Một test chỉ có `verify(eventPublisher).publishEvent(...)` không chứng minh được listener thực thi đúng phase. Một test gọi trực tiếp phương thức listener cũng không chứng minh Spring đã đăng ký transaction synchronization. Để kiểm thử đúng, cần dựng **Spring context, transaction manager, event publisher và tài nguyên transaction thật**, rồi chủ động kiểm soát commit/rollback.

Sau bài học, bạn có thể:

- Phân biệt `@EventListener` thông thường với `@TransactionalEventListener`.
- Xác định các phase `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Viết JUnit 5 test cho commit, rollback do exception, rollback-only, event ngoài transaction và lỗi trước khi publish.
- Kiểm tra cả callback lẫn dữ liệu database sau khi transaction kết thúc.
- Hiểu `fallbackExecution` và lý do không thể dùng fallback để chứng minh đã commit.
- Tránh bẫy `@Transactional` trên test method mặc định rollback cuối test.
- Đọc đúng ngoại lệ, async behavior, propagation và transaction đã hoàn tất.
- Tách kiểm thử imperative JDBC và reactive transaction để không nhận kết quả PASS giả.

Phần chính dùng **Java 17+, Spring Framework 6.2.x, JDBC H2 và TransactionTemplate**. Không cần Spring Boot. Khi đưa vào ứng dụng Boot, các nguyên tắc về phase vẫn giữ nguyên.

## 2. Cơ chế bên trong: publish không đồng nghĩa xử lý ngay

Một event thường được phát qua `ApplicationEventPublisher`:

~~~java
publisher.publishEvent(new OrderCreated("order-101"));
~~~

Đó có thể là Java record nhỏ:

~~~java
public record OrderCreated(String orderId) {}
~~~

Và một bean lắng nghe:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    notificationService.send(event.orderId());
}
~~~

Ba đoạn này là **minh họa**, chưa phải chương trình độc lập. Chúng cần bean `publisher`, `notificationService` và các import/class tương ứng. Bộ test đầy đủ ở mục 6.

Khi có một imperative transaction phù hợp:

1. Code nghiệp vụ mở transaction qua `PlatformTransactionManager`.
2. Code phát event bên trong transaction.
3. Spring nhận `@TransactionalEventListener` và đăng ký callback vào transaction synchronization hiện hành.
4. Sau khi nghiệp vụ kết thúc, transaction manager bắt đầu commit hoặc rollback.
5. Listener chỉ được kích hoạt ở phase nó khai báo.

Do đó, đối với listener `AFTER_COMMIT`, việc `publishEvent(...)` trả về bình thường **không chứng minh** callback đã chạy. Đôi khi callback thậm chí sẽ không bao giờ chạy vì transaction rollback.

Với `@EventListener` đồng bộ thông thường, listener thường chạy ngay trong stack gọi publisher. Nếu code test nhầm hai annotation, kết quả hoàn toàn khác. Cần kiểm tra class import: `org.springframework.context.event.EventListener` và `org.springframework.transaction.event.TransactionalEventListener`.

## 3. Hợp đồng của bốn TransactionPhase

| Phase | Thời điểm thực thi | Commit thông thường | Rollback thông thường |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction manager commit tài nguyên | Có | Không |
| `AFTER_COMMIT` | Sau commit thành công | Có | Không |
| `AFTER_ROLLBACK` | Sau rollback | Không | Có |
| `AFTER_COMPLETION` | Khi transaction hoàn tất, commit hoặc rollback | Có | Có |

**Mặc định** của `@TransactionalEventListener` là `AFTER_COMMIT`.

Mô hình commit:

~~~text
TransactionTemplate.execute(...)
       |
       +--> INSERT/UPDATE bằng JdbcTemplate
       +--> publishEvent(OrderCreated)
       |     |
       |     +--> đăng ký callbacks theo phase
       |
       +--> callback nghiệp vụ trả về
       |
       +--> BEFORE_COMMIT
       +--> COMMIT dữ liệu
       +--> AFTER_COMMIT
       +--> AFTER_COMPLETION
       |
       +--> TransactionTemplate trả về
~~~

Mô hình rollback:

~~~text
TransactionTemplate.execute(...)
       |
       +--> INSERT/UPDATE
       +--> publishEvent(OrderCreated)
       +--> throw RuntimeException
       |
       +--> ROLLBACK dữ liệu
       +--> AFTER_ROLLBACK
       +--> AFTER_COMPLETION
       |
       +--> truyền exception cho caller
~~~

Cần lưu ý:

- Thấy `BEFORE_COMMIT` **không chứng minh commit thành công**. Có thể xảy ra lỗi database khi commit sau callback.
- `AFTER_COMPLETION` chạy ở cả hai outcome. Nó không đồng nghĩa `AFTER_COMMIT`.
- Trong implementation Spring, callback `AFTER_COMMIT` của `@TransactionalEventListener` gắn với giai đoạn completion đã commit. Không nên ràng buộc vào thứ tự không được business contract cam kết giữa nhiều synchronization callbacks.
- Nếu transaction không tồn tại, listener mặc định không được gọi.
- Nếu một event chưa được publish trước lỗi, transaction vẫn có thể rollback nhưng **không có callback nào cho event chưa từng tồn tại**.

## 4. Ma trận test và các bằng chứng cần thu thập

Một bài test tốt chứng minh **phase, transaction outcome và dữ liệu**. Không chỉ kiểm tra log.

| Tình huống | Cách kết thúc transaction | Listener mặc định mong đợi | Database |
| --- | --- | --- | --- |
| Commit A | Callback thành công, commit | `before:A`, `commit:A`, `complete:A` | A tồn tại |
| Rollback B | Throw exception sau publish | `rollback:B`, `complete:B` | B không tồn tại |
| Rollback-only C | `status.setRollbackOnly()` | `rollback:C`, `complete:C` | C không tồn tại |
| Ngoài transaction N | Publish trực tiếp | Không có callback mặc định | Không đổi |
| Lỗi trước publish D | Throw exception trước khi gọi publisher | Không có callback nào | D không tồn tại |

Để kiểm tra fallback, thêm một bean riêng có `@TransactionalEventListener(fallbackExecution = true)`. Nó vẫn chạy sau commit nếu có transaction, nhưng được phép chạy ngay nếu không có transaction. Vì vậy test N phải thấy fallback, **không được gọi đó là commit**.

Các “oracle” nên độc lập:

1. **Collector:** một danh sách dấu vết callback cho biết event nào đi tới phase nào.
2. **Database:** query ngoài transaction sau khi hoàn tất để xác nhận commit hoặc rollback.
3. **Exception/result:** kiểm tra lỗi hoặc trạng thái trả về đúng.
4. **Timing:** assertion đặt sau ranh giới commit/rollback, không đặt sớm ngay sau `publishEvent`.

Một transaction có thể rollback mà không ném exception nếu code chủ động đánh dấu rollback-only; vì vậy không dùng “không có exception” làm bằng chứng commit.

## 5. Chuẩn bị dự án Java 17+ và Gradle

Cấu trúc dự án:

~~~text
tx-listener-test/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/
            └── example/
                └── TransactionalEventListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'tx-listener-test'
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
    testImplementation 'org.springframework:spring-jdbc:6.2.15'
    testImplementation 'com.h2database:h2:2.3.232'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

Ý nghĩa:

- `spring-context`: context, publisher và listener adapter.
- `spring-jdbc`: `JdbcTemplate`, `DataSourceTransactionManager` và hỗ trợ JDBC transaction; `spring-tx` được giải quyết theo dependency graph.
- H2 JDBC: một database thật trong bộ nhớ để kiểm tra commit/rollback; không phải Mockito.
- JUnit Jupiter: test lifecycle, assertions, và nền tảng chạy JUnit.
- Java toolchain: chọn JDK 17 để phù hợp baseline của Spring 6.2.

Trong dự án Spring Boot, nên để Spring Boot BOM quản lý các phiên bản Spring/H2/JUnit. Ví dụ cố định version nhằm giúp người học tái hiện cấu hình, không có nghĩa chúng là phiên bản mới nhất tại mọi thời điểm.

## 6. Mã nguồn kiểm thử hoàn chỉnh

Lưu **toàn bộ** nội dung sau vào `src/test/java/example/TransactionalEventListenerTest.java`:

~~~java
package example;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TransactionalEventListenerTest {

    public record OrderCreated(String id) {}

    public static final class PhaseRecorder {
        private final CopyOnWriteArrayList<String> events =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(OrderCreated event) {
            events.add("before:" + event.id());
        }

        // Không ghi phase => AFTER_COMMIT.
        @TransactionalEventListener
        public void committed(OrderCreated event) {
            events.add("commit:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderCreated event) {
            events.add("rollback:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void completed(OrderCreated event) {
            events.add("complete:" + event.id());
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    // Tách fallback khỏi collector chính để dễ so sánh.
    public static final class FallbackRecorder {
        private final CopyOnWriteArrayList<String> events =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(fallbackExecution = true)
        public void accept(OrderCreated event) {
            events.add("fallback:" + event.id());
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");

            // Mỗi test có DB riêng để tránh phụ thuộc test order.
            String dbName = "txevent_"
                    + UUID.randomUUID().toString().replace("-", "");
            ds.setUrl("jdbc:h2:mem:" + dbName + ";DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public PhaseRecorder phaseRecorder() {
            return new PhaseRecorder();
        }

        @Bean
        public FallbackRecorder fallbackRecorder() {
            return new FallbackRecorder();
        }
    }

    private AnnotationConfigApplicationContext context;
    private ApplicationEventPublisher publisher;
    private JdbcTemplate jdbc;
    private TransactionTemplate tx;
    private PhaseRecorder phases;
    private FallbackRecorder fallback;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(Config.class);
        publisher = context;
        jdbc = context.getBean(JdbcTemplate.class);
        tx = context.getBean(TransactionTemplate.class);
        phases = context.getBean(PhaseRecorder.class);
        fallback = context.getBean(FallbackRecorder.class);

        jdbc.execute(
                "CREATE TABLE tx_items (id VARCHAR(64) PRIMARY KEY)");
    }

    @AfterEach
    void tearDown() {
        if (context != null) {
            context.close();
        }
    }

    private int countRows(String id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_items WHERE id = ?",
                Integer.class,
                id);
        return result.intValue();
    }

    private void assertPhases(String... expected) {
        List<String> actual = phases.snapshot();
        assertEquals(expected.length, actual.size());
        assertEquals(Set.of(expected), Set.copyOf(actual));
    }

    @Test
    void commitCallsCommitPhasesAndPersistsData() {
        tx.executeWithoutResult(status -> {
            jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "A");
            publisher.publishEvent(new OrderCreated("A"));

            // Callback chưa chạy vì transaction chưa commit.
            assertTrue(phases.snapshot().isEmpty());
            assertTrue(fallback.snapshot().isEmpty());
        });

        assertPhases("before:A", "commit:A", "complete:A");
        assertEquals(List.of("fallback:A"), fallback.snapshot());
        assertEquals(1, countRows("A"));
    }

    @Test
    void exceptionAfterPublishRollsBack() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO tx_items(id) VALUES (?)", "B");
                    publisher.publishEvent(new OrderCreated("B"));
                    throw new IllegalStateException("rollback requested");
                }));

        assertEquals("rollback requested", error.getMessage());
        assertPhases("rollback:B", "complete:B");
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("B"));
    }

    @Test
    void rollbackOnlyAlsoTriggersRollbackPhase() {
        tx.executeWithoutResult(status -> {
            jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "C");
            publisher.publishEvent(new OrderCreated("C"));
            status.setRollbackOnly();
        });

        assertPhases("rollback:C", "complete:C");
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("C"));
    }

    @Test
    void outsideTransactionOnlyFallbackRuns() {
        publisher.publishEvent(new OrderCreated("N"));

        assertTrue(phases.snapshot().isEmpty());
        assertEquals(List.of("fallback:N"), fallback.snapshot());
        assertEquals(0, countRows("N"));
    }

    @Test
    void errorBeforePublishHasNoEventCallbacks() {
        assertThrows(IllegalArgumentException.class,
                () -> tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO tx_items(id) VALUES (?)", "D");
                    throw new IllegalArgumentException(
                            "validation failed before event");
                }));

        assertTrue(phases.snapshot().isEmpty());
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("D"));
    }
}
~~~

Đây là **file JUnit 5 hoàn chỉnh**, không phải pseudo-code. `@BeforeEach` dựng Spring context và bảng database; `@AfterEach` đóng context. Mỗi method test có transaction boundary tường minh. Không có `@Transactional` bao bên ngoài test method nên `TransactionTemplate` tự mở/đóng transaction theo đúng vị trí assertion.

### Vì sao dùng @EnableTransactionManagement?

Với Spring Framework context thuần, `@EnableTransactionManagement` đăng ký hạ tầng transaction annotation. Listener transaction được Spring nhận diện qua cơ chế event listener adapter, còn `DataSourceTransactionManager` cung cấp transaction thực để nó đăng ký callback. Test không nên dựa vào những bean mà Spring Boot có thể tự tạo nếu đang chủ động dựng `AnnotationConfigApplicationContext` tối giản.

### Vì sao dùng một DataSource cho cả JdbcTemplate và manager?

`JdbcTemplate` phải thực hiện SQL bằng **connection tham gia transaction đang được quản lý**. Cả nó và `DataSourceTransactionManager` cùng nhận một bean `DataSource`. Nếu test ghi dữ liệu vào một datasource khác với datasource mà transaction manager quản lý, database có thể commit tự động dù test nghĩ đã rollback.

### Vì sao database có tên UUID?

Mỗi test có một H2 in-memory database riêng, tránh dữ liệu còn sót khi test chạy song song hoặc thứ tự test thay đổi. `DB_CLOSE_DELAY=-1` giữ database qua những connection mới trong cùng JVM. Đây là cách cô lập dễ hiểu, không phải lựa chọn tối ưu duy nhất cho test suite lớn.

### Vì sao dùng CopyOnWriteArrayList?

Collection này giúp collector an toàn khi có thread khác đọc/ghi; `snapshot()` tạo list riêng để assertion không đọc cùng lúc collection đang thay đổi. Tuy nhiên, **thread-safe không biến test async thành test có đồng bộ hoàn tất**. Bộ test hiện tại cố ý dùng multicaster đồng bộ mặc định và transaction boundary xác định.

### Vì sao so sánh Set và số lượng?

`assertPhases` xác nhận đủ số callback và đúng nhãn, không ràng buộc vào một thứ tự tình cờ giữa các transaction synchronizations cùng giai đoạn. Nếu có callback trùng, so sánh số lượng và tập nhãn giúp phát hiện. Để kiểm tra `@Order`, hãy viết test thứ tự riêng với hợp đồng rõ ràng.

## 7. Chạy test và kết quả dự kiến

Trong thư mục dự án, với JDK 17+ và Gradle:

~~~bash
gradle test
~~~

Nếu đã có Gradle Wrapper, chạy `./gradlew test` trên Linux/macOS hoặc `gradlew.bat test` trên Windows. Báo cáo JUnit của Gradle thường nằm tại `build/reports/tests/test/index.html`.

Có **5 phương thức `@Test`** trong file trên. Nếu các dependency được giải quyết và context/transaction manager hoạt động đúng, cả năm test sẽ qua.

Bảng kết quả cần đối chiếu:

| Test | Nhãn transaction phase | Fallback | Hàng trong H2 |
| --- | --- | --- | --- |
| Commit A | `before:A`, `commit:A`, `complete:A` | `fallback:A` | A = 1 |
| Exception rollback B | `rollback:B`, `complete:B` | Không có | B = 0 |
| Rollback-only C | `rollback:C`, `complete:C` | Không có | C = 0 |
| Ngoài transaction N | Không có | `fallback:N` | N = 0 |
| Lỗi trước publish D | Không có | Không có | D = 0 |

Đây là **kỳ vọng theo mã và contract**, không phải một bản log test đã được chạy trong môi trường hiện tại. File kiểm thử không chủ động in các nhãn ra stdout; chúng được kiểm tra bằng JUnit assertions. Nếu build fail, phải xem đúng lỗi compile/dependency/runtime thay vì sửa assertion để test “xanh”.

## 8. Phân tích sâu ca commit

Trong test:

~~~java
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "A");
    publisher.publishEvent(new OrderCreated("A"));
    assertTrue(phases.snapshot().isEmpty());
});
~~~

Ở thời điểm `publishEvent`, Spring đã biết event và đã có transaction, nhưng **callback ở phase chưa chạy**. Khi callback bên trong template kết thúc:

1. Transaction manager bắt đầu quy trình commit.
2. Listener `BEFORE_COMMIT` chạy.
3. Database commit thao tác insert.
4. Listener `AFTER_COMMIT` và `AFTER_COMPLETION` được gọi theo outcome thành công.
5. `TransactionTemplate` trả về cho test.
6. Test assert nhãn và `COUNT(*)`.

Vì vậy, assertion `phases.snapshot().isEmpty()` **bên trong** callback là chủ ý: nó kiểm tra listener không được gọi quá sớm. Assertion ba nhãn và dữ liệu A = 1 được đặt **ngoài** callback để tránh lỗi timing.

Một listener `@TransactionalEventListener(fallbackExecution=true)` vẫn bám vào transaction khi có transaction. Nó **không chạy ngay** chỉ vì bật fallback; thuộc tính này chỉ có tác dụng khi không có transaction. Do đó ở ca A, `fallback:A` xuất hiện sau commit theo phase mặc định.

**Cần thận trọng:** nếu một callback `BEFORE_COMMIT` lỗi hoặc commit database thất bại, `BEFORE_COMMIT` có thể đã chạy nhưng `AFTER_COMMIT` không diễn ra. Chính vì thế DB assertion là phần quan trọng của test.

## 9. Phân tích sâu ca rollback do exception

Tại test B:

~~~java
assertThrows(IllegalStateException.class,
    () -> tx.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "B");
        publisher.publishEvent(new OrderCreated("B"));
        throw new IllegalStateException("rollback requested");
    }));
~~~

Transaction manager rollback sau khi callback nghiệp vụ ném exception. Do event đã được publish, synchronization tương ứng tồn tại. Vì vậy test cần thấy `AFTER_ROLLBACK` và `AFTER_COMPLETION`, không thấy `AFTER_COMMIT`.

Cần chứng minh ba điều cùng lúc:

- Exception là loại và thông điệp mong đợi, không phải một lỗi setup bất kỳ.
- Collector có đúng `rollback:B` và `complete:B`, không chứa `commit:B`.
- Sau transaction, database không chứa hàng B.

Nếu exception xảy ra **trước** `publishEvent(...)`, event chưa tồn tại nên không thể trông đợi listener rollback nhận event B. Test D trong file phân biệt chính xác tình huống này: database rollback, nhưng collector rỗng.

Chỉ mock `RuntimeException` ở một service mà không dùng transaction manager thật chưa đủ để chứng minh event phase hoạt động.

## 10. Rollback-only: không có exception vẫn có thể rollback

Trong test C:

~~~java
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "C");
    publisher.publishEvent(new OrderCreated("C"));
    status.setRollbackOnly();
});
~~~

`status.setRollbackOnly()` yêu cầu transaction manager rollback khi kết thúc transaction. Trong trường hợp transaction mới do `TransactionTemplate` mở như ví dụ, method có thể trả về bình thường, nhưng database không có hàng C và listener rollback vẫn được gọi.

Đây là bài kiểm tra cần thiết vì một test chỉ assert “không ném lỗi” có thể kết luận sai rằng đã commit.

Nếu code tham gia transaction có sẵn với propagation `REQUIRED`, một inner scope đánh dấu rollback-only có thể khiến outer commit ném `UnexpectedRollbackException`. Outcome và vị trí nhận exception phụ thuộc propagation, không phải lúc nào cũng giống một transaction mới độc lập.

**Nguyên tắc kiểm thử:** kiểm tra transaction status và hiệu ứng dữ liệu cuối cùng, không chỉ nhìn luồng exception.

## 11. Không có transaction và fallbackExecution

Khi gọi:

~~~java
publisher.publishEvent(new OrderCreated("N"));
~~~

ngoài bất kỳ transaction nào, các listener `@TransactionalEventListener` mặc định bỏ qua event N. Spring không thể gắn callback vào một commit/rollback không tồn tại.

Nếu listener bật:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void accept(OrderCreated event) {
    // Nhận được event ngay cả khi không có transaction.
}
~~~

nó có thể chạy lập tức khi publish ngoài transaction. Đây là **minh họa**, method cần nằm trong bean Spring.

Đừng gọi việc đó là “AFTER_COMMIT đã chạy” theo nghĩa nghiệp vụ. Trong nhánh fallback **không hề có commit**. Điều này nguy hiểm nếu listener gửi email xác nhận đơn hàng trong khi nơi phát không bao giờ tạo transaction.

Cũng cần phân biệt **publish sau transaction đã đóng** với **publish bên trong transaction**. Nếu service commit trước rồi mới gọi `publishEvent` ở ngoài transaction, listener mặc định bị bỏ qua; để có callback sau commit, hãy publish trong transaction và cho listener được đăng ký ngay khi transaction còn active.

### Thử cả fallback trong transaction

Khi có transaction, listener bật fallback **không bỏ qua phase** mà vẫn chờ phase phù hợp. Trong code đầy đủ, `FallbackRecorder` chỉ thêm `fallback:A` sau commit A; nó không thêm gì cho rollback B/C. Test này bảo đảm cấu hình fallback không vô tình khiến mọi outcome đều được xử lý.

## 12. Bẫy khi dùng @Transactional trên phương thức test

Với `Spring TestContext Framework`, test có `@Transactional` thường chạy trong **test-managed transaction**, và mặc định sẽ rollback khi test method kết thúc. Điều này khác hẳn việc `TransactionTemplate` tự commit ngay trước assertion.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class OrderEventIntegrationTest {
    @Autowired
    ApplicationEventPublisher publisher;

    // Phương thức minh họa, chưa bao gồm mọi bean/import cần thiết.
    public void aTestBody() {
        publisher.publishEvent(new OrderCreated("A"));
        // AFTER_COMMIT chưa chạy: transaction test vẫn mở.
    }
}
~~~

Đây là đoạn minh họa cần `spring-test` và cấu hình test. Vấn đề có hai phần:

1. Assertion trong thân test được thực hiện **trước lúc kết thúc** test-managed transaction.
2. Mặc định Spring TestContext rollback ở cuối test, nên `AFTER_COMMIT` có thể **không bao giờ được gọi**.

Không giải quyết điều này bằng `Thread.sleep(500)`, vì callback đang chờ **transaction phase**, không phải thiếu vài millisecond.

### Giải pháp 1: không bao test bằng @Transactional

Ví dụ mục 6 không gắn `@Transactional` lên test class/method. Mỗi test dùng `TransactionTemplate`, rồi assert ở bên ngoài. Đây là cách dễ hiểu nhất khi cần chủ động xác nhận commit hoặc rollback.

**Lưu ý:** nếu bạn đặt `@Transactional` trên test method **và** gọi `TransactionTemplate` với propagation `REQUIRED`, template có thể tham gia transaction do TestContext mở. Khi đó `executeWithoutResult` trả về chưa chắc đồng nghĩa outer test transaction đã kết thúc.

### Giải pháp 2: TestTransaction của Spring Test

Spring Test có `TestTransaction.flagForCommit()` và `TestTransaction.end()` để kết thúc test-managed transaction theo cách có kiểm soát.

~~~java
// Đoạn minh họa trong một test-managed transaction:
publisher.publishEvent(new OrderCreated("A"));

TestTransaction.flagForCommit();
TestTransaction.end();

// Bây giờ mới xác nhận AFTER_COMMIT.
~~~

Đoạn này không phải file độc lập; phải có Spring TestContext, bean transaction manager và import `org.springframework.test.context.transaction.TestTransaction`. Nếu dùng `@Commit` hoặc `@Rollback(false)`, commit có thể diễn ra sau phần thân test, vì vậy assertion vẫn cần đặt ở vị trí thích hợp, ví dụ một callback `@AfterTransaction`.

## 13. BEFORE_COMMIT exception và lỗi sau commit

### BEFORE_COMMIT có thể làm transaction thất bại

Một validation listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void validate(OrderCreated event) {
    if ("REJECT".equals(event.id())) {
        throw new IllegalStateException("event rejected");
    }
}
~~~

Nếu callback `BEFORE_COMMIT` ném unchecked exception, transaction manager có thể rollback; đây là lỗi **trước commit**. Test riêng cần xác nhận exception/rollback, không có `AFTER_COMMIT` và database không còn bản ghi.

Đặt listener cố tình ném lỗi trong configuration riêng cho test đó; không gắn nó vào collector chung ở mục 6 vì sẽ làm các ca commit thất bại ngoài mục tiêu.

### AFTER_COMMIT không thể quay ngược thời gian

Khi listener `AFTER_COMMIT` xử lý, database đã commit. Nếu gửi HTTP hoặc email thất bại tại đây, lỗi không tự hoàn nguyên dữ liệu đã commit. Vì vậy, test không nên kỳ vọng “AFTER_COMMIT ném lỗi thì transaction đặt hàng rollback”.

Để bảo đảm các side effect quan trọng sau commit:

- Dùng retry có giới hạn và idempotency.
- Theo dõi lỗi và outcome thực sự của handler.
- Dùng transactional outbox hoặc message broker khi cần đảm bảo không mất công việc qua restart.
- Không coi Spring in-process event là durable queue hoặc exactly-once delivery.

### Ghi database trong listener sau commit

Javadoc cảnh báo sau commit/rollback/completion, transaction resources có thể vẫn truy cập được nhưng thao tác ghi thêm có thể “tham gia” tài nguyên cũ mà **không được commit mới**. Nếu cần ghi một bản ghi audit sau commit, dùng transaction **mới** có ranh giới thực, chẳng hạn một bean khác với `@Transactional(propagation = REQUIRES_NEW)` qua Spring proxy.

Đừng tự gọi `this.saveAudit()` và nghĩ proxy transaction tự được áp dụng cho self-invocation. Test cần xác nhận bản ghi audit tồn tại trong database **sau transaction mới**, không chỉ `jdbc.update` trả số hàng.

## 14. Async, @Order và timing của callback

Trong imperative transaction, context thường được gắn với **thread đang thực thi transaction**. Nếu bạn tự đẩy `publishEvent` sang một thread khác trước khi đăng ký transaction synchronization, thread mới có thể không có transaction context.

Không nên chỉ bật executor của `SimpleApplicationEventMulticaster` rồi suy ra mọi transaction listener sẽ chạy async. Spring 6.1+ hỗ trợ `ApplicationListener.supportsAsyncExecution()`; những listener đồng bộ với transaction có thể cần đăng ký callback ở thread gốc.

Với `@Async`, có thêm các rủi ro:

- Công việc thực sự chạy sau khi publisher trả về.
- Exception ở worker không nhất thiết quay về publisher.
- Một callback chỉ tạo `Mono`/`CompletableFuture` mà không chờ nó có thể kết thúc sớm so với side effect.
- ThreadLocal transaction context của caller không tự động được truyền sang worker.
- `Thread.sleep` trong test chỉ tạo hy vọng theo thời gian, không bảo đảm handler hoàn tất.

Nếu cần test async, dùng `CountDownLatch`, `Future` hoặc tín hiệu hoàn tất được kiểm soát với timeout, sau đó assert kết quả thật. Không trộn test async vào bộ kiểm tra phase đồng bộ mà không mô tả rõ transaction boundary.

### @Order

`@Order` có thể ưu tiên listener trong những điều kiện phù hợp. Nó không thay đổi thứ tự các **phase transaction**. Một callback `AFTER_COMMIT` không thể được đưa lên trước `BEFORE_COMMIT` chỉ nhờ `@Order(-100)`.

Nếu nghiệp vụ yêu cầu thứ tự giữa hai listener cùng phase, viết test riêng dùng `@Order` tường minh và dấu vết có thứ tự; còn test phase chung nên dùng so sánh số lượng/tập nhãn để không phụ thuộc chi tiết ngoài hợp đồng.

## 15. Kiểm thử reactive transaction: trường hợp khác

Từ Spring Framework 6.1, `@TransactionalEventListener` hỗ trợ cả hai cơ chế:

| Cơ chế | Transaction manager | Context | Cách phát event phù hợp |
| --- | --- | --- | --- |
| JDBC/JPA imperative | `PlatformTransactionManager` | ThreadLocal | `ApplicationEventPublisher` trong transaction |
| R2DBC reactive | `ReactiveTransactionManager` | Reactor Context | `TransactionalEventPublisher`, event source mang `TransactionContext` |

Bộ test chính dùng `DataSourceTransactionManager` và `JdbcTemplate`, nên **không chứng minh** hành vi reactive. Reactive transaction không dựa vào ThreadLocal transaction context.

Ý tưởng kiểm thử reactive:

~~~java
Mono<Void> work = reactiveRepository.save(order)
        .then(transactionalEventPublisher.publishEvent(
                new OrderCreated("A")));

StepVerifier.create(transactionalOperator.transactional(work))
        .verifyComplete();
~~~

Đây là đoạn **minh họa**, cần Spring reactive transaction, R2DBC repository, `TransactionalOperator`, `TransactionalEventPublisher`, Reactor Test và những bean tương ứng. Việc chỉ tạo `Mono` mà không subscribe chưa chạy save/publish; `StepVerifier` thực sự subscribe và chờ transaction operator hoàn tất.

Để test rollback reactive, phát event thành công trong transaction trước khi chèn `Mono.error(...)`, rồi assert `AFTER_ROLLBACK`, `AFTER_COMPLETION` và trạng thái R2DBC database. Không dùng `DataSourceTransactionManager` cho R2DBC và không dùng publisher thường rồi giả định source đã mang reactive `TransactionContext`.

## 16. Troubleshooting: test đỏ vì đâu?

| Hiện tượng | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| `AFTER_COMMIT` không chạy | Chưa commit, test mặc định rollback, không có transaction | Xác minh ranh giới transaction trước assertion |
| `AFTER_ROLLBACK` không chạy | Event chưa được publish trước lỗi | Phát event trong transaction trước khi tạo lỗi |
| Listener không được gọi | Chưa là Spring bean, annotation import sai | Dựng context thật, kiểm tra registration |
| Listener chạy ngoài transaction | `fallbackExecution=true` | Kiểm tra nhánh fallback riêng |
| Database vẫn chứa hàng sau rollback | JdbcTemplate dùng datasource khác, transaction sai | Kiểm tra manager và resource thực |
| Test chỉ mock publisher | Không có transaction synchronization | Sử dụng publisher/context/manager thật |
| Test gọi thẳng listener | Chỉ test body logic | Thêm integration test phát qua Spring |
| Kết quả phụ thuộc thứ tự chạy suite | Database/collector chia sẻ trạng thái | Cô lập context và DB mỗi test |
| `BEFORE_COMMIT` chạy nhưng không có dữ liệu | Commit thất bại sau callback | Kiểm tra exception và DB cuối |
| Listener AFTER_COMMIT ghi DB nhưng không lưu | Không mở transaction mới | Dùng REQUIRES_NEW đúng proxy |
| Test có `@Transactional` và tự gọi TransactionTemplate | Tham gia transaction test có sẵn | Bỏ annotation hoặc dùng TestTransaction |
| Async test lúc PASS lúc FAIL | Assertion chạy trước worker | Chờ completion với timeout |
| Reactive listener không chạy | Event source thiếu reactive TransactionContext | Dùng TransactionalEventPublisher |
| Rollback-only có kết quả khác kỳ vọng | Propagation/lồng transaction | Kiểm tra inner/outer status và UnexpectedRollbackException |
| Listener chạy hai lần | Nhiều bean/listener registrations hoặc context cha-con | Kiểm tra beans và event source |
| Test sự kiện lỗi mà không có callback rollback | Lỗi xảy ra trước publish | Test thứ tự phát và thời điểm lỗi |

## 17. Checklist và bài tập thực hành

Checklist:

- [ ] Listener được Spring đăng ký từ bean thật.
- [ ] Event được publish **bên trong transaction active** khi test phase.
- [ ] Commit/rollback xảy ra **trước assertion** tương ứng.
- [ ] `AFTER_COMMIT` và `AFTER_ROLLBACK` không bị nhầm.
- [ ] `AFTER_COMPLETION` được kiểm tra ở cả hai outcome.
- [ ] Database được truy vấn ngoài transaction và cho kết quả phù hợp.
- [ ] Exception được tạo sau publish nếu test kỳ vọng callback rollback.
- [ ] Trường hợp không transaction và fallback được kiểm tra độc lập.
- [ ] Không có transaction ngoài do `@Transactional` test class làm sai thời điểm.
- [ ] Listener bất đồng bộ có tín hiệu hoàn tất với timeout, không dùng sleep.
- [ ] Reactive và imperative manager không bị sử dụng chéo.
- [ ] Không giả định event nội bộ bảo đảm giao hàng qua crash/restart.

Bài tập mở rộng:

1. Tạo listener `BEFORE_COMMIT` ném exception cho event ID `"REJECT"`, rồi xác nhận không commit database và callback `AFTER_COMMIT` không chạy.
2. Thử `@SpringJUnitConfig` + `@Transactional`, kiểm chứng rollback mặc định; sau đó dùng `TestTransaction.flagForCommit()` và `end()`.
3. Thêm listener `@TransactionalEventListener(fallbackExecution=true)` ở phase `AFTER_ROLLBACK`. Phân biệt fallback chạy ngay ngoài transaction với rollback thật.
4. Phát hai event khác nhau trong một transaction, assert số lần callback ở mỗi phase và thứ tự chỉ khi có `@Order` rõ ràng.
5. Thêm một listener `AFTER_COMMIT` ghi audit trong transaction mới. Xác nhận chỉ có audit khi business commit và audit tồn tại thật sau callback.
6. Chuyển sang R2DBC + `StepVerifier` và kiểm thử commit/rollback bằng reactive transaction context thực.
7. Dùng Testcontainers PostgreSQL để kiểm tra constraint/commit failure mà H2 không thể mô phỏng chính xác.
8. Thêm một external side effect bị lỗi sau commit, kiểm chứng transaction nghiệp vụ không rollback lại và thiết kế outbox/retry đúng.

## 18. Tài liệu tham khảo

- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2 — `TransactionalEventListener`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2 — `TransactionPhase`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework Javadoc 6.2 — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc 6.2 — `DataSourceTransactionManager`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework Reference 6.2 — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework Reference 6.2 — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework Javadoc — `TestTransaction`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework Reference — Embedded Database Support: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/embedded-database-support.html
- Spring Framework Javadoc — `TransactionalEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
