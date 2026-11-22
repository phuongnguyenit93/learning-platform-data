# @BeforeTransaction và @AfterTransaction trong Spring Boot Testing

## Mục tiêu

Trong Spring TestContext, khi một JUnit test được chạy trong **test-managed transaction**, Spring có thể mở giao dịch trước test và tự **rollback** khi test kết thúc. Điều này phù hợp với kiểm thử repository, nhưng gây nhầm lẫn khi người học muốn kiểm dữ liệu **trước khi bắt đầu giao dịch** hoặc **sau khi commit/rollback đã xảy ra**. Các phương thức `@BeforeEach` và `@AfterEach` của JUnit không giải quyết đúng yêu cầu này vì chúng thường chạy **bên trong chính test-managed transaction**.

Hai annotation chuyên biệt của Spring:

- **`@BeforeTransaction`** — thực thi callback **trước khi** Spring bắt đầu test-managed transaction.
- **`@AfterTransaction`** — thực thi callback **sau khi** Spring đã kết thúc transaction của test bằng commit hoặc rollback.

Bài thuộc nhánh **Giao dịch kiểm thử** của module **Spring Boot – testing**. Trọng tâm là *ranh giới giao dịch của test*, cách quan sát dữ liệu đã commit bằng connection khác và cleanup đúng thời điểm.

Sau bài này, bạn có thể:

1. Mô tả lifecycle chính xác của `@BeforeTransaction`, `@BeforeEach`, `@Test`, `@AfterEach` và `@AfterTransaction`.
2. Phân biệt **transaction do Spring TestContext quản lý** với transaction của service, HTTP server, `REQUIRES_NEW` hoặc một transaction tự mở.
3. Hiểu điều kiện để hai hook transaction được gọi — test cần thực sự có test-managed transaction.
4. Viết test xác minh **rollback mặc định**, `@Commit` và `@Rollback(false)` bằng dữ liệu thật trên H2.
5. Dùng JDBC query ngoài transaction để quan sát trạng thái trước/sau thay vì chỉ nhìn vào entity còn nằm trong persistence context của JPA.
6. Dọn bản ghi đã commit trong `@AfterTransaction` mà không bị rollback theo test.
7. Biết lúc nào dùng `TestTransaction.flagForCommit()`, `TestTransaction.end()/start()`, `@Sql`, `TransactionTemplate` hoặc một test không `@Transactional`.
8. Tránh false positives do chưa flush, timeout chạy trên thread khác, multi-transaction-manager và các side effects bên ngoài database.
9. Chạy ví dụ Java 17 + Spring Boot 3.3.5 + Spring Data JPA + H2 + Gradle + JUnit Jupiter một cách độc lập.

**Kết luận cần nhớ ngay:** `@BeforeTransaction` và `@AfterTransaction` không phải tên thay thế của JUnit `@BeforeEach` và `@AfterEach`. Chúng được điều phối bởi **`TransactionalTestExecutionListener`**, ở **ngoài ranh giới** của test-managed transaction, và chỉ phù hợp khi Spring đang quản lý giao dịch cho test đó.

## 1. Test-managed transaction là gì?

Một `@Transactional` gắn với JUnit test method hoặc test class có thể kích hoạt cơ chế **test-managed transaction** của Spring TestContext. `TransactionalTestExecutionListener` phát hiện annotation, tìm `PlatformTransactionManager` phù hợp, mở transaction **trước khi gọi method test** và theo mặc định **rollback khi test kết thúc**.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class AccountRepositoryIntegrationTest {

    @Test
    void createsAccount() {
        // repository.save(...) thường tham gia
        // test-managed transaction nếu dùng propagation REQUIRED.
    }
}
~~~

Đây là snippet mô tả (chưa có service/entity/imports) chứ không phải project chạy độc lập. Để test-managed transaction hoạt động, cần:

- Spring TestContext được kích hoạt (ví dụ `@DataJpaTest`, `@SpringBootTest` với Spring/JUnit extension).
- `TransactionalTestExecutionListener` được đăng ký; nó thường có trong các listener mặc định.
- Có `PlatformTransactionManager` phù hợp trong ApplicationContext.
- Test class/method được đánh dấu `@Transactional` — trực tiếp hoặc qua meta-annotation như `@DataJpaTest`.
- Transaction propagation của test không vô hiệu hóa test-managed transaction.

**Mặc định rollback**, trừ khi có `@Commit`, `@Rollback(false)` hoặc logic lập trình thay đổi rollback flag. Đây là **chính sách của test-managed transaction**, không phải lời hứa mọi transaction/side effect trong toàn ứng dụng đều rollback.

### Ba loại transaction cần phân biệt

| Phạm vi | Do ai quản lý? | Ví dụ | Liên hệ tới rollback của JUnit |
| --- | --- | --- | --- |
| Test-managed transaction | Spring `TransactionalTestExecutionListener` | Test JUnit có `@Transactional` | Mặc định rollback sau test |
| Spring-managed transaction | AOP transaction của service/repository | `@Service @Transactional` | Thường tham gia test transaction khi cùng thread, manager và `REQUIRED/SUPPORTS` |
| Application-managed transaction | App code tự điều khiển transaction | `TransactionTemplate`, JDBC manual transaction | Có thể độc lập; phải kiểm boundary và propagation |

Nếu service dùng `REQUIRES_NEW`, transaction của service có thể commit độc lập. Nếu HTTP test gửi request qua `RANDOM_PORT`, server xử lý trên **thread khác**, nên server commit không bị rollback chỉ vì test method mang `@Transactional`.

## 2. Thứ tự lifecycle chính xác

Với một JUnit Jupiter test method có test-managed transaction, luồng điển hình:

~~~text
Spring TestContext khởi tạo context, inject dependencies
    |
    v
@BeforeTransaction                [KHÔNG có test-managed transaction]
    |
    v
BEGIN test-managed transaction
    |
    v
@BeforeEach                      [BÊN TRONG test-managed transaction]
    |
    v
@Test                            [BÊN TRONG test-managed transaction]
    |
    v
@AfterEach                       [BÊN TRONG test-managed transaction]
    |
    v
ROLLBACK (mặc định) / COMMIT (khi @Commit / @Rollback(false))
    |
    v
@AfterTransaction                [KHÔNG có test-managed transaction]
~~~

Đây là lifecycle chính xác về **tương quan với test-managed transaction**; không mô tả mọi JUnit extension khác, `@Sql` execution listener hoặc transaction do service/async thread tự mở.

### Bảng so sánh

