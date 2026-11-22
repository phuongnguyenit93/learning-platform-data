# REQUIRES_NEW và dữ liệu có thể được commit ngoài transaction của test

## 1. Hiện tượng: có @Transactional trên test mà dữ liệu vẫn tồn tại

Trong **Spring Boot - testing**, nhóm **Giao dịch kiểm thử**, lỗi hiểu sai thường gặp là cho rằng mọi database write trong một JUnit test có `@Transactional` sẽ được rollback tự động. Spring TestContext chỉ rollback **transaction mà test listener quản lý**. Một method Spring bean được gắn `@Transactional(propagation = Propagation.REQUIRES_NEW)` lại có thể mở **physical transaction độc lập**, commit trong lúc test-managed transaction còn đang hoạt động.

Giả sử service ghi phiếu nhập và đồng thời ghi audit:

~~~text
TestContext mở transaction T_TEST
        |
        +-- InventoryWriter.save() [REQUIRED, tham gia T_TEST]
        |
        +-- AuditWriter.record()   [REQUIRES_NEW]
        |       |
        |       +-- suspend T_TEST
        |       +-- mở T_AUDIT trên resource/connection khác
        |       +-- INSERT audit
        |       +-- COMMIT T_AUDIT
        |       +-- resume T_TEST
        |
        +-- kết thúc test: ROLLBACK T_TEST

Sau rollback:
  dữ liệu thuộc T_TEST   -> mất
  dữ liệu thuộc T_AUDIT  -> còn lại
~~~

Điều này **không chứng minh Spring TestContext rollback lỗi**. Hai scope đang dùng các physical transactions khác nhau. Transaction mới đã commit độc lập nên không thể bị rollback chỉ vì transaction ngoài kết thúc sau đó.

Bài học cần trả lời đầy đủ: REQUIRES_NEW hoạt động ra sao; khác REQUIRED/NESTED thế nào; TestContext mở và rollback transaction khi nào; cách test commit bằng việc quan sát dữ liệu **sau test**; cách cleanup; vì sao self-invocation, thread khác, HTTP thật, DB lock và connection pool ảnh hưởng kết quả; khi nào nên/không nên dùng REQUIRES_NEW trong ứng dụng.

Ví dụ chính sử dụng **Java 17, Spring Boot 3.5.16, Spring JDBC, H2 và JUnit Jupiter**. Nó gồm application, hai service, cấu hình database, DDL và ba ca test đầy đủ. JDBC được chọn để quan sát commit/rollback trực tiếp, tránh nhập nhằng JPA flush và first-level cache.

## 2. Test-managed transaction khác transaction của Spring service

Theo Spring Framework, có ba loại transaction boundary:

| Loại | Bên quản lý | Ví dụ |
| --- | --- | --- |
| **Test-managed transaction** | `TransactionalTestExecutionListener` hoặc `TestTransaction` | `@Transactional` trên JUnit test class/method |
| **Spring-managed transaction** | Transaction interceptor/AOP của một Spring bean | `@Transactional(REQUIRED)` hoặc `REQUIRES_NEW` ở service |
| **Application-managed transaction** | Code chủ động thao tác API transaction | `TransactionTemplate`, `PlatformTransactionManager` |

Test-managed transaction thường được gắn với **thread chạy test**, sử dụng `PlatformTransactionManager` mà Spring TestContext phát hiện hoặc được chỉ định bằng qualifier. Method service `REQUIRED` gọi từ test trong cùng thread thường tham gia transaction đó. Method service `REQUIRES_NEW` **không** tham gia: Spring tạm ngưng resource của outer và tạo transaction mới.

Một kết quả quan trọng: `@Rollback`/`@Commit` trên test quy định kết quả của **test-managed transaction**, không phải “lệnh rollback tất cả những gì ứng dụng từng commit”.

### Điều kiện để propagation được áp dụng thật

- Service là **bean trong Spring ApplicationContext**.
- Public method được gọi qua **Spring transaction proxy** trong cấu hình proxy-based thông thường. `this.someRequiresNewMethod()` có thể bỏ qua proxy.
- Có transaction manager đúng với datasource/resource cần kiểm tra.
- Manager hỗ trợ mở/suspend/resume transaction liên quan.
- Connection pool có đủ connection cho outer và inner.
- Test được chạy đồng bộ trong transaction thread nếu muốn dựa vào test-managed rollback.

Không lấy việc method được annotate làm bằng chứng rằng transaction advice đã thực sự chạy. Một Mockito mock hoặc lời gọi Java trực tiếp không tự khởi động Spring transaction.

## 3. REQUIRED, REQUIRES_NEW, NESTED: cùng tên “nested” nhưng nghĩa khác

| Propagation | Đang có outer transaction | Physical transaction | Khi outer rollback |
| --- | --- | --- | --- |
| `REQUIRED` | Join outer | Cùng một transaction vật lý | Các write tham gia outer đều rollback |
| `REQUIRES_NEW` | Suspend outer, mở transaction mới | Transaction vật lý **khác** | Inner đã commit vẫn còn |
| `NESTED` | Tạo savepoint trong cùng transaction khi hỗ trợ | Thường cùng transaction vật lý | Outer rollback xóa cả thay đổi của nested |
| `SUPPORTS` | Tham gia outer nếu có | Theo outer nếu đã tồn tại | Khi join thì rollback theo outer |
| `NOT_SUPPORTED` | Suspend outer và chạy không có transaction | Không tạo T_NEW | SQL có thể auto-commit theo datasource |
| `MANDATORY` | Yêu cầu outer transaction tồn tại | Join outer | Không có outer thì lỗi |

