# Preemptive timeout và rủi ro thao tác ngoài ngữ cảnh giao dịch trong kiểm thử Spring Boot

## 1. Hiện tượng: test được rollback nhưng dữ liệu vẫn tồn tại

Trong một integration test của Spring Boot, lập trình viên thường dùng `@Transactional`, `@JdbcTest` hoặc `@DataJpaTest` và kỳ vọng các thay đổi database được tự động **rollback** sau mỗi test. Kỳ vọng này thường đúng khi code chạy trên **thread thực thi test**. Tuy nhiên, nếu bọc thao tác ghi bằng `assertTimeoutPreemptively(...)` của JUnit Jupiter, đoạn callback được chạy trên **một thread khác**, tách khỏi transaction mà Spring TestContext đã liên kết với thread test. Kết quả có thể rất bất ngờ: assertion không hề báo timeout, test vẫn xanh, nhưng INSERT/UPDATE/DELETE lại được commit và còn trong database sau khi test được Spring rollback.

Đây không phải lỗi của JDBC, JPA hay việc Spring “quên rollback”. **Spring đã rollback đúng transaction của test**, nhưng lệnh ghi được thực thi ở thread khác nên **không nằm trong transaction ấy**. Với JDBC/H2 thông thường, một lệnh INSERT không thuộc Spring transaction trên connection có auto-commit được commit độc lập và không bị ảnh hưởng bởi rollback ở thread ban đầu.

**Tình huống ngắn:**

~~~java
// Trong một test đã được Spring quản lý transaction:
assertTimeoutPreemptively(Duration.ofSeconds(5), () -> {
    jdbcTemplate.update(
            "INSERT INTO audit_marks (id, note) VALUES (?, ?)",
            42L, "escaped");
});
~~~

Đây là snippet nguy hiểm để minh họa, không phải chương trình độc lập. Ngay cả khi callback chạy trong 1 ms và không có timeout, nó vẫn chạy trên thread riêng của JUnit. Vì vậy **timeout không nhất thiết phải xảy ra thì nguy cơ mới tồn tại**.

**Mục tiêu bài học:**

1. Phân biệt **test-managed transaction**, **Spring-managed transaction** và **application-managed transaction**.
2. Giải thích Spring TestContext liên kết transaction với **ThreadLocal** trước khi chạy test method.
3. So sánh JUnit Jupiter **assertTimeout**, **assertTimeoutPreemptively** và **@Timeout(threadMode=...)**.
4. Hiểu vì sao `assertTimeoutPreemptively` có thể làm thao tác ghi thoát khỏi rollback, đồng thời gây rò rỉ ThreadLocal khác.
5. Xác minh transaction state bằng **TestTransaction.isActive()** và **TransactionSynchronizationManager.isActualTransactionActive()** đúng ngữ cảnh.
6. Viết ví dụ Java 17 + Spring Boot **3.3.5** + Gradle + H2 + **@JdbcTest**, có test an toàn và một demo nguy hiểm **@Disabled mặc định**.
7. Kiểm tra rollback thật **sau test** bằng **@AfterTransaction**, không chỉ nhìn dữ liệu khi transaction còn mở.
8. Dùng **try/finally**, database chỉ dành cho test và cleanup để tránh để lại dữ liệu khi cố ý minh họa commit ngoài transaction.
9. Biết các biên khác cũng làm mất transaction context: `CompletableFuture`, `ExecutorService`, `@Async`, server-side HTTP threads, và propagation **REQUIRES_NEW**.
10. Xây checklist tránh false-positive trong CI và không dùng preemptive timeout như biện pháp bảo đảm rollback/kill task.

**Phạm vi:** Spring Framework TestContext/JUnit Jupiter (không phải HTTP request timeout, SQL statement timeout hoặc transaction timeout production). Code sử dụng JDK 17, Spring Boot 3.3.5, Spring Framework 6.1.x và H2. Không triển khai thực tế trên database production để chạy demo có ghi dữ liệu ngoài transaction.

## 2. Test-managed transaction khác transaction thường ở đâu?

Ba loại dễ bị gọi chung là “transaction”:

| Khái niệm | Ai tạo/quản lý? | Nơi lưu ngữ cảnh | Kết thúc thế nào? |
|---|---|---|---|
| **Test-managed transaction** | `TransactionalTestExecutionListener` của Spring TestContext; có thể điều khiển bằng `TestTransaction` | ThreadLocal của thread test | Mặc định rollback sau transactional test |
| **Spring-managed transaction** | Spring `PlatformTransactionManager`, thường qua `@Transactional` trên service/proxy | Transaction được bind theo thread hiện hành | Commit/rollback theo propagation và kết quả invocation |
| **Application-managed transaction** | Code chủ động dùng `TransactionTemplate`, transaction manager hoặc connection JDBC | Theo cơ chế transaction code/connection | Theo lệnh commit/rollback của ứng dụng |

Khi transactional test gọi một Spring service với propagation `REQUIRED`, service thường **tham gia cùng transaction đang có trên thread test**. Vì vậy thay đổi dữ liệu do service thực hiện cũng được rollback cuối test. Nhưng khi callback chạy ở thread mới không có test-managed transaction, service `@Transactional(REQUIRED)` có thể **tạo transaction mới và commit thành công** tại thời điểm service trả về. Trường hợp JDBC thông thường không mở Spring transaction thì connection có thể auto-commit sau update.

Các cơ chế transaction khác nhau có thể cùng hiện diện. **Không phải cứ method test có @Transactional thì mọi thread sinh ra từ nó đều được bao phủ.**

### 2.1. Vòng đời của transactional test

~~~text
Thread T1 — JUnit/Spring test thread
  |
  | Spring TestContext / TransactionalTestExecutionListener
  | Bắt đầu test-managed transaction TX-A
  | Bind JDBC Connection/transaction state với ThreadLocal(T1)
  |
  +-- @BeforeEach        [thông thường bên trong TX-A]
  +-- @Test method        [bên trong TX-A]
  |     jdbc.update(...)  [tham gia TX-A]
  +-- @AfterEach         [thông thường bên trong TX-A]
  |
  | Rollback TX-A (default)
  | Unbind resources / transaction state trên T1
  |
  +-- @AfterTransaction   [ngoài TX-A]
~~~

