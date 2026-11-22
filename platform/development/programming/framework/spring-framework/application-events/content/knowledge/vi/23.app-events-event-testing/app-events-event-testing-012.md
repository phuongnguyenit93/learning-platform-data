# Kiểm thử AFTER_COMMIT và rollback trong Spring Framework Application Events

## 1. Mục tiêu: chứng minh event được xử lý theo **kết quả transaction thực sự**

Khi ứng dụng Spring publish một domain event trong một database transaction, có hai câu hỏi tách biệt:

1. **Event đã được publish chưa?** Lời gọi **ApplicationEventPublisher.publishEvent(...)** có thể xảy ra trước khi database commit.
2. **Transaction cuối cùng commit hay rollback?** Kết quả này quyết định có nên thực hiện phản ứng như gửi thông báo, cập nhật projection hoặc gọi một hệ thống bên ngoài.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** cho phép listener được gọi **sau khi transaction gắn với event đã commit thành công**. Trái lại, **AFTER_ROLLBACK** dành cho nhánh rollback; **AFTER_COMPLETION** cho cả hai kết quả. Muốn kiểm thử đúng phải **chủ động làm transaction kết thúc** và kiểm tra cả event lẫn trạng thái dữ liệu, thay vì chỉ gọi phương thức listener hoặc nhìn thấy log “đã publish”.

Bài này tập trung vào **Spring Framework Application Events**, nhóm **Kiểm thử event**. Ta sẽ học:

- Cơ chế đăng ký callback của **@TransactionalEventListener**, thời điểm khác nhau giữa **@EventListener** và **AFTER_COMMIT**.
- Cách thiết kế **test matrix** cho commit, rollback-only, exception rollback, ngoài transaction, fallbackExecution.
- Hai chiến lược test: **TransactionTemplate** với transaction thật và **@Transactional test + TestTransaction**.
- Một dự án **Java 17+**, **Spring Framework 6.2.9**, **H2**, **JUnit Jupiter 5** dùng Gradle để chạy các integration tests.
- Những bẫy: test mặc định rollback; **@MockBean / gọi trực tiếp method** không mô phỏng listener adapter; **REQUIRES_NEW**, **@Async**, transaction propagation, database visibility, false positives và durability.

**Nguyên tắc:** Một assertion “listener chưa chạy” khi transaction **vẫn đang mở** chưa chứng minh listener sẽ **không bao giờ** chạy; nó có thể đang chờ commit. Và assertion “publishEvent() đã gọi” không chứng minh transaction đã commit.

## 2. Nhắc lại cơ chế event gắn với transaction

Một listener thông thường:

~~~java
@EventListener
public void on(OrderPlaced event) {
    // Với multicaster đồng bộ mặc định, thường chạy ngay khi publish.
}
~~~

Một listener theo phase:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Spring gọi sau khi transaction gắn với event commit thành công.
}
~~~

Hai đoạn trên **chỉ là snippet minh họa**; cần import tương ứng, Spring-managed bean và event type **OrderPlaced**.

Nếu service đang ở trong transaction:

~~~text
BEGIN TRANSACTION
   |
   +-- INSERT order
   |
   +-- publisher.publishEvent(OrderPlaced)
   |       |
   |       +-- @EventListener                   -> thường xử lý ngay
   |       |
   |       +-- @TransactionalEventListener
   |                -> đăng ký transaction synchronization
   |
   +-- business method trả về
   |
   +-- COMMIT thành công
                |
                +-- BEFORE_COMMIT callback (trước commit thực tế)
                +-- AFTER_COMMIT listener
                +-- AFTER_COMPLETION listener
~~~

**Đừng hiểu sơ đồ trên là lịch gọi tuyệt đối của mọi callback:** **BEFORE_COMMIT** thuộc bước trước commit; **AFTER_COMMIT** và **AFTER_COMPLETION** xảy ra trong tiến trình hoàn tất transaction. Thứ tự các synchronizations cụ thể có thể chịu ảnh hưởng cấu hình và **@Order**. Điểm cần test là **AFTER_COMMIT chỉ thuộc nhánh commit thành công**; **AFTER_ROLLBACK chỉ thuộc nhánh rollback**.

Nếu transaction cuối cùng rollback:

~~~text
BEGIN TRANSACTION
   |
   +-- INSERT order
   +-- publish OrderPlaced
   +-- @EventListener thường đã chạy
   |
   +-- setRollbackOnly() hoặc exception gây rollback
   |
   +-- ROLLBACK
          |
          +-- AFTER_ROLLBACK listener
          +-- AFTER_COMPLETION listener
          +-- KHÔNG gọi AFTER_COMMIT listener
          +-- INSERT order không tồn tại sau rollback
~~~

**Quan trọng:** sự kiện được publish **trước rollback** không tự biến mất khỏi memory/log. Một **@EventListener đồng bộ** có thể đã thực hiện side effect bên ngoài trước khi transaction rollback. **@TransactionalEventListener(AFTER_COMMIT)** giúp gắn phản ứng với outcome, nhưng bản thân nó không phải durable message queue.

## 3. Các transaction phases cần phân biệt