`REQUIRES_NEW` tạo **transaction vật lý mới** và tự quyết định commit/rollback. `NESTED` dựa vào savepoint; release savepoint **không** biến những thay đổi nested thành một commit độc lập. Hỗ trợ NESTED còn tùy transaction manager và JDBC savepoints; không mặc định mọi JPA manager hoạt động giống JDBC.

~~~text
REQUIRED:
  T_TEST [write A][write B][ROLLBACK]     => A=0, B=0

REQUIRES_NEW:
  T_TEST [write A]---suspend----------[ROLLBACK] => A=0
                  T_NEW [write B][COMMIT]         => B=1

NESTED (khi có savepoint):
  T_TEST [write A][savepoint][write B][release][ROLLBACK]
                                                => A=0, B=0
~~~

Nếu **không có outer transaction**, cả `REQUIRED` và `REQUIRES_NEW` đều có thể mở transaction mới rồi commit khi method thành công; nhưng semantics của chúng khác nhau khi đã có outer.

## 4. Transaction lifecycle của một JUnit Jupiter test

Trong một test `@SpringBootTest` (hoặc các test slice có transaction manager) được gắn `@Transactional`, Spring TestContext mở test-managed transaction trước method và mặc định rollback sau method. Trình tự khái quát:

~~~text
@BeforeTransaction              [ngoài T_TEST]
           |
TestContext BEGIN T_TEST
           |
@BeforeEach                     [trong T_TEST]
           |
@Test                           [trong T_TEST]
           |
@AfterEach                      [trong T_TEST]
           |
TestContext ROLLBACK/COMMIT T_TEST
           |
@AfterTransaction               [ngoài T_TEST]
~~~

Đây là lý do **`@AfterEach` không phù hợp để kết luận dữ liệu đã commit**: nó vẫn có thể nhìn thấy những INSERT chưa commit trong cùng transaction test, rồi Spring rollback chúng ngay sau đó.

`@BeforeTransaction` và `@AfterTransaction` là Spring TestContext lifecycle hooks cho transactional test. Chúng có thể query DB **ngoài transaction test**, rất hữu ích để chứng minh inner transaction đã commit độc lập và cleanup dữ liệu còn sót.

`@BeforeAll` và `@AfterAll` (JUnit lifecycle cấp lớp) không chạy bên trong test-managed transaction theo cách thông thường. Đừng tùy tiện dùng chúng để ghi dữ liệu chung khi test chạy song song hoặc test environment có shared database.

### @Transactional trên test không có đầy đủ propagation như service

Spring TestContext chỉ hỗ trợ một số thuộc tính của `@Transactional` trên test: tên transaction manager, và `Propagation.NOT_SUPPORTED`/`NEVER` để **không mở test transaction**. Đừng viết:

~~~java
// Sai ý định: không dùng annotation này trên JUnit test
// để mong TestContext thực thi đầy đủ REQUIRES_NEW semantics.
@Test
@Transactional(propagation = Propagation.REQUIRES_NEW)
void misleadingTest() {
}
~~~

Đây là đoạn **phản ví dụ** không phải phần của chương trình runnable. Muốn kiểm tra REQUIRES_NEW, **đặt propagation trên Spring service bean được gọi qua proxy**.

Tương tự, `rollbackFor`/`noRollbackFor` trên test method không điều khiển test listener giống như trên method service. Với test-managed transactions, dùng `@Rollback`, `@Commit` hoặc `TestTransaction`.

## 5. Chuẩn bị ví dụ chạy được: database in-memory và hai services

Ví dụ dùng bảng `tx_events`, mỗi bản ghi được nhận diện bằng `event_key`. Hai writer khác bean:

- `RequiredEventWriter` có method `@Transactional` mặc định REQUIRED; khi test transaction có sẵn, nó ghi vào **T_TEST**.
- `IndependentEventWriter` có method `@Transactional(REQUIRES_NEW)`; nó suspend T_TEST, ghi/commit ở **T_NEW**.
- Method thứ hai của independent writer cố ý ném `IllegalStateException` để chứng minh inner **rollback độc lập**.
- Test tạo UUID khác nhau ở `@BeforeTransaction`, tránh dữ liệu giữa các test dính nhau.
- `@AfterTransaction` assert **sau** khi outer đã rollback/commit, rồi cleanup các row đã commit trong `finally`.

Không cần HTTP server, Docker hoặc database ngoài. H2 đủ cho semantics demo; muốn kiểm tra locking/isolation giống production thì nên chạy với database cùng loại production.

### Cây tệp

~~~text
settings.gradle
build.gradle
src/main/java/com/example/txdemo/
  TxDemoApplication.java
  RequiredEventWriter.java
  IndependentEventWriter.java
src/test/resources/
  application.properties
  schema.sql
src/test/java/com/example/txdemo/
  RequiresNewIsolationTest.java
~~~

Mọi Java file dùng package `com.example.txdemo`. Project cần Gradle Wrapper để chạy các lệnh ở cuối bài.

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

### settings.gradle