`@BeforeTransaction` được chạy **trước** khi TX-A bắt đầu; `@AfterTransaction` chạy **sau** khi TX-A kết thúc. Đây là các hooks chuyên dụng của Spring TestContext, hữu ích để kiểm chứng trạng thái database thật sau rollback. JUnit `@BeforeAll`/`@AfterAll` cũng không nằm trong test-managed transaction mặc định. Các methods `@BeforeEach`/`@AfterEach` nằm trong test-managed transaction đối với transactional test, dù bản thân gắn `@Transactional` lên lifecycle method không phải cơ chế kích hoạt transaction test.

**Điều kiện cần:** Spring TestContext phải có `PlatformTransactionManager` và test chạy với Spring `@Transactional`, hoặc test slice có transaction mặc định như `@JdbcTest`. Với `@JdbcTest` của Spring Boot 3.3, tests mặc định transactional và rollback. Nếu test thực tế không transactional, không có transaction để “thoát khỏi” — preemptive timeout vẫn có nguy cơ thread-local khác nhưng không thể đòi Spring rollback một transaction chưa từng tồn tại.

### 2.2. Đường đi của preemptive callback

~~~text
Thread T1 — transactional test thread        Thread T2 — timeout worker
┌───────────────────────────────────┐      ┌─────────────────────────────┐
│ Begin TX-A; bind ThreadLocal(T1)   │      │ Không có TX-A trên T2       │
│                                   │      │                             │
│ assertTimeoutPreemptively(...) ─────────►│ jdbc.update INSERT          │
│                                   │      │ Lấy connection độc lập      │
│                                   │      │ Tự commit hoặc TX mới      │
│ callback trả về; test kết thúc     │◄─────│                             │
│ Rollback TX-A                      │      └─────────────────────────────┘
│ Chỉ undo những writes thuộc TX-A  │
└───────────────────────────────────┘

Kết quả: dữ liệu do T2 commit có thể vẫn tồn tại sau rollback của TX-A.
~~~

JDBC connection mà Spring gắn vào T1 thường được truy xuất qua `TransactionSynchronizationManager` và `DataSourceUtils`. T2 không thấy tài nguyên ThreadLocal tương ứng. **ThreadLocal không tự được lan truyền qua thread pool**; càng không nên tự sao chép một đối tượng Connection/TransactionStatus từ T1 sang T2 để chữa lỗi — việc đó không làm transaction trở thành thread-safe.

## 3. Ba cách đặt timeout trong JUnit Jupiter

### 3.1. assertTimeout: kiểm sau khi code hoàn tất, cùng thread

`Assertions.assertTimeout(Duration, Executable)` chạy callback **trên thread gọi hàm**. Callback chạy xong, JUnit đo thời gian và fail nếu vượt giới hạn. Nó **không cắt ngang callback sớm** chỉ vì đã quá thời gian.

~~~java
assertTimeout(Duration.ofSeconds(3), () -> {
    // Cùng thread với transactional test.
    repository.save(entity);
});
~~~

Snippet là ý tưởng; tên repository/entity cần được định nghĩa trong app thật. Vì chạy trong cùng thread, callback vẫn nhìn thấy TX-A của test và write thường được rollback. Đây là phương án ưu tiên nếu bạn đang test database với test-managed transaction và chỉ cần **đưa ra assertion về thời gian thực thi**.

**Đánh đổi:** một tác vụ bị treo có thể kéo dài test, vì `assertTimeout` không buộc dừng code khi hết hạn. Cần phối hợp timeout của JDBC driver/HTTP client/DB statement khi muốn đặt giới hạn tài nguyên thực; không thay bằng một preemptive wrapper nguy hiểm chỉ để có thời gian tối đa.

### 3.2. assertTimeoutPreemptively: chạy callback ở thread khác

`Assertions.assertTimeoutPreemptively(Duration, Executable)` luôn chạy executable/supplier trên **thread khác thread gọi**. Nếu vượt giới hạn, JUnit cố ngắt bằng `Thread.interrupt()` và báo thất bại; **không bảo đảm dừng mọi loại công việc**. Một tác vụ không tôn trọng interrupt có thể tiếp tục sau khi assertion timeout đã trả kết quả, gây side effects muộn.

~~~java
assertTimeoutPreemptively(Duration.ofSeconds(3), () -> {
    // KHÁC thread với test-managed transaction.
    repository.save(entity);
});
~~~

Snippet mang tính cảnh báo, **không** nên đưa thẳng vào transactional integration test. Vấn đề không nằm ở số giây: ngay cả callback hoàn tất trước 3 giây thì nó vẫn ở thread khác. Ngoài JDBC rollback, những ngữ cảnh gắn ThreadLocal khác như Spring SecurityContext, request attributes, MDC logging hoặc locale context cũng có thể không được truyền như bạn kỳ vọng, tùy công cụ/framework.

### 3.3. @Timeout: xem threadMode, không chỉ xem số giây

JUnit Jupiter hỗ trợ annotation `@Timeout` và `Timeout.ThreadMode`:

| Cấu hình | Chạy đoạn test ở thread nào? | Tác động đối với test-managed transaction |
|---|---|---|
| `@Timeout(..., threadMode = SAME_THREAD)` | Cùng thread với Spring TestContext | Giữ phạm vi TX-A; khi quá hạn JUnit có thể interrupt thread |
| `@Timeout(..., threadMode = SEPARATE_THREAD)` | Thread khác, preemptive | Có rủi ro giống assertTimeoutPreemptively |
| `@Timeout(..., threadMode = INFERRED)` | Theo tham số cấu hình JUnit | Cần biết config; không suy đoán luôn an toàn |
| `assertTimeout(...)` | Thread gọi assertion | Non-preemptive; giữ TX-A của thread đó |
| `assertTimeoutPreemptively(...)` | Thread khác thread gọi | Tách TX-A ngay cả khi callback hoàn thành nhanh |

`INFERRED` là mặc định cho `@Timeout`; nó lấy từ `junit.jupiter.execution.timeout.thread.mode.default`. Nếu không có giá trị cấu hình hợp lệ, JUnit Jupiter dùng **SAME_THREAD** như phương án dự phòng. Với transactional tests nhạy cảm, nên **đặt SAME_THREAD tường minh** để không phụ thuộc một thay đổi cấu hình global trong suite/CI.

