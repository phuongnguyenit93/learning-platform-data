# Giao dịch JDBC so với giao dịch Reactive trong kiểm thử

## 1. Vì sao cùng là SQL transaction nhưng cách kiểm thử lại khác?

Trong Spring Boot, một nghiệp vụ ghi cơ sở dữ liệu có thể đi qua **JDBC (imperative/blocking)** hoặc **R2DBC (Reactive Relational Database Connectivity)**. Cả hai đều dùng khái niệm giao dịch (transaction): nhiều thao tác ghi được **commit cùng nhau** hoặc **rollback khi thất bại**. Tuy nhiên, **cách Spring gắn transaction vào luồng thực thi khác nhau**.

- **JDBC** thường dùng `DataSource`, `JdbcTemplate` và một `PlatformTransactionManager` như `JdbcTransactionManager` hoặc `DataSourceTransactionManager`. Transaction gắn với **thread hiện tại** qua Spring `TransactionSynchronizationManager` và connection tương ứng.
- **R2DBC** thường dùng `ConnectionFactory`, `DatabaseClient`/`R2dbcEntityTemplate` và `ReactiveTransactionManager` như `R2dbcTransactionManager`. Transaction đi theo **Reactor Context của subscription**, không phụ thuộc một thread cố định.
- Với Spring Boot 3.x, **`@JdbcTest` mặc định transactional và rollback sau mỗi test**, còn **`@DataR2dbcTest` mặc định không transactional**. Đây là sự khác biệt đặc biệt quan trọng khi chạy một test suite rồi kiểm tra dữ liệu còn sót.
- Một Publisher R2DBC được tạo nhưng **chưa subscribe** thường chưa chạy SQL. Trong khi `jdbcTemplate.update(...)` là một lời gọi imperative thực thi ngay khi gọi method.
- `@Transactional` trên một JUnit test method thông thường **không tự tạo Reactor transaction** cho mọi Publisher chạy bên trong nó. Spring TestContext test-managed transaction cần `PlatformTransactionManager`; R2DBC reactive transaction cần bọc **pipeline** bằng `TransactionalOperator` hoặc gọi một method reactive `@Transactional` qua proxy được cấu hình phù hợp.

**Mục tiêu bài học:** hiểu ranh giới của transaction; biết kiểm thử commit, rollback, subscription và visibility; tránh dùng rollback mặc định của JDBC để suy ra hành vi của R2DBC; tạo những test deterministic trên Java 17+, JUnit Jupiter và Spring Boot 3.x.

Sau bài này bạn sẽ có hai bộ test **tách thành hai project/module độc lập**:

1. **JDBC + H2 + `@JdbcTest`:** 5 bài JUnit kiểm tra test-managed rollback, `TestTransaction`, `TransactionTemplate` commit/rollback.
2. **R2DBC + H2 + `@DataR2dbcTest`:** 6 bài JUnit kiểm tra lazy subscription, `TransactionalOperator` commit/rollback, dữ liệu trong transaction và ảnh hưởng của vị trí `onErrorResume`.

Không cần WebFlux HTTP server, Docker hay database production. Mỗi sample có `schema.sql` riêng; **không đặt cả hai bộ dependency vào một Boot app duy nhất mà không cấu hình tường minh**, vì `DataSource`/`ConnectionFactory` và auto-configuration có thể tương tác hoặc vô hiệu hóa nhau.

## 2. Giao dịch là gì và điều gì được rollback?

Một giao dịch SQL thường có bốn đặc tính ACID: atomicity, consistency, isolation, durability. Đối với test, ta quan tâm đặc biệt đến:

- **Atomicity:** các thay đổi trong cùng transaction có thể được commit hoặc rollback cùng nhau.
- **Isolation:** một transaction khác có thể nhìn thấy những thay đổi nào, tùy isolation level của database.
- **Transaction boundary:** thời điểm bắt đầu, kết thúc, commit/rollback và connection nào tham gia.
- **Error boundary:** ngoại lệ hoặc tín hiệu lỗi nào đủ để transaction manager quyết định rollback.
- **Cleanup:** sau test, dữ liệu đã commit có được dọn đúng cách hay không.

Một dòng SQL `INSERT` chạy thành công **không đồng nghĩa** đã commit. Một test đọc lại được dữ liệu **trong chính giao dịch đang mở** cũng không chứng minh giao dịch khác đã thấy dữ liệu.

### 2.1. Bức tranh ba lớp

```text
                JDBC IMPERATIVE
JUnit thread ─── TransactionTemplate / @Transactional ─── JDBC
                 │ thread-bound TransactionStatus
                 └── DataSource Connection -> SQL -> commit/rollback

                R2DBC REACTIVE
JUnit thread ─── tạo Mono/Flux (assembly)
                 │
                 └── StepVerifier.subscribe()
                       │ Reactor subscriber Context
                       └── TransactionalOperator
                             └── ConnectionFactory Connection
                                   -> SQL publishers -> commit/rollback
```

Sơ đồ là mô hình kiến trúc: Spring có nhiều implementation của transaction managers; cú pháp thật khác theo project và Spring version. Nhưng sự phân biệt **thread-bound vs subscription-context-bound** là nguyên lý cốt lõi.

### 2.2. Đừng nhầm transaction với một connection được lấy bất kỳ

Với JDBC, Spring thường liên kết connection với transaction hiện tại trên thread. Nếu dùng `JdbcTemplate` với **cùng DataSource** và transaction manager phù hợp, các câu SQL thực hiện trong callback transactional cùng tham gia giao dịch.

Nhưng:

- Dùng `DriverManager.getConnection(...)` trực tiếp có thể mở connection khác, không tự tham gia transaction do Spring quản lý.
- Chạy truy vấn ở thread mới hoặc executor khác có thể không có transaction ThreadLocal ban đầu.
- `@Transactional(propagation = REQUIRES_NEW)` có thể tạm ngừng transaction cũ và tạo transaction mới.
- Dùng nhiều DataSources hoặc nhiều managers có thể dẫn đến nhiều transaction độc lập.

Với R2DBC, Spring gắn connection vào **Reactor Context**. `DatabaseClient`/R2DBC operations do Spring quản lý thường có thể sử dụng connection đang nằm trong reactive transaction. Nhưng tự mở connection khác hoặc tự gọi `subscribe()` tạo subscription riêng có thể làm mất transaction scope dự kiến.

## 3. Bảng so sánh JDBC và R2DBC trong Spring Boot Testing

| Tiêu chí | JDBC | R2DBC |
|---|---|---|
| Kiểu truy cập DB | Imperative, thường blocking | Reactive Publisher, điều phối bất đồng bộ |
| Entry point | `DataSource` / `JdbcTemplate` | `ConnectionFactory` / `DatabaseClient` |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Manager ví dụ | `JdbcTransactionManager`, `DataSourceTransactionManager` | `R2dbcTransactionManager` |
| Nơi lưu transaction context | ThreadLocal của thread thực thi | Reactor subscriber `Context` |
| Cách programmatic thường dùng | `TransactionTemplate` | `TransactionalOperator` |
| Thời điểm SQL | `jdbcTemplate.update(...)` chạy trong lời gọi method | Publisher SQL thường chạy **khi subscribe** |
| Kết quả của write | Số hàng ảnh hưởng, trả ngay | `Mono<Long>`/Publisher kết quả |
| Test slice Boot 3 | `@JdbcTest` | `@DataR2dbcTest` |
| Transaction/rollback mặc định của slice | **Có**, rollback sau test | **Không**, phải quản lý rõ |
| Test framework quản lý rollback | `TransactionalTestExecutionListener` / `TestTransaction` | Không tự tạo reactive rollback cho test method void |
| Kiểm tra tín hiệu hoàn tất/lỗi | JUnit assertions, `assertThrows` | `StepVerifier` + terminal signal |
| Commit | Callback/method kết thúc thành công theo manager | Transactional publisher hoàn tất thành công |
| Rollback | Runtime exception, rollback-only hoặc policy | Publisher phát terminal `onError`, rollback-only, và cancel theo Spring reactive semantics |
| Xác minh sau test | Đọc ở transaction mới | Subscribe một truy vấn mới **ngoài** transaction cần kiểm tra |

**Không biến bảng thành tuyệt đối:** transaction propagation, timeout, rollback rules, reactive stream cancellation, driver và isolation level có thể ảnh hưởng kết quả. Với `@Transactional`, bản chất manager và loại return value của method quyết định đường imperative hay reactive.

## 4. Vì sao @Transactional không có một ý nghĩa cho mọi cách gọi?

### 4.1. JDBC: thread-bound transaction

Với Spring transaction AOP được kích hoạt, một method imperative có thể khai báo:

```java
@Transactional
public void transfer(String from, String to, int amount) {
    jdbcTemplate.update("update accounts set balance = balance - ? where id = ?",
            amount, from);
    jdbcTemplate.update("update accounts set balance = balance + ? where id = ?",
            amount, to);
}
```

**Snippet minh họa**, giả định có `JdbcTemplate` và bảng `accounts`. Khi method được **gọi qua Spring proxy**, Spring mở hoặc tham gia transaction. Nếu exception khiến manager rollback, hai lệnh không commit riêng lẻ.

Điều kiện:

- `@Transactional` là metadata, cần Spring transaction infrastructure/proxy.
- **Self-invocation** như `this.transfer(...)` trong cùng class thường bỏ qua AOP proxy.
- Transaction gắn với **thread**; chuyển tác vụ sang thread khác không tự kế thừa connection/transaction.
- Default rollback rules thường rollback với `RuntimeException` và `Error`; checked exception cần rule/cấu hình phù hợp.
- Transaction test-managed bên ngoài có thể bị ảnh hưởng nếu code dùng `REQUIRES_NEW` hoặc `NOT_SUPPORTED`.

### 4.2. R2DBC: transaction gắn với Publisher/subscription

Reactive service có thể viết:

```java
@Transactional
public Mono<Void> transfer(String from, String to, int amount) {
    return debit(from, amount)
            .then(credit(to, amount));
}
```

Đây là **snippet minh họa**; `debit/credit` phải trả Publisher dùng R2DBC infrastructure/transaction phù hợp, và method cần được Spring proxy intercept. Khi dùng `ReactiveTransactionManager`, Spring mở transaction khi Publisher được subscribe theo cơ chế reactive transaction interceptors, chứ không phải “mở transaction trên JUnit thread rồi để nó tự đi theo mọi thao tác”.

Nếu test chỉ gọi:

```java
Mono<Void> result = service.transfer("A", "B", 10);
assertNotNull(result);
```

thì đó là **phản ví dụ**: không subscribe, không kiểm tra SQL/commit/rollback. Đúng hơn, dùng `StepVerifier.create(result).verifyComplete()` hoặc test error tương ứng.

### 4.3. Spring TestContext test-managed transaction không phải reactive context

Theo Spring Framework, `TransactionalTestExecutionListener` của TestContext cần một `PlatformTransactionManager` để hỗ trợ test-managed transactions. Với một `@JdbcTest`, annotation test đã cấu hình transactional; JUnit method chạy bên trong transaction do listener tạo rồi rollback sau test.

**Không suy ra**:

```java
@DataR2dbcTest
@Transactional
class ReactiveRepositoryTest {
}
```

sẽ tự động cho mọi Publisher được rollback sau mỗi test. Đó là một **phản mẫu không đáng tin**: reactive transaction cần được tổ chức quanh pipeline, còn test method JUnit thường có return type `void` và TestContext listener không mở reactive transaction bằng `ReactiveTransactionManager` như cách nó làm với PlatformTransactionManager.

Muốn test rollback R2DBC, bọc Publisher trong `TransactionalOperator` hoặc gọi method reactive `@Transactional` được proxy xử lý, rồi kiểm tra trạng thái bên ngoài transaction sau terminal.

## 5. Thời điểm thực thi SQL: gọi method vs subscribe

### 5.1. JDBC imperative

```java
int affected = jdbcTemplate.update(
        "insert into ledger_entries(code, amount) values (?, ?)",
        "J-001", 100);
```

Sau khi method trả về thành công, JDBC statement đã được thực thi trên connection. Nhưng **transaction có thể chưa commit**, đặc biệt trong `@JdbcTest`. Nếu test-managed transaction rollback, dòng mới sẽ bị hoàn tác.

### 5.2. R2DBC lazy Publisher

```java
Mono<Long> pending = databaseClient.sql(
        "insert into ledger_entries(code, amount) values (:code, :amount)")
        .bind("code", "R-001")
        .bind("amount", 100)
        .fetch()
        .rowsUpdated();

// Chỉ tạo Mono; chưa có subscription từ test.
```

Đây là snippet có `DatabaseClient` của Spring R2DBC, thường chỉ **mô tả** công việc SQL; nó chưa cung cấp bằng chứng INSERT đã chạy. Khi test gọi:

```java
StepVerifier.create(pending)
        .expectNext(1L)
        .verifyComplete();
```

subscription được kích hoạt, transaction (nếu đã bọc) mới có cơ hội thực thi và hoàn tất.

**Chú ý:** không khẳng định mọi Publisher đều cold; một số nguồn hot có thể tạo tác dụng độc lập subscription. Với Spring `DatabaseClient` mặc định, SQL execution được trì hoãn tới subscription. Với repository/adapter custom, hãy xác nhận semantics thực tế.

### 5.3. Không gọi subscribe() rời rạc bên trong transaction

Phản mẫu:

```java
Mono<Void> work = saveFirst()
        .doOnNext(value -> saveSecond().subscribe())
        .then();
```

Đây là **snippet phản mẫu**, giả định `saveFirst/saveSecond` đã tồn tại và kiểu dữ liệu phù hợp. `subscribe()` bên trong side-effect tạo subscription khác; công việc thứ hai có thể chạy ngoài transaction context, hoàn tất sau pipeline chính hoặc báo lỗi mà test không chờ.

Thay bằng **compose**:

```java
Mono<Void> work = saveFirst()
        .then(saveSecond())
        .then();
```

Khi cả hai Publisher được liên kết trong cùng reactive pipeline và bọc đúng transaction, Reactor Context có thể được truyền cho cả hai thao tác. Test phải xác nhận terminal của **pipeline chung**, không chỉ của publisher đầu tiên.

## 6. Programmatic transaction: TransactionTemplate vs TransactionalOperator

### 6.1. JDBC với TransactionTemplate

```java
TransactionTemplate template =
        new TransactionTemplate(platformTransactionManager);

template.executeWithoutResult(status -> {
    jdbcTemplate.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "J-A", 10);
    jdbcTemplate.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "J-B", 20);
});
```

Đây là **snippet** trong context đã có manager/template, không phải chương trình độc lập. Khi callback kết thúc bình thường, transaction manager commit theo policy; khi callback ném runtime exception, transaction rollback. Có thể gọi `status.setRollbackOnly()` để yêu cầu rollback dù callback trả thành công.

Một `TransactionTemplate` không nên được dùng để “bao” một async Publisher mà không đợi Publisher thực thi; callback trả về có thể kết thúc transaction **trước khi database operations trong Publisher chạy**.

### 6.2. R2DBC với TransactionalOperator

```java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Long> work = insertOne()
        .then(insertTwo())
        .thenReturn(2L)
        .as(operator::transactional);

StepVerifier.create(work)
        .expectNext(2L)
        .verifyComplete();
```

**Snippet minh họa**: `insertOne/insertTwo` trả về R2DBC Mono tương ứng. `.as(operator::transactional)` bọc publisher trong một transaction reactive, và StepVerifier subscribe. Khi work thành công và hoàn tất, transaction được commit.

Nếu một upstream operation phát `onError` chưa được recovery **bên trong transaction**, operator rollback. Nếu downstream cancel transaction publisher, Spring Framework từ 5.3 có semantics **rollback on cancel**. Các operator như `take(n)`, `next()` hoặc timeout có thể gây cancellation; cần hiểu điểm này khi xử lý `Flux` nhiều phần tử.

### 6.3. Ba thời điểm quan trọng khi kiểm tra R2DBC

```text
Assembly:
    Mono<?> work = ... .as(transactionalOperator::transactional)
    Chưa subscribe -> chưa bắt đầu transaction cho work.

Subscription:
    StepVerifier.create(work).verify(...)
    Spring mở reactive transaction, tạo/giữ connection trong Reactor Context.

Termination:
    onComplete -> commit (nếu không rollback-only)
    onError    -> rollback (theo policy)
    cancel     -> rollback trong Spring reactive tx từ Framework 5.3+
```

Một `Mono.just(...)` hoàn tất nhanh không chứng minh DB transaction nếu không có SQL Publisher trong work. Một `StepVerifier.expectNext(...)` mà **quên verify** cũng không thực thi subscription của test.

## 7. Ví dụ Java 17+ hoàn chỉnh — project JDBC riêng

Mẫu JDBC dùng `@JdbcTest`, H2 và `JdbcTemplate`. Test transaction rollback mặc định; những test muốn **commit thật** sẽ đánh dấu `Propagation.NOT_SUPPORTED` trên JUnit method rồi dùng `TransactionTemplate` mở transaction độc lập.

**Đích chạy:** Spring Boot 3.x, Java 17+, JUnit Jupiter, Spring JDBC và H2. Mẫu được thiết kế để nằm trong **một project JDBC độc lập**, không kèm `spring-boot-starter-data-r2dbc`. Tên package: `com.example.jdbctx`.