~~~groovy
rootProject.name = 'requires-new-demo'
~~~

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate`/JDBC transaction infrastructure và HikariCP. `spring-boot-starter-test` có JUnit Jupiter, AssertJ, Spring TestContext. H2 chỉ dùng trong test runtime; muốn chạy ứng dụng độc lập ngoài test cần cấu hình một JDBC driver/datasource thích hợp.

### src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS tx_events (
    event_key VARCHAR(100) PRIMARY KEY,
    category VARCHAR(32) NOT NULL
);
~~~

Schema này cố ý không có foreign key. Outer và inner ghi **các row với primary keys khác nhau** để không bị kẹt do inner tham chiếu tới row outer chưa commit.

### src/test/resources/application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:requiresnew_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
~~~

`maximum-pool-size=4` cung cấp đủ connections trong demo một thread có outer + inner. Đây **không** phải công thức sizing production. `DB_CLOSE_DELAY=-1` giữ in-memory DB trong vòng đời JVM, nên test phải cleanup committed rows chứ không thể dựa vào việc đóng một connection để xóa dữ liệu.

### src/main/java/com/example/txdemo/TxDemoApplication.java

~~~java
package com.example.txdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }
}
~~~

`@SpringBootTest` sẽ tìm application configuration này. Không cần Spring MVC/WebFlux starter vì thử nghiệm là về transaction JDBC.

## 6. Writer REQUIRED: tham gia outer test transaction

**Tệp `src/main/java/com/example/txdemo/RequiredEventWriter.java`:**

~~~java
package com.example.txdemo;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiredEventWriter {
    private final JdbcTemplate jdbc;

    public RequiredEventWriter(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional
    public void write(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "REQUIRED"
        );
    }
}
~~~

Khi test transaction đã active trong cùng thread và cùng transaction manager, Spring-managed `@Transactional` mặc định `REQUIRED` sẽ tham gia **T_TEST**. Dù method `write` đã return, SQL write vẫn nằm trong outer transaction **chưa commit**. Đến cuối test, rollback T_TEST xóa bản ghi đó.

Nếu không có outer transaction, chính method REQUIRED sẽ mở transaction rồi commit/rollback theo kết quả method. Vì vậy không thể khẳng định mọi method REQUIRED đều rollback hoặc đều commit: phải xác định transaction đang tồn tại.

## 7. Writer REQUIRES_NEW: commit và rollback độc lập

**Tệp `src/main/java/com/example/txdemo/IndependentEventWriter.java`:**

~~~java
package com.example.txdemo;

import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentEventWriter {
    private final JdbcTemplate jdbc;

    public IndependentEventWriter(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "INDEPENDENT"
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeThenFail(String eventKey) {
        jdbc.update(
                "INSERT INTO tx_events (event_key, category) VALUES (?, ?)",
                eventKey, "FAILED_INNER"
        );

        throw new IllegalStateException("audit rejected");
    }
}
~~~

Khi được gọi qua Spring proxy trong một outer transaction, mỗi method REQUIRES_NEW:

1. Suspend các transaction resources của outer.
2. Mở transaction mới có resource phù hợp (thường là một JDBC connection khác).
3. Thực thi câu `INSERT` bên trong transaction mới.
4. Nếu `write` return bình thường: commit transaction mới.
5. Nếu `writeThenFail` ném unchecked exception: rollback transaction mới theo default rollback rules.
6. Resume outer transaction.

**Lưu ý:** inner rollback độc lập **không bắt buộc outer rollback**. Caller có thể bắt exception và tiếp tục nếu outer vẫn hợp lệ. Trong demo, outer rollback cuối test do `@Rollback`, không phải do inner tự ép rollback.

Hai writers là hai `@Service` riêng để lời gọi của test đi qua proxy. Nếu một method `this.writeThenFail(...)` được gọi nội bộ từ cùng class trong mô hình proxy-based AOP, propagation có thể **không** kích hoạt.

## 8. Bộ JUnit tích hợp: kiểm chứng dữ liệu đã commit sau test

**Tệp `src/test/java/com/example/txdemo/RequiresNewIsolationTest.java`:**

~~~java
package com.example.txdemo;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Transactional
@Rollback
class RequiresNewIsolationTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    RequiredEventWriter requiredWriter;

    @Autowired
    IndependentEventWriter independentWriter;

    private String runId;
    private boolean expectedRequiredCommitted;
    private boolean expectedIndependentCommitted;

    private String requiredKey() {
        return "required-" + runId;
    }

    private String independentKey() {
        return "new-" + runId;
    }

    private String failedKey() {
        return "failed-" + runId;
    }

    private int count(String eventKey) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events WHERE event_key = ?",
                Integer.class,
                eventKey
        );
        return result == null ? 0 : result;
    }

    @BeforeTransaction
    void prepareOutsideTransaction() {
        runId = UUID.randomUUID().toString();
        expectedRequiredCommitted = false;
        expectedIndependentCommitted = false;

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(count(requiredKey())).isZero();
        assertThat(count(independentKey())).isZero();
        assertThat(count(failedKey())).isZero();
    }

    @Test
    void newTransactionCommitsEvenWhenTestTransactionRollsBack() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        requiredWriter.write(requiredKey());
        independentWriter.write(independentKey());
        expectedIndependentCommitted = true;

        // Thấy thay đổi của chính outer transaction,
        // chưa chứng minh nó đã commit.
        assertThat(count(requiredKey())).isEqualTo(1);
    }

    @Test
    void failingInnerTransactionRollsBackItsOwnInsert() {
        requiredWriter.write(requiredKey());

        assertThatThrownBy(() ->
                independentWriter.writeThenFail(failedKey())
        ).isInstanceOf(IllegalStateException.class)
         .hasMessage("audit rejected");

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count(requiredKey())).isEqualTo(1);
        // T_TEST sẽ rollback theo annotation của lớp.
    }

    @Test
    @Commit
    void commitOverridesDefaultTestRollback() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isFalse();

        requiredWriter.write(requiredKey());
        independentWriter.write(independentKey());

        expectedRequiredCommitted = true;
        expectedIndependentCommitted = true;
    }

    @AfterTransaction
    void verifyCommittedStateAndCleanUp() {
        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(
                TransactionSynchronizationManager
                        .isActualTransactionActive()
        ).isFalse();

        try {
            assertThat(count(requiredKey()))
                    .isEqualTo(expectedRequiredCommitted ? 1 : 0);
            assertThat(count(independentKey()))
                    .isEqualTo(expectedIndependentCommitted ? 1 : 0);
            assertThat(count(failedKey())).isZero();
        } finally {
            jdbc.update(
                    """
                    DELETE FROM tx_events
                    WHERE event_key IN (?, ?, ?)
                    """,
                    requiredKey(),
                    independentKey(),
                    failedKey()
            );
        }
    }
}
~~~

### 8.1. Chính xác ba ca đang chứng minh điều gì?

| Ca | Outer T_TEST | Inner T_NEW | Sau khi test transaction kết thúc, trước cleanup |
| --- | --- | --- | --- |
| `newTransactionCommitsEvenWhenTestTransactionRollsBack` | REQUIRED write rồi **rollback** | REQUIRES_NEW write rồi **commit** | `required=0`, `new=1` |
| `failingInnerTransactionRollsBackItsOwnInsert` | REQUIRED write rồi **rollback** | REQUIRES_NEW insert sau đó exception → **rollback** | `required=0`, `failed=0` |
| `commitOverridesDefaultTestRollback` | Method-level `@Commit` làm T_TEST **commit** | REQUIRES_NEW **commit** | `required=1`, `new=1` |

Hai test đầu dùng rollback mặc định/`@Rollback`; test thứ ba có `@Commit` ở method nên ghi đè chính sách rollback ở class.

**Điểm quan trọng nhất nằm ở `@AfterTransaction`.** Khi hook này chạy, Spring đã hoàn tất commit/rollback của test-managed transaction. Query lúc đó mới có thể phân biệt **row đã commit độc lập** với **row chỉ tồn tại tạm trong outer**. Sau khi assert, `finally` xóa đúng các row của runId, tránh làm bẩn test sau.

### 8.2. Vì sao không kiểm tra hoàn toàn trong @AfterEach?

`@AfterEach` của một transactional test vẫn chạy trong **T_TEST**. Một câu `SELECT` trong cùng T_TEST có thể thấy dữ liệu chính T_TEST chưa commit, cho nên không trả lời “bản ghi còn sau rollback không?”. `@AfterTransaction` phù hợp hơn.

### 8.3. Vì sao dùng UUID cho mỗi test?

Vì test REQUIRES_NEW tạo row đã commit thực. Nếu mọi test dùng chung `event_key = "audit"`, chạy suite nhiều lần có thể gặp `duplicate key` hoặc assert nhầm dữ liệu của test trước. UUID giảm va chạm; cleanup cụ thể trong `finally` tránh xóa dữ liệu của test khác.

### 8.4. Có thể quan sát được inner commit ngay trong T_TEST không?

Với H2 mặc định `READ_COMMITTED` và cách truy cập phù hợp, outer có thể quan sát commit của transaction khác. Nhưng ở `REPEATABLE_READ`, snapshot/caching hoặc JPA first-level cache có thể giữ dữ liệu cũ. Vì vậy hãy kiểm tra committed state **sau khi outer kết thúc** bằng transaction/connection mới thay vì dựa vào một query bên trong outer.

### 8.5. Nếu @AfterTransaction assertion thất bại?

`finally` vẫn chạy cleanup trên đường exception thông thường trong JVM, giúp hạn chế dirty data khi test báo FAIL. Nếu process bị kill/crash thì cleanup trong JVM không chạy; CI quan trọng nên dùng schema/database test riêng hoặc lifecycle teardown bên ngoài process.

## 9. Điểm sâu: vì sao flush không tương đương commit?

Ví dụ dùng JDBC nên `JdbcTemplate.update` thực thi SQL ngay trong transaction. Nhưng **SQL đã được gửi tới database không có nghĩa đã commit**: JDBC connection vẫn ở transaction có thể rollback.

Trong JPA, một thay đổi managed entity có thể chỉ được gửi tới DB khi `flush()` hoặc commit. Vì vậy hai khái niệm thường bị trộn:

- **Flush:** đồng bộ trạng thái persistence context với database bên trong transaction; SQL có thể được gửi đi, nhưng vẫn **có thể rollback**.
- **Commit:** kết thúc transaction thành công, làm thay đổi bền vững theo semantics của database.

Một `@Transactional(REQUIRES_NEW)` service JPA có thể gọi `repository.save(...)` rồi return; transaction interceptor sẽ commit khi method hoàn tất, và JPA provider flush như cần. Nếu method ném runtime exception trước commit, transaction mới có thể rollback.

Trong test JPA, nếu muốn phát hiện DB constraint/optimistic locking đúng lúc, cần cân nhắc `entityManager.flush()` hoặc `saveAndFlush`. Nhưng **không được dùng `flush()` làm bằng chứng outer transaction đã commit**.

### First-level cache của EntityManager

Nếu outer T_TEST đã load entity X, inner T_NEW update X và commit, `EntityManager` của outer có thể vẫn giữ object X đã load trước đó. `findById` trong outer không nhất thiết đọc lại DB. Hãy dùng context mới hoặc `clear()/refresh()` phù hợp, và tốt nhất là query **sau outer transaction** để chứng minh final state.

Trong ví dụ JDBC đơn giản không có first-level entity cache, giúp bài học tập trung vào propagation.

## 10. Khi nào inner transaction không thấy outer data?

`REQUIRES_NEW` sử dụng physical transaction khác; nó không mặc nhiên được đọc những dữ liệu **chưa commit** trong outer transaction.

Một lỗi thiết kế:

~~~text
T_TEST: INSERT orders(id=123)      [chưa commit]
T_NEW:  INSERT audit(order_id=123) [foreign key tham chiếu 123]

Ở READ_COMMITTED, T_NEW chưa thấy order 123 đã commit.
Có thể bị chặn bởi khóa/constraint, timeout hoặc thất bại.
~~~

Kết quả cụ thể phụ thuộc DB, lock manager, isolation và foreign key implementation. Không kết luận mọi DB sẽ luôn trả cùng một exception.

Demo chủ động tránh vấn đề này bằng cách insert các primary key khác nhau vào bảng `tx_events` không có foreign key. Với nghiệp vụ thật:

- Nếu audit phải được commit độc lập **kể cả khi order thất bại**, chỉ lưu metadata độc lập như requestId, actor và event “attempted/failed”.
- Nếu audit event phải mang ý nghĩa **order đã thành công**, không được commit nó trước khi outer commit.
- Nếu cần xử lý sau commit, cân nhắc `@TransactionalEventListener(phase=AFTER_COMMIT)`, transaction synchronization hoặc **transactional outbox**.
- Nếu cần atomicity giữa order và audit, `REQUIRES_NEW` có thể là lựa chọn **sai**, vì nó chủ động phá atomicity.

Không sửa lỗi bằng cách bật READ_UNCOMMITTED toàn hệ thống mà chưa phân tích consistency/DB semantics.

## 11. Spring transaction proxy và bẫy self-invocation

Ví dụ không chạy đúng như tưởng tượng:

~~~java
@Service
class OrderService {
    @Transactional
    public void create() {
        persistOrder();
        audit();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void audit() {
        // Ghi audit...
    }
}
~~~

Đây là **skeleton giải thích**, thiếu định nghĩa `persistOrder()` và imports. Ở proxy-based transaction management mặc định, lời gọi `audit()` từ **cùng instance `this`** không đi qua Spring AOP proxy; annotation REQUIRES_NEW có thể không có hiệu lực.

Cách nên làm:

~~~java
@Service
class OrderService {
    private final IndependentEventWriter auditWriter;

    OrderService(IndependentEventWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void create(String eventKey) {
        // Ghi dữ liệu order vào outer transaction...
        auditWriter.write(eventKey); // qua Spring-managed proxy
    }
}
~~~

Đây cũng là skeleton, nhưng nguyên lý đúng: **gọi public method trên bean khác** để transaction advice kích hoạt. Trong bộ ví dụ chạy chính, test gọi thẳng hai bean `RequiredEventWriter` và `IndependentEventWriter` đã được Spring inject.

Kiểm tra bằng Mockito `verify(writer).write(...)` **không** chứng minh physical commit. Khi mục tiêu là transaction, dùng database thật và kiểm tra dữ liệu sau completion.

## 12. @Commit, @Rollback, TestTransaction điều khiển cái gì?

| API/annotation | Điều khiển | Không làm được |
| --- | --- | --- |
| `@Rollback` | Rollback T_TEST sau test method | Không rollback T_NEW đã commit |
| `@Commit` | Commit T_TEST sau test method | Không biến mọi service call thành một transaction |
| `TestTransaction.flagForRollback()` | Đánh dấu T_TEST rollback khi end | Không “thu hồi” inner commit |
| `TestTransaction.flagForCommit()` | Đánh dấu T_TEST commit khi end | Không thay propagation ở service |
| `TestTransaction.end()` | Kết thúc test-managed transaction hiện hành | Không tự dọn dữ liệu committed ngoài nó |
| `TestTransaction.start()` | Bắt đầu test-managed transaction mới | Không phục hồi transaction cũ đã kết thúc |

`@Commit` trên một test method ghi đè `@Rollback` ở class như trong ví dụ. Nó thay **chính sách kết thúc T_TEST**, không thay annotation `REQUIRES_NEW` của bean.

Khi muốn chủ động quan sát trạng thái sau rollback ngay giữa một test:

~~~java
// Body code minh họa trong transactional @Test:
TestTransaction.flagForRollback();
TestTransaction.end();

assertThat(TestTransaction.isActive()).isFalse();
// Dùng JDBC/query từ connection mới để xem dữ liệu committed.

TestTransaction.start();
// Những thao tác sau đây có thể tiếp tục trong T_TEST mới.
~~~

Đây không phải tệp Java độc lập; phải có Spring TestContext và dependency phù hợp. Với nhu cầu thông thường, `@AfterTransaction` dễ hiểu hơn vì không thay đổi lifecycle giữa test.

### Không dùng rollbackFor của service để điều khiển test

`@Transactional(rollbackFor=IOException.class)` ở service bean điều chỉnh rollback rules của **Spring transaction interceptor**. TestContext không hỗ trợ đầy đủ `rollbackFor` trên annotation `@Transactional` của **test method**; dùng `@Rollback`, `@Commit` hoặc `TestTransaction.flagForRollback/flagForCommit`.

## 13. Checked exception, RuntimeException và inner rollback

Theo default Spring transaction rules, unchecked exception (`RuntimeException` và `Error`) gây rollback; checked exception thông thường không tự động gây rollback nếu không có chỉ thị tương ứng.

Ví dụ runnable ở phần 7 dùng:

~~~java
throw new IllegalStateException("audit rejected");
~~~

`IllegalStateException` là unchecked exception, nên inner `REQUIRES_NEW` rollback theo mặc định.

Một method production có checked exception có thể cần:

~~~java
@Transactional(
        propagation = Propagation.REQUIRES_NEW,
        rollbackFor = java.io.IOException.class
)
public void recordWithIO() throws java.io.IOException {
    // Logic ghi DB và có thể phát IOException.
}
~~~

Đây là method minh họa; chưa đủ class để biên dịch độc lập. Quy tắc rollback của **inner** không quyết định trực tiếp kết quả của **outer**. Nếu exception propagate qua outer method `@Transactional` và không được catch, outer cũng có thể rollback theo rules của nó. Nếu caller bắt exception, outer có thể tiếp tục tùy resource/transaction state.

Sau exception làm transaction thành rollback-only, không nên cố commit lại **cùng** transaction thất bại. Phải rollback và chọn transaction mới khi thật sự cần retry.

## 14. Connection pool exhaustion: chi phí của REQUIRES_NEW

Spring Framework cảnh báo `REQUIRES_NEW` có thể làm cạn pool connections, bởi outer transaction vẫn giữ connection của nó trong khi inner cần connection **khác**.

~~~text
Pool size = 2, hai request đồng thời

Thread A: T_OUTER giữ connection 1
Thread B: T_OUTER giữ connection 2

Thread A gọi REQUIRES_NEW -> chờ connection thứ 3
Thread B gọi REQUIRES_NEW -> chờ connection thứ 3

Không request nào nhả outer connection:
  -> pool starvation / connection timeout
~~~

Spring Framework khuyến nghị connection pool lớn hơn số thread đồng thời ít nhất một connection khi dùng REQUIRES_NEW. Đây là chỉ dẫn **mức tối thiểu để tránh tình trạng phổ biến**, không thay thế việc đo concurrency, nested transaction depth và thời gian giữ connection.

Trong demo có `spring.datasource.hikari.maximum-pool-size=4` để đủ cho một test thread có outer + inner. Con số 4 không chứng minh ứng dụng production với 100 request đồng thời sẽ an toàn.

Nếu inner bị treo, đừng mặc định có race bug ở Java. Kiểm tra:

- Pool active/idle/pending connections.
- DB lock waits nếu inner đụng row outer đang khóa.
- Foreign key tới dữ liệu outer chưa commit.
- Isolation/timeout giữa transaction managers.
- Số nested independent transactions.
- Timeout của connection acquisition và transaction.

Thử nghiệm stress phải có timeout có chủ đích; không dùng `Thread.sleep` như một cách “đồng bộ” threads.

## 15. @Transactional trên test và HTTP server thật

Một đường khác khiến dữ liệu sống sót không cần REQUIRES_NEW là **request HTTP được xử lý trong thread khác**.

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpTest {
    // HTTP client gọi embedded server chạy thread riêng.
}
~~~

Đây là skeleton, không phải test độc lập. Khi dùng `TestRestTemplate`, RestAssured hoặc một HTTP client thật để gọi server ở random port, server thường xử lý request trong transaction riêng. Dù test client có `@Transactional`, commit phía server **không** nằm trong test-managed transaction của client và **không tự rollback** khi test kết thúc.

So sánh:

| Hành vi | Test-managed rollback thường áp dụng? |
| --- | --- |
| Direct call tới Spring `REQUIRED` service trong cùng thread | Có, nếu cùng transaction manager |
| Direct call tới `REQUIRES_NEW` service | Không đối với inner đã commit |
| Real HTTP request đến server trên thread khác | Không tự áp dụng |
| `@Async`/executor thread ghi DB | Không tự áp dụng |
| `MockMvc` sync request cùng thread | Có thể tham gia, tùy handler/thread/transaction setup |
| JUnit preemptive timeout chuyển test body sang thread khác | Có nguy cơ nằm ngoài T_TEST |

Spring TestContext đặc biệt cảnh báo `assertTimeoutPreemptively(...)` của JUnit có thể chạy body trên một thread khác với thread đã gắn transaction, khiến write thật **không được rollback**. Tránh kiểu timeout đó khi đang dựa vào test-managed rollback; chọn một hình thức timeout không làm đổi thread hoặc thiết kế explicit transaction boundaries.

## 16. @DataJpaTest và @JdbcTest có bẫy tương tự không?

Có. Những slice như `@DataJpaTest`/`@JdbcTest` thường mở test-managed transaction và rollback sau test. Nhưng một bean được import hoặc lời gọi application code dùng `REQUIRES_NEW` vẫn có thể mở transaction độc lập và commit.

**Lưu ý:** data slices thường không scan mọi `@Service` của ứng dụng. Nếu muốn test một service thật có propagation REQUIRES_NEW, dùng `@Import(ServiceClass.class)` có chủ đích hoặc `@SpringBootTest`. Đừng thay service bằng Mockito mock mà lại tuyên bố đã kiểm tra transaction propagation.

Trong JPA test, cần thêm:

- Flush EntityManager để phát hiện constraint/optimistic locking đúng lúc.
- Clear hoặc query trong một persistence context mới để tránh stale first-level cache.
- Xác định datasource/transaction manager nếu ứng dụng có nhiều.
- Không nhầm `@Sql` setup được commit với entity rollback của test.

`@DirtiesContext` chủ yếu làm mất hiệu lực Spring context cache, **không tự rollback committed data trên external DB**. Test database/cluster tạm bị hủy theo lifecycle có thể giúp cleanup, nhưng đó là tác dụng của hạ tầng, không phải của annotation này.

## 17. @TransactionalEventListener và outbox: khi nào nên dùng thay REQUIRES_NEW?

Nếu mục tiêu là **ghi log cố gắng thực hiện một hành động kể cả khi business rollback**, independent audit có thể hợp lý. Nhưng nếu muốn công bố “đơn hàng đã thành công”, inner audit commit **trước** outer commit có thể gây dữ liệu sai khi outer rollback.

Giải pháp phải dựa trên semantics:

- **Audit attempt/failure:** có thể viết qua REQUIRES_NEW nếu không lệ thuộc row outer chưa commit.
- **Thông báo sau commit:** dùng callback sau commit, `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc một công cụ orchestration rõ ràng.
- **Gửi message bền vững, không bỏ sót khi crash:** cân nhắc **transactional outbox** được commit nguyên tử cùng business row.
- **Atomicity cả order và audit:** dùng cùng REQUIRED transaction nếu hợp đồng yêu cầu cả hai commit/rollback cùng nhau.

