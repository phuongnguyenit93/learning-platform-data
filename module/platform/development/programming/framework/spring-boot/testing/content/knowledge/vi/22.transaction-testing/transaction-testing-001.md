# Giao dịch kiểm thử: Test-managed transaction, transaction của ứng dụng và transaction của database

## 1. Tại sao @Transactional trên test dễ gây hiểu nhầm?

Một test Spring Boot gọi `orderService.save(...)`, truy vấn database thấy bản ghi vừa được thêm, toàn bộ assertion PASS. Thế nhưng khi test kết thúc thì bản ghi biến mất. Trong một test khác, bạn gọi HTTP thật tới `POST /orders` từ test cũng có `@Transactional`, nhưng bản ghi lại **không biến mất**. Hai kết quả này có thể hoàn toàn đúng, bởi **test-managed transaction**, **transaction do ứng dụng quản lý** và **transaction vật lý do database thực hiện** có ranh giới khác nhau.

Bài này tập trung vào đúng ba cơ chế:

- **Test-managed transaction:** do Spring TestContext mở trước test method và **rollback mặc định** sau test.
- **Spring/application transaction:** do service `@Transactional`/proxy hoặc `TransactionTemplate` yêu cầu. Nó có thể tham gia transaction sẵn có hoặc tự mở/commit/rollback.
- **Database transaction:** được DB/driver thực hiện qua connection, isolation, locks, `COMMIT`, `ROLLBACK` và savepoint. Một transaction ứng dụng không có nghĩa là một “database giả”.

Không có mặc định “ba lớp = ba transaction khác nhau”. Khi test và service dùng cùng transaction manager, cùng thread và propagation `REQUIRED`, chúng thường cùng dùng **một transaction vật lý**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Xác định **ai mở, ai sở hữu commit/rollback** trong các test `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest`.
2. Giải thích `@Transactional` trên test khác `@Transactional` trên service ở đâu.
3. Biết khi nào `REQUIRED` tham gia transaction test và khi nào `REQUIRES_NEW` commit riêng.
4. Dùng `@BeforeTransaction`, `@AfterTransaction`, `TestTransaction`, `@Commit`, `@Rollback`.
5. Test checked/unchecked exception rollback rules mà không bị transaction test che mất.
6. Chứng minh request HTTP qua `RANDOM_PORT` không tự chia sẻ transaction của JUnit thread.
7. Phân biệt `flush()`, constraint enforcement, savepoint, rollback-only, database isolation và commit.
8. Viết integration tests lặp lại được, biết khi nào phải cleanup thay vì trông cậy rollback.
9. Tránh lỗi `assertTimeoutPreemptively`, self-invocation, `@Async`, reactive context và DB transactions khác nhau.
10. Chọn đúng test để chứng minh behavior thật của application thay vì chỉ kiểm code trong “transaction do test cấp”.

## 2. Sơ đồ ba tầng transaction

~~~text
JUnit Jupiter test thread
      |
      v
Spring TransactionalTestExecutionListener
      |        @Transactional test => BEGIN test-managed TX
      |        JDBC connection A được gắn với test thread
      v
@Test method
      |
      +----> Spring proxy OrderService.create() @Transactional(REQUIRED)
                   |
                   +-- TransactionInterceptor / PlatformTransactionManager
                   |      thấy transaction hiện tại
                   |      tham gia transaction trên connection A
                   |
                   +-- JdbcTemplate INSERT
                           |
                           v
                        Database
                           |
                           +-- row hiện diện trong TX A, CHƯA COMMIT
      |
      v
@Test kết thúc
      |
      +-- Spring TestContext rollback mặc định TX A
      |
      +-- row biến mất, dù service return bình thường
~~~

Thay `REQUIRED` bằng `REQUIRES_NEW`:

~~~text
Connection A: transaction của test (chưa commit)
      |
      +--- gọi bean khác, method @Transactional(REQUIRES_NEW)
                  |
                  +-- tạm suspend tài nguyên TX A
                  +-- lấy Connection B
                  +-- BEGIN TX B
                  +-- INSERT audit
                  +-- COMMIT TX B
                  +-- resume TX A
      |
      +--- TestContext ROLLBACK TX A

KẾT QUẢ: row của TX A mất; audit từ TX B vẫn còn.
~~~

Tình huống trên yêu cầu Spring proxy thực sự intercept lời gọi bean, transaction manager hỗ trợ propagation và connection pool đủ connections.

### Từ ngữ chính xác

Spring Framework có thể gọi:

- **Test-managed:** quản lý bởi `TransactionalTestExecutionListener` hoặc `TestTransaction`.
- **Spring-managed:** giao dịch do Spring quản lý trực tiếp trong application context, thường bằng `@Transactional`.
- **Application-managed:** ứng dụng dùng transaction manager theo chương trình, ví dụ `TransactionTemplate`.

Trong đề bài, “transaction của ứng dụng” bao gồm cả **transaction khai báo trên Spring service** lẫn **transaction do code ứng dụng điều khiển**. Cả hai đều có thể sử dụng `PlatformTransactionManager`. “Transaction của database” là **giao dịch vật lý thật**, không phải tên gọi khác của annotation.

## 3. Bảng so sánh

| Câu hỏi | Test-managed | Application/Spring-managed | Database transaction |
| --- | --- | --- | --- |
| Ai kích hoạt? | TestContext listener hoặc `TestTransaction` | Transactional proxy hoặc `TransactionTemplate` | Transaction manager/JDBC driver/DB session |
| Nơi cấu hình | `@Transactional` test, `@Rollback`/`@Commit` | `@Transactional` service, propagation, rollback rules | Connection, isolation, autocommit, constraints |
| Mặc định kết thúc | **Rollback sau test** | Commit khi success, rollback theo rules | Commit/rollback thực do caller điều khiển |
| Có thể dùng cùng physical TX? | Có | Có nếu REQUIRED tham gia | Chỉ một TX khi cùng connection |
| Có đi qua HTTP? | Không tự động | HTTP server thường tự mở TX riêng | Server connection độc lập |
| Điều chứng minh | Test code chạy trong TX và rollback theo TestContext | Business commit/rollback ở boundary thực | Visibility, constraints, locks, state durable |
| Có rollback mail/Kafka/file? | Không tự động | Không tự động | Không |
| Có rollback REQUIRES_NEW đã commit? | Không | Outer TX không rollback inner commit | Commit B độc lập với rollback A |