| Phase | Khi nào xử lý? | Có chạy khi rollback? | Điểm nên kiểm thử |
| --- | --- | --- | --- |
| **BEFORE_COMMIT** | Trước khi transaction thực hiện commit, khi nhánh commit tiến hành | Thông thường **không** nếu transaction bị rollback trước commit | Đã gọi khi commit path và không gọi khi rollback-only |
| **AFTER_COMMIT** | Sau khi commit thành công | **Không** | Chỉ có event ở commit path; DB thay đổi đã commit |
| **AFTER_ROLLBACK** | Sau khi rollback | **Có** | Có event ở rollback path; DB thay đổi không tồn tại |
| **AFTER_COMPLETION** | Sau khi hoàn tất, commit hoặc rollback | **Có** | Cả hai nhánh đều nhận event |
| **@EventListener thường** | Khi event được dispatch, mặc định đồng bộ | Có thể **đã chạy** trước rollback | Phân biệt “published” với “committed” |

**@TransactionalEventListener** mặc định sử dụng **AFTER_COMMIT** nếu không khai báo **phase**. Trong chương trình sử dụng **PlatformTransactionManager** kiểu imperative, nó gắn với transaction đang hoạt động trên thread tại thời điểm event được phát.

### Điều gì xảy ra nếu publish không có transaction?

Theo mặc định **fallbackExecution=false**: transactional event listener **không được gọi** khi không có transaction phù hợp. Nếu khai báo **fallbackExecution=true**, listener được phép xử lý event **ngay cả khi không có transaction**, thường ngay lúc publish theo cơ chế dispatch tương ứng.

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void withFallback(OrderPlaced event) {
    // Trong transaction: chờ commit.
    // Ngoài transaction: xử lý theo fallback ngay khi dispatch.
}
~~~

Vì vậy, với **fallbackExecution=true**, không thể nói “listener này luôn chứng minh DB đã commit”. Chỉ những lời gọi từ **transaction thực sự active** mới mang semantics AFTER_COMMIT.

## 4. Ma trận test tối thiểu phải có

| Kịch bản | @EventListener thường | AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION | DB row |
| --- | --- | --- | --- | --- | --- |
| Publish **trong transaction**, sau đó **commit** | Có | **Có** | Không | Có | **Còn** |
| Publish **trong transaction**, gọi **setRollbackOnly()** | Có | **Không** | **Có** | Có | **Không còn** |
| Publish rồi transaction ném **RuntimeException** | Có, nếu đã publish trước exception | **Không** | **Có** | Có | **Không còn** |
| Publish **ngoài transaction** | Có | **Không** (mặc định) | Không | Không | Không có thao tác DB trong test này |
| Publish ngoài transaction với **fallbackExecution=true** | Không thay đổi hành vi listener thường | Listener fallback **có chạy** | Theo annotation của từng listener | Theo annotation của từng listener | Không liên quan commit |
| Publish trong **@Transactional test** mà test kết thúc mặc định rollback | Có | **Không** | **Có** khi test transaction kết thúc | Có khi kết thúc | Ghi thay đổi được rollback |
| **@Transactional test** gọi TestTransaction.flagForCommit(); end() | Có | **Có sau end()** | Không | Có | Dữ liệu được commit |

**Không đọc sai cột “DB row”:** đây là trạng thái của thay đổi database được thực hiện trong transaction **ở ví dụ cụ thể**. Event in-memory có thể đã được gửi tới listener không transactional trước khi DB commit.

## 5. Sai lầm lớn nhất: test @Transactional mặc định rollback

Trong Spring TestContext Framework, một test method/class có **@Transactional** được chạy trong **test-managed transaction** nếu có transaction manager và listener test phù hợp. **Mặc định Spring sẽ rollback transaction sau khi test kết thúc**, nhằm giữ database test sạch.

~~~java
@Test
@Transactional
void misleadingTest() {
    service.createOrderAndPublishEvent();

    // Sai nếu mong AFTER_COMMIT đã chạy ở đây:
    // transaction do Spring Test quản lý vẫn đang active.
    verify(notificationSender).send(...);
}
~~~

Đây là **phản ví dụ** mang tính giải thích; không phải class chạy độc lập. Hai vấn đề:

1. Khi method test đang chạy, transaction chưa commit, nên **AFTER_COMMIT listener đúng thiết kế phải chưa chạy**.
2. Khi test kết thúc, Spring Test mặc định **rollback**; vì thế AFTER_COMMIT listener không chạy sau test.

Nhiều test bị hiểu nhầm là “listener hỏng” chỉ vì quên điều này. Hoặc test chỉ verify publisher và báo PASS dù chưa từng thử commit.

### Cách kiểm soát bằng TestTransaction

Trong test-managed transaction, Spring Test cung cấp:

- **TestTransaction.isActive()**: kiểm tra test transaction đang hoạt động.
- **TestTransaction.isFlaggedForRollback()**: xem outcome được đánh dấu.
- **TestTransaction.flagForCommit()**: đánh dấu transaction hiện tại cần commit khi kết thúc.
- **TestTransaction.flagForRollback()**: đánh dấu rollback.
- **TestTransaction.end()**: kết thúc **ngay lập tức** và commit/rollback theo flag, giúp assert sau completion.
- **TestTransaction.start()**: bắt đầu một test-managed transaction mới nếu cần, sau khi cái trước đã kết thúc.

Mẫu kiểm thử chuẩn:

~~~java
@Test
@Transactional
void verifyAfterCommit() {
    service.createOrderAndPublishEvent();
    assertFalse(recorder.afterCommitReceived());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertTrue(recorder.afterCommitReceived());
}
~~~