### 7.1. Dependencies JDBC

Gradle Groovy DSL, phần dependencies của build file **đã có Spring Boot plugin/BOM, repositories và Java 17 toolchain**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven với Spring Boot parent/BOM và test runner thích hợp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **trích đoạn** chứ không phải toàn bộ build file. H2 runtime có mặt ở test runtime; Boot `@JdbcTest` có thể dùng embedded DB phù hợp. Không cần server HTTP, Reactor, R2DBC hoặc Spring Data JPA.

### 7.2. Cây file project JDBC

```text
jdbc-tx-project/
└── src/
    ├── main/java/com/example/jdbctx/
    │   └── JdbcTxApplication.java
    └── test/
        ├── java/com/example/jdbctx/
        │   └── JdbcTransactionTest.java
        └── resources/
            └── schema.sql
```

### 7.3. File ứng dụng

**`src/main/java/com/example/jdbctx/JdbcTxApplication.java`**

```java
package com.example.jdbctx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcTxApplication.class, args);
    }
}
```

Không cần khai báo manual DataSource/transaction manager. Boot JDBC starter và embedded H2 cung cấp cơ sở để auto-configure JDBC infrastructure cho slice.

### 7.4. SQL schema dùng cho test

**`src/test/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

Schema cố ý đơn giản, không có trigger/sequence/identity. Mỗi test dùng key riêng. Script được Spring Boot SQL initializer thực thi khi khởi động test context với cấu hình thích hợp, **không chạy lại sau mỗi transaction**.

### 7.5. Lớp JDBC test hoàn chỉnh

**`src/test/java/com/example/jdbctx/JdbcTransactionTest.java`**

```java
package com.example.jdbctx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@JdbcTest(properties = "spring.sql.init.mode=always")
class JdbcTransactionTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager transactionManager;

    private void insert(String code, int amount) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, amount);
    }

    private int count(String code) {
        Integer result = jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class,
                code);
        return result == null ? 0 : result;
    }

    @Test
    void jdbcSliceStartsRollbackOnlyTestTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        insert("J-ROLLBACK-DEFAULT", 10);
        assertThat(count("J-ROLLBACK-DEFAULT")).isEqualTo(1);

        // Hàng có thể đọc trong test transaction;
        // @JdbcTest sẽ rollback khi test method kết thúc.
    }

    @Test
    void explicitEndShowsRollbackAndNewTestTransaction() {
        insert("J-ROLLBACK-END", 20);
        assertThat(count("J-ROLLBACK-END")).isEqualTo(1);
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        TestTransaction.end();
        assertThat(TestTransaction.isActive()).isFalse();

        TestTransaction.start();
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count("J-ROLLBACK-END")).isZero();
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void transactionTemplateCommitsWhenCallbackReturns() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        try {
            template.executeWithoutResult(status ->
                    insert("J-COMMIT", 30));

            // Callback đã kết thúc: transactionTemplate đã commit.
            assertThat(count("J-COMMIT")).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    "J-COMMIT");
        }
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void transactionTemplateRollsBackOnRuntimeException() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        assertThatThrownBy(() ->
                template.executeWithoutResult(status -> {
                    insert("J-ERROR", 40);
                    throw new IllegalStateException("reject");
                }))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("reject");

        assertThat(count("J-ERROR")).isZero();
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void rollbackOnlyWorksEvenWithoutAnException() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.executeWithoutResult(status -> {
            insert("J-ONLY", 50);
            status.setRollbackOnly();
        });

        assertThat(count("J-ONLY")).isZero();
    }
}
```

**Kỳ vọng:** **5 JUnit Jupiter test methods pass** trên một dự án Spring Boot 3.x/H2 được tạo theo các file trên. Không có stdout chủ động từ sample. H2 schema có thể được tạo khi test context khởi động; Spring/Gradle/Maven có thể in logging của riêng chúng.

**Lưu ý:** import `TransactionStatus` trong snippet không bắt buộc cho mã hiện tại; có thể bỏ vì callback suy luận kiểu. Nó không làm Java compile fail. `@Transactional(NOT_SUPPORTED)` trên ba test cuối là có chủ đích: chúng **không nhận test-managed transaction bao quanh**, nên `TransactionTemplate` có thể commit/rollback theo callback một cách quan sát được từ câu SELECT sau callback. Nếu bỏ `NOT_SUPPORTED`, template mặc định có thể **tham gia transaction test có sẵn**, và SELECT sau callback vẫn thấy dữ liệu trong transaction đó thay vì chứng minh một commit độc lập.

### 7.6. Diễn giải riêng từng test JDBC

| Test | Ý nghĩa thực tế |
|---|---|
| `jdbcSliceStartsRollbackOnlyTestTransaction` | `@JdbcTest` tạo test transaction, thấy INSERT ngay trong transaction và được rollback khi method xong |
| `explicitEndShowsRollbackAndNewTestTransaction` | `TestTransaction.end()` thực hiện rollback, `start()` tạo transaction mới để chứng minh row biến mất |
| `transactionTemplateCommitsWhenCallbackReturns` | Không có outer test tx; callback kết thúc bình thường, transaction được commit, test dọn row trong finally |
| `transactionTemplateRollsBackOnRuntimeException` | Callback ném runtime error, rollback và exception được đẩy ra test |
| `rollbackOnlyWorksEvenWithoutAnException` | `status.setRollbackOnly()` yêu cầu rollback dù callback không ném lỗi |

Hai tests cuối không tạo fixture còn sót vì transaction đã rollback. Test commit có cleanup tường minh. Nếu chạy suite song song trên DB chung, cần tạo schema/database riêng hoặc unique keys và cleanup đủ chắc chắn; sample dùng embedded DB trong test project riêng.

## 8. Ví dụ Java 17+ hoàn chỉnh — project R2DBC riêng

Đây là phần **đối xứng về nghiệp vụ, khác về transaction boundary**. R2DBC sample dùng `@DataR2dbcTest`, `DatabaseClient`, H2 R2DBC driver, `ReactiveTransactionManager` và `TransactionalOperator`. **Không** thêm `@Transactional` lên JUnit test class để “tự động rollback”; mọi giao dịch muốn kiểm thử được bọc tường minh trong Publisher.

**Đích chạy:** Spring Boot 3.x, Java 17+, JUnit Jupiter, Project Reactor, Spring R2DBC và H2 R2DBC driver. Tên package: `com.example.r2dbctx`. Hai project dùng cùng tên table nhưng **có in-memory database khác nhau**, không nhằm kiểm chứng distributed transaction JDBC + R2DBC trên một database chung.

### 8.1. Dependencies R2DBC

Gradle Groovy DSL — trong project có Spring Boot plugin/BOM, repositories và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — phần dependencies của project có Boot parent/BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

R2DBC có driver/protocol riêng, **không dùng `jdbc:h2:...` làm R2DBC URL**. H2 R2DBC in-memory URL ví dụ có dạng `r2dbc:h2:mem:///...`. Tùy release driver, các options của H2 được truyền qua query; ví dụ sử dụng cú pháp có trong tài liệu chính thức r2dbc-h2.

### 8.2. Cây file R2DBC

```text
r2dbc-tx-project/
└── src/
    ├── main/java/com/example/r2dbctx/
    │   └── ReactiveTxApplication.java
    └── test/
        ├── java/com/example/r2dbctx/
        │   └── ReactiveTransactionTest.java
        └── resources/
            └── schema.sql
```

### 8.3. Application class

**`src/main/java/com/example/r2dbctx/ReactiveTxApplication.java`**

```java
package com.example.r2dbctx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

Không có JDBC starter/JPA starter trong project này. Spring Boot có thể tự cấu hình `ConnectionFactory`, `DatabaseClient` và R2DBC transaction manager khi classpath/conditions phù hợp.

### 8.4. Schema riêng cho R2DBC

**`src/test/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

Với embedded H2 và Boot SQL initialization, script có thể khởi tạo bằng R2DBC `ConnectionFactory`. Mẫu đặt `spring.sql.init.mode=always` để ý định rõ ràng, và URL giữ in-memory DB tồn tại khi connection được đóng trong test.

### 8.5. Lớp test R2DBC hoàn chỉnh

**`src/test/java/com/example/r2dbctx/ReactiveTransactionTest.java`**