**Khi kiểm database:** luôn trả lời bốn câu: transaction manager nào, connection nào, thread nào, ai commit/rollback?

## 4. Test-managed transaction: cơ chế Spring TestContext

`TransactionalTestExecutionListener` được Spring TestContext đăng ký theo mặc định. Khi class/method test có Spring `@Transactional` và context có `PlatformTransactionManager` phù hợp, listener bắt đầu test-managed transaction trước test body, thường bind resource vào thread hiện tại, rồi rollback sau method.

Đây là lý do test sau không lưu dữ liệu lâu dài mặc dù SQL chạy thành công:

~~~java
@SpringBootTest
@Transactional
class ExampleTest {
    @Autowired OrderService service;

    @Test
    void create() {
        service.create("O-1");
        // Dữ liệu hiện diện bên trong transaction test.
    } // Spring TestContext rollback sau test
}
~~~

**Đoạn này là minh họa**: cần `OrderService` thật, datasource/transaction manager và imports. Không khẳng định phương thức service tự commit nếu đang tham gia outer transaction.

### 4.1 Vòng đời đầy đủ của test method

~~~text
Tạo ApplicationContext và inject dependencies
          |
          v
@BeforeTransaction         NGOÀI transaction
          |
          v
TestContext BEGIN transaction
          |
          v
JUnit Jupiter @BeforeEach  TRONG transaction
          |
          v
JUnit Jupiter @Test        TRONG transaction
          |
          v
JUnit Jupiter @AfterEach   TRONG transaction
          |
          v
TestContext ROLLBACK (mặc định) / COMMIT (khi được yêu cầu)
          |
          v
@AfterTransaction          NGOÀI transaction
~~~

`@BeforeTransaction` và `@AfterTransaction` chỉ chạy với **test method có test-managed transaction thực sự**. `@BeforeAll`/`@AfterAll` không nằm trong transaction của từng method. Đặt `@Transactional` trên riêng lifecycle method `@BeforeEach` không tạo một test-managed transaction mới cho riêng method đó.

### 4.2 Hỗ trợ thuộc tính @Transactional ở tầng test

| Attribute của @Transactional | Spring TestContext có dùng để quản lý test TX? |
| --- | --- |
| `value` hoặc `transactionManager` | Có, để chọn manager |
| `propagation=NOT_SUPPORTED` hoặc `NEVER` | Có, test sẽ **không** được bọc trong test-managed TX |
| `REQUIRED`/`REQUIRES_NEW`/`NESTED` và các propagation khác | Không áp dụng đầy đủ semantics của proxy-level propagation cho chính test |
| `isolation` | Không được TestContext hỗ trợ |
| `timeout` | Không được TestContext hỗ trợ |
| `readOnly` | Không được TestContext hỗ trợ |
| `rollbackFor`/`noRollbackFor` | Không dùng cho test rollback policy |

Thay vì `@Transactional(rollbackFor=...)` **trên test**, hãy dùng `@Rollback`, `@Commit` hoặc `TestTransaction.flagForRollback()/flagForCommit()`. Trong khi đó `rollbackFor` **trên Spring service** là cấu hình application transaction có hiệu lực khi transactional advice chạy.

## 5. @Rollback, @Commit và TestTransaction

Theo mặc định, Spring TestContext **rollback** transaction của test dù assertions PASS hoặc FAIL.

~~~java
@SpringBootTest
@Transactional
class ExampleTest {

    @Test
    void defaultRollback() {
        // rollback sau test
    }

    @Test
    @Commit
    void commitAfterTest() {
        // commit sau test; cần cleanup database
    }

    @Test
    @Rollback(false)
    void equivalentCommit() {
        // commit sau test
    }
}
~~~

Đây là **mẫu annotation, không phải project runnable độc lập**.

`TestTransaction` cung cấp API để điều khiển transaction **ngay trong test**:

~~~java
assertTrue(TestTransaction.isActive());

service.create("DEMO-1");

TestTransaction.flagForCommit();   // chỉ gắn cờ
TestTransaction.end();             // COMMIT thật tại đây
assertFalse(TestTransaction.isActive());

assertEquals(1, countRows("DEMO-1")); // đọc ngoài test TX

// Có thể TestTransaction.start() để mở test-managed TX mới.
~~~

Đây là đoạn minh họa nằm trong một test đã cấu hình Spring transaction và các helpers. Nếu bạn commit thật mà không cleanup, bản ghi vẫn còn cho test tiếp theo.

**Phân biệt:** `TestTransaction` là API của Spring TestContext; `TransactionTemplate` là API transaction chương trình của ứng dụng. `TestTransaction.flagForCommit()` không tự chạy SQL COMMIT cho tới khi transaction kết thúc.

## 6. Service @Transactional và propagation

Các propagation modes quan trọng:

| Propagation | Nếu test TX đã tồn tại | Kết quả cần chú ý |
| --- | --- | --- |
| `REQUIRED` | Tham gia TX test | Test rollback hủy cả writes từ service |
| `SUPPORTS` | Tham gia nếu có | Test có TX có thể che behavior ngoài production |
| `MANDATORY` | Thành công vì test có TX | Production caller không có TX sẽ bị từ chối |
| `REQUIRES_NEW` | Suspend TX test, mở TX độc lập | Commit inner vẫn tồn tại sau test rollback |
| `NESTED` | Thường dùng savepoint cùng physical TX | Không commit độc lập như REQUIRES_NEW |
| `NOT_SUPPORTED` | Suspend TX test, chạy không TX Spring | JDBC auto-commit có thể giữ writes |
| `NEVER` | Báo lỗi nếu có TX | Test-level @Transactional khiến method bị từ chối |

`REQUIRES_NEW` thường cần thêm connection; nếu outer TX giữ một connection và pool tối đa chỉ có một, inner TX có thể đợi tới timeout. Spring khuyến nghị pool size vượt số lượng concurrent threads ít nhất một connection nếu thiết kế dùng `REQUIRES_NEW`.

### 6.1 REQUIRED và UnexpectedRollbackException

Một inner service `@Transactional(REQUIRED)` ném unchecked exception qua proxy có thể đánh dấu transaction chung `rollback-only`. Outer service bắt exception Java không có nghĩa transaction có thể commit:

~~~java
@Transactional
public void outer() {
    try {
        collaborator.writeAndFail(); // @Transactional(REQUIRED)
    } catch (RuntimeException ex) {
        // Caught, nhưng physical TX có thể đã bị mark rollback-only.
    }
    // Khi outer cố commit, có thể nhận UnexpectedRollbackException.
}
~~~