| Annotation | Nguồn | Chạy tương quan với test transaction | Mục đích điển hình |
| --- | --- | --- | --- |
| `@BeforeTransaction` | Spring TestContext | **Trước BEGIN**, ngoài test transaction | Đọc baseline đã commit; tạo dữ liệu tiền-điều-kiện bên ngoài test transaction khi cần |
| `@BeforeEach` | JUnit Jupiter | **Trong** transaction đối với transactional test | Tạo fixture thuộc transaction sẽ rollback |
| `@Test` | JUnit Jupiter | **Trong** transaction | Chạy SUT và assertions nội bộ |
| `@AfterEach` | JUnit Jupiter | **Trong** transaction đối với transactional test | Kiểm trạng thái tạm thời, teardown không cần commit riêng |
| `@AfterTransaction` | Spring TestContext | **Sau END**, ngoài test transaction | Kiểm commit/rollback thực tế và cleanup những thay đổi đã commit |
| `@BeforeAll` | JUnit Jupiter | Ngoài test transaction của từng method | Setup cấp class; không dựa vào transaction per-test |
| `@AfterAll` | JUnit Jupiter | Ngoài test transaction của từng method | Teardown cấp class; cần tự kiểm phạm vi dữ liệu |

Các hook `@BeforeTransaction` và `@AfterTransaction` là Spring TestContext hooks; **không** phải JUnit lifecycle callbacks. Nếu một JUnit test thuần không có SpringExtension/TestContext phù hợp, annotation Spring sẽ không tự được gọi.

### Vì sao `@AfterEach` không quan sát được commit cuối test?

Giả sử:

~~~java
@AfterEach
void checkDatabase() {
    // Tại đây test transaction vẫn đang active.
    // Dữ liệu vừa save có thể đang tồn tại bên trong transaction.
}
~~~

Do rollback/commit chưa diễn ra, assertion ở đây **không chứng minh được trạng thái cuối sau khi transaction kết thúc**. Muốn biết một row còn tồn tại **sau rollback**, hãy kiểm từ `@AfterTransaction`, với dữ liệu được truy vấn ở ngoài test transaction.

Ngược lại, muốn setup/cleanup nằm trong transaction sẽ rollback cùng test, `@BeforeEach` hoặc `@AfterEach` thường là nơi phù hợp.

## 3. Import, khả năng gọi và điều kiện chạy

Hai annotation nằm trong package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

Chúng khác hoàn toàn với:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
~~~

Một ví dụ cấu trúc:

~~~java
@BeforeTransaction
void verifyInitialState() {
    // Đọc dữ liệu đã commit trước test transaction.
}

@BeforeEach
void createFixtureInsideTestTransaction() {
    // Có thể tạo dữ liệu tạm thời, sẽ rollback mặc định.
}

@Test
void behavior() {
    // Kiểm logic nghiệp vụ.
}

@AfterEach
void inspectWithinTestTransaction() {
    // Chưa có rollback/commit cuối test.
}

@AfterTransaction
void verifyFinalState() {
    // Transaction của test đã kết thúc.
}
~~~

Đây là snippet method không độc lập. Trong Spring Framework hiện đại, callback Spring có thể là **non-public void method**; không bắt buộc `public`. Các method `@BeforeTransaction`/`@AfterTransaction` cũng có thể được khai báo qua **default methods của test interface**, theo hỗ trợ của TestContext. Với **Spring Framework 6.1 + JUnit Jupiter**, callback còn có thể nhận những arguments mà JUnit `ParameterResolver` giải được (như `TestInfo` hoặc bean `@Autowired`).

Ví dụ Spring Framework 6.1:

~~~java
@BeforeTransaction
void verifyState(@Autowired DataSource dataSource) {
    // Dùng DataSource đã được inject bởi SpringExtension
    // để đọc baseline.
}
~~~

Đây là snippet không độc lập, cần import DataSource và injection context phù hợp. Cách đơn giản, tương thích và dễ review nhất trong demo là **field injection** `JdbcTemplate`/repository rồi hook không có parameters.

### Khi nào hai hook KHÔNG chạy?

- Test không có `@Transactional` hoặc một annotation khác bật test-managed transaction.
- Không có Spring TestContext/`TransactionalTestExecutionListener` để điều phối chúng.
- Test được đánh dấu `@Transactional(propagation = NOT_SUPPORTED)` hoặc `NEVER`: Spring **không mở** test-managed transaction.
- Test method dùng một context không có transaction manager phù hợp, khiến transaction support không khởi tạo thành công (trường hợp này thường là lỗi setup, không phải cơ chế bỏ qua yên lặng).
- Bạn gắn `@Transactional` **chỉ trên service** nhưng không bật test-managed transaction cho method test: transaction service không làm callback transaction của test tự xuất hiện.

**Nhận biết quan trọng:** `@BeforeTransaction`/`@AfterTransaction` chạy **theo test transaction**, không chạy trước/sau **mỗi lời gọi repository.save(...)** hoặc mỗi method `@Transactional` của service.

## 4. Vì sao cần kiểm “ngoài giao dịch”?

Ví dụ bài test:

~~~java
@Test
void insertWithinTestTransaction() {
    repository.save(new JournalEntry(...));
    assertEquals(1, repository.count());
}
~~~

Đoạn này chỉ minh họa với entity/repository có sẵn. Nếu cả save và count chạy trong **cùng test transaction**, result 1 chỉ chứng minh transaction **tự nhìn thấy dữ liệu của mình**. Nó chưa chứng minh:

- Row đã **commit** và visible với transaction khác.
- Row còn tồn tại **sau rollback**.
- Database constraint có được kiểm vào lúc `flush/commit` hay không.
- Một process/job khác có thể đọc dữ liệu ngay sau test không.
- Cleanup của `@AfterEach` có thực sự xóa record đã được commit từ transaction khác không.

`@BeforeTransaction` phù hợp để xác minh **baseline** đã commit từ trước. `@AfterTransaction` phù hợp để xác minh **trạng thái sau transaction**. Cùng một SQL query có thể trả kết quả khác nhau tùy gọi **trong hay ngoài** transaction.

### Phân biệt `flush` với `commit`

Trong JPA:

- `repository.save(entity)` đưa entity vào persistence context và có thể lên lịch SQL.
- `repository.saveAndFlush(entity)` buộc JPA đồng bộ SQL pending về database trong transaction hiện có.
- **`flush` không commit**: row vẫn có thể rollback nếu transaction chưa kết thúc.
- Sau `@Commit`, transaction hoàn tất và row có thể visible với connection mới.
- Sau rollback, row không còn trong database đã commit.

Bài runnable bên dưới dùng `saveAndFlush` để đảm bảo INSERT đã được gửi xuống H2 **trong giao dịch**, rồi dùng `JdbcTemplate` **ngoài giao dịch** ở `@AfterTransaction` để quan sát kết quả cuối.

## 5. Project chạy được: Spring Boot 3.3.5 + Java 17 + JPA/H2

Để minh họa rõ commit/rollback, ta dùng một bảng nhỏ `tx_probe_notes` có `test_key` duy nhất theo mỗi lần test method được chạy. Không mở HTTP server, không cần PostgreSQL, không cần Docker. Bộ test gồm **3 method**:

1. **Rollback mặc định:** save row bên trong transaction, cuối test rollback, `@AfterTransaction` phải thấy **0 row**.
2. **`@Commit`:** save row, commit cuối test, `@AfterTransaction` phải thấy **1 row** rồi xóa riêng row ấy.
3. **`@Rollback(false)`:** cũng yêu cầu commit, giúp phân biệt annotation và default rollback; cuối test cleanup có phạm vi.

Một UUID riêng cho từng method tránh đụng độ khi chạy lại hoặc khi nhiều test có chung database. Hooks kiểm rõ `TestTransaction.isActive()` để chứng minh vị trí tương đối với test transaction.

### 5.1. Cây thư mục

~~~text
transaction-hook-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/txhooks/
    │   ├── TxHooksApplication.java
    │   ├── TxProbeNote.java
    │   └── TxProbeNoteRepository.java
    └── test/java/com/example/txhooks/
        └── TransactionBoundaryHooksTest.java
~~~

Đây là danh sách source/config. Các file `gradlew`/Wrapper JAR phải tạo bằng Gradle phù hợp hoặc lấy từ repository; `gradle-wrapper.jar` là binary, không thể tái tạo bằng chép một đoạn Markdown.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'transaction-hook-demo'
~~~

### 5.3. `build.gradle` (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter-data-jpa` cung cấp Hibernate, transaction manager, repository và DataSource support.
- `spring-boot-starter-test` cung cấp `@DataJpaTest`, Spring TestContext/JUnit Jupiter và assertions.
- H2 ở `testRuntimeOnly` để test slice tự dùng database in-memory; không cần một DB server thật.
- `useJUnitPlatform()` giúp Gradle tìm và chạy `@Test` của JUnit 5.
- Các versions theo Spring Boot BOM, tránh ghim phiên bản Hibernate/Spring khác làm sai behavior của `@DataJpaTest`.

Đừng dùng cấu hình `ddl-auto=create-drop` demo trong production. Ở ứng dụng thật, schema thường được quản lý bằng Flyway/Liquibase hoặc migration tương đương.

### 5.4. Spring Boot root configuration

**`src/main/java/com/example/txhooks/TxHooksApplication.java`**:

~~~java
package com.example.txhooks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxHooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxHooksApplication.class, args);
    }
}
~~~

Spring Boot test có thể tìm `@SpringBootConfiguration` từ root package. `@DataJpaTest` chỉ tải JPA slice, không khởi động HTTP server.

### 5.5. JPA entity thật

**`src/main/java/com/example/txhooks/TxProbeNote.java`**:

~~~java
package com.example.txhooks;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "tx_probe_notes")
public class TxProbeNote {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "test_key", nullable = false, length = 100)
    private String testKey;

    @Column(name = "message", nullable = false, length = 160)
    private String message;

    protected TxProbeNote() {
        // Required by JPA
    }

    public TxProbeNote(String testKey, String message) {
        this.testKey = testKey;
        this.message = message;
    }

    public Long getId() {
        return id;
    }

    public String getTestKey() {
        return testKey;
    }

    public String getMessage() {
        return message;
    }
}
~~~

`testKey` là fixture marker, không phải identity business. `GenerationType.IDENTITY` để H2 tạo ID; không hardcode ID trong tests. Bài kiểm row theo `test_key` vì ta cần tìm chính data do method hiện tại tạo ra.

### 5.6. Spring Data JPA repository

**`src/main/java/com/example/txhooks/TxProbeNoteRepository.java`**:

~~~java
package com.example.txhooks;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TxProbeNoteRepository
        extends JpaRepository<TxProbeNote, Long> {

    long countByTestKey(String testKey);
}
~~~

`countByTestKey` là một derived query Spring Data JPA dùng Java property `testKey`. Nó chỉ được gọi **bên trong test transaction** để xác minh trạng thái tạm thời. Khi cần kiểm dữ liệu **sau transaction kết thúc**, demo dùng `JdbcTemplate` trong `@AfterTransaction` và SQL trực tiếp, để tách góc nhìn rõ ràng.

### 5.7. Integration test hoàn chỉnh

**`src/test/java/com/example/txhooks/TransactionBoundaryHooksTest.java`**:

~~~java
package com.example.txhooks;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.show-sql=false"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
class TransactionBoundaryHooksTest {

    @Autowired
    private TxProbeNoteRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private String testKey;
    private boolean expectCommitted;

    // Spring callback: CHƯA có test-managed transaction.
    @BeforeTransaction
    void beforeTransaction() {
        assertFalse(TestTransaction.isActive());

        testKey = "case-" + UUID.randomUUID();
        expectCommitted = false;

        assertEquals(0, countCommittedRows());
    }

    // JUnit callback: ĐANG ở trong test-managed transaction.
    @BeforeEach
    void beforeEach() {
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void defaultRollbackDiscardsTheInsertedRow() {
        repository.saveAndFlush(
                new TxProbeNote(testKey, "rollback"));

        assertEquals(1L,
                repository.countByTestKey(testKey));

        // Không đặt @Commit hay @Rollback(false):
        // Spring sẽ rollback test transaction mặc định.
    }

    @Test
    @Commit
    void commitMakesTheRowVisibleAfterTransaction() {
        expectCommitted = true;

        repository.saveAndFlush(
                new TxProbeNote(testKey, "commit"));

        assertEquals(1L,
                repository.countByTestKey(testKey));
    }

    @Test
    @Rollback(false)
    void rollbackFalseAlsoCommitsTheTransaction() {
        expectCommitted = true;

        repository.saveAndFlush(
                new TxProbeNote(testKey, "rollback-false"));

        assertEquals(1L,
                repository.countByTestKey(testKey));
    }

    // JUnit callback: commit/rollback CUỐI TEST chưa xảy ra.
    @AfterEach
    void afterEach() {
        assertTrue(TestTransaction.isActive());
    }

    // Spring callback: transaction của test ĐÃ kết thúc.
    @AfterTransaction
    void afterTransaction() {
        assertFalse(TestTransaction.isActive());

        int actualCommittedRows = countCommittedRows();

        try {
            assertEquals(
                    expectCommitted ? 1 : 0,
                    actualCommittedRows);
        } finally {
            // Cleanup ngoài test-managed transaction,
            // chỉ xóa row do method hiện tại tạo.
            jdbcTemplate.update(
                    "DELETE FROM tx_probe_notes WHERE test_key = ?",
                    testKey);
        }

        assertEquals(0, countCommittedRows());
    }

    private int countCommittedRows() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM tx_probe_notes "
                    + "WHERE test_key = ?",
                Integer.class,
                testKey);

        return count == null ? 0 : count;
    }
}
~~~

### 5.8. Vì sao code này đáng tin?