Đoạn listener minh họa:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // Thực hiện việc phù hợp sau khi transaction commit.
}
~~~

Đây chỉ là skeleton, cần event type/import và cơ chế giao message. Một `AFTER_COMMIT` listener không tự cấp transaction mới cho DB write: nếu cần write bền vững sau commit, phải thiết kế transaction mới hợp lệ, ví dụ delegate sang Spring bean REQUIRES_NEW. Với event quan trọng, đánh giá rủi ro JVM crash/mất message, không mặc định listener giải quyết exactly-once delivery.

## 18. Cleanup an toàn: điều thường bị thiếu khi test xanh

Vì inner đã commit, việc chỉ dựa vào rollback cuối test có thể để lại:

- Dòng audit tồn tại trong DB.
- Primary key/unique key bị giữ, gây fail ở test sau.
- Dữ liệu liên quan tenant/user bị lẫn giữa suites.
- Kết quả test phụ thuộc thứ tự chạy.
- Những message/notification hoặc side effects ngoài DB không thể “rollback” bằng Spring TestContext.

Các lựa chọn:

| Kỹ thuật | Lợi ích | Rủi ro / giới hạn |
| --- | --- | --- |
| `@AfterTransaction` + cleanup | Nhìn thấy committed state rồi xóa đúng dữ liệu | Process crash có thể không chạy cleanup |
| `@BeforeTransaction` setup | Seed dữ liệu trước test transaction | Dữ liệu có thể tồn tại nếu quên cleanup |
| UUID per test | Không đụng row test khác | Vẫn phải dọn committed data |
| Per-test DB/schema | Isolation cao | Startup/teardown nặng hơn |
| Testcontainers DB cùng loại production | Test behavior lock/isolation thật hơn | Cần Docker và quản lý lifecycle |
| `@SqlConfig(transactionMode=ISOLATED)` | Chạy SQL script trong transaction tách khỏi T_TEST theo config | Cần hiểu thứ tự listener/script/cleanup |
| `@DirtiesContext` | Reset Spring ApplicationContext | Không bảo đảm xóa external DB |