~~~java
@Test
@Timeout(
        value = 5,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
void testWithinSameThread() {
    // Hợp lý cho Spring test-managed transaction.
}
~~~

Đây là snippet trong lớp JUnit có import `org.junit.jupiter.api.Timeout`, `org.junit.jupiter.api.Test` và `java.util.concurrent.TimeUnit`; mã hoàn chỉnh ở mục 6.

**Cảnh báo về interrupt:** SAME_THREAD tránh đổi thread nhưng không bảo đảm mọi tác vụ có thể bị ngắt an toàn. Một JDBC operation có thể bỏ qua interrupt; một operation có thể phát sinh side effects trước khi timeout được đánh dấu. Timeout là công cụ báo hiệu một vi phạm thời gian, **không phải rollback policy hay transaction boundary**.

## 4. Tại sao `@Transactional` không bảo vệ mọi thread?

Một số hiểu nhầm:

**Hiểu nhầm A:** `@Transactional` trên test method khiến mọi `Runnable` hoặc `CompletableFuture` bên trong tự tham gia cùng transaction.

Sai. Spring test transaction gắn theo thread; một callback chạy ở thread khác không tự nhận transaction của T1. Nếu lời gọi service trong T2 có `@Transactional(REQUIRED)`, Spring có thể bắt đầu **transaction mới**, không phải tham gia TX-A.

**Hiểu nhầm B:** `assertTimeoutPreemptively(5s)` chạy chỉ mất 1 ms nên “không có khác biệt” với `assertTimeout(5s)`.

Sai. Chọn thread riêng là một phần bản chất API, **không phụ thuộc có bị timeout hay không**. Nhanh hơn giới hạn chỉ bảo đảm không có timeout assertion failure.

**Hiểu nhầm C:** Nếu `TestTransaction.isActive()` true ở test method thì cũng true trong async callback.

Sai. `TestTransaction` quan sát **test-managed transaction của thread gọi nó**, không kiểm toàn bộ JVM. Trong T2, `TestTransaction.isActive()` thường false. `TransactionSynchronizationManager.isActualTransactionActive()` cũng false nếu T2 chưa mở transaction riêng; sau khi service tạo Spring-managed transaction mới, flag này có thể true **nhưng đó không phải TX-A**. Phải phân biệt “có transaction nào đó” với “đúng transaction của test”.

**Hiểu nhầm D:** Có thể dùng `@Rollback` hoặc `@Transactional` trên test để buộc thu hồi dữ liệu đã commit ở thread khác.

Sai. Rollback chỉ điều khiển transaction được quản lý. Không có cơ chế tự động quay ngược một transaction độc lập đã commit trên connection khác. `@Rollback(false)` hoặc `@Commit` còn chủ động đổi policy của transaction test, làm vấn đề khác đi.

**Hiểu nhầm E:** Nếu thêm `@Transactional` lên service, sẽ chữa được việc worker mất transaction test.

Không. Khi service được gọi từ T2, proxy `@Transactional` có thể mở **một transaction mới**, hoàn tất và commit. `@Transactional` rất hữu ích cho business atomicity nhưng **không tự gắn T2 vào test-managed transaction của T1**.

**Hiểu nhầm F:** Không dùng preemptive timeout thì mọi side effect chắc chắn rollback.

Cũng không đúng. `@Transactional(propagation=REQUIRES_NEW)` có thể commit transaction riêng ngay cả trong cùng thread; gọi HTTP đến server chạy thread/transaction khác, gửi message broker, gọi API ngoài hoặc ghi file cũng không bị database rollback của test thu hồi. Non-preemptive timeout chỉ khắc phục **một nguyên nhân đổi thread do assertion**, không bảo đảm tất cả side effects đều nằm trong TX-A.

## 5. Test phải chứng minh điều gì?

Một test tốt cho chủ đề này cần kiểm **cả thời điểm đang chạy và sau rollback**:

| Kiểm tra | Khi test vẫn đang trong TX-A | Sau TX-A rollback |
|---|---|---|
| `TestTransaction.isActive()` trên T1 | true | false |
| `TransactionSynchronizationManager.isActualTransactionActive()` trên T1 | thường true | false |
| INSERT trong `assertTimeout(...)` trên T1 | Có thể thấy row mới trong TX-A | Row biến mất do rollback |
| INSERT bên trong `assertTimeoutPreemptively(...)` trên T2 | Có thể thấy row nếu T2 đã commit | Row vẫn có thể tồn tại |
| @AfterTransaction | Chưa chạy | Có thể truy vấn trạng thái cuối bằng connection không tham gia TX-A |

**Không chứng minh rollback bằng SELECT ngay sau INSERT trong test.** Một SELECT ở cùng T1/TX-A nhìn thấy **dữ liệu chưa commit của chính nó**; nó không cho biết dữ liệu sẽ còn hay mất khi rollback. Phải kiểm bên ngoài TX-A, ví dụ trong `@AfterTransaction`.

Để tránh làm ô nhiễm bộ test, demo preemptive commit ở phần sau **được @Disabled theo mặc định**. Khi chủ động bỏ @Disabled, chạy chỉ với **embedded H2 test database** và có hook `@AfterTransaction` vừa assert kết quả, vừa **DELETE dữ liệu đã commit trong finally**. Đây là test đào tạo, **không chạy trên DB dùng chung**. Một callback treo không phản hồi interrupt vẫn có thể chạy muộn sau cleanup; đó là lý do ta không kích hoạt demo nguy hiểm trong test suite thường ngày.

## 6. Project Spring Boot 3.3.5 chạy được

### 6.1. Cấu trúc project

~~~text
settings.gradle
build.gradle
src/main/java/demo/tx/TxTimeoutApplication.java
src/test/resources/schema.sql
src/test/java/demo/tx/SameThreadTimeoutTest.java
src/test/java/demo/tx/PreemptiveThreadBoundaryTest.java
src/test/java/demo/tx/PreemptiveWriteDemoTest.java
~~~

Ở đây **không cần data.sql**: schema.sql tạo bảng rỗng; mỗi test dùng các ID riêng. `@JdbcTest` là slice JDBC được Spring Boot hỗ trợ với embedded H2, tự cấu hình JdbcTemplate và test-managed transaction. Chúng ta không cần @SpringBootTest, embedded HTTP server hay Spring Data JPA chỉ để kiểm chứng transactional boundary.

**settings.gradle**

~~~groovy
rootProject.name = 'spring-preemptive-timeout-tx'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích dependencies:** starter-jdbc mang JdbcTemplate/DataSource/transaction manager; H2 là embedded database cho JDBC test; starter-test chứa JUnit Jupiter, Spring Boot test và Spring TestTransaction support. Spring Boot BOM chọn version tương thích. Chỉ test SQL, không có web starter/Redis/database container.

**src/main/java/demo/tx/TxTimeoutApplication.java**

~~~java
package demo.tx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxTimeoutApplication.class, args);
    }
}
~~~

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE tx_marks (
    id BIGINT PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);