Đây là ví dụ giải thích (cần collaborator). Khi thiết kế partial failure, dùng savepoint/`NESTED` hoặc transaction độc lập nếu semantics business cho phép, thay vì tùy tiện bỏ exception.

### 6.2 REQUIRES_NEW khác NESTED

**REQUIRES_NEW** mở physical transaction độc lập, có commit/isolation/locks/connection riêng. **NESTED** thường đặt savepoint bên trong một physical transaction; rollback tới savepoint không chấm dứt outer transaction, nhưng outer rollback vẫn hủy mọi writes của nested scope.

Không dùng REQUIRES_NEW chỉ để “đỡ lỗi test”: nếu audit transaction đã commit còn order transaction rollback, audit phải được thiết kế theo ý nghĩa đúng (ví dụ ghi lại attempt, không phải đã hoàn tất).

## 7. Checked exception, runtime exception và rollback rules

Spring `@Transactional` thông thường (với mặc định của Spring Framework 6.2):

- `RuntimeException` hoặc `Error` đi ra khỏi transactional proxy → rollback.
- Checked exception như `IOException` → **không rollback theo mặc định**.
- Có thể dùng `@Transactional(rollbackFor = IOException.class)` khi domain rule cần rollback.
- Transaction đã bị đánh dấu rollback-only thì outer method return bình thường cũng không đảm bảo commit.

~~~java
@Transactional
public void afterUnchecked() {
    insert();
    throw new IllegalStateException("fail");   // rollback
}

@Transactional
public void afterChecked() throws IOException {
    insert();
    throw new IOException("checked");            // mặc định commit
}

@Transactional(rollbackFor = IOException.class)
public void afterCheckedWithRollback() throws IOException {
    insert();
    throw new IOException("checked");            // rollback
}
~~~

Ba method là mẫu trong service đã có `insert()`. **Cần kiểm từ ngoài application transaction**, không đặt test-level @Transactional rồi kết luận chính service đã commit/rollback.

## 8. Physical database transaction, connection và isolation

Transaction thực sự diễn ra trên connection/session:

~~~text
Connection A: BEGIN
  INSERT order O-1
  SELECT O-1     -> thấy row của chính transaction
Connection B: SELECT O-1 -> có thể KHÔNG thấy (READ COMMITTED)
Connection A: ROLLBACK
Connection B: SELECT O-1 -> không thấy

Trường hợp COMMIT:
Connection A: BEGIN -> INSERT -> COMMIT
Connection B: SELECT O-1 -> thấy row đã commit
~~~

`JdbcTemplate` sử dụng cơ chế lấy connection có nhận biết transaction của Spring; khi cùng thread và cùng transaction manager, nhiều lời gọi JDBC có thể chia sẻ connection/transaction.

**Chú ý:**

- JDBC bên ngoài Spring TX thường chạy auto-commit. Gọi `JdbcTemplate.update` không có transaction bao ngoài có thể commit statement ngay.
- Read-your-writes **không phải** bằng chứng commit. Query ngay trong test transaction có thể thấy dữ liệu chưa commit.
- Isolation cấp DB (READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE…) có semantics khác nhau giữa PostgreSQL, MySQL và H2.
- DB constraints/trigger/DDL có thể thực thi tại thời điểm SQL/flush hoặc tại commit, tùy tính năng.
- Rollback DB không đảo ngược email đã gửi, HTTP payment đã gọi hay file đã ghi.
- Với PostgreSQL, sau lỗi SQL trong transaction, câu lệnh sau có thể nhận SQLSTATE `25P02` cho tới khi rollback. H2 không mô phỏng đầy đủ hành vi này.

### 8.1 Flush khác commit

Với JPA/Hibernate:

~~~text
repository.save(entity) -> entity được quản lý trong persistence context
entityManager.flush()   -> đẩy pending SQL tới DB trong transaction
entityManager.clear()   -> bỏ cache/managed entities ở persistence context
transaction.commit()    -> commit physical transaction
~~~

`flush()` thường cần để phát hiện SQL/unique constraint sớm và tránh false positive, nhưng **flush không phải commit**. Sau flush, Spring TestContext vẫn có thể rollback.

Ví dụ minh họa trong `@DataJpaTest`:

~~~java
repository.save(entity);
entityManager.flush();
entityManager.clear();

var found = repository.findById(id).orElseThrow();
assertEquals(expected, found.getValue());
~~~

Nó kiểm persistence query thật tốt hơn chỉ đọc lại một managed entity. Nhưng nếu mục tiêu là **deferred constraint hoặc after-commit listener**, cần một test có **commit thật**.

## 9. @JdbcTest, @DataJpaTest, @DataJdbcTest và @SpringBootTest

| Annotation | Phạm vi | Test-managed TX mặc định |
| --- | --- | --- |
| `@JdbcTest` | DataSource, JdbcTemplate và JDBC infrastructure | Có, rollback sau test |
| `@DataJdbcTest` | Spring Data JDBC repositories và JDBC infrastructure | Có, rollback sau test |
| `@DataJpaTest` | EntityManager, JPA repositories và transaction support | Có, rollback sau test |
| `@SpringBootTest` | Full application context, server tùy webEnvironment | Không mặc định bọc mỗi test; thêm `@Transactional` nếu cần |

Data/JPA/JDBC slices thường dùng embedded database khi dependency có trong classpath và cấu hình cho phép. Nếu SQL phụ thuộc vendor features, dùng Testcontainers với DB phù hợp. Không thể chứng minh PostgreSQL locking/SQLSTATE trên H2 chỉ vì tests PASS.

Điểm dễ sai là dùng `@DataJpaTest` có sẵn transaction rồi kết luận service production đã đặt @Transactional đúng. Data slice test giúp kiểm repository SQL; service transaction boundary cần **test riêng không có test-managed transaction**.

## 10. Ví dụ hoàn chỉnh Java 17+ / Spring Boot 3.5.x

Bộ thực hành có **bốn test classes và 12 phương thức JUnit Jupiter**:

- 3 tests: Spring TestContext test-managed lifecycle, REQUIRED/MANDATORY, dữ liệu chưa commit vô hình với connection khác.
- 6 tests: application-level commit, runtime rollback, checked exception, rollbackFor, REQUIRES_NEW, MANDATORY không có transaction.
- 2 tests: `TestTransaction` commit/rollback/end/start.
- 1 test: HTTP server thật chạy transaction riêng và commit bất chấp test-level rollback.

