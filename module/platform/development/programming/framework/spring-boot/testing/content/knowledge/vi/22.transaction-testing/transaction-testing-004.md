# TestTransaction để kết thúc và mở lại giao dịch có chủ đích trong Spring Boot

## 1. Khi nào cần TestTransaction?

Trong Spring Boot, nhiều kiểm thử truy cập cơ sở dữ liệu được Spring TestContext bao trong một **test-managed transaction**. Với `@DataJpaTest`, `@JdbcTest` hoặc một test `@SpringBootTest @Transactional`, thay đổi dữ liệu thường được **rollback sau test**. Cách làm này thuận tiện vì không để lại bản ghi, nhưng đôi khi khiến bài test không thể trả lời những câu hỏi liên quan đến **commit**:

- Một `INSERT` được đọc lại ngay trong cùng transaction nhưng đã thực sự commit thành công chưa?
- Dữ liệu có còn tồn tại khi đọc ở transaction **khác** sau commit?
- Nếu T1 commit rồi T2 sửa dữ liệu và rollback, dữ liệu của T1 có được giữ nguyên không?
- Khi nào `@AfterEach` không dọn được dữ liệu đã commit?
- `flush()`, `commit`, `rollback`, `@Commit` và `TestTransaction.end()` khác nhau ở đâu?
- Làm sao chủ động kiểm tra một nhánh rollback **trước khi** test method hoàn tất?

Spring TestContext cung cấp `org.springframework.test.context.transaction.TestTransaction` để **đặt cờ commit/rollback, kết thúc transaction test hiện tại và khởi động một transaction test mới** mà không phải kết thúc test method.

```text
Spring TestContext mở T1 (mặc định rollback)
   |
   +-- JDBC/Repository ghi dữ liệu trong T1
   |
   +-- flagForCommit() hoặc flagForRollback()
   |     (chỉ thay đổi quyết định kết thúc)
   |
   +-- end() -----------------> COMMIT hoặc ROLLBACK T1
   |
   +-- kiểm tra dữ liệu ngoài test-managed transaction
   |
   +-- start() ---------------> MỞ T2 MỚI
   |
   +-- các thao tác khác trong T2
   |
   +-- hết test --------------> ROLLBACK T2 theo mặc định
```

**Điểm cốt lõi:** `flagForCommit()` **không tự commit**, `flagForRollback()` **không tự rollback**, còn `start()` **không hồi sinh T1**. Chỉ `end()` mới kết thúc transaction theo cờ hiện tại. Một transaction đã commit không bị đảo ngược chỉ vì transaction sau rollback.

Bài dùng **Java 17+, Spring Boot 3.5.x / Spring Framework 6.x, H2, JdbcTemplate và JUnit Jupiter** để cung cấp một dự án mẫu có thể chạy. Những nguyên tắc này cũng dùng được với JPA khi hiểu thêm `EntityManager` và `flush()`.

## 2. Test-managed, Spring-managed và application-managed transactions

| Nhóm | Ai quản lý? | Ví dụ | TestTransaction can thiệp tới đâu? |
|---|---|---|---|
| **Test-managed** | `TransactionalTestExecutionListener` của Spring TestContext | Test `@Transactional`, `@JdbcTest` | `start/end/flag` chính transaction test |
| **Spring-managed** | Spring transaction infrastructure bên trong `ApplicationContext` | Service `@Transactional` | Có thể tham gia T1 hoặc tạo transaction riêng theo propagation |
| **Application-managed** | Code dùng `TransactionTemplate` hoặc transaction manager trực tiếp | Service mở transaction programmatic | Không mặc định là transaction do TestContext điều khiển |

Trong một test đang có T1, service `@Transactional(propagation = REQUIRED)` thường tham gia T1 nếu dùng cùng transaction manager/resource, nên rollback cuối test xóa cả thay đổi của service.

Service `@Transactional(propagation = REQUIRES_NEW)` có thể tạm ngưng T1 và tạo **một transaction khác**. Nếu transaction mới commit, rollback T1 không tự xóa những thay đổi độc lập ấy. `NESTED` thường dựa trên savepoint khi được hỗ trợ, **không tương đương** `REQUIRES_NEW`.

**HTTP integration:** với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, client test và embedded HTTP server chạy trên các thread khác nhau. TestTransaction ở client **không quản lý** transaction do server thread mở, và rollback của client không xóa những DB rows mà server đã commit.

## 3. Điều kiện để gọi TestTransaction đúng

Bạn cần:

1. Test được chạy qua Spring TestContext và có `TransactionalTestExecutionListener` (thường bật mặc định).
2. Spring context có một `PlatformTransactionManager` thích hợp với datasource.
3. Test thực sự transactional, chẳng hạn do `@JdbcTest`/`@DataJpaTest` hoặc `@Transactional` trên test.
4. Code gọi `TestTransaction` trên **thread của test** đang có `TransactionContext`.
5. Test **không** bị tắt transaction bởi `@Transactional(propagation=NOT_SUPPORTED)` hoặc `NEVER`.

```java
import org.springframework.test.context.transaction.TestTransaction;

assertTrue(TestTransaction.isActive());
assertTrue(TestTransaction.isFlaggedForRollback());
```

Đây là đoạn minh họa **bên trong test transactional có rollback mặc định** và import JUnit assertions. Test `@SpringBootTest` không có `@Transactional` không tự động có một test-managed transaction. Tương tự, `TestTransaction` không phải factory cho phép mở transaction tùy ý ở một plain JUnit unit test.

**Thread-bound:** Spring TestContext sử dụng state gắn với thread. `CompletableFuture`, executor, Reactor schedulers hoặc preemptive timeout callback không tự kế thừa transaction test từ caller.

## 4. Sáu phương thức TestTransaction và ý nghĩa

| API | Trả lời câu hỏi | Lưu ý |
|---|---|---|
| `isActive()` | Có test-managed transaction active trên thread hiện tại không? | Không có nghĩa “mọi transaction hệ thống đều inactive” |
| `isFlaggedForRollback()` | Cờ rollback hiện tại là true hay false? | Ném lỗi nếu không có transaction test active |
| `flagForCommit()` | Khi kết thúc, hãy thử commit transaction này | **Không commit ngay** |
| `flagForRollback()` | Khi kết thúc, hãy rollback transaction này | **Không rollback ngay** |
| `end()` | Kết thúc transaction test hiện tại theo cờ | Không được gọi khi inactive |
| `start()` | Mở **transaction test mới** trong context hiện tại | Chỉ khi đã `end()` hoặc context chưa có active transaction |

Import không phụ thuộc package Boot 3.5 hay 4.x:

```java
import org.springframework.test.context.transaction.TestTransaction;
```

### 4.1. Cờ chỉ là ý định, không phải thao tác DB

```java
TestTransaction.flagForCommit();
assertFalse(TestTransaction.isFlaggedForRollback());
assertTrue(TestTransaction.isActive());

TestTransaction.flagForRollback();
assertTrue(TestTransaction.isFlaggedForRollback());
assertTrue(TestTransaction.isActive());
```

Sau cả hai lệnh, transaction vẫn active. `flagForRollback()` gọi sau `flagForCommit()` sẽ **đổi lại cờ của chính transaction đó**. Muốn kết thúc phải gọi `end()` hoặc đợi Spring TestContext kết thúc test method.

### 4.2. Vòng đời commit T1 rồi khởi động T2

```java
// Đang trong T1 của test.
TestTransaction.flagForCommit();
TestTransaction.end();                    // Commit T1 nếu thành công
assertFalse(TestTransaction.isActive());

// Lúc này có thể kiểm tra dữ liệu ngoài test transaction.
TestTransaction.start();                  // Bắt đầu T2 mới
assertTrue(TestTransaction.isActive());
```

Đoạn trên không phải chương trình độc lập. Khi bắt đầu T2, **default rollback flag** của test được dùng trở lại: với `@JdbcTest` mặc định là rollback; với test có `@Commit` hoặc `@Rollback(false)`, mặc định có thể là commit.

### 4.3. Những lời gọi không hợp lệ

- `start()` khi một test-managed transaction vẫn active: thường ném `IllegalStateException`.
- `end()`, `flagForCommit()`, `flagForRollback()` khi không có test-managed transaction active: ném `IllegalStateException`.
- `isFlaggedForRollback()` cũng cần transaction active; kiểm tra `isActive()` trước.
- Không gọi `TestTransaction.start()` như phương tiện thay thế `TransactionTemplate` trong application code.

## 5. Chọn một ví dụ JDBC để nhìn thấy ranh giới commit rõ nhất

Ta dùng `@JdbcTest`: Spring Boot tạo hạ tầng JDBC và `JdbcTemplate`, sử dụng H2 test database, và **mặc định rollback giao dịch của từng test**. Vì đề bài là `TestTransaction`, không cần mang toàn bộ controller/service/JPA vào context.

API SQL của ví dụ:

```sql
CREATE TABLE tx_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    note_text VARCHAR(200) NOT NULL
);
```

Mỗi test sử dụng `note_id` có UUID riêng; khi một test cố ý commit bản ghi, `@AfterTransaction` sẽ xóa nó **sau khi transaction cuối của test kết thúc**. Nhờ vậy, bài học về commit không biến thành rủi ro dữ liệu tồn lưu trên DB test dùng chung.