~~~

Bảng có primary key ID, nên các tests không ghi trùng ID. `schema.sql` nằm trong **test classpath**. Trong Spring Boot 3.3, `@JdbcTest` bao gồm hạ tầng SQL initialization với H2 embedded; theo default SQL init, schema.sql được áp dụng khi test ApplicationContext khởi tạo.

**Tại sao dùng H2?** Ta có một DB disposable trong process, không cần cổng mạng và không ảnh hưởng dữ liệu thật. Nhưng demo có side effects ở thread khác nên vẫn cần cleanup, kể cả với H2: TestContext có thể cache ApplicationContext và DataSource giữa test classes trong cùng suite.

### 6.2. Test an toàn: assertTimeout và @Timeout SAME_THREAD

**src/test/java/demo/tx/SameThreadTimeoutTest.java**

~~~java
package demo.tx;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
class SameThreadTimeoutTest {

    @Autowired
    JdbcTemplate jdbc;

    private Long expectedRolledBackId;

    private long count(long id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_marks WHERE id = ?",
                Long.class, id);
    }

    @Test
    void nonPreemptiveTimeoutKeepsTestTransaction() {
        expectedRolledBackId = 1101L;
        Thread testThread = Thread.currentThread();

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertTimeout(Duration.ofSeconds(5), () -> {
            assertSame(testThread, Thread.currentThread());
            assertTrue(TestTransaction.isActive());

            int updated = jdbc.update(
                    "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                    expectedRolledBackId, "same-thread");

            assertEquals(1, updated);
            assertEquals(1L, count(expectedRolledBackId));
        });
    }

    @Test
    @Timeout(
            value = 5,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void timeoutAnnotationExplicitlyKeepsTestThread() {
        expectedRolledBackId = 1102L;

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        jdbc.update(
                "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                expectedRolledBackId, "timeout-annotation");

        assertEquals(1L, count(expectedRolledBackId));
    }

    @Test
    void nonPreemptiveSupplierAlsoKeepsTransaction() {
        Thread parent = Thread.currentThread();

        Long result = assertTimeout(
                Duration.ofSeconds(5),
                () -> {
                    assertSame(parent, Thread.currentThread());
                    assertTrue(TestTransaction.isActive());
                    return jdbc.queryForObject(
                            "SELECT COUNT(*) FROM tx_marks",
                            Long.class);
                });

        assertNotNull(result);
        assertTrue(result >= 0L);
    }

    @AfterTransaction
    void verifyRollbackAfterSpringEndsTransaction() {
        // Mỗi @Test có test instance riêng theo mặc định JUnit.
        if (expectedRolledBackId == null) {
            return;
        }

        assertFalse(TestTransaction.isActive());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());

        // Chỉ bây giờ mới chứng minh row đã được rollback.
        assertEquals(0L, count(expectedRolledBackId));
    }
}
~~~

**Ba test ở class này có ý nghĩa khác nhau:**
- **nonPreemptiveTimeoutKeepsTestTransaction:** Assert cùng Thread object trước/trong callback, kiểm TestTransaction active và INSERT nhìn thấy trong TX-A. Sau test, `@AfterTransaction` xác minh row ID 1101 **không còn**.
- **timeoutAnnotationExplicitlyKeepsTestThread:** `@Timeout(threadMode=SAME_THREAD)` đặt timeout cho test method nhưng không chuyển nội dung sang worker T2. `@AfterTransaction` xác minh row ID 1102 đã rollback.
- **nonPreemptiveSupplierAlsoKeepsTransaction:** overload trả value của `assertTimeout` cũng chạy trên thread gọi. Không ghi DB; nó chỉ xác nhận transaction state và có thể đọc bảng.
- `@AfterTransaction` chạy ngoài transaction; trường `expectedRolledBackId` là instance field chỉ được set bởi hai tests có INSERT. Mặc định JUnit Jupiter tạo test instance mới cho mỗi test method, nên hook của test không ghi không nhầm ID.
- Test không cần `@Transactional` tường minh vì `@JdbcTest` mặc định transactional. Khi chuyển sang `@SpringBootTest` chung, cần cấu hình `@Transactional` cho test có ý định rollback và bảo đảm transaction manager hiện diện.

**Điểm quan trọng:** Assertion `count(id)==1` **ngay sau INSERT** chỉ chứng minh transaction hiện tại nhìn thấy write; assertion `count(id)==0` trong **@AfterTransaction** mới chứng minh rollback sau test.

### 6.3. Test an toàn: quan sát việc mất transaction trên worker thread

**src/test/java/demo/tx/PreemptiveThreadBoundaryTest.java**

~~~java
package demo.tx;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
class PreemptiveThreadBoundaryTest {

    @Test
    void preemptiveCallbackHasNoTestManagedTransaction() {
        Thread parent = Thread.currentThread();

        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertTimeoutPreemptively(Duration.ofSeconds(5), () -> {
            assertNotSame(parent, Thread.currentThread());
            assertFalse(TestTransaction.isActive());
            assertFalse(TransactionSynchronizationManager
                    .isActualTransactionActive());
        });
    }

    @Test
    void completableFutureAlsoDoesNotInheritTransaction() {
        assertTrue(TestTransaction.isActive());

        boolean activeOnWorker = CompletableFuture.supplyAsync(
                TransactionSynchronizationManager
                        ::isActualTransactionActive).join();

        assertFalse(activeOnWorker);
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void nonPreemptiveWrapperDoesNotFixNestedAsyncHop() {
        assertTimeout(Duration.ofSeconds(5), () -> {
            // Wrapper ở T1 vẫn có test transaction.
            assertTrue(TestTransaction.isActive());

            // Nhưng chính nested async call được đẩy sang T2.
            boolean workerActive = CompletableFuture.supplyAsync(
                    TransactionSynchronizationManager
                            ::isActualTransactionActive).join();

            assertFalse(workerActive);
            assertTrue(TestTransaction.isActive());
        });
    }
}
~~~

Đây là **ba test không ghi DB**, nên chạy mặc định an toàn. Chúng xác nhận nguyên nhân thật sự: thread mà Spring gắn test transaction **khác** thread được callback/async work dùng. `CompletableFuture.supplyAsync` sử dụng executor khác (thường ForkJoin common pool), không tự copy test transaction từ ThreadLocal của parent.

**Điều tinh tế:** `assertTimeout` không đổi thread, nhưng bên trong callback bạn vẫn có thể **tự** dùng `CompletableFuture`, `ExecutorService`, `@Async` hay HTTP call. Khi ấy hoạt động của worker bên trong vẫn có thể nằm ngoài TX-A. Chỉ đổi preemptive thành non-preemptive **không đủ** nếu test đã có thread hop khác.

### 6.4. Demo nguy hiểm, tắt mặc định: INSERT thật thoát khỏi rollback

Lớp dưới đây cố ý dùng `assertTimeoutPreemptively` để ghi trong T2 và sau đó xác minh rằng row vẫn tồn tại **sau rollback của T1**. Để tránh làm bẩn CI, **toàn lớp được @Disabled mặc định**. Chỉ chạy sau khi chủ động xóa `@Disabled`, và chỉ trên disposable H2 test database. Hook `@AfterTransaction` có `finally` xóa row.

**src/test/java/demo/tx/PreemptiveWriteDemoTest.java**

~~~java
package demo.tx;

import java.time.Duration;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@Disabled("Educational commit-leak demo; enable only on disposable H2")
@JdbcTest
class PreemptiveWriteDemoTest {

    private static final long ESCAPED_ID = 2101L;

    @Autowired
    JdbcTemplate jdbc;

    private boolean attemptedWrite;

    private long countEscapedRow() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_marks WHERE id = ?",
                Long.class, ESCAPED_ID);
    }

    @Test
    void preemptiveWriteIsNotRolledBackWithTestTransaction() {
        assertTrue(TestTransaction.isActive());
        attemptedWrite = true;

        assertTimeoutPreemptively(Duration.ofSeconds(15), () -> {
            // Worker không thừa hưởng TX-A của test.
            assertFalse(TestTransaction.isActive());
            assertFalse(TransactionSynchronizationManager
                    .isActualTransactionActive());

            int changed = jdbc.update(
                    "INSERT INTO tx_marks(id, note) VALUES (?, ?)",
                    ESCAPED_ID, "committed-outside-test-tx");

            assertEquals(1, changed);
        });

        // Đã hoàn tất callback trước timeout. T1 vẫn giữ TX-A.
        assertTrue(TestTransaction.isActive());
    }

    @AfterTransaction
    void verifyCommittedSideEffectThenAlwaysCleanUp() {
        if (!attemptedWrite) {
            return;
        }

        // Method chạy SAU khi Spring rollback TX-A.
        assertFalse(TestTransaction.isActive());

        try {
            // Dữ liệu T2 đã commit nên vẫn có: rollback T1 không xóa.
            assertEquals(1L, countEscapedRow());
        } finally {
            // Dọn row độc lập trên thread ngoài TX-A.
            jdbc.update(
                    "DELETE FROM tx_marks WHERE id = ?",
                    ESCAPED_ID);
        }
    }
}
~~~