Trong `@AfterTransaction` của ví dụ, `finally` cleanup **cả trường hợp test assertion thất bại thông thường**. SQL xóa đúng ba keys riêng, không dùng `DELETE FROM tx_events` toàn bảng; điều đó giảm nguy cơ phá dữ liệu của test khác.

Nếu test dùng một database chung có test parallel workers, **không được dùng cleanup toàn bảng**. Với CI quan trọng, nên có database/schema ephemeral để kể cả process bị kill thì lần chạy sau không bị dirty state.

### @Sql với transactionMode ISOLATED

Spring hỗ trợ cấu hình để một script `@Sql` chạy trong transaction độc lập khi có transaction manager. Ví dụ chỉ là đoạn annotation:

~~~java
@Sql(
        scripts = "/cleanup-test-data.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
~~~

Phải cung cấp tệp SQL thật, imports và kiểm tra lifecycle ordering; **không copy đoạn này như một test hoàn chỉnh**. Đừng tự giả định timing của script luôn là sau outer transaction trong mọi cấu hình: cơ chế listener/phase phải được đọc đúng. Với mục đích **assert ngay sau outer rollback**, `@AfterTransaction` thường rõ ràng hơn.

## 19. Chẩn đoán lỗi theo dấu hiệu

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Test `@Transactional` PASS nhưng audit tồn tại trong DB | Inner REQUIRES_NEW commit | Query sau T_TEST, cleanup chủ động |
| `@AfterEach` thấy record, test khác không thấy | Nó query bên trong outer trước rollback | Dùng `@AfterTransaction` |
| Annotation REQUIRES_NEW có nhưng inner không commit | Self-invocation hoặc proxy không chạy | Tách bean, kiểm tra Spring proxy/transaction logs |
| Inner không thấy order outer vừa tạo | Outer chưa commit, transaction tách rời | Tránh FK/dependency vào uncommitted data |
| Inner insert treo/timeout | Pool thiếu connection hoặc DB lock | Xem Hikari stats/lock waits |
| JPA save rồi test không thấy exception | Chưa flush SQL | `flush()`/`saveAndFlush` khi cần |
| Dữ liệu vẫn tồn tại khi chỉ dùng REQUIRED qua HTTP | Server thread có transaction riêng | Test/cleanup server DB ngoài T_TEST |
| Test fail do duplicate key khi chạy lại | Inner row đã commit từ lần trước | UUID/test namespace + teardown |
| `@Commit` không rollback | Đã chủ ý đổi chính sách T_TEST | Xem class/method annotation precedence |
| `NESTED` “commit” nhưng dữ liệu vẫn bị outer rollback | Nested dùng savepoint, không commit vật lý | Phân biệt NESTED/REQUIRES_NEW |
| Spring TestTransaction không active | Test không có active test-managed transaction | Kiểm tra `@Transactional`, manager và propagation |
| Một task async hoàn tất sau cleanup | Lời gọi không được await/join | Đồng bộ lifecycle và side effects |
| Mock test gọi writer nhưng DB trống | Mockito không mở SQL transaction | Dùng integration test phù hợp |

**Đừng sửa lỗi bằng cách tăng thời gian chờ tùy tiện hoặc thêm `@Commit` vào mọi test**. Điều đó có thể che lấp sai thiết kế transaction và làm dữ liệu test tồn tại lâu hơn.

## 20. Khi nào nên và không nên dùng REQUIRES_NEW?

**Có thể phù hợp** khi cần một thao tác nhỏ, độc lập có thể commit/rollback riêng và kết quả đó **không phụ thuộc dữ liệu outer chưa commit**: audit của lần thử thất bại, ghi nhận sự kiện kỹ thuật, hoặc một đơn vị công việc có transaction boundary độc lập được thiết kế.

**Không phù hợp** nếu nghiệp vụ yêu cầu tất cả thay đổi phải atomic; nếu inner phải tham chiếu row outer chưa commit; nếu inner ghi thông điệp “thành công” trước outer commit; nếu connection pool không đủ; hoặc nếu chỉ muốn test xanh mà không muốn dọn dữ liệu.

Khi cần retry sau exception, không cố retry trong transaction đã rollback-only. Tạo transaction mới, đọc lại dữ liệu và cân nhắc idempotency/uniqueness. REQUIRES_NEW không tự mang lại exactly-once, distributed transaction hay bền vững sự kiện qua mọi lỗi crash.

## 21. Checklist QA khi kiểm thử transaction propagation

- [ ] Xác định test-managed T_TEST và service-managed T_NEW rõ ràng?
- [ ] Có `PlatformTransactionManager` và đúng database connection resource?
- [ ] `REQUIRES_NEW` đặt trên public method của Spring bean, được gọi qua proxy?
- [ ] Không gắn `@Transactional(REQUIRES_NEW)` lên JUnit test rồi coi như service semantics?
- [ ] Test phân biệt REQUIRED, REQUIRES_NEW và NESTED/savepoint?
- [ ] Có kiểm tra dữ liệu SAU outer rollback/commit bằng `@AfterTransaction`/transaction mới?
- [ ] Không lấy `@AfterEach` hoặc self-query trong T_TEST làm bằng chứng commit?
- [ ] Có ca inner commit, outer rollback và row inner vẫn còn?
- [ ] Có ca inner unchecked exception làm chính inner rollback?
- [ ] Có ca `@Commit`/`@Rollback` nếu cần đối chiếu chính sách outer?
- [ ] Có cleanup ngoài T_TEST và key riêng cho từng test?
- [ ] Không dùng dữ liệu production/shared DB cho những lệnh delete nguy hiểm?
- [ ] Outer không khóa row mà inner cũng phải update hoặc tham chiếu chưa commit?
- [ ] Pool đủ connection cho outer+inner, có timeout phù hợp?
- [ ] Với JPA đã cân nhắc flush và first-level cache?
- [ ] Với real HTTP/async đã hiểu transaction thread khác?
- [ ] Không dùng preemptive timeout thay đổi test thread nếu dựa vào rollback?
- [ ] Không giả định `@DirtiesContext` xóa committed external DB?
- [ ] Không dùng REQUIRES_NEW cho sự kiện “business success” trước khi outer commit mà không có thiết kế consistency?
- [ ] Nếu DB isolation/lock semantics quyết định kết quả production, đã có integration test trên DB giống production?

## 22. Chạy test và đọc đúng kết quả

Trên Linux/macOS từ dự án có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.txdemo.RequiresNewIsolationTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.txdemo.RequiresNewIsolationTest"
~~~

Có **3 ca JUnit** trong `RequiresNewIsolationTest`. Bảng kỳ vọng mà `@AfterTransaction` đối chiếu, trước cleanup:

~~~text
Case 1: T_TEST rollback, T_NEW commit   -> required=0, new=1
Case 2: T_TEST rollback, T_NEW rollback -> required=0, failed=0
Case 3: T_TEST commit,   T_NEW commit   -> required=1, new=1
~~~

Đây là **kết quả dự kiến theo Java/Spring/H2 semantics**, không phải console output đã quan sát khi chạy Gradle. Code không in `System.out.println`, nên không có stdout ứng dụng cố định. Nếu môi trường thiếu JDK, Gradle Wrapper hoặc dependency, test chưa thể thực thi chỉ bằng `javac` mà không có classpath Spring/JUnit.

**Ghi nhớ:** `@Transactional` trên test chỉ đảm bảo rollback **T_TEST**. `@Transactional(propagation = REQUIRES_NEW)` trên service dùng **physical transaction độc lập**, có thể commit trong lúc T_TEST chưa kết thúc. Khi cần chứng minh dữ liệu còn tồn tại, phải kiểm tra **sau** outer completion và dọn committed state một cách có chủ đích.

### Tài liệu chính thức

- [Spring Framework — TestContext transaction management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html)
- [Spring Framework — @TransactionalEventListener](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot 3.5 — Gradle plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)