Các tình huống kiểm tra:
- Transaction mặc định đang active và sẽ rollback.
- `flagForCommit()` chỉ thay cờ, không kết thúc transaction.
- `end()` với rollback xóa thay đổi trước khi test kết thúc.
- `flagForCommit(); end()` lưu row bền để query ngoài transaction đọc được.
- Commit T1 rồi update trong T2; rollback T2 giữ bản v1 đã commit.
- `start()` khi active bị từ chối.
- `end()/flag` khi không có active transaction bị từ chối.

## 6. Dự án Java 17+ hoàn chỉnh

### 6.1. Cấu trúc file

```text
build.gradle
src/main/java/com/example/txlab/
    TxLabApplication.java
src/test/resources/sql/
    tx-notes-schema.sql
src/test/java/com/example/txlab/
    TestTransactionBoundaryTest.java
```

### 6.2. build.gradle theo Boot 3.5.x

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chọn một bản Boot 3.5.x patch phù hợp với chính sách cập nhật của dự án; `3.5.8` là ví dụ cụ thể cho build. Các Spring/JUnit dependencies nên được đồng bộ bởi Boot BOM. Cần Gradle/JDK tương thích, repository có thể tải dependencies. H2 chỉ ở test runtime để không vô tình thành datasource production.

Nếu dùng Maven, cần Spring Boot parent/BOM, starter-jdbc, starter-test, H2 ở test scope và Surefire/JUnit Jupiter phù hợp.

### 6.3. Application class

Tệp `src/main/java/com/example/txlab/TxLabApplication.java`:

```java
package com.example.txlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }
}
```

`@SpringBootApplication` giúp Spring Boot tìm application configuration, nhưng `@JdbcTest` vẫn chỉ nạp JDBC slice chứ không tự khởi động HTTP server.

### 6.4. SQL schema dùng trong test

Tệp `src/test/resources/sql/tx-notes-schema.sql`:

```sql
CREATE TABLE tx_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    note_text VARCHAR(200) NOT NULL
);
```

Spring SQL initialization chạy khi application context/datasource được khởi tạo. Script không được chạy lại chỉ vì `TestTransaction.start()` mở transaction mới.

### 6.5. JUnit Jupiter test đầy đủ

Tệp `src/test/java/com/example/txlab/TestTransactionBoundaryTest.java`:

```java
package com.example.txlab;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/tx-notes-schema.sql"
})
class TestTransactionBoundaryTest {

    @Autowired
    JdbcTemplate jdbc;

    // Với JUnit Jupiter mặc định, mỗi test method có instance riêng.
    // Chỉ theo dõi row do test hiện tại đã chủ động commit.
    private String committedId;

    private String newId() {
        return "tx-" + UUID.randomUUID();
    }

    private void insert(String id, String note) {
        int affected = jdbc.update(
                "INSERT INTO tx_notes (note_id, note_text) VALUES (?, ?)",
                id, note);
        assertEquals(1, affected);
    }

    private int count(String id) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_notes WHERE note_id = ?",
                Integer.class, id);
        return value == null ? 0 : value;
    }

    private String readNote(String id) {
        return jdbc.queryForObject(
                "SELECT note_text FROM tx_notes WHERE note_id = ?",
                String.class, id);
    }

    // Kết thúc transaction theo cờ hiện tại; chạy assertion khi
    // không có test-managed transaction; luôn mở lại T kế tiếp.
    private void endVerifyAndRestart(Runnable verifyOutsideTx) {
        TestTransaction.end();

        try {
            assertFalse(TestTransaction.isActive());
            verifyOutsideTx.run();
        } finally {
            TestTransaction.start();
        }
    }

    @BeforeTransaction
    void beforeInitialTransaction() {
        assertFalse(TestTransaction.isActive());
    }

    @AfterTransaction
    void cleanupCommittedRowAfterTest() {
        assertFalse(TestTransaction.isActive());

        if (committedId != null) {
            // Không chạy trong test transaction cuối:
            // DELETE của JdbcTemplate được commit bằng auto-commit.
            jdbc.update(
                    "DELETE FROM tx_notes WHERE note_id = ?",
                    committedId);
        }
    }

    @Test
    void startsWithRollbackFlagEnabled() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        String id = newId();
        insert(id, "uncommitted");
        assertEquals(1, count(id));

        // Không commit: TestContext rollback transaction cuối test.
    }

    @Test
    void changingFlagDoesNotImmediatelyCommitOrRollback() {
        String id = newId();
        insert(id, "pending");

        TestTransaction.flagForCommit();
        assertTrue(TestTransaction.isActive());
        assertFalse(TestTransaction.isFlaggedForRollback());
        assertEquals(1, count(id));

        // Đổi lại cờ rollback trước khi test kết thúc.
        TestTransaction.flagForRollback();
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
    }

    @Test
    void canRollbackAndStartNewTransactionBeforeTestEnds() {
        String id = newId();
        insert(id, "will rollback");

        TestTransaction.flagForRollback();
        endVerifyAndRestart(
                () -> assertEquals(0, count(id)));

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
        assertEquals(0, count(id));
    }

    @Test
    void canCommitAndReadOutsideTheTransaction() {
        String id = newId();
        committedId = id;
        insert(id, "committed");

        TestTransaction.flagForCommit();
        assertFalse(TestTransaction.isFlaggedForRollback());

        endVerifyAndRestart(() -> {
            assertEquals(1, count(id));
            assertEquals("committed", readNote(id));
        });

        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());
        assertEquals("committed", readNote(id));
    }

    @Test
    void rollingBackSecondTransactionKeepsFirstCommit() {
        String id = newId();
        committedId = id;
        insert(id, "v1");

        TestTransaction.flagForCommit();
        endVerifyAndRestart(
                () -> assertEquals("v1", readNote(id)));

        // Đang ở T2, sửa dữ liệu đã commit của T1.
        assertEquals(1, jdbc.update(
                "UPDATE tx_notes SET note_text = ? WHERE note_id = ?",
                "v2", id));
        assertEquals("v2", readNote(id));

        TestTransaction.flagForRollback();
        endVerifyAndRestart(
                () -> assertEquals("v1", readNote(id)));

        // Helper đã mở T3, mặc định rollback cuối test.
        assertTrue(TestTransaction.isActive());
        assertEquals("v1", readNote(id));
    }

    @Test
    void cannotStartNewTransactionWhileOneIsActive() {
        assertTrue(TestTransaction.isActive());

        assertThrows(
                IllegalStateException.class,
                TestTransaction::start);

        assertTrue(TestTransaction.isActive());
    }

    @Test
    void cannotEndOrChangeFlagWhenInactive() {
        // Rollback T1, sau đó thử API khi không active.
        TestTransaction.end();
        try {
            assertFalse(TestTransaction.isActive());

            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::end);
            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::flagForCommit);
            assertThrows(
                    IllegalStateException.class,
                    TestTransaction::flagForRollback);
        } finally {
            TestTransaction.start();
        }

        assertTrue(TestTransaction.isActive());
    }
}
```

**Các bảo đảm trong ví dụ:**
- Bảng SQL tồn tại trước mỗi test nhờ schema init lúc context khởi tạo.
- IDs có UUID nên không dựa vào thứ tự chạy hay dữ liệu từ các test trước.
- Chỉ những test cố ý commit mới điền `committedId`.
- `@AfterTransaction` được Spring gọi sau khi test-managed transaction cuối kết thúc, nên cleanup row đã commit không bị rollback cùng T2/T3.
- Helper dùng `finally`: assertion sau `end()` thất bại cũng cố mở transaction test mới để lifecycle rõ ràng.
- Không dùng `@Commit` hay `@Rollback(false)` trên lớp, nên T2/T3 bắt đầu với default rollback.
- Nếu process bị kill trước callback cuối hoặc DB connection gặp lỗi, cleanup không được bảo đảm; vì vậy test nên sử dụng **H2/DB cô lập**, không chạy vào production.

### 6.6. Ý nghĩa của bảy ca test

| Ca | Bằng chứng có cơ sở | Chưa chứng minh |
|---|---|---|
| `startsWithRollbackFlagEnabled` | T1 active, rollback mặc định | Row được commit |
| `changingFlagDoesNotImmediatelyCommitOrRollback` | Thay cờ không kết thúc T1 | `flagForCommit` đã ghi bền dữ liệu |
| `canRollbackAndStartNewTransactionBeforeTestEnds` | T1 rollback trước khi test hết, T2 active và thấy row đã mất | Transaction độc lập của service cũng bị rollback |
| `canCommitAndReadOutsideTheTransaction` | T1 commit và row đọc được ngoài test transaction | Replica hoặc external system đã nhận thay đổi |
| `rollingBackSecondTransactionKeepsFirstCommit` | T1 commit `v1`, T2 ghi `v2` rồi rollback nên `v1` tồn tại | Isolation/locking dưới concurrent load |
| `cannotStartNewTransactionWhileOneIsActive` | `start()` không phải nested transaction API | Mọi transaction manager đều có cùng propagation |
| `cannotEndOrChangeFlagWhenInactive` | `end/flag` yêu cầu active test transaction | TestTransaction dùng được ngoài Spring TestContext |