**Giải thích thí nghiệm:**

1. `@JdbcTest` làm Spring khởi tạo TX-A trên thread T1 của test method.
2. `attemptedWrite=true` giúp @AfterTransaction biết có một demo cần kiểm tra và cleanup.
3. JUnit chạy callback của `assertTimeoutPreemptively` trên T2, nơi `TestTransaction.isActive()` và actual transaction flag đều false **trước khi INSERT**.
4. `JdbcTemplate.update` trên T2 lấy connection không tham gia TX-A. Với H2 DataSource/auto-commit mặc định của bài, INSERT được commit độc lập.
5. T2 kết thúc nhanh trước deadline, trả về T1. Spring cuối test rollback TX-A; rollback này không tác động transaction độc lập đã commit trên T2.
6. `@AfterTransaction` chạy ngoài TX-A, đếm row ID 2101 và **kỳ vọng bằng 1**. Đây là bằng chứng kiểm tra sau rollback.
7. `finally` chạy DELETE để không giữ row trong H2 khi demo hoạt động bình thường.

**Rủi ro ngay cả trong demo có cleanup:** Nếu callback bị block, timeout và không dừng dù bị interrupt, T2 có thể INSERT **sau khi** @AfterTransaction đã cleanup. Do đó `finally` chỉ là biện pháp bảo vệ trong kịch bản demo bình thường, **không phải bảo đảm tuyệt đối** cho thread bị treo. Đó là lý do demo để `@Disabled`, dùng ID riêng, chỉ chạy trên DB disposable và không bao giờ thử trên database dùng chung/prod.

**Một biến thể cố ý nguy hiểm khác cần nhận diện:**