```java
package com.example.r2dbctx;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@DataR2dbcTest(properties = {
        "spring.r2dbc.url=r2dbc:h2:mem:///reactive_tx_demo"
                + "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.sql.init.mode=always"
})
class ReactiveTransactionTest {

    @Autowired
    DatabaseClient client;

    @Autowired
    ReactiveTransactionManager transactionManager;

    private TransactionalOperator tx() {
        return TransactionalOperator.create(transactionManager);
    }

    private Mono<Long> insert(String code, int amount) {
        return client.sql(
                "insert into ledger_entries(code, amount) "
                + "values (:code, :amount)")
                .bind("code", code)
                .bind("amount", amount)
                .fetch()
                .rowsUpdated();
    }

    private Mono<Long> count(String code) {
        return client.sql(
                "select count(*) from ledger_entries where code = :code")
                .bind("code", code)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    private Mono<Long> delete(String code) {
        return client.sql(
                "delete from ledger_entries where code = :code")
                .bind("code", code)
                .fetch()
                .rowsUpdated();
    }

    @Test
    void buildingPublisherDoesNotExecuteSqlWithoutSubscribe() {
        Mono<Long> prepared = insert("R-NOT-SUBSCRIBED", 10);

        assertThat(prepared).isNotNull();

        StepVerifier.create(count("R-NOT-SUBSCRIBED"))
                .expectNext(0L)
                .verifyComplete();

        // Không subscribe prepared -> INSERT chưa chạy.
    }

    @Test
    void transactionCommitsOnSuccessfulCompletion() {
        Mono<Long> operation = insert("R-COMMIT", 20)
                .then(count("R-COMMIT"))
                .as(tx()::transactional);

        try {
            StepVerifier.create(operation)
                    .expectNext(1L)
                    .verifyComplete();

            // Một subscription MỚI, ở ngoài transaction đã hoàn tất.
            StepVerifier.create(count("R-COMMIT"))
                    .expectNext(1L)
                    .verifyComplete();
        }
        finally {
            StepVerifier.create(delete("R-COMMIT"))
                    .expectNextCount(1)
                    .verifyComplete();
        }
    }

    @Test
    void transactionRollsBackOnTerminalError() {
        Mono<Void> operation = insert("R-ROLLBACK", 30)
                .then(Mono.<Void>error(
                        new IllegalStateException("reject")))
                .as(tx()::transactional);

        StepVerifier.create(operation)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "reject".equals(error.getMessage()))
                .verify();

        StepVerifier.create(count("R-ROLLBACK"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void writesAreVisibleInsideTransactionButRolledBack() {
        AtomicLong seenInside = new AtomicLong(-1L);

        Mono<Void> operation = insert("R-INSIDE", 40)
                .then(count("R-INSIDE"))
                .doOnNext(seenInside::set)
                .then(Mono.<Void>error(
                        new IllegalArgumentException("rollback me")))
                .as(tx()::transactional);

        StepVerifier.create(operation)
                .expectErrorMessage("rollback me")
                .verify();

        assertThat(seenInside.get()).isEqualTo(1L);

        StepVerifier.create(count("R-INSIDE"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void recoveringErrorInsideTransactionCanCommit() {
        Mono<Void> operation = insert("R-RECOVER-IN", 50)
                .then(Mono.<Void>error(
                        new IllegalStateException("upstream failed")))
                .onErrorResume(error -> Mono.empty())
                .as(tx()::transactional);

        try {
            StepVerifier.create(operation)
                    .verifyComplete();

            StepVerifier.create(count("R-RECOVER-IN"))
                    .expectNext(1L)
                    .verifyComplete();
        }
        finally {
            StepVerifier.create(delete("R-RECOVER-IN"))
                    .expectNextCount(1)
                    .verifyComplete();
        }
    }

    @Test
    void recoveringErrorOutsideTransactionKeepsRollback() {
        Mono<Void> operation = insert("R-RECOVER-OUT", 60)
                .then(Mono.<Void>error(
                        new IllegalStateException("upstream failed")))
                .as(tx()::transactional)
                .onErrorResume(error -> Mono.empty());

        StepVerifier.create(operation)
                .verifyComplete();

        StepVerifier.create(count("R-RECOVER-OUT"))
                .expectNext(0L)
                .verifyComplete();
    }
}
```

**Kết quả dự kiến:** **6 JUnit Jupiter tests pass** với Spring Boot 3.x/Reactive H2 driver/JUnit 5 phù hợp. Mã không chủ động in stdout; summary do test runner quyết định.

Tại sao test thứ hai dùng `try/finally`? `@DataR2dbcTest` không tự rollback mỗi test. Một publisher hoàn tất thành công trong `TransactionalOperator` sẽ commit; vì vậy **chính test phải xóa fixture đã commit**. Trong hai test có error đi qua operator, transaction rollback nên không còn row. Các tên mã khác nhau giảm va chạm trong cùng context.

### 8.6. Vì sao .then(...) và .as(tx::transactional) quan trọng?

Trong test:

```java
Mono<Long> operation = insert("R-COMMIT", 20)
        .then(count("R-COMMIT"))
        .as(tx()::transactional);
```

- `insert(...)` trả Mono của SQL INSERT.
- `then(count(...))` chỉ subscribe count sau khi insert hoàn tất thành công; count nằm trong **cùng pipeline**.
- `as(tx()::transactional)` đặt transaction scope quanh **toàn pipeline**.
- `StepVerifier.create(operation).verifyComplete()` (hoặc có value expectation) kích hoạt subscription và đợi terminal.
- Sau terminal complete của transactional Publisher, operator đã thực hiện đường commit theo semantics của manager; query ngoài operator là phép đo dữ liệu đã commit.

Nếu bạn bọc chỉ riêng `insert` bằng operator rồi gọi `count` sau đó, count ở bên ngoài transaction. Điều đó có thể là chủ đích, nhưng không giống test “đọc trong cùng giao dịch”.

### 8.7. Tại sao onErrorResume đặt ở đâu lại quan trọng?

Hai test cuối cùng là cặp đối chiếu:

**Recovery nằm bên trong transaction scope**:

```java
insert("A", 1)
        .then(Mono.error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

Nếu operator bên ngoài chỉ thấy `onComplete` thành công, nó **có thể commit** thay đổi, dù upstream đã phát lỗi và được chuyển thành empty completion.

**Recovery nằm bên ngoài transaction scope**:

```java
insert("B", 1)
        .then(Mono.error(new IllegalStateException("failed")))
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> Mono.empty());
```

Bây giờ transactional operator nhận `onError` trước và rollback, rồi consumer ở bên ngoài mới chuyển lỗi thành completion. Test có thể kết thúc xanh, nhưng row B không được commit.

Đây là điểm nguy hiểm trong reactive business services: **một test chỉ assert `verifyComplete()` không đủ để kết luận đã commit**. Cần query sau completion và hiểu **ranh giới error/recovery**.

## 9. Chạy hai bộ test

Chạy mỗi project/module ở thư mục tương ứng; chúng không chia sẻ application context, database, dependencies hay transaction manager.

### 9.1. JDBC project

Linux/macOS:

```bash
./gradlew test --tests "com.example.jdbctx.JdbcTransactionTest"

# Hoặc nếu dùng Maven Wrapper:
./mvnw -Dtest=JdbcTransactionTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jdbctx.JdbcTransactionTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=JdbcTransactionTest" test
```

### 9.2. R2DBC project

Linux/macOS:

```bash
./gradlew test --tests "com.example.r2dbctx.ReactiveTransactionTest"