Đây là **snippet**, cần các class/test fixtures tương ứng. **flagForCommit() tự nó không commit**; chỉ **end()** hoặc việc Spring Test kết thúc transaction mới thực sự thực hiện outcome.

**@Commit** hoặc **@Rollback(false)** cũng có thể dùng để đổi hành vi cuối test, nhưng khi cần assert trong **cùng test method** ngay sau commit, **TestTransaction.end()** rõ ràng hơn. Một test commit thật sẽ để lại dữ liệu trừ khi cleanup phù hợp; hãy dùng database test cô lập và ID riêng.

## 6. Dự án Java 17+ chạy được: Spring transaction + H2 + JUnit Jupiter

Ví dụ dùng **Spring Framework 6.2.9**, **JDK 17+**, **Gradle 8.x**, **JUnit Jupiter 5.11.4** và **H2 2.3.232**. Nó không cần Spring Boot, web server hay broker.

Ta sử dụng:

- **DriverManagerDataSource** và **JdbcTemplate** để có thay đổi database quan sát được.
- **DataSourceTransactionManager** và **TransactionTemplate** để commit/rollback chính xác.
- Một bean listener có các methods **@EventListener** và **@TransactionalEventListener** theo nhiều phases.
- Các **Set** ghi nhận event ID đã thấy, nhằm assert theo ID mà không phụ thuộc thứ tự các callback hoặc trình tự chạy test.
- Hai file integration test, một file chủ động tạo transaction qua **TransactionTemplate**, một file dùng **@Transactional test + TestTransaction**.

**Không phụ thuộc vào thứ tự test:** mỗi test dùng **UUID mới**, vì vậy database in-memory và recorder có thể được Spring TestContext cache giữa các test mà không gây trùng ID.

### 6.1. Cấu trúc thư mục

~~~text
after-commit-test-demo/
  build.gradle
  src/test/java/demo/PhaseListenerIntegrationTest.java
  src/test/java/demo/TestManagedTransactionTest.java
~~~

Nội dung file **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework:spring-context:6.2.9'
    testImplementation 'org.springframework:spring-jdbc:6.2.9'
    testImplementation 'org.springframework:spring-test:6.2.9'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'

    testRuntimeOnly 'com.h2database:h2:2.3.232'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
~~~

**Java 17+** là yêu cầu cho Spring Framework 6.x. **Gradle 8.x** chạy với JDK phù hợp; các dependency ở đây đều dùng cho test, vì ví dụ không có application main. Lệnh ở mục 6.4 chạy **JUnit tests**, không phải lệnh **gradle run**.

### 6.2. File 1: PhaseListenerIntegrationTest.java

Nội dung **src/test/java/demo/PhaseListenerIntegrationTest.java**:

~~~java
package demo;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PhaseListenerIntegrationTest.Config.class)
public class PhaseListenerIntegrationTest {

    // POJO event thuần Java: không cần kế thừa ApplicationEvent.
    public record OrderPlaced(String id) {}

    public static final class Recorder {
        final Set<String> immediate = ConcurrentHashMap.newKeySet();
        final Set<String> beforeCommit = ConcurrentHashMap.newKeySet();
        final Set<String> afterCommit = ConcurrentHashMap.newKeySet();
        final Set<String> afterRollback = ConcurrentHashMap.newKeySet();
        final Set<String> afterCompletion = ConcurrentHashMap.newKeySet();
        final Set<String> withFallback = ConcurrentHashMap.newKeySet();