Chưa có stdout cố định của nghiệp vụ: những test trên dùng assertions và không `System.out.println`. Chỉ tuyên bố runtime PASS sau khi chạy đúng Gradle/Maven task và kiểm tra report; ví dụ được **thiết kế để chạy**, không phải bản log thực thi trong bài viết.

### 6.7. Chạy test

Linux/macOS:

```bash
./gradlew test --tests "com.example.txlab.TestTransactionBoundaryTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.txlab.TestTransactionBoundaryTest"
```

Maven wrapper nếu dự án đã có pom.xml/dependencies tương đương:

```bash
./mvnw -Dtest=TestTransactionBoundaryTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=TestTransactionBoundaryTest test
```

Cần JDK 17+, wrapper và dependency JUnit Jupiter phù hợp. Gradle report thường ở `build/reports/tests/test/index.html`; Maven Surefire ở `target/surefire-reports/`. Xác nhận **7 test methods được khám phá và thực thi**, không bị `SKIPPED`, `NO-SOURCE` hoặc bỏ qua bởi cấu hình CI.

## 7. Đọc một chuỗi commit T1, rollback T2, restart T3

```text
DB ban đầu không có key X

Bước   Transaction         Hành động                 DB nhìn thấy
----   -----------         ---------                 ------------
 A     T1 active           INSERT X = "v1"          T1: v1
 B     T1 active           flagForCommit()           T1 vẫn active
 C     T1 end()            COMMIT T1                 v1 đã commit
 D     Ngoài test tx       SELECT X                  v1
 E     T2 start()          Bắt đầu transaction mới   T2: v1
 F     T2 active           UPDATE X = "v2"          T2: v2
 G     T2 active           flagForRollback()         T2 vẫn active
 H     T2 end()            ROLLBACK T2               v1 vẫn được lưu
 I     Ngoài test tx       SELECT X                  v1
 J     T3 start()          Bắt đầu transaction mới   T3: v1
 K     Kết thúc test       ROLLBACK T3               v1 vẫn được lưu
 L     @AfterTransaction   DELETE X                   DB sạch
```

B và G chỉ là đổi cờ. **C và H mới là ranh giới thật**, khi transaction manager kết thúc một transaction. Việc T2 rollback không thể hoàn tác commit T1 đã hoàn thành.

Khi ở đoạn D/I, không có *test-managed transaction* active, nhưng nếu gọi một service `@Transactional` thì service có thể tự mở Spring-managed transaction. Phân biệt **test transaction không active** với **toàn bộ hệ thống không có giao dịch**.

## 8. @BeforeTransaction, @AfterTransaction và JUnit callbacks

Spring TestContext có hai callback ngoài transaction:

- `@BeforeTransaction`: chạy **trước khi transaction test ban đầu bắt đầu**.
- `@AfterTransaction`: chạy **sau khi transaction cuối của test kết thúc**.

Chúng khác `@BeforeEach` và `@AfterEach` của JUnit Jupiter. Hai callback `BeforeEach/AfterEach` ở mức method thường chạy **trong** test-managed transaction khi active.

| Hook | Vị trí bình thường | Phù hợp để |
|---|---|---|
| `@BeforeTransaction` | Trước T1 | Kiểm tra baseline đã commit |
| `@BeforeEach` | Trong T1 | Tạo fixture dự kiến rollback cùng test |
| `@Test` | Trong T1, có thể có đoạn không tx sau `end()` | Chạy assertions, end/start theo từng ranh giới |
| `@AfterEach` | Trong transaction active cuối | Cleanup fixture chưa commit |
| `@AfterTransaction` | Sau khi transaction cuối của test kết thúc | Đọc DB ngoài tx, dọn dữ liệu đã commit |

**Quan trọng:** `@BeforeTransaction` và `@AfterTransaction` là hooks của **test method lifecycle**, không tự được gọi lại mỗi lần test thủ công `end()/start()`. Trong ví dụ, kiểm tra giữa hai transaction được gọi trực tiếp trong `endVerifyAndRestart`; callback `@AfterTransaction` chỉ chạy cuối cùng.

Nếu dữ liệu đã commit tại T1, một lệnh `DELETE` trong `@AfterEach` nhưng thuộc T2 có thể bị rollback cuối test, làm **bản ghi T1 vẫn còn**. Đó là lý do test mẫu dùng `@AfterTransaction` để cleanup row đã commit.

## 9. TestTransaction so với @Commit và @Rollback