**Thứ nhất: test được quản lý transaction thật.** `@DataJpaTest` là một transactional test slice trong Boot 3.3. Spring TestContext mở transaction quanh method; `TestTransaction.isActive()` kiểm trực tiếp điều kiện này trong `@BeforeEach`/`@AfterEach`.

**Thứ hai: `@BeforeTransaction` quan sát baseline.** Vì test chưa mở transaction, câu `SELECT COUNT(*)` qua `JdbcTemplate` đọc database đã commit. Mỗi method có một `testKey` riêng nên expected 0 không phụ thuộc kết quả test khác.

**Thứ ba: nội dung test được flush xuống DB nhưng chưa commit.** `saveAndFlush` bảo đảm SQL INSERT chạy trong transaction, nên `repository.countByTestKey` thấy 1; điều này **không đồng nghĩa** một connection bên ngoài đã thấy record.

**Thứ tư: `@AfterTransaction` thấy kết quả cuối.**

- Test **default rollback**: row đã insert bị rollback, expected **0**.
- Test có **`@Commit`**: transaction commit, expected **1**.
- Test có **`@Rollback(false)`**: cũng commit, expected **1**.

**Thứ năm: cleanup được thực hiện ngoài transaction vừa kết thúc.** Lệnh `JdbcTemplate.update("DELETE ... WHERE test_key = ?")` chỉ nhắm row của method hiện tại. Trong demo H2/autocommit khi không có transaction Spring đang active, DELETE được commit; assertion cuối kiểm đã dọn sạch.

**Thứ sáu: cleanup vẫn chạy khi assertion về số row thất bại.** Khối `try/finally` cố gắng DELETE kể cả khi `assertEquals` ném `AssertionError`. Điều này giúp giảm dữ liệu rác sau failure bình thường. Nó không bảo đảm cleanup khi JVM bị kill, DB không truy cập được hoặc process crash.

### Kết quả dự kiến cho từng test

| Test | Trong `@Test` sau `saveAndFlush` | Sau transaction ở `@AfterTransaction` | Sau cleanup |
| --- | ---: | ---: | ---: |
| `defaultRollbackDiscardsTheInsertedRow` | 1 | 0 | 0 |
| `commitMakesTheRowVisibleAfterTransaction` | 1 | 1 | 0 |
| `rollbackFalseAlsoCommitsTheTransaction` | 1 | 1 | 0 |

Bộ project định nghĩa **3 JUnit `@Test` methods**. Hook transaction chạy cho **mỗi test method**, nhưng không được tính là test method độc lập. Với cấu hình phù hợp, dự kiến **3 test pass**; đây là kết quả suy ra từ source, **không phải kết quả đã chạy Gradle trên máy người học**.

## 6. Chạy project và kiểm báo cáo

Trong thư mục root có `gradlew`, `build.gradle` và JDK 17:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy chỉ class transaction hooks:

~~~bash
./gradlew test --tests 'com.example.txhooks.TransactionBoundaryHooksTest'
~~~

Báo cáo thông thường nằm tại:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.txhooks.TransactionBoundaryHooksTest.xml
~~~

Không có `System.out.println`, nên không có stdout nghiệp vụ cố định. Gradle có thể báo `BUILD SUCCESSFUL` khi thành công; nếu test task được cache, có thể hiện `UP-TO-DATE` hoặc `FROM-CACHE`.

Muốn buộc chạy test lại khi chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu repo chưa có Gradle Wrapper, tạo từ một Gradle tương thích đã cài, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó giữ Wrapper scripts/JAR theo chính sách repository. Không tự thay Gradle version của project team khi chưa đánh giá compatibility.

### Đọc báo cáo đúng phạm vi

Nếu test `@Commit` fail tại `@AfterTransaction` vì expected 1 nhưng actual 0, hãy kiểm transaction có thật sự commit không, có annotation override không, datasource trong JDBC và JPA có cùng database không, hoặc có mã dọn dữ liệu trước hook không. Không sửa expected thành 0 chỉ để test xanh.

Nếu test rollback fail expected 0 nhưng actual 1, xem có:

- Transaction bị commit vì `@Commit`/`@Rollback(false)` ở class/method hoặc meta-annotation.
- Code dùng `REQUIRES_NEW` trong service, commit độc lập.
- Repository/transaction manager khác DataSource mà `JdbcTemplate` đọc.
- Lệnh SQL viết trực tiếp trên connection autocommit ngoài Spring test transaction.
- Method test chạy trên thread khác do preemptive timeout hoặc async logic.

Chẩn đoán nên bắt đầu bằng **transaction boundary** và **đúng data source**, không chỉ stack trace của một assertion.

## 7. `@Commit` và `@Rollback` khác gì nhau?

Một transactional test mặc định rollback. Annotation của Spring có thể đổi cách hoàn tất:

~~~java
@Test
@Commit
void shouldCommitAtEnd() {
    // Commit test transaction khi test kết thúc.
}
~~~

~~~java
@Test
@Rollback(false)
void shouldAlsoCommitAtEnd() {
    // Về kết quả cuối, tương đương @Commit.
}
~~~

~~~java
@Test
@Rollback
void shouldRollBackAtEnd() {
    // Rollback rõ ràng, kể cả khi class đặt @Commit.
}
~~~

Các ví dụ là snippets method, không phải standalone classes. `@Commit` là annotation convenience mang ý nghĩa `@Rollback(false)`. Khi cả class có `@Commit` và method có `@Rollback`, cấu hình cụ thể của method có thể override ở mức phù hợp.

**Đừng dùng `@Transactional(rollbackFor = ... )` trên test và kỳ vọng listener tôn trọng giống service AOP.** Theo Spring TestContext, những thuộc tính như `rollbackFor/noRollbackFor`, `isolation`, `timeout` của `@Transactional` **không phải cơ chế được hỗ trợ** để điều khiển test-managed transaction giống service transaction. Dùng `@Commit`, `@Rollback` hoặc `TestTransaction.flagForCommit()/flagForRollback()`.

### Dữ liệu commit có thể làm bẩn suite

Nếu đặt `@Commit` lên test dùng database chung mà không cleanup, row sẽ còn sau test. Bài demo khắc phục bằng `@AfterTransaction` kết hợp marker. Trên môi trường production-like, nên:

- Dùng database/schema test riêng hoặc Testcontainers.
- Theo dõi resource IDs/test-run keys.
- Xóa chỉ dữ liệu test tạo trong transaction cleanup được commit.
- Không dùng `deleteAll()` toàn hệ thống trong DB dùng chung.
- Có teardown ở tầng hạ tầng khi JVM bị kill trước `@AfterTransaction`.

## 8. `@AfterEach` cleanup có thể bị rollback theo test

Mẫu dễ gây nhầm:

~~~java
@AfterEach
void cleanup() {
    repository.deleteAll();
}
~~~