~~~java
@Timeout(
        value = 3,
        threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
@Test
void unsafeTransactionTestMethod() {
    jdbc.update("INSERT INTO tx_marks(id, note) VALUES (?, ?)",
            3001L, "danger");
}
~~~

Đây là **snippet cảnh báo**, không phải một method trong project runnable. `@Timeout(SEPARATE_THREAD)` có thể chạy toàn test body trên thread không mang test-managed transaction, khiến giao dịch và cleanup bị hiểu sai. **Không dùng cấu hình này cho transactional integration test** trừ khi bạn thật sự điều khiển transaction trong worker và biết side effects sẽ được dọn ra sao.

## 7. Chạy project và kiểm số lượng tests

Nếu project có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chỉ chép các tệp mẫu mà chưa có Gradle Wrapper scripts/JAR, cần dùng Gradle tương thích để tạo wrapper hoặc chạy `gradle test`. Source mẫu không tự tạo `./gradlew`.

Tổng số phương thức kiểm thử JUnit Jupiter trong **ba file Java hoàn chỉnh**:

| Test class | @Test được khai báo | Mặc định thực thi | Trọng tâm |
|---|---:|---:|---|
| SameThreadTimeoutTest | **3** | **3 PASS** dự kiến | assertTimeout, @Timeout SAME_THREAD, rollback |
| PreemptiveThreadBoundaryTest | **3** | **3 PASS** dự kiến | preemptive/CompletableFuture mất ThreadLocal |
| PreemptiveWriteDemoTest | **1** | **1 DISABLED** | Demo commit ngoài rollback và cleanup |
| **Tổng** | **7** | **6 thực thi, 1 skipped** | Không có test cố ý fail trong suite mặc định |

Đây là kết quả **mong đợi từ mã nguồn**, không phải tuyên bố đã chạy thực tế trên máy của bạn. Spring Boot có thể cache ApplicationContext/H2 giữa test classes, nhưng tests mặc định không tạo write thoát transaction; hai writes của SameThreadTimeoutTest đều rollback; demo nguy hiểm được tắt.

Báo cáo Gradle thường tại:

~~~text
build/reports/tests/test/index.html
~~~

Chạy riêng test an toàn:

~~~bash
./gradlew test --tests demo.tx.SameThreadTimeoutTest
./gradlew test --tests demo.tx.PreemptiveThreadBoundaryTest
~~~

Muốn tự quan sát demo:
1. Sử dụng **project và embedded H2 riêng**, không dùng database của môi trường chia sẻ.
2. Xóa annotation **@Disabled** trên PreemptiveWriteDemoTest.
3. Chạy đúng lớp này; đừng bật cả suite nếu có context/fixture khác dùng chung ID 2101.
4. Quan sát assertion `@AfterTransaction` chứng minh row vẫn còn sau rollback, rồi `finally` xóa row.
5. Khôi phục `@Disabled` sau thí nghiệm. Nếu test timeout, process bị kill hoặc mất kết nối giữa chừng, hủy toàn bộ H2 database/test context và chạy lại từ đầu; đừng giả định cleanup đã hoàn tất.

Ví dụ lệnh khi đã chủ động bỏ `@Disabled`:

~~~bash
./gradlew test --tests demo.tx.PreemptiveWriteDemoTest
~~~

**Không tạo một demo production database để chứng minh commit leak.** Dù chỉ là bài học, side effect có thể không đảo ngược được khi ghi DB ngoài transaction, gửi email, gọi webhook hoặc tạo message.

## 8. @BeforeTransaction, @AfterTransaction, @BeforeEach và @AfterEach

| Hook hoặc phase | Nằm trong test-managed transaction? | Lý do dùng |
|---|---|---|
| `@BeforeTransaction` | **Không** | Kiểm trạng thái DB trước TX-A |
| `@BeforeEach` | **Có** đối với transactional test | Chuẩn bị dữ liệu thuộc TX-A |
| `@Test` method | **Có**, nếu test-managed transaction được kích hoạt | Thực thi assertions và thay đổi dữ liệu |
| `@AfterEach` | **Có** đối với transactional test | Cleanup/assert dữ liệu vẫn thuộc TX-A |
| `@AfterTransaction` | **Không** | Xác minh rollback/commit đã thực sự xảy ra |
| `@BeforeAll` / `@AfterAll` | Không thuộc TX-A theo mặc định | Khởi tạo/tổng kết cấp lớp |

Không gắn `@Transactional` lên JUnit `@BeforeEach` với kỳ vọng nó tự tạo test transaction; phải để test-managed transaction được kích hoạt bởi test method/class và `TransactionalTestExecutionListener`. `@BeforeEach` trong transactional test được chạy sau khi Spring mở TX-A, nhưng `@BeforeAll` và `@BeforeTransaction` xảy ra ngoài.

Ví dụ chỉ để minh họa vị trí hooks:

~~~java
@BeforeTransaction
void beforeTx() {
    assertFalse(TestTransaction.isActive());
}

@BeforeEach
void setUp() {
    assertTrue(TestTransaction.isActive());
}

@AfterEach
void tearDown() {
    assertTrue(TestTransaction.isActive());
}

@AfterTransaction
void afterTx() {
    assertFalse(TestTransaction.isActive());
}
~~~

Đây là snippet dành cho một lớp test được Spring quản lý và transactional; không phải source file standalone. Hook `@AfterTransaction` đặc biệt quan trọng vì một SELECT trong `@AfterEach` vẫn có thể thấy dữ liệu chưa được rollback.

## 9. @Transactional propagation và những side effects không bị test rollback

### 9.1. REQUIRED, SUPPORTS và REQUIRES_NEW

Một Spring service gọi từ test thread có `@Transactional(propagation=REQUIRED)` thường tham gia transaction hiện hành. Nhưng nếu chạy ở T2 vì preemptive timeout, nó không thấy test transaction của T1 và có thể mở transaction riêng rồi commit.

Ngay cả trên **cùng T1**, service `@Transactional(propagation=REQUIRES_NEW)` có thể tạm đình chỉ TX-A, mở TX-B, commit TX-B và quay lại TX-A; rollback của TX-A không thu hồi commit TX-B. Vì vậy nếu cần bảo đảm không còn dữ liệu sau test, không chỉ kiểm thread mà còn kiểm **transaction propagation** thực tế.

**Không đếm các transaction khác nhau chỉ bằng `isActualTransactionActive()`**: hàm này trả biết có transaction thực đang active trên thread, không nói đó là TX-A hay TX-B. Trong các bài test phức tạp, kết hợp TestTransaction, transaction manager logging, @AfterTransaction assertions và DB isolation.

### 9.2. HTTP, @Async, CompletableFuture, ExecutorService

- `@Async` thường chuyển việc sang Executor thread, nên không tự giữ test-managed transaction.
- `CompletableFuture.supplyAsync` không tự copy transaction ThreadLocal.
- ExecutorService.submit(...) dùng thread của executor, không phải thread test.
- `@SpringBootTest(RANDOM_PORT)` gửi HTTP đến server thread riêng: transaction của server request **không nằm trong transaction của JUnit test client**, ngay cả khi test method có @Transactional.
- Kafka/message queue, filesystem, HTTP requests ra ngoài và email cũng không được đảo ngược bằng một JDBC test rollback.

**Tránh tự truyền `TransactionSynchronizationManager` resources hoặc JDBC Connection object qua thread** như một cách khắc phục nhanh. Connection/transaction context gắn với lifecycle cụ thể và thường không thread-safe; truyền tay có thể gây race, corruption hoặc sử dụng tài nguyên sau khi đóng.

Nếu nghiệp vụ đòi thực thi bất đồng bộ, hãy thiết kế **transaction boundary thực sự trong mỗi worker/task**, dùng fixture riêng và cleanup phù hợp. Nếu chỉ muốn đo thời gian query trong một transactional test, không sinh thread mới khi không cần.

### 9.3. Công cụ timeout khác cũng có thể tạo thread mới

Spring Framework cảnh báo về các cơ chế preemptive timeouts của testing framework nói chung. Ví dụ lịch sử có **JUnit 4 @Test(timeout=...) / Timeout Rule**, JUnit Jupiter **assertTimeoutPreemptively**, và TestNG **@Test(timeOut=...)**. Cơ chế của từng phiên bản nên được kiểm tra thực tế. Không suy đoán rằng vì annotation đặt trên test mà transaction context tự đi theo callback.

Ngay cả khi một timeout API không đổi thread, task có thể tự spawn thread. **Vấn đề gốc là transaction gắn ThreadLocal và thread thực thi thay đổi**, chứ không phải tên “preemptive” trên API.

## 10. Chọn giải pháp phù hợp với mục tiêu

**Mục tiêu A — Kiểm thời gian xử lý database nhưng cần test-managed rollback.** Dùng `assertTimeout(Duration, ...)` hoặc `@Timeout(threadMode=SAME_THREAD)` có kiểm soát. Thêm statement timeout/driver timeout nếu cần giới hạn I/O thực tế. Kiểm rollback sau test bằng @AfterTransaction khi đó là contract quan trọng.

**Mục tiêu B — Dừng một lời gọi ngoài hệ thống có thể treo.** Dùng timeout tại boundary của công cụ thật: HTTP client connect/request timeout, JDBC queryTimeout, RPC deadline hoặc Testcontainers readiness/health limits. Một JUnit preemptive timeout không bảo đảm có thể stop driver/remote operation an toàn và không đảo ngược side effects đã commit.

**Mục tiêu C — Kiểm sự bất đồng bộ.** Thừa nhận worker có transaction boundary riêng. Dùng test DB disposable, đồng bộ hoàn tất của worker bằng Future/CountDownLatch (có deadline), và cleanup sau khi worker thật sự kết thúc. Không dựa rollback ở thread cha để dọn worker commit.

**Mục tiêu D — Cần test preemptive cancellation đúng nghĩa.** Chọn một logic **thuần CPU không có side effects hoặc ThreadLocal dependency**, test cách nó phản hồi interruption. Nếu phải kiểm side effects của task, thiết kế compensation/cleanup và thực thi trong môi trường cô lập; không biến preemptive timeout thành “an toàn tự động”.

**Mục tiêu E — Suite chạy parallel.** Mỗi test phải dùng unique keys, không dùng shared mutable static fixtures. Transaction test theo mỗi thread nhưng database vẫn chung nếu test classes/context share datasource. Các writes thoát khỏi transaction có thể tạo race hoặc pollute tests khác; cần isolation và quản lý dữ liệu riêng.

## 11. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Test @Transactional đã pass nhưng DB có thêm rows | Lệnh ghi chạy ngoài TX-A vì preemptive/async/HTTP | Xem thread và @AfterTransaction; cleanup đúng |
| `TestTransaction.isActive()` true trước callback nhưng false bên trong | Callback chạy thread mới | Dùng assertTimeout hoặc SAME_THREAD |
| `isActualTransactionActive()` true ở worker mà dữ liệu vẫn commit | Worker có TX-B riêng | Phân biệt TX-A và TX-B, xem propagation |
| Callback chạy nhanh vẫn commit ngoài test | assertTimeoutPreemptively luôn chạy thread khác | Không dùng preemptive cho transactional writes |
| `@Timeout` test làm side effects bất ngờ | threadMode SEPARATE_THREAD hoặc global INFERRED config | Đặt SAME_THREAD tường minh |
| `@AfterEach` thấy row nên tưởng không rollback | @AfterEach còn ở trong TX-A | Dùng @AfterTransaction để kiểm sau rollback |
| @AfterTransaction không chạy | Test không được cấu hình transactional hoặc listener không hoạt động | Kiểm @JdbcTest/@Transactional, transaction manager |
| @JdbcTest không rollback | Bị vô hiệu @Transactional, NOT_SUPPORTED, commit flag hoặc outside thread | Kiểm TestTransaction/annotations/thread |
| TEST pass riêng nhưng fail khi chạy cả suite | Dữ liệu từ T2 commit còn trong shared H2/DB | Cô lập IDs/schema/DB, cleanup sau worker |
| Assertion preemptive fail rồi vẫn có INSERT sau đó | Callback không ngừng vì interrupt | Không xem preemptive là kill switch |
| DB UPDATE bị treo do lock | Main transaction giữ lock, worker chờ lock khác | Tránh cập nhật cùng row hai threads, DB statement timeout |
| Spring Security/MDC/Locale bị mất trong callback | ThreadLocal không được truyền tự động | Thiết kế context propagation rõ hoặc tránh đổi thread |
| @Transactional service không rollback với test | Service chạy worker T2/REQUIRES_NEW | Xem transaction boundary và after-commit state |
| @Transactional test không rollback HTTP endpoint write | Server HTTP request trên thread khác | Test DB riêng, cleanup; đừng trông chờ TX-A |
| @Commit hoặc @Rollback(false) được dùng | Test intentionally commit | Phân biệt commit policy với timeout behavior |

**Checklist debug 10 bước:**

1. Test có thật sự mở test-managed transaction không? Dùng `TestTransaction.isActive()` ngay trong test method.
2. Có `PlatformTransactionManager` và `@JdbcTest`, `@DataJpaTest`, hoặc `@Transactional` thích hợp không?
3. Có `assertTimeoutPreemptively`, `@Timeout(SEPARATE_THREAD)`, `CompletableFuture`, `@Async`, executor hoặc HTTP RANDOM_PORT không?
4. Log tên/ID thread tại nơi test bắt đầu và nơi DB update, nhưng không lộ secret.
5. Kiểm `TransactionSynchronizationManager.isActualTransactionActive()` tại mỗi boundary; nhớ nó không phân biệt TX-A/TX-B.
6. Xem service `@Transactional` propagation: REQUIRED/SUPPORTS/REQUIRES_NEW/NOT_SUPPORTED.
7. Kiểm test có dùng @Commit, @Rollback(false), TestTransaction.flagForCommit hoặc end() không.
8. Chỉ so dữ liệu sau rollback trong @AfterTransaction, không chỉ @AfterEach.
9. Kiểm DB connection/auto-commit, rollback logs và lock status theo driver.
10. Nếu có bất kỳ outside-tx write nào, cleanup dữ liệu độc lập hoặc dùng disposable DB; không để rò rỉ sang suite khác.

## 12. Các chú ý về thiết kế test bền vững

**Đừng dùng Thread.sleep để tạo một timeout demo phụ thuộc scheduling.** Thread.sleep là cách mô phỏng độ chậm đơn giản nhưng có thể khiến test flaky trên CI. Với chủ đề này, không cần vượt deadline; chỉ cần callback chạy thread khác đã đủ chứng minh cơ chế. Bộ ví dụ cố ý dùng callbacks nhanh và assertions về thread/transaction state.

**Timeout dài không phải cách sửa rò rỉ transaction.** Tăng từ 5 giây lên 60 giây làm callback có thêm thời gian hoàn tất nhưng nó **vẫn chạy T2**. Vấn đề là cấu trúc execution, không phải giá trị timeout.

**Chặn trong cùng transaction có thể lock database.** Nếu TX-A giữ row lock rồi T2 trong preemptive callback cố update chính row ấy, T2 có thể chờ TX-A; T1 lại đang chờ T2 kết thúc -> deadlock-like wait. Ví dụ dùng một row mới, không lock row chung, và không yêu cầu main thread đọc dữ liệu chưa commit trước khi worker ghi.

**Cần quan sát sau rollback và dọn cleanup.** @AfterTransaction hữu ích nhưng mọi delete/compensation vẫn có thể thất bại vì network/DB outage; trong CI nên dùng database tạm, schema riêng, container per suite hoặc policy teardown phù hợp. Một test tạo committed side effect không nên chạy vô điều kiện trên DB dùng chung.

**Không lạm dụng @DirtiesContext.** Nó làm Spring xây lại ApplicationContext nhưng **không đồng nghĩa xóa database bên ngoài**. H2 in-memory có thể được thu hồi khi DataSource/context đóng, nhưng Testcontainers/external DB còn dữ liệu đến khi bạn chủ động cleanup. Dùng đúng cơ chế isolation.

**Cẩn thận với global timeout configuration.** `@Timeout` ở mode INFERRED dựa vào JUnit property; nếu suite cấu hình global SEPARATE_THREAD, một test Spring transactional không tường minh mode có thể vô tình đổi execution thread. Dùng SAME_THREAD cho tests nhạy cảm.

## 13. Bài tập tự luyện

1. **So sánh API:** Tạo hai test với `assertTimeout` và `assertTimeoutPreemptively`, cùng kiểm Thread.currentThread() và TestTransaction.isActive(). Vì sao code nhanh hơn deadline vẫn có khác biệt?
2. **Rollback:** Thêm một INSERT trong same-thread test, assert count=1 trong test rồi assert count=0 ở @AfterTransaction. Assertion nào thực sự xác minh rollback?
3. **Preemptive commit:** Trong H2 disposable, chủ động bật PreemptiveWriteDemoTest, giải thích vì sao afterTransaction thấy count=1 rồi cần DELETE. Vì sao không bật demo mặc định?
4. **@Timeout:** Đổi SAME_THREAD sang SEPARATE_THREAD trong một demo riêng, kiểm transaction state. Vì sao lựa chọn threadMode ảnh hưởng semantics nhiều hơn việc timeout có xảy ra?
5. **INFERRED:** Tìm giá trị `junit.jupiter.execution.timeout.thread.mode.default` trong CI. Viết test với SAME_THREAD tường minh để tránh lệ thuộc config.
6. **@Async:** Viết một Spring service method @Async gọi repository. Khi test có @Transactional, service có dùng TX-A không? Thiết kế cleanup hợp lệ.
7. **REQUIRES_NEW:** Gọi một service có @Transactional(REQUIRES_NEW) từ transactional test cùng thread, kiểm after-commit/rollback. Vì sao không có preemptive timeout vẫn có write tồn tại?
8. **JDBC lock:** Cố gắng cập nhật cùng row từ T1/T2 trong một môi trường H2 riêng và dùng statement timeout để tránh treo. Tránh chạy kiểu demo này trong CI mặc định.
9. **Server thread:** Gửi HTTP POST tới @SpringBootTest(RANDOM_PORT), sau đó rollback test method. Vì sao server-side database write không tự rollback?
10. **Test cleanup:** Chỉnh demo để luôn dùng ID/namespace mới và xóa sau khi worker hoàn tất; phân tích trường hợp worker bỏ qua interrupt.
11. **ThreadLocal khác:** Lấy MDC/SecurityContext trong T1 và T2, quan sát khác biệt. Có nên sao chép raw JDBC Connection giữa threads để sửa không? Giải thích rủi ro.
12. **Test design review:** Tìm trong repo các chỗ dùng preemptive timeout trong test có @Transactional/@JdbcTest/@DataJpaTest; đề xuất thay bằng same-thread timeout và thêm afterTransaction verification khi cần.

## 14. Tham khảo chính thức

- [Spring Framework 6.1 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, ThreadLocal, preemptive timeouts, @BeforeTransaction/@AfterTransaction và propagation.
- [JUnit Jupiter User Guide — Assertions, Preemptive Timeouts](https://docs.junit.org/5.11.4/user-guide/): `assertTimeout`, `assertTimeoutPreemptively` và cảnh báo ThreadLocal/Spring.
- [JUnit Jupiter User Guide — @Timeout Thread Modes](https://docs.junit.org/5.11.4/user-guide/): `SAME_THREAD`, `SEPARATE_THREAD`, `INFERRED` và global configuration.
- [Spring Boot 3.3 — JDBC Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @JdbcTest, JdbcTemplate, embedded datasource và rollback.
- [Spring TestTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): isActive, flagForRollback/flagForCommit, start/end.
- [Spring @AfterTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): chạy sau khi transactional test kết thúc.
- [Spring TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): thread-bound resources và actual transaction flag.
- [JDK 17 ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): state theo từng thread.
- [Java SE 17 CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): async execution và executor boundaries.

**Ghi nhớ:** Trong Spring TestContext, **test-managed transaction thuộc thread test**, không phải một lớp phủ toàn bộ tiến trình JVM. `assertTimeoutPreemptively` và `@Timeout(SEPARATE_THREAD)` có thể chuyển code kiểm thử sang thread không mang transaction ấy; write có thể commit riêng và **không bị rollback cuối test**, dù callback không hề timeout. Với transactional integration tests, ưu tiên **assertTimeout** hoặc `@Timeout(SAME_THREAD)`, kiểm trạng thái thật bằng **@AfterTransaction**, và cô lập/cleanup mọi side effect của các worker threads. Timeout không thay thế thiết kế transaction và resource boundaries.