| Nhu cầu | Công cụ phù hợp | Điều khác biệt |
|---|---|---|
| Test CRUD thường, dữ liệu không nên tồn tại sau test | Rollback mặc định | Không cần TestTransaction |
| Muốn commit khi test method hoàn tất | `@Commit` hoặc `@Rollback(false)` | Declarative; cần cleanup |
| Muốn commit ở giữa test, rồi kiểm tra dữ liệu | `flagForCommit(); end(); ... start()` | Có thể quan sát DB sau commit |
| Muốn rollback ở giữa test, rồi tiếp tục với transaction mới | `flagForRollback(); end(); ... start()` | Phân tách rõ T1 và T2 |
| Muốn production service tự quản lý transaction | Test service thật, transaction setup phù hợp | Đừng để test transaction che boundary service |
| Muốn mở transaction trong code application | `TransactionTemplate` | Không phải TestContext API |

`@Commit` làm thay đổi **default decision** của test transaction; nó không tự thực hiện commit trước khi test method kết thúc. `@Rollback(false)` có ý nghĩa tương tự. `TestTransaction.flagForCommit()` có tác dụng trên **giao dịch hiện tại** và `end()` kết thúc giao dịch ấy ngay giữa test.

Khi `TestTransaction.start()` tạo transaction kế tiếp, cờ quay về **default của test**; nếu test có `@Commit` thì transaction mới có thể cũng được commit ở cuối, không phải rollback. Vì vậy phải kiểm tra cờ trên **mỗi transaction mới** thay vì dùng kết quả đọc từ T1.

Ví dụ minh họa:

```java
TestTransaction.start();
assertTrue(TestTransaction.isActive());
assertTrue(TestTransaction.isFlaggedForRollback());
```

Assertion cuối chỉ đúng cho **setup rollback mặc định** của bài, không phải điều hiển nhiên cho mọi test.

## 10. TestTransaction, JPA flush và first-level cache

Với `@DataJpaTest`, `EntityManager` thường giữ entity managed trong persistence context. `repository.save(entity)` không bảo đảm SQL/constraint đã được thực thi ngay trong mọi trường hợp. `entityManager.flush()` yêu cầu Hibernate gửi những thay đổi pending xuống database **nhưng không commit**.

```java
repository.save(entity);
entityManager.flush();            // Đồng bộ SQL, chưa commit
TestTransaction.flagForCommit();
TestTransaction.end();            // Kết thúc transaction T1
TestTransaction.start();          // Transaction T2 mới
```

Đây là đoạn minh họa trong test có repository/entity/EntityManager hợp lệ, không phải file độc lập. Nếu commit/flush gặp constraint violation hoặc transaction đã bị đánh dấu rollback-only, `flagForCommit()` **không thể ép database bỏ qua lỗi**. Đừng báo “commit thành công” trước khi `end()` thực sự hoàn thành.

**Lỗi false positive thường gặp:** gọi `save` rồi `findById` trên cùng `EntityManager` có thể nhận lại chính managed entity từ first-level cache, thay vì quan sát một SELECT thật. Khi cần kiểm chứng mapping/SQL, hãy `flush → clear → read`, hoặc kết thúc và mở một transaction mới rồi đọc lại; có thể thêm JDBC assertion để quan sát dữ liệu ngoài JPA cache.

Với một transaction bị đánh dấu rollback-only sau exception, dùng `TestTransaction.flagForCommit()` không biến nó thành transaction khỏe mạnh. Hãy đọc root cause và để rollback; đừng tiếp tục thao tác trên cùng persistence context đã lỗi.

## 11. Những ranh giới mà TestTransaction không quản lý

### 11.1. @Transactional(REQUIRES_NEW)