Dùng **Spring JDBC + H2 test database**, không cần Docker. Với production, cần cấu hình database thật/migration/security riêng.

### 10.1 Cấu trúc

~~~text
src/
  main/java/example/txdemo/
    TxDemoApplication.java
    AuditService.java
    OrderService.java
    OrderController.java
  test/java/example/txdemo/
    TestManagedTransactionTest.java
    ApplicationTransactionTest.java
    TestTransactionControlTest.java
    HttpTransactionBoundaryTest.java
  test/resources/
    schema.sql
    application.properties
~~~

Các file dùng package `example.txdemo`. Test nằm cùng package hierarchy với `@SpringBootApplication`.

### 10.2 build.gradle dependencies

Trong project đã cấu hình plugin/dependency management Spring Boot 3.5.x và Java toolchain 17, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **phần cấu hình dependencies**, không phải build.gradle đầy đủ. `starter-web` chỉ cần cho ví dụ HTTP; core JDBC tests có thể chạy không cần MVC server.

### 10.3 src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS tx_order (
    order_id VARCHAR(80) PRIMARY KEY,
    note VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_event (
    event_key VARCHAR(80) PRIMARY KEY
);
~~~

Test uses H2 in-memory. Production nên dùng migration Flyway/Liquibase; **không dùng DDL test trực tiếp trên production DB**.

### 10.4 src/test/resources/application.properties

~~~properties
spring.datasource.generate-unique-name=true
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.transaction-isolation=TRANSACTION_READ_COMMITTED
spring.sql.init.mode=always
~~~

Unique in-memory database cho mỗi ApplicationContext; pool đủ 2 connections khi REQUIRES_NEW; isolation READ_COMMITTED phục vụ test visibility; SQL init đọc schema. Cấu hình không ngụ ý H2 giống mọi DB vendor.

## 11. Production code: ứng dụng và các service

### 11.1 TxDemoApplication.java

~~~java
package example.txdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }
}
~~~

### 11.2 AuditService.java

~~~java
package example.txdemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String eventKey) {
        jdbc.update(
                "INSERT INTO audit_event(event_key) VALUES (?)",
                eventKey);
    }
}
~~~

Gọi `AuditService.record` qua **bean khác** giúp Spring AOP proxy xử lý REQUIRES_NEW. Tác vụ audit commit độc lập, **không nên nhầm với thành công cuối cùng của order** nếu outer transaction sau đó rollback.

### 11.3 OrderService.java