Nếu class là transactional test, `@AfterEach` thường **vẫn nằm trong test transaction**. Mệnh lệnh DELETE có thể được đưa vào transaction rồi rollback cùng test. Với data được commit **từ giao dịch khác**, DELETE ấy có thể không thực sự xóa record đã commit.

Với dữ liệu được tạo và rollback bởi **chính test transaction**, thường không cần cleanup riêng. Nhưng với `@Commit` hoặc các giao dịch độc lập, cleanup cần **thật sự commit**. `@AfterTransaction` là một vị trí hợp lý để quan sát và dọn state **sau** test transaction.

### Khác biệt giữa cleanup và assertion

Một test không nên chỉ viết:

~~~java
@AfterTransaction
void cleanup() {
    repository.deleteAll();
}
~~~

Cách này có nguy cơ xóa dữ liệu test khác, đồng thời không biết commit/rollback đã đúng chưa. Tốt hơn:

1. Tạo marker trước test.
2. Biết **expected outcome** (commit hay rollback).
3. Đọc trạng thái thực tế từ database sau transaction.
4. Assert expected outcome.
5. Cleanup đúng marker, **ngay cả khi assertion fail bình thường**.
6. Kiểm cleanup thành công hoặc báo lỗi nếu không.

Project runnable làm đủ các bước này. Nó không dùng `repository.deleteAll()`, không sửa schema/table khác, và không cần port HTTP.

## 9. `TestTransaction` cho phép điều khiển transaction ngay trong test

Spring cung cấp `org.springframework.test.context.transaction.TestTransaction` để tương tác với test-managed transaction:

- `TestTransaction.isActive()`: có transaction đang được TestContext quản lý trên thread không?
- `TestTransaction.flagForCommit()`: yêu cầu transaction hiện tại commit khi được kết thúc.
- `TestTransaction.flagForRollback()`: yêu cầu rollback khi kết thúc.
- `TestTransaction.end()`: kết thúc transaction test hiện tại theo rollback/commit flag.
- `TestTransaction.start()`: bắt đầu một test-managed transaction mới khi lifecycle/test context cho phép.

Ví dụ minh họa bên trong transactional JUnit method:

~~~java
@Test
void commitsMidTestThenStartsNewTransaction() {
    repository.saveAndFlush(new TxProbeNote(testKey, "first"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    // Quan sát dữ liệu đã commit từ connection mới.
    assertEquals(1, countCommittedRows());

    TestTransaction.start();
    assertTrue(TestTransaction.isActive());

    // Các thao tác mới trong transaction này mặc định rollback
    // nếu được đặt rollback flag tương ứng.
    TestTransaction.flagForRollback();
}
~~~

Đây là **snippet nâng cao**, không được thêm vào class runnable để giữ ví dụ chính đơn giản. Nó giả định `repository`, `testKey` và `countCommittedRows()` của project. Khi dùng `TestTransaction.end()` sớm, phải theo dõi hook lifecycle, state của test transaction và cleanup cẩn thận; đừng gọi `start()` hoặc `end()` tùy tiện khi transaction không active.

### `TestTransaction` không tương đương `TransactionTemplate`

- `TestTransaction` làm việc với **test-managed transaction** do Spring TestContext quản lý.
- `TransactionTemplate` chủ động thực thi một callback với transaction manager; có thể mở/suspend transaction khác tùy propagation.
- `@BeforeTransaction`/`@AfterTransaction` là **callbacks trước/sau transaction của test method**, không phải callbacks mỗi lần `TransactionTemplate.execute(...)` chạy.

Vì vậy gọi `TransactionTemplate.executeWithoutResult(...)` trong một JUnit test **không tự làm** `@BeforeTransaction`/`@AfterTransaction` chạy quanh mỗi callback. Hook chỉ gắn với lifecycle của transactional test method do listener quản lý.

## 10. Khi một method test không có transaction

Giả sử class có `@Transactional`, nhưng một method muốn không tham gia test-managed transaction:

~~~java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void worksWithoutTestTransaction() {
    // Không có test-managed transaction.
}
~~~

Đây là snippet Java với imports Spring transaction phù hợp. Với method này, `@BeforeTransaction`/`@AfterTransaction` **không được gọi** vì Spring không bắt đầu test-managed transaction cho method đó. Nếu một test không hề đánh dấu `@Transactional`, hai callback cũng không tự chạy.

Điều này quan trọng khi dùng `@SpringBootTest` mà người viết chỉ gắn `@Transactional` lên **service**. Mặc dù service method có giao dịch, JUnit test method có thể **không phải transactional test**; hai hook Spring TestContext sẽ không bao quanh giao dịch service.

### Những phương thức trong class hỗn hợp

Nếu trong cùng class có một số methods transactional và một số không:

- Hooks chạy cho các methods có test-managed transaction.
- Hooks bỏ qua methods không có test-managed transaction.
- `@BeforeEach`/`@AfterEach` vẫn theo lifecycle JUnit cho từng test method.
- Assertions gọi `TestTransaction.isActive()` trong `@BeforeEach` nên phản ánh đúng method; đừng hardcode luôn `true` cho cả class nếu có method `NOT_SUPPORTED`.

Bài runnable giữ cả ba methods transactional bằng `@DataJpaTest` để ý nghĩa lifecycle nhất quán và dễ theo dõi.

## 11. Repository và `REQUIRES_NEW`: trường hợp rollback không xóa hết

Một service có thể tách transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(String testKey) {
    auditRepository.save(new AuditEvent(testKey));
}
~~~

Đây là snippet lý thuyết; cần class/field/imports. `REQUIRES_NEW` có thể **suspend transaction hiện tại** và tạo transaction khác, độc lập với test transaction.

Nếu test default rollback gọi `writeAudit(...)` qua một Spring proxy thật, audit row có thể **đã commit** trước khi test transaction rollback. `@AfterTransaction` có thể thấy audit row còn tồn tại, dù test method không có `@Commit`.

Điều này không phải bug của callback. Nó phản ánh:

- Transaction service độc lập với test transaction;
- Commit của transaction B không bị rollback của A hoàn tác;
- Có thể có constraint/lock contention nếu A và B cùng thao tác các row liên quan;
- Có thể cạn connection pool nếu test giữ connection A và `REQUIRES_NEW` cần connection B.

**Quan trọng:** `@Transactional` trên một method nội bộ được gọi bằng `this.method()` trong cùng object có thể không đi qua Spring AOP proxy, vì vậy `REQUIRES_NEW` có thể không thực sự được áp dụng. Test cần kiểm wiring/proxy thật khi propagation là contract.

### Cleanup cho `REQUIRES_NEW`

Nếu service ghi audit trong transaction riêng, test fixture cần theo dõi audit IDs/test key và dọn sau test trong transaction được commit. Không giả định “test đang @Transactional nên mọi bảng sẽ tự sạch”. `@AfterTransaction` là nơi có thể kiểm state cuối, nhưng teardown ở DB/container riêng cũng có thể cần nếu có nhiều side effects.

## 12. HTTP test có transaction khác

Khi dùng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpIntegrationTest {
    // TestRestTemplate/WebTestClient gửi HTTP tới server.
}
~~~

Snippet minh họa, không phải source runnable. HTTP client trên test thread gửi request qua socket; controller/service chạy trên **server thread** và thường mở một transaction khác. Rollback test-managed transaction chỉ ảnh hưởng giao dịch của test thread, **không tự rollback transaction đã commit trên server**.

Do đó:

- `@BeforeTransaction` không phải hook “trước mỗi HTTP server transaction”.
- `@AfterTransaction` không phải hook “sau mọi HTTP request”.
- Nó chỉ chạy ở boundary của **test-managed transaction**.
- Dữ liệu server đã commit có thể tồn tại cả sau khi test rollback.
- Cleanup qua repository/API ở transaction ngoài test hoặc database/schema container riêng thường là cần thiết.

Để chứng minh **HTTP API thực sự commit**, dùng `RANDOM_PORT`, request HTTP, rồi GET hoặc query DB từ connection/transaction khác. Để chứng minh **lifecycle của test transaction**, project JPA slice trong bài này là đủ và nhanh hơn.

## 13. `@Sql` và những mức chuẩn bị dữ liệu khác

Spring TestContext có `@Sql` để chạy scripts trước/sau test method. Nó có thể là lựa chọn tốt khi fixture là dữ liệu SQL tĩnh; trong khi `@BeforeTransaction`/`@AfterTransaction` là lifecycle hooks thích hợp cho **Java logic** cần quan sát DB trước/sau transaction.

Ví dụ minh họa:

~~~java
@Sql(
    scripts = "/sql/seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Transactional
@Test
void readsSeedData() {
    // ...
}
~~~

Đây không phải project runnable vì chưa có `seed.sql`, imports hoặc table mapping tương ứng.

Điểm cần quan tâm là **transaction mode** của `@Sql`. Nếu một script cleanup được chạy **trong transaction cuối cùng sẽ rollback**, script ấy không dọn được data server đã commit. Khi cần SQL cleanup commit riêng, có thể cấu hình `SqlConfig.TransactionMode.ISOLATED` phù hợp với datasource/transaction manager và phạm vi dữ liệu.

Không coi `@Sql(AFTER_TEST_METHOD)` luôn tương đương `@AfterTransaction` cho mọi cấu hình; listener ordering và transaction mode của `@Sql` có thể khác. Khi yêu cầu là **assert trạng thái sau rollback/commit**, `@AfterTransaction` diễn đạt trực tiếp hơn.

### Vì sao `@BeforeTransaction` không phải @BeforeAll?

`@BeforeAll` chạy một lần trước tất cả test methods của class (theo JUnit instance lifecycle), còn `@BeforeTransaction` được gọi **cho từng transactional test method**. Do đó:

- Baseline theo từng case → `@BeforeTransaction`.
- Khởi tạo resource dùng chung cho class → `@BeforeAll` hoặc test infrastructure phù hợp.
- Fixture nằm trong transaction sẽ rollback → `@BeforeEach`.
- Cleanup data đã commit theo marker của case → `@AfterTransaction`.
- Teardown external container ở cuối class/suite → lifecycle cấp class/infrastructure.

## 14. Tránh false positives do JPA persistence context

Trong JPA, test thường có một `EntityManager`/Hibernate persistence context gắn với transaction. Nếu gọi `repository.save(entity)` và assert trên object vừa save, test chưa chắc đã kiểm database constraint hoặc SQL đã thực thi.

Ví dụ:

~~~java
repository.save(new TxProbeNote(testKey, "sample"));
// Đọc thuộc tính của object Java không phải bằng chứng INSERT.
~~~

Một lỗi `NOT NULL`, unique constraint hoặc data truncation có thể chỉ bị phát hiện lúc `flush/commit`. Vì vậy khi kiểm ORM/database behavior, dùng `saveAndFlush` hoặc `entityManager.flush()` tại bước thích hợp.

Trong project:

~~~java
repository.saveAndFlush(
    new TxProbeNote(testKey, "rollback"));
~~~

SQL đã được gửi xuống H2, nhưng rollback ở cuối test vẫn xóa tác dụng của transaction. `@AfterTransaction` sử dụng `JdbcTemplate` ở ngoài transaction để kiểm dữ liệu cuối.

### Query ở ngoài transaction cũng có thể bị ảnh hưởng bởi caching/routing

- Nếu dùng read replica có lag, query sau commit có thể chưa thấy row ngay.
- Nếu DataSource dùng routing theo tenant, hook phải đọc đúng tenant/schema.
- Với JPA EntityManager vẫn giữ managed entities, `repository.findById` trong cùng persistence context có thể trả cache.
- `JdbcTemplate` truy vấn DB trực tiếp hơn nhưng vẫn có thể đi qua proxy/routing DataSource.
- Với DB transaction isolation `REPEATABLE_READ`, một transaction khác đã mở snapshot cũ có thể không thấy commit mới.

Bài demo tránh các tình huống này bằng một H2 primary in-memory và query JDBC sau khi test transaction hoàn tất. Khi production có replication hoặc eventual consistency, test cần phù hợp với contract thay vì chờ một giả định không được bảo đảm.

## 15. Preemptive timeout có thể thoát khỏi test transaction

Spring TestContext gắn transaction state với **thread hiện tại**. Nếu JUnit hoặc framework timeout chạy body test trên **thread khác**, các thao tác trong body có thể không tham gia test-managed transaction dù hook vẫn quan sát transaction của thread gốc.

Một mẫu nguy hiểm:

~~~java
@Test
@Transactional
void writeWithPreemptiveTimeout() {
    assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> repository.save(new TxProbeNote("x", "y")));
}
~~~

Đây là snippet minh họa, cần imports và repository; **không khuyến nghị** dùng với real database viết dữ liệu. `assertTimeoutPreemptively` chạy đoạn code trong thread khác, có nguy cơ transaction không lan theo thread, row **được commit** và vẫn tồn tại sau rollback test thread.

Spring Framework cũng cảnh báo tương tự với các loại preemptive timeout khác chạy test body trên thread mới. Với transactional tests, ưu tiên timeout không chuyển thread hoặc kiểm soát transaction/cleanup rõ ràng. Nếu dùng async/reactive code, cần hiểu cơ chế truyền context/transaction riêng, không mặc định thread-bound transaction bao phủ mọi scheduler.

### `assertTimeout` và `assertTimeoutPreemptively`

Hai API JUnit có ngữ nghĩa khác nhau. `assertTimeout` (không preemptive) thực thi phần code ở cùng thread gọi trong trường hợp thông dụng, còn `assertTimeoutPreemptively` có thể thực thi ở thread riêng. Khi test có JDBC/JPA test-managed transaction, khác biệt này có thể quyết định một row có bị rollback hay không.

## 16. Nhiều transaction managers và @Transactional qualifier

Trong ứng dụng có một DataSource duy nhất, `PlatformTransactionManager` thường được auto-configured phù hợp. Nhưng có nhiều nguồn dữ liệu, cần biết **transaction manager nào** mà TestContext đang chọn.

Ví dụ:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
@Test
void orderRepositoryTest() {
    // ...
}
~~~

Snippet minh họa, cần bean với tên phù hợp. Một `@BeforeTransaction` query tới audit DB trong khi test transaction quản lý orders DB sẽ thấy behavior khác; không được kết luận rollback của orders có thể xóa dữ liệu audit.

Để test chính xác:

1. Xác định `@Transactional` của method/class chỉ định manager nào.
2. Xác minh repository hoặc `JdbcTemplate` inject DataSource tương ứng.
3. Nếu có nhiều managers, dùng qualifier hoặc `TransactionManagementConfigurer` theo cơ chế Spring hỗ trợ.
4. Kiểm dữ liệu trước/sau bằng đúng DB/schema.
5. Khi service dùng transaction manager khác, coi nó là transaction độc lập có thể cần cleanup riêng.

### `@BeforeTransaction` có thể chạy khi chưa có Spring tx nhưng service sẽ tạo tx riêng

Đó là một behavior hợp lệ: callback chỉ thông báo **test transaction** chưa active. Nó **không chứng minh không có transaction nào ở DB** (ví dụ transaction do service riêng hoặc JDBC connection khác đang chạy). Tránh hiểu `TestTransaction.isActive() == false` như “toàn hệ thống không có giao dịch”.

## 17. So sánh với các giải pháp khác

| Mục tiêu | Công cụ phù hợp | Ghi chú |
| --- | --- | --- |
| Kiểm baseline trước test tx | `@BeforeTransaction` | Ngoài test tx, chạy per transactional method |
| Setup fixture nằm trong test tx | `@BeforeEach` | Rollback cùng test mặc định |
| Kiểm trạng thái trong test tx | JUnit `@Test` hoặc `@AfterEach` | Chưa có commit/rollback cuối method |
| Kiểm DB sau test tx | `@AfterTransaction` | Ngoài test tx, quan sát commit/rollback |
| Commit thay vì rollback cuối test | `@Commit` / `@Rollback(false)` | Cần cleanup committed data |
| Điều khiển commit/end ngay giữa test | `TestTransaction` | Dành cho nâng cao, theo lifecycle của test tx |
| Transaction độc lập trong Java callback | `TransactionTemplate` | Không phải TestContext lifecycle hook |
| Fixture SQL tĩnh theo lifecycle | `@Sql` và transaction mode | Cẩn thận ISOLATED và phạm vi script |
| Test JPA repository nhanh | `@DataJpaTest` | Transactional, rollback mặc định |
| Test JDBC query nhanh | `@JdbcTest` | Transactional, rollback mặc định |
| Test full bean graph/config | `@SpringBootTest` | Không tự transactional nếu thiếu annotation |
| Kiểm commit qua HTTP server thật | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Server tx riêng; cleanup chủ động |
| Dọn state của external DB test | Cleanup scoped + transaction được commit | Hoặc tách DB/schema/container |

## 18. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@BeforeTransaction` không chạy | Test không transactional hoặc không có TestContext listener | Kiểm `@Transactional`, `@DataJpaTest`, TestContext |
| `@AfterTransaction` không chạy | Không có test-managed transaction hoặc propagation `NOT_SUPPORTED/NEVER` | Test riêng hoặc bật transaction |
| `@AfterEach` thấy row dù test rollback | `@AfterEach` vẫn chạy trong transaction | Kiểm kết quả cuối bằng `@AfterTransaction` |
| Row vẫn tồn tại sau test default rollback | Data được commit ở tx độc lập/HTTP/thread khác | Vẽ transaction boundary, cleanup riêng |
| `@AfterTransaction` query thấy 0 dù test `@Commit` | @Rollback override, sai DB/manager hoặc cleanup sớm | Kiểm annotations, qualifiers, DataSource |
| `@AfterTransaction` thấy 1 với default rollback | `REQUIRES_NEW` hoặc auto-commit write độc lập | Kiểm propagation, proxy và side effects |
| Test pass dù DB constraint sai | `save` chưa flush | Dùng `saveAndFlush`/`entityManager.flush` |
| `@BeforeTransaction` ném table not found | Schema test/migration chưa sẵn sàng | Chạy migrations/DDL đúng trước test lifecycle |
| `@Commit` khiến suite có data rác | Thiếu cleanup sau commit | Cleanup theo test key/ID ở `@AfterTransaction` |
| Cleanup `@AfterEach` không xóa committed row | Cleanup nằm trong transaction sẽ rollback | Dọn sau transaction hoặc transaction mới thực sự commit |
| `TestTransaction.isActive()` luôn false | Test thiếu @Transactional hoặc chạy body thread khác | Kiểm TestContext và timeout kiểu preemptive |
| `TestTransaction.end()` báo transaction không active | Gọi khi không có test tx | Kiểm `isActive`/lifecycle trước khi end |
| DataSource query trong hook khác repository | Multi-DataSource hoặc tenant routing sai | Dùng đúng qualifier/schema/manager |
| `@AfterTransaction` gây lỗi khi cleanup | DELETE sai table/column hoặc DB unavailable | Kiểm schema, log sanitized, báo lỗi cleanup |
| Dùng `deleteAll()` xóa dữ liệu test khác | Cleanup quá rộng trong DB chia sẻ | Filter bằng test key/resource IDs |
| Test H2 pass nhưng Postgres fail | Dialect, isolation, DDL, locking khác | Testcontainers trên engine production |
| Lỗi connection pool timeout | Test giữ transaction/connection trong lúc mở tx khác | Tránh nested REQUIRES_NEW vô ý, pool config |
| Hooks chạy nhiều lần hơn mong đợi | Mỗi transactional method có cặp callback | Phân biệt lifecycle per-method và per-class |
| Hook có parameter nhưng không resolve | JUnit extension/version không phù hợp | Dùng field injection hoặc Spring Framework 6.1+ |
| Test @SpringBootTest không tự rollback | @SpringBootTest không tự là @Transactional | Đánh dấu test transaction nếu cần, hoặc cleanup |
| Event/cache/file còn sau rollback | Side effect nằm ngoài JDBC tx | Cleanup/compensation cho từng resource |

### Quy trình đọc lỗi

1. Xem annotation của test method/class: có test-managed transaction thật không?
2. Kiểm `@Commit`/`@Rollback` và các annotation override.
3. Đặt assertions về `TestTransaction.isActive()` tại đúng hook để chứng minh boundary.
4. Kiểm `saveAndFlush` đã gửi SQL xuống DB nhưng **chưa** commit.
5. Trong `@AfterTransaction`, query đúng DataSource, đúng marker, đúng schema.
6. Kiểm `REQUIRES_NEW`, HTTP request, async hoặc preemptive timeout.
7. Kiểm cleanup có thật sự được commit, không bị rollback theo test.
8. Nếu có nhiều DB managers, chọn đúng bean và qualifier.
9. Nếu chạy trên test DB thật, xác minh tenant/fixture/replica lag.
10. Không sửa expected thành kết quả thực tế chỉ để giữ test xanh; đối chiếu contract.

## 19. Bài tập tự luyện

**Bài A — thứ tự lifecycle:** Vẽ sơ đồ cho 5 annotation `@BeforeTransaction`, `@BeforeEach`, `@Test`, `@AfterEach`, `@AfterTransaction`. Ghi rõ điểm BEGIN và ROLLBACK/COMMIT.

**Bài B — default rollback:** Chạy `defaultRollbackDiscardsTheInsertedRow`. Tạm đổi expected `0` thành `1` trong điều kiện rollback để kiểm test đỏ rồi hoàn nguyên.

**Bài C — @Commit:** Chạy `commitMakesTheRowVisibleAfterTransaction`. Bỏ `@Commit` và quan sát assertion trong `@AfterTransaction` fail vì expected 1 nhưng database còn 0. Khôi phục annotation.

**Bài D — @Rollback(false):** Thử thay `@Rollback(false)` bằng `@Rollback` trên test thứ ba và mô tả lý do phải thay expectation, nếu đây là hành vi chủ ý.

**Bài E — cleanup:** Bỏ câu `DELETE FROM tx_probe_notes WHERE test_key = ?` trong một nhánh test DB cô lập và chạy lại. Quan sát record commit còn lại; đưa cleanup scoped trở lại.

**Bài F — @AfterEach:** Chuyển assertion `actualCommittedRows` vào `@AfterEach`, phân tích tại sao nó không chứng minh dữ liệu sau commit/rollback.

**Bài G — TestTransaction:** Trong một transactional test độc lập, gọi `flagForCommit()` và `end()`, query database trước khi `start()` một giao dịch mới. Đảm bảo cleanup cuối test và không làm hỏng lifecycle.

**Bài H — không có test transaction:** Tạo test class `@SpringBootTest` không `@Transactional`. Gắn `@BeforeTransaction`/`@AfterTransaction` rồi quan sát chúng không chạy, dù JUnit `@BeforeEach` vẫn chạy.

**Bài I — propagation:** Viết một service `REQUIRES_NEW` tạo audit row trên DB test. Gọi từ transactional test rollback mặc định, xác minh audit có thể còn sau rollback và thiết kế cleanup riêng.

**Bài J — preemptive timeout:** So sánh `assertTimeout` và `assertTimeoutPreemptively` trong test JDBC có ghi dữ liệu; giải thích nguy cơ thoát transaction do thread khác. Chỉ thử trên DB riêng.

**Bài K — Testcontainers:** Thay H2 bằng PostgreSQL Testcontainers, chạy migration test schema, thực hiện commit/rollback tests và kiểm metadata engine trước khi cleanup.

**Bài L — đa DataSource:** Dùng orders và audit DataSource khác nhau. Chỉ rõ `@Transactional(transactionManager=...)` và truy vấn đúng DB ở `@AfterTransaction`.

## 20. Checklist kiểm thử transaction hooks

- [ ] Tôi biết test đang dùng `@DataJpaTest`, `@JdbcTest` hay `@SpringBootTest` và có test-managed transaction?
- [ ] `TransactionalTestExecutionListener`/`PlatformTransactionManager` đã sẵn sàng?
- [ ] Tôi phân biệt `@BeforeTransaction`/`@AfterTransaction` với JUnit `@BeforeEach`/`@AfterEach`?
- [ ] Tôi biết `@BeforeTransaction` xảy ra trước BEGIN và `@AfterTransaction` sau COMMIT/ROLLBACK?
- [ ] Tôi không nhầm `@AfterEach` với thời điểm sau rollback?
- [ ] Tôi chỉ dùng hooks cho transactional tests; không kỳ vọng chúng chạy khi propagation `NOT_SUPPORTED/NEVER`?
- [ ] Tôi đặt `@Commit`/`@Rollback` đúng phạm vi và không dùng `rollbackFor` để điều khiển test tx?
- [ ] Với JPA, tôi đã `flush` khi muốn kiểm SQL/constraints?
- [ ] Tôi đọc database sau transaction bằng connection/transaction phù hợp và đúng test key?
- [ ] Tôi dọn dữ liệu commit bằng transaction thực sự được commit, không dùng cleanup toàn bảng?
- [ ] Tôi hiểu transaction service `REQUIRES_NEW` hoặc HTTP server có thể độc lập với test tx?
- [ ] Tôi không dùng preemptive timeout làm test DB thoát khỏi transaction-bound thread?
- [ ] Nếu có nhiều transaction managers, hooks và queries dùng đúng DataSource?
- [ ] Test không phụ thuộc thứ tự và không giữ state đã commit giữa các methods?
- [ ] Database test có credentials/schema cô lập, không chạm production?
- [ ] Test outcomes/assertions đọc lại đúng expected chứ không chỉ xanh vì cùng persistence context?
- [ ] Gradle/JUnit report cho biết test thực sự đã chạy, không chỉ `UP-TO-DATE`?

## 21. Tham khảo chính thức

- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction, lifecycle, các hook, programmatic `TestTransaction`, timeout và flush.
- [Spring Framework — @BeforeTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html): thời điểm callback trước transaction.
- [Spring Framework — @AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-aftertransaction.html): thời điểm callback sau transaction.
- [Spring Framework 6.1 — AfterTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): void method, JUnit parameter resolution.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `isActive`, `flagForCommit`, `end`, `start`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest` và default rollback.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): repository transaction semantics.
- [JUnit Jupiter — Lifecycle Methods](https://docs.junit.org/5.10.2/user-guide/#writing-tests-annotations): `@BeforeEach`, `@AfterEach`, test lifecycle.

**Ghi nhớ:** `@BeforeTransaction` kiểm **trạng thái trước khi test transaction mở**, `@AfterTransaction` kiểm **trạng thái khi test transaction đã commit/rollback**. `@BeforeEach` và `@AfterEach` ở **bên trong** transaction cho transactional tests. Dùng đúng callback, flush đúng lúc, định nghĩa commit/rollback expectation và cleanup scoped sẽ giúp kiểm chứng giao dịch thật thay vì chỉ kiểm dữ liệu tạm thời trong một persistence context.