Một service được gọi **qua Spring proxy** có thể có:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(...) {
    // Thao tác DB trong transaction riêng.
}
```

Đây là method minh họa, không phải Java file độc lập. Khi chạy giữa test T1, `REQUIRES_NEW` có thể mở T2 độc lập và **commit T2**. Rollback của T1 sẽ không xóa audit record đã commit. Ngược lại `REQUIRED` thường tham gia T1 nếu dùng đúng cùng transaction manager/resource.

Bài `TestTransaction` minh họa commit/rollback **test-managed transactions**; nó không thay thế việc test thật propagation của service.

### 11.2. HTTP server thật, async, executor, preemptive timeout

`@SpringBootTest(RANDOM_PORT)` chạy HTTP handler ở thread server khác. Test thread `@Transactional` không làm cho server thread dùng cùng transaction. Một server request đã commit sẽ cần cleanup riêng, không tự bị test rollback.

`assertTimeoutPreemptively` của JUnit Jupiter có thể chạy callback trong thread khác, nơi không có transaction `ThreadLocal` do Spring TestContext gắn ở test thread. Một JDBC write ở đó có thể commit độc lập và làm bẩn test database. Nếu cần timeout mà không muốn tách thread, dùng `assertTimeout` khi thích hợp (nó không tự ngắt một JDBC call bị treo).

Tương tự, `CompletableFuture.runAsync`, custom executor hay Reactor schedulers không mang theo TestTransaction mặc định. `isActive()==false` ở background thread không chứng minh test thread không có transaction.

### 11.3. Side effects bên ngoài RDBMS

SQL rollback không tự thu hồi Redis key, Kafka event, email đã gửi hay file đã ghi. `TestTransaction` không phải distributed transaction coordinator. Các test có side effects này cần isolation và cleanup riêng.

## 12. Transaction isolation và hai kết nối độc lập

Một test đọc lại dữ liệu **trong cùng T1** chưa chứng minh transaction bên ngoài nhìn thấy được. Muốn kiểm tra:
- Commit visibility: `end()` T1 rồi đọc bằng JDBC ngoài test transaction.
- Rollback: `end()` T1 với rollback rồi đọc để thấy row không tồn tại.
- Dirty reads/nonrepeatable reads/phantoms: cần **hai transaction/connections đồng thời** và sự phối hợp thời điểm, không chỉ một chuỗi tuần tự T1 → T2.

H2 có thể khác PostgreSQL/MySQL về isolation levels, locks, deferred constraints và deadlock behavior. Nếu nghiệp vụ phụ thuộc các chi tiết này, dùng Testcontainers với database gần production. `TestTransaction` giúp mở/kết thúc transaction test, nhưng nó không thể một mình chứng minh mọi hành vi concurrency.

## 13. SQL fixture và cleanup có chủ đích

Một số chiến lược an toàn:

- Đặt schema trong SQL initialization (như ví dụ).
- Tạo fixture bên trong test transaction để nó tự rollback.
- Dùng `@BeforeTransaction` khi cần fixture đã commit trước T1 và có kế hoạch xóa.
- Dùng `@AfterTransaction` để cleanup dữ liệu test đã commit.
- Dùng `@Sql` và `@SqlConfig(transactionMode=ISOLATED)` có chủ đích khi cần fixture ở transaction riêng; không mặc định kết quả sẽ rollback với T1.
- Dùng UUID cho keys, tách DB/schema/container per test suite nếu có nhiều test commit.

Không dùng `@DirtiesContext` như một cách xóa dữ liệu đã commit: nó ảnh hưởng context cache, không tự xóa database bên ngoài. Không chạy `DELETE FROM all_business_tables` trên một datasource không chắc chắn là test DB.

Đặc biệt, một `@AfterEach` chạy trong T2 rồi rollback có thể làm cleanup “ảo” (DELETE bị rollback), khiến dữ liệu T1 vẫn tồn tại. Kiểm tra lifecycle callback và transaction state thật trước khi quyết định cleanup ở đâu.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `IllegalStateException` khi `start()` | Test transaction vẫn active | Chỉ start sau end; kiểm tra isActive |
| `IllegalStateException` khi `end()` | Không có active test transaction | Đọc isActive, annotations, thread |
| `flagForCommit()` nhưng DB vẫn rollback | Chưa end, cờ bị đổi lại, transaction rollback-only | Theo dõi flag, end, root cause |
| Sau `start()` flag rollback trở lại | T2 dùng default rollback của test | Hành vi đúng ở setup mặc định |
| Sau `start()` flag commit | Test có `@Commit`/`@Rollback(false)` | Xác định default chính xác |
| Test save/find xanh nhưng row không commit | Query cùng T1 thấy uncommitted data | end rồi đọc ngoài transaction |
| `@AfterEach` dọn nhưng row vẫn còn | DELETE nằm trong T2 rồi rollback | Dọn ở `@AfterTransaction` |
| Fail khi gọi `end()` | Constraint/flush failure hoặc transaction manager lỗi | Không gắn nhãn commit thành công trước khi end |
| Row leak sang test khác | T1 đã commit, cleanup thiếu | ID riêng, DB cô lập, cleanup ngoài tx |
| @BeforeTransaction không chạy lại mỗi start | Hook theo lifecycle test method, không theo từng transaction | Assert trực tiếp ở boundary |
| Test rollback không xóa thay đổi từ service | REQUIRES_NEW hoặc separate resource | Test propagation và cleanup |
| Test qua RANDOM_PORT để lại DB row | HTTP server thread có transaction riêng | Cleanup từ DB test độc lập |
| `assertTimeoutPreemptively` rò dữ liệu | Callback ở thread khác | Tránh preemptive timeout khi ghi DB |
| JPA find thấy giá trị cũ | First-level cache | Flush/clear/reload qua transaction mới |
| Multiple transaction managers | Listener chọn sai manager hoặc ambiguous | Chỉ rõ `@Transactional(transactionManager="...")` |
| R2DBC Mono/Flux không theo test transaction JDBC | ReactiveTransactionManager/Reactor Context khác PlatformTransactionManager | Test reactive riêng bằng TransactionalOperator/StepVerifier |
| `@Sql` fixture không commit như nghĩ | @Sql cùng transaction test | Cấu hình transactionMode rõ |
| Test “xanh” nhưng không chạy | Test bị skip/NO-SOURCE | Kiểm tra test report |

## 15. Version và phạm vi API

Mã ví dụ ở trên sử dụng Spring Boot 3.5.x, import:

```java
org.springframework.boot.test.autoconfigure.jdbc.JdbcTest
org.springframework.test.context.transaction.TestTransaction
```

Trong Spring Boot 4.x, `@JdbcTest` đã được chuyển vào module chuyên biệt, ví dụ import:

```java
org.springframework.boot.jdbc.test.autoconfigure.JdbcTest
```

Với dự án Boot 4, cần test module `spring-boot-jdbc-test` phù hợp BOM và tránh pha trộn Spring 6/7 hoặc Boot 3/4 dependencies. **Bản thân `TestTransaction` thuộc Spring Framework TestContext** (package `org.springframework.test.context.transaction`), không phải API do Spring Boot định nghĩa.

**R2DBC:** `TestTransaction` trong bài này được dùng với một `PlatformTransactionManager` kiểu JDBC/JPA, không phải mặc định có thể dùng giống hệt cho một `ReactiveTransactionManager` gắn với Reactor Context. Với ứng dụng reactive, nên thiết kế test transaction riêng phù hợp `TransactionalOperator` và các signals của publisher.

## 16. Checklist trước khi coi bài test transaction là đáng tin

- [ ] Xác nhận TestContext tạo một test-managed transaction thật bằng `isActive()`.
- [ ] Xác định đúng `PlatformTransactionManager` khi có nhiều datasources.
- [ ] Biết cờ rollback mặc định và ảnh hưởng của `@Commit`/`@Rollback(false)`.
- [ ] Hiểu flag chỉ đổi quyết định, còn `end()` mới commit/rollback.
- [ ] Sau `end()`, kiểm tra DB ngoài test transaction, không chỉ đọc lại cùng T1.
- [ ] Chỉ `start()` sau `end()`, khôi phục transaction trong `finally` nếu cần.
- [ ] Sau `start()`, kiểm tra cờ của transaction **mới**, không suy luận từ T1.
- [ ] Có test T1 commit/T2 rollback khi use case yêu cầu ranh giới đó.
- [ ] Với JPA, phân biệt flush/commit và chú ý persistence cache.
- [ ] Dữ liệu commit có ID riêng, cleanup ngoài transaction hoặc database/container cô lập.
- [ ] Không dựa vào `@AfterEach` rollback để xóa row đã commit từ T1.
- [ ] Không coi test `@Transactional` là bằng chứng service transaction boundary production.
- [ ] Không giả định HTTP server thread/async threads dùng TestTransaction của test.
- [ ] Tránh preemptive timeouts làm DB writes chạy ngoài transaction.
- [ ] Nếu cần isolation/concurrency, test trên DB dialect phù hợp bằng hai giao dịch thực sự độc lập.
- [ ] Chạy JUnit tests và xác minh số ca thực thi trong report trước khi tuyên bố PASS.

## 17. Tài liệu chính thức

- [Spring Framework — Transaction Management in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, programmatic TestTransaction, lifecycle callbacks và rủi ro preemptive timeouts.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): signatures và preconditions của `start/end/flag`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest` và rollback mặc định, `@SpringBootTest` với server thật.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Framework — @BeforeTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html), [@AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-aftertransaction.html): hooks ngoài transaction.

**Kết luận:** `TestTransaction` là công cụ của Spring TestContext để chủ động **kết thúc T1 bằng commit hoặc rollback, quan sát dữ liệu tại ranh giới rồi mở T2 mới**. Nó không thay thế transaction manager trong production, không “hồi sinh” một transaction đã kết thúc, và rollback cuối test không xóa dữ liệu đã commit trước đó hoặc side effects ngoài SQL. Dùng nó khi cần bằng chứng thực sự về commit/rollback, với test database an toàn, `try/finally` để khôi phục lifecycle và cleanup cho những record đã commit.