~~~java
package example.txdemo;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final AuditService audit;

    public OrderService(
            JdbcTemplate jdbc,
            AuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    @Transactional
    public void create(String id) {
        insert(id, "created");
    }

    @Transactional
    public void createThenThrowRuntime(String id) {
        insert(id, "runtime");
        throw new IllegalStateException("runtime failure");
    }

    @Transactional
    public void createThenThrowChecked(String id)
            throws IOException {
        insert(id, "checked");
        throw new IOException("checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void createThenRollbackChecked(String id)
            throws IOException {
        insert(id, "checked rollback");
        throw new IOException("checked failure");
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void createMandatory(String id) {
        insert(id, "mandatory");
    }

    @Transactional
    public void createThenFailAfterAudit(
            String orderId, String eventKey) {
        insert(orderId, "outer");
        audit.record(eventKey);
        throw new IllegalStateException("outer failure");
    }

    private void insert(String id, String note) {
        jdbc.update(
                "INSERT INTO tx_order(order_id, note) VALUES (?, ?)",
                id, note);
    }
}
~~~

Các method `public` là entrypoints được gọi qua bean/proxy từ test/controller. `createThenThrowChecked` kiểm behavior Spring 6.2 mặc định: checked exception không tự rollback, trừ khi policy đã được thay đổi. Method `createThenFailAfterAudit` cho thấy outer rollback và independent audit commit.

### 11.4 OrderController.java

~~~java
package example.txdemo;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/orders/{id}")
    public ResponseEntity<Void> create(@PathVariable("id") String id) {
        orders.create(id);
        return ResponseEntity
                .created(URI.create("/orders/" + id))
                .build();
    }
}
~~~

Endpoint cố ý đơn giản. Khi chạy production, cần validation ID, authentication/authorization và idempotency; ví dụ không phải một API order hoàn chỉnh.

## 12. Test-managed transaction: kiểm cả trước và sau rollback

File `src/test/java/example/txdemo/TestManagedTransactionTest.java`:

~~~java
package example.txdemo;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
@DisplayName("Transaction của test: lifecycle và rollback")
class TestManagedTransactionTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager txManager;

    @BeforeTransaction
    void beforeTransaction() {
        assertFalse(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @BeforeEach
    void beforeEachRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
        assertTrue(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @AfterEach
    void afterEachStillInsideTransaction() {
        assertTrue(TestTransaction.isActive());
    }

    @AfterTransaction
    void afterRollbackRowsAreGone() {
        assertFalse(TestTransaction.isActive());

        Integer remaining = jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id LIKE 'TMT-%'
                """, Integer.class);
        assertEquals(0, remaining.intValue());
    }

    @Test
    @DisplayName("REQUIRED service dùng chung transaction của test")
    void requiredJoinsTestTransaction() {
        orders.create("TMT-REQUIRED");

        assertEquals(1, count("TMT-REQUIRED"));
        assertTrue(TestTransaction.isActive());
        // Sau test TestContext rollback, @AfterTransaction kiểm lại.
    }

    @Test
    @DisplayName("MANDATORY PASS vì test đã có transaction")
    void mandatorySeesTestTransaction() {
        orders.createMandatory("TMT-MANDATORY");

        assertEquals(1, count("TMT-MANDATORY"));
        // Production caller không có transaction sẽ khác.
    }

    @Test
    @DisplayName("Connection khác không thấy row chưa commit")
    void independentTransactionCannotSeeUncommittedRow() {
        orders.create("TMT-ISOLATION");
        assertEquals(1, count("TMT-ISOLATION"));

        TransactionTemplate separate =
                new TransactionTemplate(txManager);
        separate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Integer observed = separate.execute(status ->
                jdbc.queryForObject("""
                        SELECT COUNT(*) FROM tx_order
                        WHERE order_id = ?
                        """,
                        Integer.class, "TMT-ISOLATION"));

        assertEquals(0, observed.intValue());
    }

    private int count(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }
}
~~~

**Ba bài test**. `@BeforeEach`/`@AfterEach` chạy trong test-managed TX, còn `@BeforeTransaction`/`@AfterTransaction` nằm ngoài. Phép đếm trong test thấy uncommitted row của chính transaction; sau default rollback không còn row.

`independentTransactionCannotSeeUncommittedRow` tạm suspend outer TX, mở transaction khác và query cùng ID. Với H2 READ_COMMITTED, inner query thấy 0 vì row chưa commit. Test này không chứng minh tất cả DB isolation levels hoặc concurrency behavior production.

**Lưu ý:** nếu code production dùng multiple transaction managers, test phải chỉ định manager đúng; chỉ nhìn `TestTransaction.isActive()` không nói transaction nào đang quản lý tài nguyên khác.

## 13. Application transactions: không dùng @Transactional trên test

File `src/test/java/example/txdemo/ApplicationTransactionTest.java`:

~~~java
package example.txdemo;

import java.io.IOException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@DisplayName("Transaction ứng dụng: commit và rollback thực")
class ApplicationTransactionTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;

    @AfterEach
    void cleanupCommittedRows() {
        jdbc.update(
                "DELETE FROM tx_order WHERE order_id LIKE 'APP-%'");
        jdbc.update(
                "DELETE FROM audit_event WHERE event_key LIKE 'APP-%'");
    }

    @Test
    @DisplayName("Service return bình thường thì commit")
    void successCommits() {
        assertFalse(
                TransactionSynchronizationManager
                        .isActualTransactionActive());

        orders.create("APP-COMMIT");

        assertEquals(1, countOrder("APP-COMMIT"));
    }

    @Test
    @DisplayName("RuntimeException gây rollback")
    void uncheckedExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> orders.createThenThrowRuntime("APP-RUNTIME"));

        assertEquals(0, countOrder("APP-RUNTIME"));
    }

    @Test
    @DisplayName("Checked exception mặc định có thể commit")
    void checkedExceptionDoesNotRollbackByDefault() {
        assertThrows(IOException.class,
                () -> orders.createThenThrowChecked("APP-CHECKED"));

        assertEquals(1, countOrder("APP-CHECKED"));
    }

    @Test
    @DisplayName("rollbackFor checked exception khiến rollback")
    void checkedExceptionWithRollbackRule() {
        assertThrows(IOException.class,
                () -> orders.createThenRollbackChecked("APP-CHECKED-RB"));

        assertEquals(0, countOrder("APP-CHECKED-RB"));
    }

    @Test
    @DisplayName("Audit REQUIRES_NEW commit dù outer rollback")
    void requiresNewAuditSurvivesOuterRollback() {
        assertThrows(IllegalStateException.class,
                () -> orders.createThenFailAfterAudit(
                        "APP-OUTER", "APP-AUDIT"));

        assertEquals(0, countOrder("APP-OUTER"));
        assertEquals(1, countAudit("APP-AUDIT"));
    }

    @Test
    @DisplayName("MANDATORY lỗi nếu caller không có transaction")
    void mandatoryFailsWithoutTransaction() {
        assertThrows(IllegalTransactionStateException.class,
                () -> orders.createMandatory("APP-MANDATORY"));

        assertEquals(0, countOrder("APP-MANDATORY"));
    }

    private int countOrder(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }

    private int countAudit(String key) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM audit_event
                WHERE event_key = ?
                """, Integer.class, key);
    }
}
~~~

**Sáu bài test** không có `@Transactional` ở class/method. Transaction service có quyền **commit/rollback ở entrypoint thật**. Sau mỗi test, `@AfterEach` xóa các rows có prefix `APP-%` vì **không có rollback TestContext** để dọn hộ.

Bài `mandatoryFailsWithoutTransaction` đặc biệt hữu ích: method `createMandatory` PASS khi gọi từ `TestManagedTransactionTest` do test cung cấp TX; ở đây fail vì không có transaction ứng dụng bên ngoài. Nó minh họa việc test-managed transaction có thể **che lỗi thiếu transaction ở production caller**.

Bài `requiresNewAuditSurvivesOuterRollback` không có shared test TX: outer service tự mở TX; inner audit mở TX B, commit; outer throw, rollback TX A. Kết quả DB là order=0, audit=1. Đây là bằng chứng rõ hơn việc mock AuditService rồi đoán về commit.

## 14. TestTransaction: commit và rollback giữa test method

File `src/test/java/example/txdemo/TestTransactionControlTest.java`:

~~~java
package example.txdemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
@DisplayName("Điều khiển test-managed transaction bằng TestTransaction")
class TestTransactionControlTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    @DisplayName("Commit ngay giữa test rồi đọc ngoài transaction")
    void commitThenObserveOutsideTransaction() {
        orders.create("TT-COMMIT");
        assertTrue(TestTransaction.isActive());
        assertEquals(1, count("TT-COMMIT"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        try {
            assertEquals(1, count("TT-COMMIT"));
        } finally {
            // Transaction đã COMMIT nên cần cleanup độc lập.
            jdbc.update(
                    "DELETE FROM tx_order WHERE order_id = ?",
                    "TT-COMMIT");
        }
    }

    @Test
    @DisplayName("Rollback rồi bắt đầu test transaction mới")
    void rollbackThenStartAgain() {
        orders.create("TT-ROLLBACK");

        TestTransaction.flagForRollback();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(0, count("TT-ROLLBACK"));

        TestTransaction.start();
        assertTrue(TestTransaction.isActive());

        orders.create("TT-SECOND");
        assertEquals(1, count("TT-SECOND"));
        // Transaction thứ hai rollback mặc định sau test.
    }

    private int count(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }
}
~~~

**Hai bài test**. Phép kiểm ngay trong transaction ban đầu không chứng minh commit; sau `TestTransaction.flagForCommit(); TestTransaction.end();`, query được thực hiện ngoài TX và chứng minh row đã được commit. Tại thời điểm đó test không còn được rollback tự động cho row đã commit; `finally` dọn data.

Không lạm dụng `TestTransaction` để thay transaction manager application. Nó tồn tại trong vòng đời test do TestContext quản lý, không dành cho production service.

## 15. HTTP thật: test transaction không đi theo server thread

File `src/test/java/example/txdemo/HttpTransactionBoundaryTest.java`:

~~~java
package example.txdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
@DisplayName("HTTP server transaction độc lập với test thread")
class HttpTransactionBoundaryTest {

    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    @DisplayName("HTTP POST commit dù test sẽ rollback")
    void httpServerCommitsIndependently() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/orders/HTTP-1"))
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(201, response.statusCode());
    }

    @AfterTransaction
    void observeAfterTestRollbackAndCleanup() {
        try {
            Integer total = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM tx_order
                    WHERE order_id = ?
                    """, Integer.class, "HTTP-1");

            // Row do server TX commit, vẫn còn sau test rollback.
            assertEquals(1, total.intValue());
        } finally {
            jdbc.update(
                    "DELETE FROM tx_order WHERE order_id = ?",
                    "HTTP-1");
        }
    }
}
~~~

**Một bài test**. Spring Boot chạy HTTP server thực trên random port. HttpClient/JUnit thread có test-managed transaction, nhưng controller/server service hoạt động trong **server thread** và có transaction riêng. Sau khi Spring TestContext rollback transaction JUnit, `@AfterTransaction` vẫn thấy row `HTTP-1` đã được server commit, rồi cleanup.

**Đừng dùng `MockMvc` để kết luận trường hợp này.** MockMvc thông thường xử lý request ở mock servlet environment trong cùng thread test, nên có thể tham gia test-managed TX. `RANDOM_PORT` mới chứng minh boundary của HTTP thật.

### Tổng số test methods

| Test class | Số @Test | Điều kiểm |
| --- | ---: | --- |
| `TestManagedTransactionTest` | 3 | Test lifecycle, REQUIRED/MANDATORY, isolation |
| `ApplicationTransactionTest` | 6 | Commit, runtime/checked rollback, REQUIRES_NEW, MANDATORY |
| `TestTransactionControlTest` | 2 | Commit/rollback bằng TestTransaction |
| `HttpTransactionBoundaryTest` | 1 | HTTP server commits outside test TX |
| **Tổng** | **12** | JDBC transaction behavior trên H2 |

## 16. Lệnh chạy và kết quả dự kiến

Ở thư mục project có Gradle wrapper:

~~~bash
./gradlew test --tests example.txdemo.TestManagedTransactionTest --tests example.txdemo.ApplicationTransactionTest --tests example.txdemo.TestTransactionControlTest --tests example.txdemo.HttpTransactionBoundaryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.txdemo.TestManagedTransactionTest --tests example.txdemo.ApplicationTransactionTest --tests example.txdemo.TestTransactionControlTest --tests example.txdemo.HttpTransactionBoundaryTest
~~~

**Kết quả kỳ vọng:** **12 JUnit Jupiter methods PASS** với Java 17+/Spring Boot 3.5.x, starter dependencies và các file đầy đủ. Test không có `System.out.println`; Gradle/IDE có thể hiển thị `BUILD SUCCESSFUL`. Đây là **kỳ vọng từ thiết kế, không phải stdout đã được ghi nhận sau lần build thực tế**.

Nếu test gặp lỗi, kiểm:

- `schema.sql` thực sự được Spring Boot SQL init nạp vào H2.
- H2 là test runtime dependency, datasource không vô tình trỏ đến production.
- Context có đúng một transaction manager hoặc cấu hình manager rõ.
- Hikari có đủ connections cho `REQUIRES_NEW`.
- Endpoint HTTP không bị Spring Security/CSRF chặn khi dự án thêm security.
- Không chạy test classes song song trên một database tên cố định; `generate-unique-name=true` giữ context DB tách biệt.

## 17. Fixture và @Sql: khi nào dữ liệu được commit?

Một tình huống thường sai: `@BeforeEach` tạo dữ liệu ở transaction test, sau đó method `REQUIRES_NEW` chạy ở connection khác và cần đọc fixture này. **Fixture chưa commit**, nên inner transaction không nhìn thấy nó dưới READ_COMMITTED.

~~~text
@BeforeTransaction -> có thể seed dữ liệu đã commit
BEGIN test transaction A
@BeforeEach        -> inserts ở A, chưa commit
@Test
  service REQUIRES_NEW -> transaction B không thấy dữ liệu chưa commit ở A
@AfterEach
ROLLBACK A
@AfterTransaction  -> cleanup / verify ngoài A
~~~

Nếu một inner transaction phải thấy fixture:

- Seed bằng `@BeforeTransaction` và committed JDBC/TransactionTemplate.
- Hoặc dùng `@SqlConfig(transactionMode = ISOLATED)` để nạp SQL bằng transaction riêng được commit.
- Hoặc tránh REQUIRES_NEW trong scenario nếu chính service không dùng nó.
- Cleanup dữ liệu seed committed sau test, không dựa vào rollback A.

Minh họa annotation:

~~~java
@Sql(
    scripts = "/sql/seed-accounts.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@SpringBootTest
@Transactional
class ExistingFixtureTest {
    // SQL fixture được commit độc lập với transaction test.
}
~~~

Đây là **mẫu**, không thuộc bộ 12 tests; cần file `src/test/resources/sql/seed-accounts.sql` và imports. Khi dùng `@Sql` thực tế, chú ý thời điểm chạy `BEFORE_TEST_METHOD`/`AFTER_TEST_METHOD`, transaction mode và cleanup scripts.

**Không** trộn `@Sql`, Flyway và Boot SQL init thiếu kiểm soát làm schema bị tạo lại hoặc dữ liệu fixture duplicate.

## 18. Commit-time behavior, JPA và transaction events

JPA `EntityManager` có first-level cache và cơ chế dirty checking. Một test:

~~~java
repository.save(account);
assertEquals(expected, repository.findById(id).orElseThrow());
~~~

có thể đọc managed object, không chắc đã ép SQL/constraint chạy. Để kiểm mapping/constraint sớm:

~~~java
repository.save(account);
entityManager.flush();
entityManager.clear();
var loaded = repository.findById(id).orElseThrow();
assertEquals(expected, loaded.getBalance());
~~~

Đây là **đoạn minh họa**, cần JPA entity/repository/EntityManager thật. `flush` không commit; DB có thể rollback dữ liệu đã flush. Với deferred constraints, `@TransactionalEventListener(phase=AFTER_COMMIT)` hoặc custom transaction synchronizations, phải test **commit thật**.

### Rollback không hủy mọi side effects

- SQL row cùng transaction: rollback được theo DB.
- Email đã gửi: không rollback bằng SQL transaction.
- HTTP payment đã gọi: không rollback tự động.
- Kafka message đã publish ngoài transaction chung: có thể còn.
- Local file đã ghi: không rollback.
- `REQUIRES_NEW` audit đã commit: không rollback bởi outer transaction.

Khi cần atomicity giữa DB và publish event, cân nhắc outbox pattern, idempotency, after-commit event với xử lý crash gap, hoặc distributed transaction khi thật sự phù hợp.

## 19. Thread boundaries, preemptive timeout và reactive transaction

Spring TestContext bind transaction vào **thread đang chạy test**. Vì vậy:

- `@Async`, `CompletableFuture.supplyAsync`, scheduler/background worker có thread khác.
- HTTP server thread trong `RANDOM_PORT` là thread khác.
- `assertTimeoutPreemptively` của JUnit Jupiter có thể chạy test body ở thread khác với thread đã được TestContext gắn transaction.

Không nên viết:

~~~java
assertTimeoutPreemptively(
    Duration.ofSeconds(2),
    () -> orderService.create("PREEMPTIVE"));
~~~

trong test-managed transaction rồi tin mọi write sẽ rollback. Transaction của test có thể không theo thread mới, và service có thể commit độc lập. Nếu cần timeout test, xem `assertTimeout` không preemptive, query/DB deadline, test riêng với cleanup và cơ chế cancel thật.

Với **R2DBC/WebFlux**, reactive transaction có thể dùng `ReactiveTransactionManager` và **Reactor Context**, không đơn giản dựa vào JDBC ThreadLocal. Bài ví dụ này là **Spring JDBC + servlet MVC**, không nên copy transaction assumptions sang Flux/Mono mà không kiểm context propagation.

## 20. Transaction của ứng dụng có thể không chạy vì self-invocation

Spring declarative transaction thường dựa trên AOP proxy. Gọi method trong cùng object bằng `this.inner()` có thể bỏ qua proxy:

~~~java
@Service
class DangerousService {

    public void outer() {
        innerRequiresNew();  // self-invocation, không qua proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void innerRequiresNew() {
        // Có thể KHÔNG mở transaction mới như kỳ vọng.
    }
}
~~~

Đây là mẫu giải thích, không nằm trong runnable sample. Trong `OrderService`, audit method được đặt trên **AuditService riêng** để lời gọi đi qua proxy.

Một test đã có test transaction có thể che bug self-invocation: code chạy dưới transaction do test mở sẵn, nhưng production không đạt propagation như thiết kế. Giải pháp: tách bean, gọi qua proxy thực hoặc dùng `TransactionTemplate` với propagation được cấu hình rõ. Viết thêm test **không có test-level transaction**.

## 21. TransactionTemplate và TestTransaction khác nhau

| Công cụ | Mục đích | Dùng trong production? |
| --- | --- | --- |
| `TestTransaction` | Điều khiển lifecycle test-managed transaction | Không; dành cho Spring TestContext |
| `TransactionTemplate` | Programmatic transaction management của ứng dụng | Có thể |
| `PlatformTransactionManager` | Abstract việc begin/commit/rollback resource | Có; Spring wiring |
| `@Transactional` trên service | Declarative transaction management qua proxy | Có |
| `@Transactional` trên test | Kích hoạt test-managed transaction | Có trong tests |

Ví dụ ứng dụng dùng `TransactionTemplate`:

~~~java
@Service
public class ProgrammaticWriter {

    private final TransactionTemplate transactions;
    private final JdbcTemplate jdbc;

    public ProgrammaticWriter(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.transactions = new TransactionTemplate(manager);
        this.jdbc = jdbc;
    }

    public void save(String id) {
        transactions.executeWithoutResult(status ->
                jdbc.update(
                    "INSERT INTO tx_order(order_id,note) VALUES (?,?)",
                    id, "programmatic"));
    }
}
~~~

Đây là class minh họa (cần package/imports). Với propagation mặc định REQUIRED, `TransactionTemplate` cũng có thể **tham gia test transaction** thay vì commit riêng; việc dùng API lập trình không tự đảm bảo physical transaction mới.

## 22. Các vấn đề database-specific và concurrency

H2 in-memory phù hợp ví dụ, nhưng không thay PostgreSQL/MySQL/Oracle/SQL Server trong mọi semantics:

- **Isolation:** READ_COMMITTED/REPEATABLE_READ/SERIALIZABLE có implementation và lock behavior khác nhau.
- **Deferred constraints:** một số constraint chỉ phát hiện khi commit; flush trong test không đủ.
- **DDL rollback:** PostgreSQL hỗ trợ transactional DDL rộng hơn nhiều DB khác; một số DDL tự commit.
- **SQL exception:** PostgreSQL có transaction-aborted `25P02` sau lỗi, cần rollback trước câu query sau.
- **Savepoints:** `NESTED` phụ thuộc JDBC driver/manager.
- **Locking:** `SELECT FOR UPDATE`, `SKIP LOCKED`, deadlocks không thể kiểm bằng một connection.
- **Time zone/collation:** kiểm đúng driver/dialect nếu business logic phụ thuộc SQL behavior.

Nếu production cần chống oversell hoặc lost update, test phải có **ít nhất hai connection/transaction độc lập**, barrier phối hợp, timeout và assertions sau commit. Đừng dùng hai lời gọi trên cùng thread/test transaction rồi coi là concurrency test.

### Test với Testcontainers

Đối với PostgreSQL, có thể chạy `@SpringBootTest` hoặc JDBC slice kết nối PostgreSQLContainer qua `@ServiceConnection`, áp dụng migrations thật rồi kiểm state/SQLSTATE/locks. Tùy test slice, cấu hình `@AutoConfigureTestDatabase(replace=NONE)` để tránh bị thay bằng H2. Không dùng production DB credentials.

## 23. Lỗi thường gặp và cách tránh

**1. Test @Transactional làm service có transaction dù production thiếu.**  
Tách service transaction test không có @Transactional trên test để chứng minh commit/rollback thật.

**2. Service return thành công được xem như commit.**  
Với REQUIRED tham gia transaction test, chỉ TestContext mới sở hữu commit/rollback.

**3. @Commit hoặc @Rollback(false) nhưng quên cleanup.**  
Dữ liệu tồn tại sau test. Dùng isolated DB/fixture cleanup.

**4. Kiểm dữ liệu trước khi rollback rồi tuyên bố dữ liệu đã được commit.**  
Một transaction đọc được own writes chưa commit.

**5. Nghĩ @AfterEach chạy sau rollback.**  
Nó chạy trong test TX; dùng `@AfterTransaction` để kiểm DB sau rollback.

**6. Đặt @Transactional trên @BeforeEach mà không hiểu TestContext.**  
Annotation test-managed transaction dành cho test class/method; @BeforeEach tham gia transaction có sẵn nếu test transactional.

**7. REQUIRES_NEW được cho là sẽ rollback cùng test.**  
Transaction độc lập có thể commit; cần dọn và hiểu connection pool.

**8. Nhầm NESTED với REQUIRES_NEW.**  
NESTED thường savepoint cùng physical TX, không commit độc lập.

**9. Bắt exception nhưng transaction vẫn rollback-only.**  
Inner REQUIRED có thể đã đánh dấu rollback-only; outer commit thất bại.

**10. Checked exception mặc định rollback như unchecked.**  
Spring 6.2 mặc định rollback unchecked, không rollback checked nếu không có rule.

**11. @Transactional(readOnly/isolation/timeout) trên test được kỳ vọng hoạt động như service.**  
TestContext hỗ trợ thuộc tính hạn chế; kiểm config trên application boundary.

**12. Pool size quá nhỏ cho REQUIRES_NEW.**  
Outer giữ một connection, inner cần connection thứ hai, có thể timeout.

**13. Dùng @BeforeEach seed rồi REQUIRES_NEW không nhìn thấy row.**  
Fixture chưa commit; seed committed bên ngoài test transaction hoặc @Sql ISOLATED.

**14. Dùng @DirtiesContext để dọn DB external.**  
Context cache reset không xóa rows đã commit khỏi database.

**15. @SpringBootTest RANDOM_PORT nhưng nghĩ test rollback dọn HTTP writes.**  
Server thread có transaction độc lập, phải cleanup.

**16. Dùng MockMvc để chứng minh transaction trên live HTTP.**  
MockMvc thường cùng thread test; server TCP không như vậy.

**17. assertTimeoutPreemptively gây thread hop.**  
Có thể làm writes thoát khỏi test-managed TX.

**18. JPA save rồi đọc entity managed, không flush/clear.**  
Dễ false positive; SQL/constraint có thể chưa chạy.

**19. Flush được coi là commit.**  
Flush đẩy SQL; commit mới xác định durability và after-commit events.

**20. H2 PASS nên tin chắc PostgreSQL locking/SQLSTATE đúng.**  
Dùng Testcontainers DB production-like khi DB-specific behavior là trọng tâm.

**21. Gọi @Transactional method bằng this.method().**  
Không qua proxy, propagation có thể không áp dụng.

**22. Test transaction rollback cả email, HTTP payment, file.**  
DB rollback không tự hủy external side effects.

**23. Test chạy song song chia sẻ schema/IDs.**  
Có thể race và rò dữ liệu; phân vùng fixtures hoặc tắt parallel khi cần.

**24. Reactive transaction được đánh đồng với JDBC ThreadLocal.**  
R2DBC dùng reactive context; thiết kế test riêng.

## 24. Quy trình quyết định bài test

1. Ghi rõ **mục tiêu**: repository SQL, service commit, error rollback, HTTP server, event after commit hay DB isolation.
2. Xác định resource manager: JDBC/JPA/R2DBC/JTA, connection/data source nào.
3. Ghi rõ caller có transaction trước khi gọi service không; nếu có, propagation là gì.
4. Dùng test-managed TX cho test repository nhanh, tự rollback và không cần commit.
5. Khi kiểm business commit/rollback thật, **bỏ test-level transaction** và kiểm state sau call.
6. Đối với REQUIRES_NEW, có pool đủ và cleanup dữ liệu commit độc lập.
7. Đối với fixture cần visibility từ connection khác, seed trước test TX hoặc @Sql ISOLATED.
8. Với commit-time constraints/events, dùng `@Commit` hoặc `TestTransaction` có cleanup.
9. Đối với HTTP RANDOM_PORT và async, giả định transaction boundary khác test thread.
10. Với JPA, flush/clear khi kiểm SQL state, không nhầm với commit.
11. Khi cần concurrency/isolation, dùng nhiều connection và DB thật gần production.
12. Không dùng preemptive test timeout cho DB writes trong test-managed TX nếu mong rollback.
13. Cleanup rõ với committed state, không dựa vào test order hay @DirtiesContext.
14. Tránh production credentials, giữ test database/schema riêng và versioned migrations.
15. Chạy test cả success, exception và side-effect paths, không chỉ happy path.

### Checklist cuối

- [ ] Đã xác định ranh giới test-managed/application/DB transaction và transaction manager.
- [ ] Biết @Transactional trên test mặc định rollback, @Transactional trên service không tương đương.
- [ ] Hiểu REQUIRED/MANDATORY/REQUIRES_NEW/NESTED theo caller hiện tại.
- [ ] Có test service không được test transaction bao quanh nếu cần chứng minh commit.
- [ ] @BeforeTransaction/@AfterTransaction được dùng đúng khi kiểm state trước/sau TX.
- [ ] @BeforeEach/@AfterEach không bị hiểu sai là ngoài test TX.
- [ ] Có cleanup rõ khi dùng @Commit/@Rollback(false)/TestTransaction.commit.
- [ ] Có rollback tests cho RuntimeException và checked exception khi business cần.
- [ ] REQUIRES_NEW không gây rò state hoặc thiếu connections.
- [ ] HTTP/server/async thread được kiểm trong môi trường thật khi cần.
- [ ] JPA flush/clear, constraints và afterCommit được phân biệt.
- [ ] Không dùng assertTimeoutPreemptively khiến transaction thoát khỏi test thread.
- [ ] Test DB vendor-specific trên engine thật khi cần.
- [ ] Không dùng production data/DB credentials cho test ghi/rollback.

**Ghi nhớ:** test-managed transaction là cơ chế **cô lập test**, không phải bằng chứng rằng service production có commit/rollback đúng. Spring application transaction có thể cùng dùng một physical transaction với test hoặc mở transaction khác. Database quyết định visibility, constraints và commit/rollback thực. Khi xác định rõ **thread, connection, propagation và người sở hữu commit**, bạn sẽ tránh được phần lớn false positives và dữ liệu rò trong Spring Boot testing.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): vòng đời, thuộc tính @Transactional được hỗ trợ, TestTransaction, timeout.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW, NESTED, savepoints, connection pool.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): checked và unchecked rollback rules.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): TransactionTemplate và PlatformTransactionManager.
- [Spring Framework — Spring TestContext @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL fixtures và isolated transaction mode.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): data slices, @SpringBootTest, RANDOM_PORT thread boundary.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): isActive, flags, end/start.