# Hoặc Maven Wrapper:
./mvnw -Dtest=ReactiveTransactionTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.r2dbctx.ReactiveTransactionTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=ReactiveTransactionTest" test
```

Không chạy cả Gradle và Maven nếu project chỉ dùng một build system. Với dự án multi-module, chọn đúng module task. Nếu IDE không nhận JUnit Jupiter, kiểm tra test runtime dependencies, `useJUnitPlatform()` hoặc Surefire cấu hình tương thích. Tổng hai project có **11 bài test (5 JDBC + 6 R2DBC)**, không phải 11 test methods trong một class duy nhất.

### 9.3. Kỳ vọng theo hợp đồng

| Case | JDBC | R2DBC |
|---|---|---|
| Phương thức test slice mặc định | Có transaction + rollback | Không tự transactional |
| Thực hiện INSERT | `jdbc.update(...)` chạy khi gọi | `DatabaseClient...rowsUpdated()` thực thi khi subscribe |
| Thành công trong programmatic transaction | `TransactionTemplate` commit | `TransactionalOperator` commit |
| Exception/error chưa được recovery | Runtime exception -> rollback | `onError` -> rollback |
| Tự đánh dấu rollback | `TransactionStatus.setRollbackOnly()` | ReactiveTransaction có thể setRollbackOnly qua operator callback |
| Sau commit | JDBC query mới thấy row | R2DBC Publisher query mới thấy row |
| Dọn dữ liệu test | Test rollback hoặc cleanup sau commit | Cleanup rõ, không dựa vào slice rollback |
| Test lỗi không chờ đồng bộ | Ném exception trực tiếp trong callback | StepVerifier phải subscribe và verify terminal |

## 10. @JdbcTest, @DataJdbcTest, @DataJpaTest và @DataR2dbcTest không tương đương

Spring Boot cung cấp nhiều test slices cho các lớp truy cập dữ liệu. Những annotation có tên giống nhau không phải cam kết cùng transaction setup.

### 10.1. @JdbcTest

- Tập trung vào `DataSource` và `JdbcTemplate`.
- Thường dùng embedded database có sẵn.
- **Transactional, rollback mặc định**.
- Không tập trung vào Spring Data JDBC repository mapping.
- Hữu ích khi test SQL thủ công, mapping qua RowMapper, batch updates và JDBC transaction semantics.

### 10.2. @DataJdbcTest

- Tập trung vào Spring Data JDBC repositories/aggregate mapping.
- Có test-managed transaction và rollback mặc định trong Spring Boot 3.x.
- Có thể cần cấu hình custom repository converters/aggregates.
- Đừng nhầm Spring Data JDBC với JPA: Spring Data JDBC **không có persistence context/dirty checking** theo Hibernate, và save semantics khác.

### 10.3. @DataJpaTest

- Tập trung JPA entities/repositories và Hibernate/JPA persistence context.
- Transactional, rollback mặc định.
- JPA `flush` và first-level cache là một lớp khác ngoài SQL transaction.
- `repository.save(...)` có thể defer SQL; cần flush/clear/JDBC khi test persisted state.

Không chuyển một ví dụ JDBC trực tiếp sang JPA rồi mong các câu SQL chạy đúng thời điểm giống `JdbcTemplate.update(...)`.

### 10.4. @DataR2dbcTest

- Tập trung Spring Data R2DBC repositories, `R2dbcEntityTemplate`, `DatabaseClient` và reactive infrastructure.
- Theo Spring Boot 3.5 docs, mặc định cấu hình embedded DB nếu có driver thích hợp, nhưng **không tự chạy mỗi test trong transaction**.
- Muốn test reactive transaction cần `ReactiveTransactionManager` và Publisher transactional, qua `TransactionalOperator` hoặc proxied reactive `@Transactional`.
- Khi Publisher đã commit, phải cleanup bằng reactive Publisher riêng, schema riêng hoặc reset container.

**Bài học chính:** áp dụng thói quen “mỗi test tự rollback” từ JDBC/JPA slices sang R2DBC có thể để lại dữ liệu, tạo test order dependence và lỗi CI khó tái hiện.

## 11. @Transactional trên reactive service: chú ý return type và proxy

### 11.1. Method return type phải phù hợp reactive transaction

Spring hỗ trợ `@Transactional` cho reactive return types khi transaction manager thích hợp. Một method như sau có thể dùng reactive transaction AOP:

```java
@Service
public class ReactiveLedgerService {

    private final DatabaseClient client;

    public ReactiveLedgerService(DatabaseClient client) {
        this.client = client;
    }

    @Transactional
    public Mono<Void> recordPair() {
        return client.sql("insert into ledger_entries(code, amount) "
                + "values ('A', 10)")
                .fetch().rowsUpdated()
                .then(client.sql("insert into ledger_entries(code, amount) "
                        + "values ('B', 20)")
                        .fetch().rowsUpdated())
                .then();
    }
}
```

**Snippet minh họa**, không phải file runnable độc lập của hai project mẫu. Cần imports Spring Service, Transactional, Reactor Mono và DatabaseClient, một transaction manager phù hợp, và fixture tránh trùng primary keys. Nó thể hiện nguyên lý: **return một Publisher ghép đủ operations** để Spring reactive interceptor bọc.

Nếu method trả `void`, `String` hoặc một giá trị imperative, nó không phải reactive return shape. Với một `ReactiveTransactionManager`, Spring transaction management mong đợi pipeline reactive; không tự biến những method imperative ấy thành R2DBC transaction hợp lệ.

### 11.2. Self-invocation và object tạo bằng new

Nếu test làm:

```java
ReactiveLedgerService service =
        new ReactiveLedgerService(databaseClient);

Mono<Void> result = service.recordPair();
```

bạn đã tạo object **không đi qua Spring proxy**. Annotation `@Transactional` trên method không tự được Spring AOP áp dụng cho object tạo bằng `new`.

Tương tự, `this.recordPair()` từ method khác trong cùng class thường bypass proxy trong Spring proxy mode. Khi test unit không khởi động Spring context, hãy **dùng TransactionalOperator tường minh** hoặc chỉ kiểm tra business pipeline với fake repository, rồi có integration test riêng cho annotation/proxy wiring.

### 11.3. Dùng multiple transaction managers

Một app có cả JDBC/JPA manager và R2DBC manager cần chỉ rõ transaction nào quản lý thao tác nào. Có thể có:

- `PlatformTransactionManager` cho `DataSource`/JPA;
- `ReactiveTransactionManager` cho `ConnectionFactory`.

Chúng là **hai SPI khác nhau** và thường dùng hai connections khác nhau. Đừng kỳ vọng một `@Transactional` mơ hồ tạo atomic commit cho cả JDBC lẫn R2DBC. Cần thiết kế boundary/manager selection rõ ràng và test thứ tự commit/rollback khi hệ thống thực sự có nhiều tài nguyên.

## 12. TestThread, Reactor Context và các bẫy chuyển thread

### 12.1. JDBC transaction ThreadLocal

Khi `@JdbcTest` mở test transaction, Spring giữ thông tin giao dịch trên thread thực thi test. Nếu trong test bạn dùng:

```java
CompletableFuture.runAsync(() ->
        jdbcTemplate.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                "ASYNC-J", 1));
```

đây là **snippet phản mẫu**, giả định có import CompletableFuture. Nếu tạo một async task rồi không join, JUnit test có thể kết thúc trước khi SQL chạy; kể cả join, task chạy thread khác nên không tự tham gia transaction ThreadLocal của test. Nó có thể sử dụng connection mới/autocommit và để lại row dù test method rollback.

Một bẫy tương tự là JUnit `assertTimeoutPreemptively(...)`: preemptive timeout có thể chạy phần body trên thread khác với thread mà TestContext listener đã gắn transaction. Spring docs cảnh báo side effects có thể **không rollback** theo test-managed transaction.

Muốn test timeout mà vẫn giữ transaction semantics, cân nhắc timeout không preemptive hoặc thiết kế riêng transaction trong worker thread bằng transaction template, có cleanup rõ.

### 12.2. R2DBC transaction dựa trên Context, không cố định thread

Reactive context được truyền dọc pipeline theo Reactor. Một operator `publishOn(...)` có thể đổi thread xử lý, nhưng khi pipeline/Context được tổ chức đúng, transaction scope không phụ thuộc duy nhất vào tên thread.

Điều nguy hiểm không phải “cứ đổi thread là transaction hỏng”, mà là:

- tự gọi `subscribe()` bên trong pipeline tạo **subscription riêng**;
- dùng `block()` ở nơi event-loop cấm blocking hoặc vô tình đổi ranh giới pipeline;
- gọi JDBC blocking trong reactive pipeline, tưởng JDBC tham gia reactive R2DBC transaction;
- mở raw R2DBC connection riêng thay vì dùng connection được Spring quản lý;
- mất Reactor Context khi tích hợp thư viện Publisher không tuân theo context propagation.

### 12.3. Không trộn JdbcTemplate vào TransactionalOperator rồi mong một transaction

Phản mẫu:

```java
Mono<Void> operation = Mono.fromRunnable(() ->
        jdbcTemplate.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                "MIXED", 10))
        .as(reactiveOperator::transactional)
        .then();
```

Đây là **snippet phản mẫu**, giả định có `jdbcTemplate` và `reactiveOperator`; nó không được bảo đảm atomic transaction với R2DBC. `JdbcTemplate` dùng `DataSource`/thread-bound manager; `TransactionalOperator` dùng reactive manager/ConnectionFactory. Bao Mono quanh JDBC không tự biến JDBC connection thành reactive connection.

Nếu phải có cả JDBC và R2DBC truy cập cùng cơ sở dữ liệu:

1. Xác định logic thuộc một transaction manager chính.
2. Không giả định hai managers hợp nhất hoặc cùng connection.
3. Có thể tách giao dịch và dùng saga/outbox/idempotency khi nghiệp vụ chạy nhiều resource managers.
4. Test commit/rollback ở **từng boundary** và kiểm tra lỗi nửa chừng.
5. Với yêu cầu atomic distributed commit, cần kiến trúc/transaction protocol chuyên biệt và xác minh hỗ trợ thực tế; **không mặc định có XA chung** cho R2DBC + JDBC.

## 13. Reactive cancellation: onComplete, onError và cancel không giống nhau

Trong Reactive Streams, một subscription có thể kết thúc bằng:

- `onComplete` — publisher hoàn thành bình thường;
- `onError` — lỗi terminal;
- `cancel()` từ subscriber — hủy subscription, không nhất thiết nhận terminal signal;
- timeout hoặc các operators như `take`/`next` có thể phát sinh cancel trong những tình huống cụ thể.

Theo Spring Framework programmatic transaction documentation, **cancellation của transactional reactive Publisher dẫn đến rollback** từ Spring Framework 5.3. Vì vậy nếu code dùng `Flux` để phát hàng loạt bản ghi rồi client chỉ lấy phần tử đầu tiên, phải kiểm tra **cách transaction có thể bị cancel trước khi toàn bộ pipeline hoàn thành**.

### 13.1. Phản mẫu dùng take(1) để đánh giá commit

```java
Flux<Event> stream = saveAndStreamEvents()
        .as(transactionalOperator::transactional);