        @EventListener
        public void immediate(OrderPlaced event) {
            immediate.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderPlaced event) {
            beforeCommit.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            afterCommit.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderPlaced event) {
            afterRollback.add(event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderPlaced event) {
            afterCompletion.add(event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true)
        public void withFallback(OrderPlaced event) {
            withFallback.add(event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:after_commit_event_test;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            jdbc.execute(
                    "CREATE TABLE IF NOT EXISTS demo_orders "
                    + "(id VARCHAR(64) PRIMARY KEY)");
            return jdbc;
        }

        @Bean
        Recorder recorder() {
            return new Recorder();
        }
    }

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Recorder events;

    private TransactionTemplate tx() {
        return new TransactionTemplate(transactionManager);
    }

    private int rows(String id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders WHERE id = ?",
                Integer.class, id);
    }

    @Test
    void afterCommitRunsOnlyAfterSuccessfulCommit() {
        String id = UUID.randomUUID().toString();

        tx().executeWithoutResult(status -> {
            jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
            publisher.publishEvent(new OrderPlaced(id));

            // Đã publish, nhưng transaction vẫn chưa commit.
            assertTrue(events.immediate.contains(id));
            assertFalse(events.beforeCommit.contains(id));
            assertFalse(events.afterCommit.contains(id));
            assertFalse(events.afterRollback.contains(id));
            assertFalse(events.withFallback.contains(id));
        });

        // TransactionTemplate đã hoàn tất commit.
        assertTrue(events.beforeCommit.contains(id));
        assertTrue(events.afterCommit.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertTrue(events.withFallback.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertEquals(1, rows(id));
    }

    @Test
    void rollbackOnlyDoesNotTriggerAfterCommit() {
        String id = UUID.randomUUID().toString();

        tx().executeWithoutResult(status -> {
            jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
            publisher.publishEvent(new OrderPlaced(id));
            assertTrue(events.immediate.contains(id));

            status.setRollbackOnly();
        });

        assertFalse(events.beforeCommit.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertFalse(events.withFallback.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    void exceptionRollsBackAndSkipsAfterCommit() {
        String id = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class, () ->
                tx().executeWithoutResult(status -> {
                    jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
                    publisher.publishEvent(new OrderPlaced(id));
                    throw new IllegalStateException("force rollback");
                }));

        assertTrue(events.immediate.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    void outsideTransactionOnlyImmediateAndFallbackRun() {
        String id = UUID.randomUUID().toString();

        publisher.publishEvent(new OrderPlaced(id));

        assertTrue(events.immediate.contains(id));
        assertTrue(events.withFallback.contains(id));
        assertFalse(events.beforeCommit.contains(id));
        assertFalse(events.afterCommit.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertFalse(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }
}
~~~

**Giải thích thiết lập:**

- **@SpringJUnitConfig** tích hợp JUnit Jupiter với Spring TestContext, tải **Config** làm ApplicationContext.
- **DataSourceTransactionManager** quản lý transaction JDBC trên cùng **DataSource** được **JdbcTemplate** dùng. Vì dùng database transaction thật, có thể kiểm tra data đã commit hoặc rollback.
- **Recorder** là Spring-managed bean; adapter xử lý annotation **@TransactionalEventListener** được khởi tạo trong context. Việc gọi **publisher.publishEvent(...)** trong **TransactionTemplate** kích hoạt đăng ký synchronization đúng thread.
- Recorder dùng **Set** tách biệt theo phase và mỗi test dùng **UUID riêng**. Test không cần phụ thuộc thứ tự method hoặc xóa state của những test khác.
- **withFallback** nhận event khi commit, đồng thời nhận event ngoài transaction; trong nhánh rollback nó **không** chạy chỉ vì đã bật fallback.
- Lệnh **status.setRollbackOnly()** khiến TransactionTemplate kết thúc bằng rollback dù callback không ném exception.
- Khi callback ném **IllegalStateException**, TransactionTemplate thực hiện rollback rồi truyền exception ra caller, phù hợp cho test failure path.

### 6.3. File 2: TestManagedTransactionTest.java

File này minh họa hành vi đặc biệt của Spring TestContext khi chính test method có **@Transactional**. Nội dung **src/test/java/demo/TestManagedTransactionTest.java**:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PhaseListenerIntegrationTest.Config.class)
public class TestManagedTransactionTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PhaseListenerIntegrationTest.Recorder events;

    private int rows(String id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders WHERE id = ?",
                Integer.class, id);
    }

    @Test
    @Transactional
    void defaultTestTransactionRollsBack() {
        String id = UUID.randomUUID().toString();

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
        publisher.publishEvent(
                new PhaseListenerIntegrationTest.OrderPlaced(id));

        // Không thể kết luận listener hỏng: transaction còn mở.
        assertTrue(events.immediate.contains(id));
        assertFalse(events.afterCommit.contains(id));

        // Kết thúc theo rollback flag mặc định.
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertFalse(events.afterCommit.contains(id));
        assertTrue(events.afterRollback.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertEquals(0, rows(id));
    }

    @Test
    @Transactional
    void explicitlyCommitTestTransaction() {
        String id = UUID.randomUUID().toString();

        assertTrue(TestTransaction.isActive());

        jdbc.update("INSERT INTO demo_orders(id) VALUES (?)", id);
        publisher.publishEvent(
                new PhaseListenerIntegrationTest.OrderPlaced(id));

        assertFalse(events.afterCommit.contains(id));

        // flagForCommit chỉ đánh dấu; end() mới thực sự commit.
        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(events.afterCommit.contains(id));
        assertTrue(events.afterCompletion.contains(id));
        assertFalse(events.afterRollback.contains(id));
        assertEquals(1, rows(id));
    }
}
~~~

Với **@Transactional** ở test method, Spring TestContext tạo **test-managed transaction**. **TestTransaction.end()** kích hoạt kết thúc transaction ngay trong test, giúp kiểm chứng callback sau hoàn tất. Không đặt **@Transactional** cho mọi test một cách máy móc; nếu dùng **TransactionTemplate** để điều khiển commit/rollback, tránh để một test-managed transaction bên ngoài nuốt mất thao tác commit của TransactionTemplate.

### 6.4. Chạy và hiểu kết quả

Tại thư mục **after-commit-test-demo**, với Java 17+ và Gradle 8.x:

~~~bash
gradle --console=plain test
~~~

Kỳ vọng có **6 tests pass**: 4 test trong **PhaseListenerIntegrationTest** và 2 test trong **TestManagedTransactionTest**. Gradle có thể hiển thị tên test khác nhau theo cấu hình, nhưng những kết quả logic cần kiểm tra là:

~~~text
COMMIT                 -> AFTER_COMMIT: yes; AFTER_ROLLBACK: no;  DB rows: 1
ROLLBACK_ONLY          -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
EXCEPTION_ROLLBACK     -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
OUTSIDE_TRANSACTION    -> fallback: yes;  ordinary AFTER_COMMIT: no
TEST_DEFAULT_ROLLBACK  -> AFTER_COMMIT: no;  AFTER_ROLLBACK: yes; DB rows: 0
TEST_EXPLICIT_COMMIT   -> AFTER_COMMIT: yes; AFTER_ROLLBACK: no;  DB rows: 1
~~~

Khối trên là **bảng kỳ vọng về hành vi test**, **không phải stdout được chương trình in ra**. Các test không có **System.out.println()** tương ứng; Gradle sẽ hiển thị kết quả JUnit và trạng thái build tùy phiên bản. Một lần chạy thành công kết thúc với **BUILD SUCCESSFUL**.

Báo cáo chi tiết Gradle thường nằm trong **build/reports/tests/test/index.html**; nếu test fail, xem assertion nào sai và stack trace trước khi kết luận Spring không hỗ trợ AFTER_COMMIT.

**Lưu ý QA:** Kết quả không dựa vào ngủ cố định hay chờ executor. Các listeners trong demo đều **đồng bộ**; khi **TransactionTemplate.executeWithoutResult(...)** hoặc **TestTransaction.end()** trả về, callbacks theo phase đã được transaction manager điều phối. Demo không cần **@EnableAsync**.

## 7. Đọc kết quả test đúng cách

### 7.1. Commit test chứng minh ba điều khác nhau

Trong **afterCommitRunsOnlyAfterSuccessfulCommit()**, ta assert:

1. Sau **publishEvent(...)** nhưng khi transaction còn mở: **immediate** đã nhận event; **afterCommit** chưa có event.
2. Sau khi TransactionTemplate hoàn tất: **afterCommit** và **afterCompletion** đã nhận event; **afterRollback** không có.
3. **SELECT COUNT(*)** ở ngoài transaction trả về **1**, chứng minh row thực sự tồn tại sau commit.

Không chỉ verify một mock method được gọi rồi cho rằng dữ liệu chắc chắn commit.

### 7.2. Rollback test kiểm tra event không lọt qua nhánh commit

Trong **rollbackOnlyDoesNotTriggerAfterCommit()**, test cố ý set rollback-only. Nếu test đúng:

- **@EventListener thường** đã được gọi trước khi rollback.
- **AFTER_COMMIT** và listener fallback ràng buộc với phase commit **không chạy**.
- **AFTER_ROLLBACK** và **AFTER_COMPLETION** chạy.
- Database row **không tồn tại** sau rollback.

Nhờ vậy test phân biệt **“không có tác động hậu commit”** với việc “event không hề được publish”.

### 7.3. Exception rollback là kịch bản độc lập

Một service có thể ném runtime exception **sau khi publish event**. TransactionTemplate sẽ rollback và ném lỗi ra caller. Test phải xác nhận cả **ngoại lệ** lẫn **AFTER_ROLLBACK** và **DB row count = 0**.

Nếu exception xuất hiện **trước** khi event được publish, không thể đòi listener nhận một event chưa tồn tại. Khi viết test, hãy cố ý đặt publish trước exception nếu muốn kiểm tra callback khi rollback.

### 7.4. Ngoài transaction và fallbackExecution

Kịch bản **outsideTransactionOnlyImmediateAndFallbackRun()** chứng minh:

- Listener thường nhận event.
- Listener có **fallbackExecution=true** nhận event dù không có transaction.
- Các listener transaction-phase khác không chạy vì không có transaction hợp lệ.

Đây là **semantic test quan trọng**: nếu một nghiệp vụ cần đảm bảo “chỉ làm sau commit”, hãy cân nhắc có nên bật fallback hay không. Bật fallback có thể làm listener thực thi cả khi publisher vô tình bỏ qua transaction.

## 8. Tại sao TestTransaction hữu ích hơn chỉ dùng @Commit?

**@Commit** (hoặc **@Rollback(false)**) đổi outcome khi test-managed transaction kết thúc, nhưng thời điểm kết thúc mặc định là **sau khi method test trả về**. Vì vậy, trong một test method còn ở trong transaction, assert **afterCommit** vẫn có thể thất bại dù listener vận hành đúng.

**TestTransaction.flagForCommit(); TestTransaction.end()** tách rõ ba thời điểm:

~~~text
test starts
  |
  +-- test-managed transaction active
  +-- service publishes event
  +-- assert AFTER_COMMIT listener has not run
  |
  +-- TestTransaction.flagForCommit()
  +-- TestTransaction.end()
         |
         +-- actual commit
         +-- AFTER_COMMIT callback
  |
  +-- assert AFTER_COMMIT was invoked
  +-- assert data has committed
~~~

Muốn kiểm tra nhánh rollback: **TestTransaction.end()** theo rollback flag mặc định hoặc **flagForRollback()** rồi **end()**.

**Không được gọi TestTransaction.end() khi không có test-managed transaction active.** API này thuộc **Spring TestContext**; nó không thay thế TransactionTemplate trong code production. Nếu cần tiếp tục làm việc trong một test-managed transaction mới sau **end()**, có thể gọi **TestTransaction.start()**, nhưng phải hiểu dữ liệu đã commit ở transaction trước không được tự rollback bởi transaction sau.

Trong test có **@Transactional**, lifecycle của **@BeforeEach** và **@AfterEach** thường cũng nằm trong test-managed transaction. Với **@BeforeTransaction** và **@AfterTransaction**, có thể kiểm tra/chuẩn bị bên ngoài transaction trong trường hợp cần xác minh trạng thái DB trước hoặc sau transaction. Không dùng **@BeforeAll** để giả định đang có test-managed transaction.

## 9. Tránh test giả thành công khi dùng mocks

Một unit test kiểu:

~~~java
OrderListener listener = new OrderListener(notificationSender);
listener.on(new OrderPlaced("A"));
verify(notificationSender).send("A");
~~~

Chỉ chứng minh **method Java được gọi trực tiếp**. Nó **không chứng minh** Spring đăng ký **@TransactionalEventListener** hay chờ commit, vì test hoàn toàn bỏ qua **ApplicationEventPublisher**, listener adapter và transaction synchronization.

Nếu muốn test logic bên trong listener, unit test trực tiếp vẫn có ích. Nhưng để chứng minh **AFTER_COMMIT/rollback** phải có **integration test** qua Spring ApplicationContext và một transaction manager.

### Mock phần nào cho phù hợp?

- **Unit test business logic**: mock repository/gateway để kiểm tra quyết định.
- **Integration test transaction semantics**: dùng transaction manager thật và event publisher thật.
- **External side effects**: có thể thay email/SMS/payment gateway bằng một **fake recorder** để assert callback chạy đúng lúc.
- **Database**: H2 có ích để học, nhưng những trường hợp phụ thuộc isolation, trigger, dialect, unique constraint hoặc behavior của production DB nên được xác minh tiếp với PostgreSQL/MySQL trong Testcontainers hoặc môi trường tương đương.

Một test chỉ verify **publisher.publishEvent(...) được gọi một lần** là test publication, không phải test AFTER_COMMIT.

## 10. Phân biệt application-managed, test-managed và nested transaction

### 10.1. TransactionTemplate bên trong test không @Transactional

Đây là cách rõ nhất khi chỉ muốn kiểm tra commit/rollback:

~~~java
txTemplate.executeWithoutResult(status -> {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.id()));
});
assertTrue(recorder.wasReceivedAfterCommit(order.id()));
~~~

TransactionTemplate chủ động mở và kết thúc transaction. Assertion sau execute diễn ra **sau completion**. Snippet cần test fixture và các class tương ứng.

### 10.2. TransactionTemplate bên trong test @Transactional

Nếu test method đã có **@Transactional** và TransactionTemplate mặc định **PROPAGATION_REQUIRED**, template có thể **tham gia transaction đang mở** chứ không tự tạo một commit riêng. Khi template trả về, outer test transaction vẫn chưa kết thúc; AFTER_COMMIT listener vẫn phải chờ, và cuối test có thể rollback.

Vì vậy không nên vô ý kết hợp cả hai rồi mong **TransactionTemplate.execute(...)** trong test đã commit. Hãy chọn một phương pháp rõ ràng: test method **không @Transactional**, hoặc dùng **TestTransaction** để kết thúc outer transaction.

### 10.3. REQUIRES_NEW có transaction outcome độc lập

Một application service method có **Propagation.REQUIRES_NEW** có thể tạo transaction mới độc lập với outer transaction. Nếu event được publish **trong transaction mới**, AFTER_COMMIT gắn với **transaction mới**, không phải outer transaction.

Ví dụ logic:

~~~text
outer TX starts
   |
   +-- inner REQUIRES_NEW TX starts
   |       -> save row
   |       -> publish EventInner
   |       -> COMMIT inner
   |           -> AFTER_COMMIT(EventInner) runs
   |
   +-- outer TX later ROLLBACK
~~~

Việc outer transaction rollback **không tự thu hồi inner commit**. Nếu đang viết test yêu cầu “event không được phát khi toàn bộ use case thất bại”, phải kiểm tra contract transaction boundary thực tế, không chỉ nhìn annotation ở một method.

Ngoài ra, **self-invocation** gọi từ method này sang method khác trong cùng bean thường bỏ qua Spring proxy; **@Transactional(REQUIRES_NEW)** có thể không được áp dụng như mong đợi. Test transaction propagation nên đi qua Spring-managed proxy thật hoặc dùng TransactionTemplate với propagation được cài trực tiếp.

## 11. AFTER_COMMIT có được ghi database thêm ngay không?

Một bẫy nâng cao: tại **AFTER_COMMIT**, database transaction gốc đã commit, nhưng **transactional resources** có thể vẫn được bind/access trong bước completion. Tài liệu Javadoc Spring cảnh báo: nếu callback truy cập dữ liệu ở giai đoạn **AFTER_COMMIT / AFTER_ROLLBACK / AFTER_COMPLETION**, code có thể còn “tham gia” vào transaction resources cũ, nhưng **thay đổi mới không được commit** như một transaction độc lập.

Vì vậy đoạn sau dễ bị hiểu sai:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    auditRepository.save(new AuditRecord(event.id()));
}
~~~

**Đây là phản ví dụ về giả định transaction**, không phải code độc lập. Một lời gọi save ở callback sau commit không tự bảo đảm đã có commit mới.

Nếu phải ghi audit record sau commit trong một transaction riêng, thường đặt thao tác DB vào **một Spring-managed service khác** với **@Transactional(propagation = Propagation.REQUIRES_NEW)**, gọi qua proxy:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(String id) {
        // Ghi audit vào transaction mới.
    }
}
~~~

Snippet cần imports và repository tương ứng. **REQUIRES_NEW** cũng có chi phí connection pool và transaction riêng; cần cân nhắc lỗi ở callback sau khi giao dịch chính đã commit. Không bao giờ quảng bá AFTER_COMMIT như bảo đảm eventual delivery hoặc atomicity giữa DB và email/broker.

### Test thêm nếu có ghi DB trong AFTER_COMMIT

Một integration test nên:

1. Commit transaction chính đã publish event.
2. Assert listener AFTER_COMMIT chạy.
3. Dùng **một transaction mới** để đọc audit row, xác nhận nó thực sự **được commit**, không chỉ nằm trong persistence context cũ.
4. Mô phỏng audit writer lỗi, xác minh transaction chính vẫn đã commit và hệ thống có chính sách retry/giám sát.
5. Nếu audit là dữ liệu bắt buộc cùng transaction với nghiệp vụ, cân nhắc ghi audit **trước commit trong cùng DB transaction**, không dựa vào callback after commit.

## 12. AFTER_COMMIT không bảo đảm event không mất sau crash

**@TransactionalEventListener(AFTER_COMMIT)** chỉ là callback liên quan transaction đang hoạt động. Sau khi DB commit nhưng trước khi listener xử lý xong, JVM có thể chết; nếu listener cần gửi notification hoặc integration event quan trọng, tác vụ memory-only có thể bị mất.

Một thiết kế bền vững hơn là **transactional outbox**:

~~~text
BEGIN DB TRANSACTION
  -> save order
  -> save outbox(eventId, aggregateId, payload)
COMMIT
  -> outbox worker reads row
  -> send message / retry on failure
  -> mark row delivered
consumer -> idempotent processing
~~~

**Outbox row và business state** được ghi trong cùng transaction. Nếu transaction rollback, cả hai đều rollback; nếu commit, worker có thể phát lại sau restart. Việc message bị gửi lặp vẫn có thể xảy ra khi worker gửi thành công nhưng chưa đánh dấu delivered, nên **idempotency** là bắt buộc.

**Cách kiểm thử outbox khác kiểm thử AFTER_COMMIT:** cần xác nhận atomic commit/rollback của hai bảng, trạng thái worker sau crash, duplicate processing và khả năng retry; một unit test listener không đủ.

## 13. Những tình huống khiến test AFTER_COMMIT dễ sai

| Sai lầm | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Test method có **@Transactional** mặc định rollback | AFTER_COMMIT không chạy, tưởng listener hỏng | Dùng **TestTransaction.flagForCommit(); end()** hoặc **@Commit** với assertion sau transaction |
| Assert listener ngay sau publish khi transaction còn mở | False negative | Kết thúc commit trước khi assert |
| Gọi thẳng method listener | Unit test pass nhưng phase không được kiểm tra | Publish qua **ApplicationEventPublisher** + Spring context |
| Chỉ verify publisher đã được gọi | Không biết listener chạy trước hay sau commit | Assert recorder và trạng thái DB sau transaction |
| Publish ngoài transaction | Transactional listener bị bỏ qua | Tạo transaction thật; hiểu **fallbackExecution** |
| Bật fallbackExecution mà vẫn coi mọi callback là post-commit | Có thể chạy ngay ngoài transaction | Kiểm thử riêng outside-transaction path |
| Dùng TransactionTemplate REQUIRED bên trong @Transactional test | Template join outer transaction, chưa commit | Bỏ @Transactional ở test hoặc dùng TestTransaction |
| Mock transaction manager sai | Callback không gắn transaction thật | Dùng transaction manager thật trong integration test |
| Test event do service publish trước khi ném exception | @EventListener thường đã chạy dù DB rollback | Dùng transactional phase phù hợp |
| Chỉ assert số lần handler mà không kiểm tra DB | Không xác minh atomicity | Kiểm tra row count ngoài transaction |
| Test @Async bằng assertion lập tức | Test flaky, executor chưa xong | Dùng Awaitility/CountDownLatch và executor đúng |
| AFTER_COMMIT ghi DB nhưng không mở transaction mới | Audit row có thể không commit | Dùng REQUIRES_NEW và verify bằng transaction độc lập |
| Không phân biệt REQUIRES_NEW với outer TX | Inner commit event dù outer rollback | Test từng transaction boundary |
| Nhầm RuntimeException với checked exception rollback mặc định | Outcome không như kỳ vọng | Xác định rollback rules; test cả checked exception nếu use case cần |
| Dùng H2 rồi mặc định prod DB cùng isolation/trigger behavior | Test xanh nhưng production khác | Testcontainers/DB thật cho tình huống phụ thuộc dialect |
| Không có event ID hoặc test isolation | Test order-dependent, assertion trùng | Dùng ID duy nhất và dữ liệu cô lập |
| Dùng listener làm hệ thống đảm bảo delivery | Crash sau commit vẫn mất task | Outbox/queue + retry/idempotency |

## 14. @Async và reactive transaction: giới hạn phạm vi test

### 14.1. Async event listener

**@Async** đưa việc xử lý sang executor. Transaction context kiểu imperative thường gắn với thread và **không được truyền tự động** sang worker thread. Với **@TransactionalEventListener**, cơ chế đăng ký callback được gắn vào transaction tại lúc event được publish; không nên hiểu việc gắn **@Async** đồng nghĩa có transaction gốc trong worker.

Khi muốn test một listener **chạy bất đồng bộ sau commit**, ngoài outcome transaction phải kiểm tra:

- **Không scheduling xử lý hậu commit khi rollback**.
- Sau commit, task đã được submit vào executor phù hợp.
- Chờ listener hoàn tất bằng **CountDownLatch / Awaitility**, không dựa vào **Thread.sleep()**.
- Các lỗi async được log/giám sát; caller có thể không nhận exception.
- Trace context/tenant context nếu cần phải được propagate riêng.
- Không giả định @Async bảo đảm task còn tồn tại sau restart.

Ví dụ mục 6 cố ý dùng listener đồng bộ để cô lập bài toán transaction phase, tránh concurrency làm kết quả kiểm thử mơ hồ.

### 14.2. Reactive transaction

Từ Spring Framework 6.1, transactional event listener còn hỗ trợ trường hợp transaction phản ứng **reactive**, nhưng reactive transaction context được lưu trong **Reactor Context**, không giống ThreadLocal của imperative **PlatformTransactionManager**. Với reactive, cần công bố event kèm transaction context phù hợp (tham khảo **TransactionalEventPublisher**).

**Không thể copy nguyên test TransactionTemplate/DataSourceTransactionManager của bài này** rồi kết luận về reactive transaction. Bài này kiểm thử **imperative JDBC transaction**; nếu dùng R2DBC/reactive hãy viết integration test cho ReactiveTransactionManager, context propagation và lifecycle thích hợp.

## 15. Chiến lược kiểm thử production nên áp dụng

Để kiểm thử domain events trong một ứng dụng Spring thực tế, nên tách các lớp test:

### Unit test domain/use case

- Domain có phát đúng sự thật **OrderPlaced** hay không?
- Service có quyết định publish đúng khi nghiệp vụ hợp lệ không?
- Repository/port có được gọi đúng không?

Các test này có thể dùng fake/mocks. Chúng **không xác minh transaction callback phase**.

### Integration test transaction-bound listener

- Chạy Spring ApplicationContext với transaction manager thật.
- Publish qua ApplicationEventPublisher trong transaction thật.
- Test commit và rollback, bao gồm rollback-only và exception.
- Assert listener theo phase **sau transaction completion**.
- Assert database đã commit hoặc rollback như kỳ vọng.
- Test fallback ngoài transaction.
- Nếu listener cần ghi DB mới, test transaction riêng/REQUIRES_NEW.

### End-to-end / failure-injection tests

- Dùng production-like database khi isolation/dialect là yếu tố quan trọng.
- Tạo crash, transaction timeout, connection failure, duplicate event hoặc broker outage.
- Test outbox/inbox/retry và idempotency.
- Đảm bảo monitoring/correlation giúp nhận ra post-commit handler lỗi.

Không ép mọi bài kiểm thử vào **@SpringBootTest** nếu chỉ cần vài bean Spring Framework. Với một config nhỏ, **@SpringJUnitConfig** nhanh và có phạm vi rõ. Nếu ứng dụng phụ thuộc auto-configuration cụ thể của Spring Boot, mới cân nhắc test slice hoặc @SpringBootTest tương ứng.

## 16. Checklist trước khi kết luận QA PASS

1. **Listener được tạo bởi Spring bean, không bị gọi trực tiếp?**
2. **Event được publish qua ApplicationEventPublisher trong transaction thật?**
3. **Biết phase mặc định là AFTER_COMMIT?**
4. **Có assert BEFORE/AFTER đúng thời điểm, sau completion?**
5. **Commit path: AFTER_COMMIT chạy, AFTER_ROLLBACK không chạy, DB còn dữ liệu?**
6. **Rollback path: AFTER_COMMIT không chạy, AFTER_ROLLBACK chạy, DB không còn dữ liệu?**
7. **Có test exception xảy ra sau khi publish?**
8. **Có test publish ngoài transaction và fallbackExecution=true/false?**
9. **Nếu test có @Transactional, đã dùng TestTransaction hoặc kiểm tra sau transaction?**
10. **Nếu TransactionTemplate join outer transaction, đã không nhầm template return với commit?**
11. **Nếu dùng @Async, đã chờ completion deterministically và kiểm tra lỗi executor?**
12. **Nếu listener cần ghi DB hậu commit, đã có transaction mới và verify committed row?**
13. **Nếu event không được mất, đã có outbox/queue thay vì chỉ memory callback?**
14. **Có test trên DB phù hợp khi phụ thuộc isolation, constraint hoặc SQL dialect?**
15. **Assertion không dựa vào thứ tự test hoặc thời gian chờ cố định?**

**Kết luận:** Kiểm thử **@TransactionalEventListener(AFTER_COMMIT)** đúng nghĩa là kiểm thử **outcome của transaction**, không chỉ thao tác publish. Dùng **TransactionTemplate** để chủ động commit/rollback trong integration test, hoặc **TestTransaction** khi test method đã có **@Transactional**. Luôn xác nhận cả **callback theo phase** và **trạng thái DB sau completion**. **AFTER_COMMIT** giải quyết vấn đề “chỉ phản ứng sau commit”, nhưng không thay thế transaction mới cho thao tác ghi hậu commit và không biến listener thành durable queue.

### Tài liệu chính thức

- Spring Framework 6.2 Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 Reference — *TestContext Framework Transaction Management*: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 Javadoc — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2 Javadoc — *TransactionPhase*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework 6.2 Javadoc — *TestTransaction*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 Javadoc — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework 6.2 Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative.html