StepVerifier.create(stream.take(1))
        .expectNextCount(1)
        .verifyComplete();
```

**Snippet minh họa**, không phải test runnable độc lập. Downstream `take(1)` có thể cancel upstream transactional Flux sau giá trị đầu tiên. Dù subscriber ngoài nhìn thấy complete, transactional operator bên trong có thể nhận cancellation và rollback. Vì vậy một `verifyComplete()` của `take(1)` không chứng minh mọi SQL trước đó đã commit.

### 13.2. Khi cần test cancellation

Thiết kế test có **tín hiệu chắc chắn xác nhận SQL đã chạy trong transaction trước khi cancel**. Ví dụ dùng fake upstream có `PublisherProbe`, latch/signal có timeout hoặc TestPublisher theo kiểu controlled. Sau cancel, tạo một **subscription khác ngoài transactional operator** để đọc database và kỳ vọng row bị rollback.

Không viết test chỉ:

```java
StepVerifier.create(insert("R-CANCEL", 1)
        .then(Mono.never())
        .as(transactionalOperator::transactional))
        .thenCancel()
        .verify();
```

rồi kết luận “đã chứng minh rollback”, vì cancel có thể xảy ra **trước khi INSERT thật chạy**. Một test hủy hợp lệ cần chứng minh point-of-progress trước cancel; tốt hơn là dùng scheduler/demand/callback rõ ràng thay vì `Thread.sleep(50)`.

## 14. Test database isolation và test data lifecycle

### 14.1. @JdbcTest rollback giúp gì, không giúp gì?

Trong một test-managed transaction JDBC:

- INSERT/UPDATE/DELETE dùng cùng transactional DataSource thường rollback sau test.
- Một transaction `REQUIRES_NEW` có thể commit độc lập.
- Một async task/thread ngoài transaction test có thể commit độc lập.
- Hệ thống ngoài như queue, file, remote HTTP không tự rollback.
- DDL có thể auto-commit hoặc có semantics khác tùy database.
- Preemptive timeouts có thể tách execution khỏi transaction gắn với thread.

Vì thế mặc định rollback rất hữu ích, nhưng không phải cleanup bảo đảm cho **mọi side effect**.

### 14.2. @DataR2dbcTest cần cleanup rõ

Reactive test cần kiểm soát:

- Publisher có được subscribe/verify không?
- TransactionalOperator có bao quanh đầy đủ write pipeline không?
- Terminal là complete, error hay cancel?
- SQL đã commit hay rollback?
- Có data đã commit từ test trước trong cùng H2 context không?
- Cleanup có thật sự được subscribe và chờ complete không?

Một cleanup kiểu:

```java
client.sql("delete from ledger_entries where code = :code")
        .bind("code", "R-COMMIT")
        .fetch()
        .rowsUpdated();
```

chỉ **tạo Publisher** — chưa chắc đã xóa. Cần:

```java
StepVerifier.create(
        client.sql("delete from ledger_entries where code = :code")
                .bind("code", "R-COMMIT")
                .fetch()
                .rowsUpdated())
        .expectNextCount(1)
        .verifyComplete();
```

Nếu cleanup cần tự xử lý error, hãy để test fail rõ ràng khi cleanup không chạy. Với integration suite lớn, thường nên dùng schema/database/container riêng mỗi nhóm test hoặc seed/reset có kiểm soát thay vì dựa vào thứ tự chạy.

### 14.3. H2 không đại diện mọi behavior của PostgreSQL/MySQL

H2 giúp tái lập nhanh và kiểm tra transaction boundaries cơ bản. Nhưng khác biệt cần test trên engine thực tế gồm:

- isolation level và read phenomena;
- lock wait/deadlock, snapshot semantics, MVCC;
- SQL dialect và kiểu dữ liệu;
- generated keys/identity/sequence;
- constraint timing và lỗi duplicate key;
- DDL transaction semantics;
- behavior của pool, driver và network timeout.

Nếu nghiệp vụ cần chắc chắn trên PostgreSQL, dùng Testcontainers PostgreSQL và **hai driver khác nhau** (JDBC cho JDBC test, R2DBC Postgres cho R2DBC test). Dùng cùng một loại database **không** có nghĩa JDBC/R2DBC cùng transaction.

### 14.4. Testcontainers và migrations

Khi đưa Flyway/Liquibase vào test:

- Không mặc định migration JDBC được tự áp lên R2DBC ConnectionFactory nếu không có DataSource/migration configuration tương ứng.
- `schema.sql` minh họa đủ cho bài học; trong project thật có thể để schema migrations tạo bảng trước test.
- Tránh chạy cả Flyway/Liquibase và `schema.sql` trùng bảng nếu không chủ đích.
- Đảm bảo migrations chạy **trước** test queries, không trông đợi StepVerifier tự tạo schema.
- Không chạy destructive schema setup trên production database.

## 15. Isolation và visibility: đọc thấy row chưa chắc đã commit

Với JDBC:

```text
TX-JDBC:
  INSERT code='X'
  SELECT code='X' -> thấy X trong cùng transaction
  ROLLBACK
OUTSIDE TRANSACTION:
  SELECT code='X' -> không còn X
```

Với R2DBC:

```text
Subscriber -> TransactionalOperator:
  INSERT code='Y'
  SELECT code='Y' trong same Reactor Context -> thấy Y
  onError -> ROLLBACK
New subscriber / new operation:
  SELECT code='Y' -> không còn Y
```

Test case thứ tư của phần R2DBC kiểm chứng rõ điều này: `AtomicLong seenInside` nhận 1 bên trong transaction trước khi pipeline phát error; sau rollback, query mới nhận 0.

Nếu giao dịch B đọc trong khi giao dịch A **chưa commit**, B có thể thấy row cũ hoặc bị lock/chặn theo isolation/engine. **Không suy ra transaction đã flush/commit chỉ từ một query cùng connection**.

### 15.1. Test rollback cần quan sát sau boundary

Trong JDBC test, `TestTransaction.end()` cho phép kiểm tra ngay sau rollback. Trong R2DBC test, StepVerifier phải chờ transactional Publisher terminate, rồi **mới chạy** query ở subscription ngoài operator để đọc state.

Một test chỉ assert exception class và kết thúc không chứng minh rollback đã để database sạch. Kết hợp hai assertions: **terminal error** và **database count sau transaction**.

### 15.2. Test commit cần dọn data

Nếu muốn chứng minh commit, phải quan sát dữ liệu sau transaction và cleanup. Cả hai project ví dụ có test commit và delete fixture ở `finally`. Đừng gọi `@DirtiesContext` rồi nghĩ nó xóa rows đã commit trong database: annotation chủ yếu tác động Spring TestContext cache, không thay transaction cleanup.

## 16. Error recovery và rollback rules: ba loại thất bại khác nhau

### 16.1. JDBC exception trong callback

```java
template.executeWithoutResult(status -> {
    jdbc.update("insert into ledger_entries(code, amount) values (?, ?)",
            "J-FAIL", 1);
    throw new IllegalStateException("failed");
});
```

TransactionTemplate thấy runtime exception và rollback. Trong test, `assertThatThrownBy(...)` có thể xác nhận error; JDBC query sau callback chứng minh không còn dữ liệu.

### 16.2. R2DBC terminal error

```java
Mono<Void> work = insert("R-FAIL", 1)
        .then(Mono.<Void>error(new IllegalStateException("failed")))
        .as(transactionalOperator::transactional);
```

Khi subscribe, operator sẽ rollback theo onError. Test dùng `expectErrorMatches(...)` và query sau transaction.

### 16.3. R2DBC error được recovery trước transaction boundary

```java
Mono<Void> work = insert("R-RECOVER", 1)
        .then(Mono.<Void>error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

Operator nhìn thấy completion; nó có thể commit. Đây là behavior khác với trường hợp recovery đặt **bên ngoài** operator. Tên method test, code review và application transaction boundary phải làm rõ **rollback là business policy hay chỉ là hệ quả thứ tự operators**.

### 16.4. Checked exceptions và business errors

Với declarative JDBC `@Transactional`, default rollback rules cho checked exceptions khác runtime exceptions (có thể tùy cấu hình Spring Framework version). Với Spring Framework 6.2+ có hỗ trợ cấu hình mặc định toàn cục cho rollback rules; đừng khái quát checked exceptions luôn commit trên mọi ứng dụng.

Reactive Publisher truyền lỗi qua `onError(Throwable)`; Spring reactive transaction operator thông thường rollback khi nhận onError. Khi business cần commit một phần hoặc dùng `setRollbackOnly()`, hãy viết test explicit cho chính policy ấy, không đoán từ việc exception checked hay unchecked ở Java source.

## 17. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có khả năng | Hướng xử lý |
|---|---|---|
| JDBC test insert rồi sau test row mất | `@JdbcTest` rollback mặc định | Hành vi đúng; dùng TestTransaction để kiểm chứng |
| R2DBC test insert rồi test sau vẫn thấy row | `@DataR2dbcTest` mặc định không transactional | Bọc transaction phù hợp và cleanup committed data |
| R2DBC SQL “không chạy” | Tạo Publisher nhưng quên subscribe/verify | StepVerifier `verify...` terminal |
| R2DBC test xanh chỉ vì `assertNotNull(mono)` | Chỉ kiểm tra assembly, không chạy DB | StepVerifier với value/error/completion |
| R2DBC rollback test vẫn còn row | Error bị recovery **trước** operator; hoặc write khác subscription | Đặt boundary chính xác; assert DB sau terminal |
| JDBC `TransactionTemplate` commit test không nhìn thấy commit ngoài tx | Template đang tham gia outer test-managed transaction | `NOT_SUPPORTED` cho test, hoặc tạo explicit boundary |
| JDBC test rollback nhưng async task vẫn commit | Thread khác không mang TransactionSynchronizationManager | Không dùng detached async work; transaction/cleanup riêng |
| @Transactional trên test R2DBC không rollback | Listener không mở reactive transaction bằng ReactiveTransactionManager | Dùng TransactionalOperator/proxied reactive service |
| R2DBC @Transactional trên class tạo bằng new vô hiệu | Không qua Spring AOP proxy | Test qua bean Spring hoặc programmatic operator |
| `selfInvocation()` không được transaction | Proxy bị bypass | Refactor qua public proxied bean/method hoặc dùng programmatic |
| JDBC và R2DBC trên cùng DB nhưng không atomic | Hai managers/connections khác nhau | Tách transaction/saga/outbox, không giả định auto-join |
| JDBC trong reactive pipeline làm nghẽn event loop | `JdbcTemplate` blocking | Dùng R2DBC cho reactive DB path hoặc offload có kiểm soát, không biến thành same tx |
| R2DBC query trong transaction đọc 1, ngoài thấy 0 | Đã rollback hoặc isolation khác | Xem terminal/error và boundary, kiểm tra DB engine |
| StepVerifier pass nhưng DB không clean | Chỉ assert value/terminal, quên cleanup | Query sau transaction + explicit delete/schema reset |
| VirtualTime khiến DB test treo | Virtual scheduler không tăng tốc R2DBC network/driver | Dùng real bounded timeout; tránh giả lập DB I/O |
| R2DBC test cancel và không commit | Spring rollback on cancel | Kiểm tra downstream `take/next/timeout` và rollback |
| H2 test pass nhưng PostgreSQL fail | Driver/dialect/isolation/locking khác | Integration tests trên production DB engine |
| Schema table not found | SQL initializer không chạy hoặc wrong db/schema URL | Đặt `schema.sql` đúng resource, mode, URL và init order |
| “No qualifying bean ReactiveTransactionManager” | R2DBC transaction auto-config chưa có hoặc multi-manager ambiguity | Kiểm tra starter, ConnectionFactory và transaction manager beans |
| Cả JDBC và R2DBC bean config bất ngờ thiếu | Đưa hai stacks vào một Boot module làm auto-config thay đổi | Tách modules hoặc cấu hình rõ managers/DataSource/ConnectionFactory |
| SQL duplicate key chạy riêng thì pass, chạy suite fail | R2DBC commit data còn sót hoặc share schema | Cleanup, isolated DB/schema và unique fixtures |

### 17.1. Debug theo checklist có thứ tự

1. **Nhìn lại test annotation:** `@JdbcTest` hay `@DataR2dbcTest`?
2. **Nhìn lại manager bean:** `PlatformTransactionManager` hay `ReactiveTransactionManager`?
3. **Xác định transaction boundary:** test listener, proxy method hay operator?
4. **Với R2DBC:** có subscription thật và verify terminal không?
5. **Kiểm tra composed pipeline:** có detached `subscribe()`, `flatMap`, `then` bị bỏ sót không?
6. **Kiểm tra signal:** `onComplete`, `onError` hay `cancel`?
7. **Kiểm tra error recovery placement:** bên trong hay bên ngoài operator?
8. **Kiểm tra code dùng đúng resource:** `JdbcTemplate`/DataSource hay `DatabaseClient`/ConnectionFactory?
9. **Kiểm tra DB sau boundary:** query ở transaction/subscription mới.
10. **Kiểm tra cleanup và isolation:** data còn sót, schema sharing, parallel workers.
11. **Nếu chỉ production lỗi:** database engine, driver, pool, lock, isolation, network timeout.
12. **Kiểm tra test runner:** JUnit methods đã chạy thật, không bị skip/cached giả.

## 18. Lưu ý về timeout, concurrency và dữ liệu nhạy cảm

### 18.1. Timeout trong JDBC test

JUnit `assertTimeoutPreemptively` có thể thực hiện body trên thread khác, khiến test-managed transaction ThreadLocal không còn hiệu lực cho SQL bên trong. Spring TestContext docs cảnh báo rõ trường hợp này. Nếu cần assert duration, ưu tiên cách **không thay thread** khi đang dựa vào rollback TestContext, hoặc cấu hình một transaction riêng trong worker thread có cleanup chắc chắn.

### 18.2. Timeout trong Reactor test

`StepVerifier.verify(Duration)` giới hạn thời gian chờ verification. Nó **không tự đảo ngược một giao dịch SQL đã commit** nếu một Publisher khác đã subscribe/commit bên ngoài operator.

Ví dụ:

```java
StepVerifier.create(transactionalWork)
        .expectNext(1L)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Đây là snippet minh họa; cần `Duration` import. Với R2DBC DB thật, timeout phải dựa trên latency/CI budget hợp lý; timeout quá ngắn tạo flaky tests. Timeout có thể dẫn tới cancellation/rollback trên transaction nếu subscription bị cancel; phải kiểm tra semantics riêng, không suy đoán chỉ từ trạng thái JUnit timeout.

### 18.3. Parallel test và database

- Đừng dùng cùng một fixed primary key cho nhiều test song song trên cùng database.
- H2 in-memory thích hợp cho học tập, nhưng có thể dùng chung DB giữa context nếu cùng named memory URL.
- Với committed data, cần cleanup trong `finally` hoặc fixture teardown đã được subscribe.
- Các test có transaction/cleanup không nên chạy song song trên một bảng shared mà không khóa/partition dữ liệu.
- Không dùng dữ liệu khách hàng, secrets hoặc production DSN trong test.
- Khi debug, logging bind parameters có thể lộ dữ liệu; chỉ dùng fixtures giả và masking phù hợp.

## 19. Bài tập luyện tập

### Bài tập A — JDBC test dữ liệu biến mất

Một test dùng `@JdbcTest`, gọi `jdbcTemplate.update(...)`, rồi cùng method đọc COUNT thấy 1. Sau test database không có row. Có phải Spring lỗi?

**Đáp án:** không. `@JdbcTest` tạo test-managed transaction rollback mặc định. Query cùng transaction thấy SQL đã ghi, nhưng transaction chưa commit; rollback cuối test hoàn tác row.

### Bài tập B — R2DBC test không ghi gì

Code:

```java
Mono<Long> inserted = client.sql(
        "insert into ledger_entries(code, amount) values ('A', 10)")
        .fetch().rowsUpdated();
```

Không có dữ liệu trong DB. Vì sao?

**Đáp án:** chưa subscribe. Publisher từ DatabaseClient thường chỉ mô tả công việc. Cần `StepVerifier.create(inserted).expectNext(1L).verifyComplete()` hoặc compose vào một service reactive được subscribe.

### Bài tập C — R2DBC test khác JDBC rollback mặc định

Nếu bạn chuyển từ `@JdbcTest` sang `@DataR2dbcTest` nhưng vẫn dựa vào tự động rollback cuối test, điều gì có thể xảy ra?

**Đáp án:** `@DataR2dbcTest` không tự mở test-managed transaction mặc định. Những reactive writes có thể commit và ảnh hưởng test sau. Cần TransactionalOperator/proxied reactive @Transactional và cleanup rõ ràng.

### Bài tập D — Lỗi được recovery ở đâu?

So sánh:

```java
Mono<Void> a = insertA()
        .then(Mono.error(new IllegalStateException()))
        .onErrorResume(e -> Mono.empty())
        .as(op::transactional);

Mono<Void> b = insertB()
        .then(Mono.error(new IllegalStateException()))
        .as(op::transactional)
        .onErrorResume(e -> Mono.empty());
```

Cả hai khi subscribe đều hoàn tất thành công về phía test. Trường hợp nào có thể commit?

**Đáp án:** `a` có thể commit vì operator chỉ nhận completion sau recovery. `b` rollback trong operator vì operator đã nhận error; recovery nằm ngoài. Phải xác minh bằng DB query sau terminal.

### Bài tập E — JDBC transaction và CompletableFuture

Trong test-managed JDBC transaction, một tác vụ `CompletableFuture.runAsync(...jdbcTemplate.update...)` được chạy trên worker thread. Test thread rollback, nhưng row vẫn còn. Vì sao?

**Đáp án:** transaction context imperative gắn vào thread qua ThreadLocal, không tự truyền sang worker thread. Worker có thể dùng connection khác và autocommit. Phải quản lý transaction/cleanup riêng, không dựa vào rollback của test thread.

### Bài tập F — Test reactive hủy trước khi INSERT chạy

Bạn viết `StepVerifier.create(insert().then(Mono.never()).as(op::transactional)).thenCancel().verify()` rồi query sau đó thấy 0. Đã chứng minh rollback chưa?

**Đáp án:** chưa chắc. Có thể cancellation xảy ra trước khi INSERT được subscribe/thực thi. Cần xác nhận SQL hoàn tất **trong transaction** trước khi cancel, rồi kiểm tra DB sau cancellation.

### Bài tập G — JDBC và R2DBC cùng trỏ một DB

Một `TransactionTemplate` dùng JDBC và `TransactionalOperator` dùng R2DBC kết nối cùng PostgreSQL. Có thể coi đây là một transaction atomic không?

**Đáp án:** không. Hai transaction managers/connections khác nhau; không tự join thành distributed transaction. Thiết kế workflow, event/outbox hoặc giao thức transaction phù hợp theo yêu cầu; kiểm tra failure/partial commit.

### Bài tập H — @Transactional và self-invocation

Một reactive service có method `@Transactional Mono<Void> save()`, nhưng một method khác cùng instance gọi `this.save()`. Có bảo đảm interception không?

**Đáp án:** không trong Spring proxy mode thông thường. Self-invocation bypass proxy. Refactor qua bean/proxy phù hợp hoặc dùng TransactionalOperator nếu muốn kiểm soát rõ.

### Bài tập I — Commit một bộ thay đổi R2DBC

Bạn dùng `TransactionalOperator` bọc hai writes. Test chỉ kiểm tra `verifyComplete()`, không query DB sau đó. Đã chứng minh commit thành công theo hợp đồng chưa?

**Đáp án:** chỉ chứng minh transactional Publisher hoàn tất không báo lỗi ở test. Để kiểm tra dữ liệu đã commit và đúng content, query trong một subscription ngoài operator sau terminal, rồi cleanup.

## 20. Checklist trước khi chốt bài kiểm thử transaction

- [ ] Xác định JDBC/JPA (imperative) hay R2DBC (reactive).
- [ ] Xác định manager thực tế: PlatformTransactionManager hay ReactiveTransactionManager.
- [ ] Không giả định `@JdbcTest` và `@DataR2dbcTest` rollback giống nhau.
- [ ] Với JDBC, biết test-managed transaction có active/rollback flag không.
- [ ] Với R2DBC, biết pipeline nào được bọc bởi `TransactionalOperator`.
- [ ] Với R2DBC, mọi DB Publisher đã được subscribe và chờ terminal.
- [ ] Không dùng `assertNotNull(Mono)` như chứng minh SQL đã chạy.
- [ ] Không gọi detached `subscribe()` bên trong pipeline transaction.
- [ ] Không biến JDBC blocking operation thành R2DBC transaction chỉ bằng Mono wrapper.
- [ ] Kiểm tra Spring AOP proxy khi dùng `@Transactional` trên service.
- [ ] Phân biệt recovery bên trong/bên ngoài reactive transaction.
- [ ] Kiểm tra cancel/timeout và tác động rollback khi thuộc contract.
- [ ] Không nhầm same-transaction visibility với committed visibility.
- [ ] Test rollback bằng query **sau transaction boundary**, không chỉ assert exception.
- [ ] Test commit bằng query ở transaction mới và cleanup.
- [ ] Không dùng JUnit preemptive timeout như thể JDBC test transaction vẫn luôn đi theo thread.
- [ ] H2 chỉ là DB thử nghiệm, có thêm production-engine integration tests khi cần isolation/locking/SQL semantics.
- [ ] Schemas/resources/SQL init chạy đúng với DataSource hoặc ConnectionFactory.
- [ ] Không chạy cả JDBC và R2DBC auto-config trong một module mà không kiểm soát managers/resources.
- [ ] Không dùng production database, endpoint hoặc credentials cho test.
- [ ] JUnit test count, Gradle/Maven version và dependencies đã kiểm tra trên môi trường chạy.
- [ ] Không dùng `@DirtiesContext` thay cho cleanup rows đã commit.
- [ ] Không gọi `block()` trên reactive event-loop khi ứng dụng production yêu cầu non-blocking.
- [ ] Hành vi có liên quan cache, retry, optimistic locking hoặc isolation có test riêng khi cần.

## 21. Tổng kết

**JDBC transaction và R2DBC reactive transaction cùng giải quyết tính nguyên tử của thao tác SQL, nhưng không dùng chung cơ chế ngữ cảnh.**

- **JDBC:** công việc xảy ra qua imperative connection trên thread; `TransactionTemplate` hoặc `@Transactional` với `PlatformTransactionManager` quản lý transaction. Trong Spring Boot 3.x, `@JdbcTest` thường rollback test transaction mặc định.
- **R2DBC:** công việc nằm trong các Publishers, bắt đầu khi subscribe; `TransactionalOperator` hoặc proxied reactive `@Transactional` với `ReactiveTransactionManager` quản lý transaction gắn vào Reactor Context. `@DataR2dbcTest` mặc định **không transactional**.
- **Kiểm thử đúng:** xác nhận cả tín hiệu/kết quả và **database state sau commit/rollback**. Đừng suy luận rollback chỉ từ tên annotation, và đừng suy luận commit từ việc cùng transaction đọc thấy row.
- **Thiết kế an toàn:** compose các reactive operations trong một pipeline, tránh detached subscription và blocking JDBC trộn vào reactive transaction; dùng cleanup rõ cho data đã commit, cùng DB engine production khi cần kiểm chứng isolation/locking.

Tư duy transaction boundary rõ ràng sẽ giúp các bài kiểm thử JDBC và R2DBC đáng tin, tránh lỗi data leakage và những lần test xanh nhưng production vẫn mất tính nhất quán.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest` rollback mặc định, `@DataR2dbcTest` không transactional mặc định.
- [Spring Boot 3.5 — Test Slice Auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): cấu hình DataSource/JDBC và ConnectionFactory/R2DBC theo test slice.
- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed transactions, PlatformTransactionManager, rollback, TestTransaction và preemptive-timeout caveats.
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): PlatformTransactionManager vs ReactiveTransactionManager, thread-bound và reactive transaction SPI.
- [Spring Framework — Declarative Transaction Explained](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): imperative vs reactive @Transactional, return types, Reactor Context.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): TransactionTemplate, TransactionalOperator và rollback on cancel.
- [Spring Framework — R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html): lazy SQL, rowsUpdated, bind, ConnectionFactoryUtils và R2dbcTransactionManager.
- [Spring Data Relational — R2DBC Getting Started](https://docs.spring.io/spring-data/relational/reference/r2dbc/getting-started.html): R2DBC SQL, H2 driver và setup.
- [R2DBC H2 Driver — Documentation](https://github.com/r2dbc/r2dbc-h2): in-memory URL, connection options, transactional support.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): subscribe, terminal verification, async publisher behavior.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): schema.sql và initialization cho JDBC/R2DBC; tùy phiên bản.
