# Giao dịch Reactive và khác biệt với cơ chế ThreadLocal trong Spring Boot

## 1. Tại sao một `@Transactional` quen thuộc có thể hành xử khác trong WebFlux/R2DBC?

Trong Spring Boot, nhiều lập trình viên đã quen với cách viết một service đồng bộ:

```java
@Transactional
public void moveMoney() {
    debitAccount();
    creditAccount();
}
```

Khi service sử dụng JDBC/JPA và được gọi qua Spring proxy, transaction thường được liên kết với **thread đang thực thi**. Nhưng trong một luồng xử lý Reactive, việc xử lý một request có thể chuyển qua nhiều thread, công việc thực tế chỉ được bắt đầu khi có **subscription**, và `Mono`/`Flux` mang theo một **Reactor Context** riêng cho subscriber.

Ví dụ sau trông gần giống mã đồng bộ nhưng là một hợp đồng khác:

```java
@Transactional
public Mono<Void> moveMoney() {
    return debitReactive()
            .then(creditReactive());
}
```

Đây là **đoạn minh họa**, cần các method reactive thực, bean/service proxy và `ReactiveTransactionManager` đúng. Transaction reactive không được nhận biết bằng `ThreadLocal` kiểu JDBC/JPA. Spring dùng Reactor Context để liên kết **R2DBC Connection, trạng thái transaction và từng thao tác database trong cùng reactive pipeline**.

**Ba quy tắc trọng tâm:**

1. **Imperative**: `PlatformTransactionManager` (ví dụ `JpaTransactionManager`, `DataSourceTransactionManager`) thường gắn state/resource vào **thread**.
2. **Reactive**: `ReactiveTransactionManager` (ví dụ `R2dbcTransactionManager`) gắn state/resource vào **subscriber context**. Thread có thể thay đổi mà transaction vẫn đúng, nếu Reactor Context được truyền qua pipeline chuẩn.
3. **`@Transactional` không biến một thao tác ngoài pipeline thành cùng giao dịch**. Tự gọi `.subscribe()`, tạo publisher khác rồi không chain, dùng JDBC blocking ngoài transaction hoặc làm mất Reactor Context có thể khiến phần việc không còn tham gia transaction dự định.

Bài học hướng tới **Spring Boot testing**: cách tạo một transaction reactive thật, kiểm tra commit/rollback bằng `StepVerifier`, chứng minh những ranh giới sai thường bị bỏ qua, và hiểu vì sao `@DataR2dbcTest` **không tự rollback test** giống `@DataJpaTest`.

Phần code hoàn chỉnh dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, Reactor, R2DBC H2 và JUnit Jupiter**. Spring Boot 4.x có thay đổi module/import của test slice; nguyên tắc Reactor Context vẫn giữ.

## 2. ThreadLocal và Reactor Context: hai mô hình độc lập

### 2.1. Giao dịch đồng bộ dùng thread-bound resource

Trong JDBC/JPA, Spring có `org.springframework.transaction.support.TransactionSynchronizationManager`. Transaction interceptor mở transaction, liên kết connection/persistence context với thread, chạy method rồi quyết định commit/rollback.

```text
Thread A:
    Controller -> @Transactional Service -> JdbcTemplate -> DataSource
                  |                        |
                  +-- ThreadLocal tx state-+
    method return -> transaction manager commit/rollback
```

Lời gọi trong **cùng thread và đúng transaction manager** có thể sử dụng cùng connection. Nhưng nếu code tạo một thread mới bằng `new Thread`, `CompletableFuture` hoặc executor, ThreadLocal này **không mặc nhiên** được kế thừa sang thread đó. Gọi `@Transactional` không tự biến JDBC thành API reactive.

### 2.2. Giao dịch reactive dùng subscriber-bound context

Spring Framework có `org.springframework.transaction.reactive.TransactionSynchronizationManager`. Đây là **một lớp khác**, không phải lớp static `support.TransactionSynchronizationManager` của imperative.

```text
Subscriber S1 + Reactor Context { tx resource / R2DBC connection }
    |
    +-- Mono SQL INSERT A
    |
    +-- then / flatMap
    |
    +-- publishOn (có thể sang Thread B)
    |
    +-- Mono SQL INSERT B
    |
    +-- onComplete -> commit (theo transaction operator)
        onError / cancel -> rollback theo semantics
```

Chính **Reactor Context liên quan subscription**, chứ không phải “thread hiện tại có tên gì”, giúp các thao tác R2DBC dùng connection/transaction đúng. Khi giữ pipeline được compose hợp lệ, một `publishOn` không đồng nghĩa transaction tự mất.

**Không nhầm Reactor Context với MDC logging ThreadLocal.** Trace ID hoặc MDC muốn đi qua thread switch có thể cần cơ chế context propagation riêng. Việc log mất MDC không tự chứng minh DB transaction đã biến mất; phải quan sát transaction resource hoặc DB state.

### 2.3. Bảng so sánh

| Đặc tính | Imperative JDBC/JPA | Reactive R2DBC |
|---|---|---|
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Ví dụ implementation | `JpaTransactionManager`, `DataSourceTransactionManager` | `R2dbcTransactionManager` |
| Resource holder | ThreadLocal của Spring transaction infrastructure | Reactor Context gắn với subscriber |
| Thời điểm làm việc | Thường trong lời gọi đồng bộ của method | Khi publisher được subscribe và tín hiệu được tiêu thụ |
| API production | `TransactionTemplate`, `@Transactional` trên method thường | `TransactionalOperator`, `@Transactional` trên `Mono/Flux` |
| Data access | `JdbcTemplate`, `EntityManager` | `DatabaseClient`, `R2dbcEntityTemplate`, reactive repositories |
| Ranh giới completion | Method đồng bộ trả/throw | Reactive `onComplete`/`onError`/`cancel` |
| Thread switch | Không tự truyền ThreadLocal tới thread mới | Reactor Context thường được giữ khi compose đúng |
| Test bằng | JUnit + JDBC/JPA slices, đôi khi `TestTransaction` | Reactor Test `StepVerifier`, R2DBC thực, explicit operator |
| Tự rollback trong test slice | `@JdbcTest`/`@DataJpaTest` thường rollback | `@DataR2dbcTest` **mặc định không transactional** |
| Một publisher bị subscribe hai lần | Không phải mô hình chính | Có thể khởi tạo **hai execution/transactions** độc lập |

## 3. Spring xác định kiểu `@Transactional` như thế nào?

Spring `TransactionInterceptor` hỗ trợ cả hai mô hình. Với các method trả về **reactive type** như `Publisher`/`Mono`/`Flux`, Spring có thể áp dụng reactive transaction khi sử dụng `ReactiveTransactionManager`. Các method thông thường, kể cả `void`, cần **imperative transaction manager** cho cơ chế thông thường.

Ví dụ **đúng** cho R2DBC:

```java
@Transactional
public Mono<Void> createOrder(String id) {
    return db.sql(
            "INSERT INTO orders(id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then();
}
```

Đoạn trên là method minh họa (cần `DatabaseClient db`, bảng `orders`, Spring proxy và R2DBC transaction manager). **Publisher được trả về** để caller/framework subscribe. Spring transaction advice bao bọc **execution của publisher**, không coi việc dựng ra đối tượng `Mono` ở thời điểm gọi method là commit.

Ví dụ **sai** cho mục tiêu R2DBC transaction:

```java
@Transactional
public void createOrderWrong(String id) {
    db.sql("INSERT INTO orders(id) VALUES (:id)")
            .bind("id", id)
            .fetch().rowsUpdated()
            .subscribe();
}
```

Đây là **anti-pattern minh họa**, không phải đoạn mã trong project runnable. Vấn đề:
- Method trả `void`, không cung cấp publisher để reactive transaction interceptor quản lý.
- `.subscribe()` tự tạo một execution độc lập; exception/rollback không được trả lại cho caller.
- Nếu chỉ có `ReactiveTransactionManager`, advice không thể chuyển một method `void` thành reactive transactional operation.
- Ngay cả khi không lỗi ở bước proxy, một `subscribe()` tự phát vẫn có thể chạy ngoài transaction/pipeline mong đợi.

Một vấn đề khác là **self-invocation**: `this.createOrder(id)` trong cùng bean thường không đi qua Spring AOP proxy của `@Transactional`. Test phải gọi method thông qua Spring bean/proxy hoặc sử dụng một `TransactionalOperator` trong pipeline.

## 4. R2dbcTransactionManager và TransactionalOperator

`R2dbcTransactionManager` quản lý transaction cho một `ConnectionFactory` R2DBC, gắn connection với Reactor Context của subscriber. Spring `DatabaseClient` và hạ tầng Spring Data R2DBC dùng cơ chế `ConnectionFactoryUtils` tương ứng để lấy connection đã liên kết.

`TransactionalOperator` là API programmatic thuận tiện:

```java
TransactionalOperator tx =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Void> work = insertA()
        .then(insertB())
        .as(tx::transactional);
```

Đoạn trên là **ví dụ trong scope có `ReactiveTransactionManager` và các `Mono` thao tác R2DBC**. Khi publisher `work` được subscribe:
- Transaction operator mở transaction.
- `insertA()` được thực hiện.
- Sau khi A hoàn tất, `insertB()` được thực hiện trong **cùng reactive transaction**.
- Khi cả pipeline hoàn tất bình thường, operator commit.
- Khi pipeline phát `onError` chưa được phục hồi trước ranh giới operator, operator rollback.
- Khi subscriber **cancel**, transaction cũng rollback trong cơ chế Spring Reactive hiện đại; chi tiết này quan trọng đối với `take`, `next`, `timeout` và client disconnect.

**Không dùng `Mono.when(insertA(), insertB())` như một công thức “hai SQL song song trong cùng connection”.** Nhiều R2DBC drivers/connection không cho thực hiện các statements đồng thời trên cùng một transaction connection. Dùng `.then(...)` hoặc `concatMap` khi cần chạy tuần tự, trừ khi bạn đã thiết kế và kiểm chứng concurrency model phù hợp.

### 4.1. API Operator-style và Callback-style

Operator-style:

```java
return insertA()
        .then(insertB())
        .as(tx::transactional);
```

Callback-style:

```java
return tx.execute(status ->
        insertA().then(insertB()))
        .then();
```

Trong callback, `status` là `ReactiveTransaction`; có thể dùng `status.setRollbackOnly()` khi cần rollback theo một quyết định domain mà không muốn ném exception. Tuy nhiên, thông thường dễ đọc hơn nếu để lỗi được phát ra từ pipeline rồi để operator rollback theo mặc định.

### 4.2. Vì sao scope transaction phải bao lấy *toàn bộ* work?

So sánh:

```java
Mono<Void> bothInOneTransaction =
        insertA().then(insertB()).as(tx::transactional);
```

với:

```java
Mono<Void> onlyBIsTransactional =
        insertA().then(
                insertB().as(tx::transactional));
```

Trong phiên bản đầu, A và B nằm dưới **cùng operator transaction**. Trong phiên bản sau, A chạy **trước khi subscribe publisher của B có operator**, nên A có thể auto-commit ngoài transaction của B. Nếu B lỗi và rollback, A không tự bị xóa.

Khi review code, đừng chỉ tìm xem dự án có `@Transactional` hay `TransactionalOperator` không; hãy xác định **thực tế operator bao quanh những publisher nào**.

## 5. Reactor Context là gì, khác ThreadLocal ở điểm nào?

Reactor Context là một cấu trúc key/value liên quan **subscription** được Reactor đưa qua các operator theo quy tắc của nó. Nó hỗ trợ những trạng thái như transaction context hoặc tracing mà không phụ thuộc **một thread luôn cố định**.

### 5.1. Một ví dụ Reactor Context đơn giản, không cần database

Tệp `ReactorContextMiniDemo.java`:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class ReactorContextMiniDemo {
    public static void main(String[] args) {
        String value = Mono.deferContextual(context ->
                Mono.just(context.get("requestId")))
                .publishOn(Schedulers.parallel())
                .contextWrite(context -> context.put("requestId", "REQ-42"))
                .block();

        System.out.println(value);
    }
}
```

**Expected stdout, nếu chạy thành công với Reactor Core có trên classpath:**

```text
REQ-42
```

Đây là một **Java main class đầy đủ**, nhưng cần Reactor Core dependency khi biên dịch/chạy. Đối với project Spring Boot dùng Reactor, đặt class vào test/demo source set rồi dùng Gradle/Maven `JavaExec` hoặc IDE run với classpath đã cấu hình. Đoạn `.block()` ở đây chỉ được dùng ở **main demo trên thread bình thường** để chờ kết quả cho stdout; không copy `.block()` vào event-loop handler WebFlux.

`publishOn` làm thay đổi scheduler cho các tín hiệu phía sau, nhưng `contextWrite` và `deferContextual` cho thấy Context không đơn giản là `ThreadLocal`. Nó không phải bằng chứng cho một transaction R2DBC thực: DB transaction cần **reactive transaction manager** và connection thật.

### 5.2. Quan sát context của Spring transaction

Khi một pipeline nằm **trong reactive transaction**, có thể quan sát trạng thái bằng API Spring:

```java
Mono<Boolean> active =
        org.springframework.transaction.reactive
                .TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(manager -> manager.isActualTransactionActive())
                .as(tx::transactional);
```

Đây là **đoạn minh họa** trong class có `TransactionalOperator tx`; Java không cho xuống dòng giữa tên package ở cú pháp như ví dụ trên nếu viết trực tiếp, nên khi sử dụng hãy import class theo mục tiếp theo. Kết quả bình thường là `true` khi có một actual reactive transaction được mở. Không dùng API này để tự bind/unbind connection trong service business thường ngày.

**Hai kiểu `TransactionSynchronizationManager` hoàn toàn khác:**

```java
// Imperative: static, thread-bound
org.springframework.transaction.support
        .TransactionSynchronizationManager
        .isActualTransactionActive();

// Reactive: instance, lấy từ Reactor Context
org.springframework.transaction.reactive
        .TransactionSynchronizationManager
        .forCurrentTransaction();
```

Các dòng là **minh họa import/API**, không phải file Java độc lập. Trong code thật, import class đúng và giữ lời gọi hợp lệ. Việc gọi imperative `isActualTransactionActive()` trên thread reactive không chứng minh transaction R2DBC đã mở hoặc chưa mở.

## 6. Một dự án Spring Boot 3.5 + R2DBC H2 + StepVerifier đầy đủ

Mục đích là **chạy SQL thật** nhưng không mang JDBC ThreadLocal vào test. Ví dụ tự kiểm tra:
1. Programmatic transaction ghi hai row và commit.
2. Một lỗi giữa pipeline khiến row đầu rollback.
3. Error recovery **bên trong** transaction có thể biến lỗi thành completion và cho phép commit phần đã ghi.
4. Error recovery **bên ngoài** transaction cho phép rollback trước khi fallback được áp dụng.
5. Reactive `@Transactional` qua Spring proxy.
6. Transaction state qua **Reactive TransactionSynchronizationManager**.
7. Publisher lazy: chỉ dựng `Mono` chưa chạm database.
8. Hai subscription của cùng một cold publisher có thể thực hiện thao tác **hai lần**.
9. `publishOn` đổi scheduler mà Reactor Context vẫn được giữ trong pipeline compose đúng.

### 6.1. Cấu trúc file

```text
build.gradle
src/main/java/com/example/reactivetx/
    ReactiveTxApplication.java
    LedgerService.java
src/test/resources/
    application.properties
    sql/ledger-schema.sql
src/test/java/com/example/reactivetx/
    ReactiveTransactionTest.java
```

### 6.2. build.gradle (Java 17, Spring Boot 3.5.x)

Tệp `build.gradle` dùng Gradle Groovy DSL:

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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    testRuntimeOnly 'io.r2dbc:r2dbc-h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM đồng bộ Reactor, Spring Framework và driver versions. `r2dbc-h2` là **R2DBC driver**, không phải `com.h2database:h2` JDBC driver để thay thế. Nếu ứng dụng production dùng PostgreSQL, dùng `r2dbc-postgresql` trong runtime production và tách H2 vào test scope đúng yêu cầu.

Không cần `spring-boot-starter-webflux` chỉ để kiểm thử R2DBC transaction tại service; ứng dụng mẫu không có HTTP server. Nếu bạn muốn gọi endpoint WebFlux, có thể thêm starter WebFlux và test client nhưng đó là một phạm vi tích hợp khác.

### 6.3. Application class

Tệp `src/main/java/com/example/reactivetx/ReactiveTxApplication.java`:

```java
package com.example.reactivetx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

### 6.4. Cấu hình database cho test

Tệp `src/test/resources/application.properties`:

```properties
spring.r2dbc.url=r2dbc:h2:mem:///reactive_tx_lab?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:sql/ledger-schema.sql
```

Tệp `src/test/resources/sql/ledger-schema.sql`:

```sql
CREATE TABLE ledger_entries (
    entry_id VARCHAR(120) PRIMARY KEY,
    amount INTEGER NOT NULL CHECK (amount >= 0)
);
```

Lý do cấu hình:
- Boot tạo `ConnectionFactory` từ `spring.r2dbc.url` và R2DBC H2 driver.
- Boot có thể khởi tạo schema cho `ConnectionFactory` bằng SQL scripts; ta đặt đường dẫn tường minh và bật `spring.sql.init.mode=always`.
- `DB_CLOSE_DELAY=-1` giữ H2 in-memory DB sống qua các connection đóng/mở trong cùng process, tránh mất bảng khi reactive connection kết thúc.
- `entry_id` do test tự cung cấp, không phụ thuộc `IDENTITY` hoặc việc lấy generated key.
- Bảng có primary key và check constraint để các lần subscription trùng có thể quan sát lỗi, không tạo bản ghi yên lặng.

**Cẩn thận:** Dùng H2 chứng minh ranh giới transaction của Spring/R2DBC trong setup này, **không tự chứng minh** PostgreSQL/MySQL có cùng isolation, syntax hay lock semantics. Khi yêu cầu production-like, thay URL/driver bằng Testcontainers R2DBC tương ứng và quản lý cleanup/DB lifecycle rõ ràng.

### 6.5. Service reactive thực

Tệp `src/main/java/com/example/reactivetx/LedgerService.java`:

```java
package com.example.reactivetx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public LedgerService(
            DatabaseClient db,
            ReactiveTransactionManager transactionManager) {
        this.db = db;
        this.tx = TransactionalOperator.create(transactionManager);
    }

    private Mono<Void> insert(String id, int amount) {
        return db.sql("""
                INSERT INTO ledger_entries (entry_id, amount)
                VALUES (:id, :amount)
                """)
                .bind("id", id)
                .bind("amount", amount)
                .fetch()
                .rowsUpdated()
                .then();
    }

    public Mono<Integer> countForPrefix(String prefix) {
        return db.sql("""
                SELECT COUNT(*) AS total
                  FROM ledger_entries
                 WHERE entry_id LIKE :pattern
                """)
                .bind("pattern", prefix + ":%")
                .map((row, metadata) ->
                        ((Number) row.get("total")).intValue())
                .one();
    }

    public Mono<Void> writePairProgrammatically(String prefix) {
        return insert(prefix + ":a", 10)
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }

    public Mono<Void> writeThenFail(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("forced failure")))
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }

    public Mono<Void> recoverInsideTransaction(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("recover inside")))
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Mono.empty())
                .as(tx::transactional);
    }

    public Mono<Void> recoverOutsideTransaction(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("recover outside")))
                .as(tx::transactional)
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Mono.empty());
    }

    // Spring AOP proxy xử lý reactive @Transactional trên Publisher.
    @Transactional
    public Mono<Void> writePairDeclaratively(String prefix) {
        return insert(prefix + ":a", 10)
                .then(insert(prefix + ":b", 20));
    }

    public Mono<Boolean> reactiveTransactionIsActive() {
        return TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(TransactionSynchronizationManager
                        ::isActualTransactionActive)
                .as(tx::transactional);
    }

    public Mono<Void> writePairAfterSchedulerSwitch(String prefix) {
        return insert(prefix + ":a", 10)
                .publishOn(Schedulers.parallel())
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }
}
```

**Đọc đúng code:**
- `insert(...)` trả `Mono<Void>`; câu SQL chỉ thực thi khi có **subscription**.
- `.then(...)` thực thi B sau khi A hoàn tất, không gửi hai câu SQL song song vào một R2DBC connection.
- `writePairProgrammatically`: transaction operator bao **cả hai** lần insert.
- `writeThenFail`: sau A phát một `IllegalStateException`, nên B không chạy và operator rollback A.
- `recoverInsideTransaction`: `onErrorResume` **nằm trước** `.as(tx::transactional)` nên operator nhìn thấy `onComplete` thay vì error; A có thể **commit**.
- `recoverOutsideTransaction`: operator nhìn thấy error trước, rollback A, rồi mới có `onErrorResume` **ở ngoài** để xử lý kết quả về phía caller.
- `writePairDeclaratively`: dùng `@Transactional` trên **method public trả `Mono`**, được gọi qua Spring proxy.
- `reactiveTransactionIsActive`: quan sát **reactive** transaction context, không đọc imperative ThreadLocal.
- `publishOn` đổi scheduler trên một đoạn pipeline nhưng không có `.subscribe()` rời rạc; Reactor Context đi qua các operator chuẩn.

**Về transaction manager:** Spring Boot với một R2DBC `ConnectionFactory` thích hợp thường auto-configure `R2dbcTransactionManager`; trong demo chỉ có một reactive manager. Với nhiều managers, chọn đúng `@Transactional(transactionManager=...)` hoặc inject `ReactiveTransactionManager` đã qualifier tường minh. Không mặc định mọi `PlatformTransactionManager` và `ReactiveTransactionManager` có thể quản lý cùng một physical DB transaction.

### 6.6. Bộ JUnit Jupiter + StepVerifier đầy đủ

Tệp `src/test/java/com/example/reactivetx/ReactiveTransactionTest.java`:

```java
package com.example.reactivetx;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.test.context.transaction.TestTransaction;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReactiveTransactionTest {

    @Autowired
    LedgerService ledger;

    @Autowired
    DatabaseClient db;

    // Không có @Transactional trên test class. Mỗi JUnit test
    // sử dụng tiền tố riêng, và cleanup rõ ràng sau mỗi method.
    private final List<String> prefixes = new ArrayList<>();

    private String newPrefix() {
        String prefix = "case-"
                + UUID.randomUUID().toString().replace("-", "");
        prefixes.add(prefix);
        return prefix;
    }

    private Mono<Void> cleanOne(String prefix) {
        return db.sql("""
                DELETE FROM ledger_entries
                 WHERE entry_id LIKE :pattern
                """)
                .bind("pattern", prefix + ":%")
                .fetch()
                .rowsUpdated()
                .then();
    }

    @AfterEach
    void cleanupOutsideTransaction() {
        Mono<Void> cleanup = Flux.fromIterable(prefixes)
                .concatMap(this::cleanOne)
                .then();

        // JUnit test thread: StepVerifier subscribe và đợi completion.
        StepVerifier.create(cleanup).verifyComplete();
    }

    @Test
    void programmaticTransactionCommitsTwoRows() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairProgrammatically(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void errorSignalRollsBackEarlierSql() {
        String prefix = newPrefix();

        StepVerifier.create(ledger.writeThenFail(prefix))
                .expectErrorMatches(
                        error -> error instanceof IllegalStateException
                                && "forced failure"
                                        .equals(error.getMessage()))
                .verify();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();
    }

    @Test
    void recoveryInsideTransactionCanCommitPartialWork() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.recoverInsideTransaction(prefix))
                .verifyComplete();

        // Lỗi đã bị chuyển thành completion TRƯỚC operator.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(1)
                .verifyComplete();
    }

    @Test
    void recoveryOutsideTransactionPreservesRollback() {
        String prefix = newPrefix();

        // Caller thấy completion do fallback ngoài transaction.
        StepVerifier.create(
                ledger.recoverOutsideTransaction(prefix))
                .verifyComplete();

        // Nhưng transaction đã nhận error và rollback trước đó.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();
    }

    @Test
    void declarativeReactiveTransactionCommitsBothRows() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairDeclaratively(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void reactiveContextHasActualTransactionWhileSubscribed() {
        // Test-managed ThreadLocal transaction không được kích hoạt.
        assertFalse(TestTransaction.isActive());

        StepVerifier.create(ledger.reactiveTransactionIsActive())
                .expectNext(true)
                .verifyComplete();

        assertFalse(TestTransaction.isActive());
    }

    @Test
    void creatingPublisherDoesNotRunSqlUntilSubscription() {
        String prefix = newPrefix();
        Mono<Void> operation =
                ledger.writePairProgrammatically(prefix);

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();

        StepVerifier.create(operation).verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void subscribingTwiceRepeatsColdSqlExecution() {
        String prefix = newPrefix();
        Mono<Void> operation =
                ledger.writePairProgrammatically(prefix);

        StepVerifier.create(operation).verifyComplete();

        // Subscription thứ hai cố INSERT lại cùng primary keys.
        StepVerifier.create(operation).expectError().verify();

        // Transaction thứ hai rollback; hai rows đầu vẫn có.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void schedulerSwitchWithinPipelineKeepsTransaction() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairAfterSchedulerSwitch(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }
}
```

Có **9 test methods**. Các assertion được thiết kế để quan sát **database thật sau completion/error**. Không suy ra hai operations đã commit chỉ vì `StepVerifier.verifyComplete()` trên publisher ghi; còn cần truy vấn độc lập như trong test.

**Vì sao cleanup không bị rollback trong test?** Test class không mang `@Transactional` của TestContext; `@AfterEach` dùng R2DBC publisher và `StepVerifier` subscribe để DELETE từng prefix. `@DataR2dbcTest` cũng **không auto-rollback theo mặc định**, nên nếu chuyển sang slice vẫn phải chủ động quản lý fixture/cleanup. Những row được commit trong test vẫn tồn tại cho tới khi cleanup chạy hoặc database in-memory bị hủy.

**Không bịa stdout/test-result:** Bài viết cung cấp mã nguồn và behavior dự kiến; chưa có bằng chứng các test đã chạy trên máy của bạn. Lệnh thực thi và report ở mục 7.

## 7. Chạy test và đọc báo cáo

Nếu dự án có Gradle wrapper, từ root:

```bash
./gradlew test --tests "com.example.reactivetx.ReactiveTransactionTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactivetx.ReactiveTransactionTest"
```

Nếu dùng Maven wrapper với dependencies/BOM tương đương:

```bash
./mvnw -Dtest=ReactiveTransactionTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ReactiveTransactionTest test
```

Gradle reports thường ở `build/reports/tests/test/index.html`, Maven Surefire thường ở `target/surefire-reports/` của đúng module. Hãy xác minh **9 ca được discover/thực thi**, không chỉ build `NO-SOURCE`, `UP-TO-DATE` hoặc test bị skip. Nếu H2 connection URL hoặc SQL init fail, xem root cause của startup trước khi chỉnh assertion.

Trong ví dụ có hai kiểu test:
- `StepVerifier.create(writePublisher).verifyComplete()`: tiêu thụ **toàn bộ** publisher ghi cho tới completion, tạo điều kiện cho transaction commit.
- `StepVerifier.create(readPublisher).expectNext(...).verifyComplete()`: tạo một **subscription khác** để quan sát DB state sau ranh giới commit/rollback.

**Lưu ý thao tác SQL có thể trả `Mono<Void>`**: `verifyComplete()` không có `expectNext` vì publisher này chỉ hoàn tất hoặc phát lỗi. Nếu bạn đổi service trả `Mono<Long>` từ `rowsUpdated()`, phải assert giá trị onNext phù hợp và completion.

## 8. Vì sao @DataR2dbcTest khác @DataJpaTest?

Trong Spring Boot 3.5:

| Annotation | Stack | Test-managed rollback mặc định? |
|---|---|---|
| `@JdbcTest` | JDBC (`PlatformTransactionManager`) | **Có** trong setup thông thường |
| `@DataJdbcTest` | Spring Data JDBC | **Có** |
| `@DataJpaTest` | JPA/Hibernate | **Có** |
| `@DataR2dbcTest` | Spring Data R2DBC | **Không** |
| `@SpringBootTest` không có `@Transactional` | Context đầy đủ | **Không** |
| `@SpringBootTest @Transactional` JDBC/JPA | Thread-bound transaction của test | Thường có, nhưng không bao HTTP server thread |
| Reactive service `@Transactional` trả `Mono/Flux` | `ReactiveTransactionManager` | Mỗi **subscription/publisher call** có scope riêng; không phải rollback cả JUnit method |

`@DataR2dbcTest` cấu hình `R2dbcEntityTemplate`, Spring Data R2DBC repositories và database test phù hợp theo classpath; nó không tạo một **test-managed reactive transaction** tự động bao trọn method JUnit. Vì vậy, `repository.save(entity)` được subscribe xong có thể **commit thật** và vẫn tồn tại sau test.

Khi viết slice test R2DBC:
1. Tạo database test cô lập và schema/fixture rõ.
2. Dùng `StepVerifier` hoặc subscriber phù hợp để đảm bảo publisher thực thi.
3. Bọc chính pipeline cần atomicity bằng **`TransactionalOperator`** hoặc gọi method `@Transactional` reactive thật qua proxy.
4. Cleanup dữ liệu ngoài transaction hoặc tái tạo database/container.
5. Không giả định `@Rollback`/`TestTransaction` của TestContext có thể thay thế cơ chế transaction Reactor Context.

**Về `@Transactional` trên test method reactive:** Spring TestContext test-managed transactions truyền thống gắn với `PlatformTransactionManager`/thread, khác với `ReactiveTransactionManager`. Đừng thêm `@Transactional` trên JUnit `void` test rồi tin các `Mono` R2DBC được subscribe bên trong sẽ auto-rollback. Mục tiêu cần bảo vệ là **pipeline/đường service có transaction**, không phải annotation đặt sai cấp.

## 9. Subscription: nơi một giao dịch reactive thực sự bắt đầu

`DatabaseClient` và Spring Data R2DBC trả về cold publishers trong nhiều thao tác. Khi xây dựng:

```java
Mono<Void> operation = db.sql(
        "INSERT INTO ledger_entries(entry_id, amount) VALUES (...)")
        .fetch()
        .rowsUpdated()
        .then();
```

Đây là ví dụ cú pháp chưa đầy đủ SQL binds, dùng để giải thích laziness. Tại thời điểm `operation` được tạo, **SQL chưa thực sự được gửi**. Khi có subscriber, execution diễn ra. Nếu publisher có `TransactionalOperator`, transaction cũng được tạo khi subscriber chạy qua operator.

### 9.1. Hai subscription có thể là hai transactions

```java
Mono<Void> save = service.writePairProgrammatically(prefix);

StepVerifier.create(save).verifyComplete();
StepVerifier.create(save).expectError().verify();
```

Đoạn trên là ví dụ trong scope có service, prefix và test. Nếu `writePairProgrammatically` trả một cold publisher như bài demo:
- Subscription 1: INSERT A/B, commit.
- Subscription 2: cố INSERT lại A/B, bị primary key violation và rollback.
- Dữ liệu đã commit ở subscription 1 vẫn còn.

**Không coi một đối tượng `Mono` là “một tác vụ chạy đúng một lần”**. Nó là một mô tả execution; nhiều subscriber có thể làm cùng side effect nhiều lần. Dùng idempotency key/unique constraints/transaction isolation theo yêu cầu nghiệp vụ thay vì chỉ trông vào việc giữ một biến `Mono`.

### 9.2. `.subscribe()` thủ công phá đường lan truyền lỗi

Anti-pattern:

```java
public Mono<Void> createBroken(String id) {
    repository.save(id).subscribe();
    return Mono.empty();
}
```

Đây là đoạn minh họa, cần repository kiểu phù hợp. Caller nhận `Mono.empty()` hoàn tất ngay, trong khi operation save chạy độc lập; nếu save fail, lỗi có thể không đến caller, transaction outer không nhất thiết bao trọn thao tác.

Cách đúng:

```java
public Mono<Void> createComposed(String id) {
    return repository.save(id).then();
}
```

Khi method `createComposed` được bao bằng transaction reactive, chính save publisher nằm **trong cùng pipeline**, và error/completion được truyền lên cho interceptor/operator.

### 9.3. `.block()` không phải cách “giữ transaction”

Gọi `.block()` trong WebFlux event-loop có thể bị từ chối (`IllegalStateException`) hoặc chặn luồng xử lý; ngoài ra, `.block()` tạo **một subscription mới**, không tự kế thừa Reactor Context transaction của publisher đang bao ngoài.

Đừng dùng:

```java
@Transactional
public Mono<Void> brokenTransfer() {
    firstReactiveWrite().block();
    return secondReactiveWrite();
}
```

Đây là anti-pattern minh họa. Trong code reactive, **compose**:

```java
@Transactional
public Mono<Void> correctTransfer() {
    return firstReactiveWrite().then(secondReactiveWrite());
}
```

Với JUnit/test command-line, có thể `block()` **ở ranh giới ngoài cùng trên thread không thuộc event-loop** để đợi kết quả, nhưng `StepVerifier` thường diễn đạt các signals và kỳ vọng lỗi rõ hơn. Không dùng `block()` **bên trong** một service reactive transaction chỉ để viết code giống JDBC.

## 10. Error recovery có thể làm transaction commit ngoài ý muốn

Đây là một trong những bài học quan trọng nhất. Xét hai pipeline:

```java
Mono<Void> inside =
        firstInsert()
          .then(Mono.<Void>error(
                  new IllegalStateException("failure")))
          .onErrorResume(error -> Mono.empty())
          .as(tx::transactional);
```

```java
Mono<Void> outside =
        firstInsert()
          .then(Mono.<Void>error(
                  new IllegalStateException("failure")))
          .as(tx::transactional)
          .onErrorResume(error -> Mono.empty());
```

Các đoạn là **minh họa** trong class có `firstInsert()` và operator. Ở `inside`, error được chuyển thành normal completion **trước khi transaction operator xử lý kết quả**; operator có thể commit firstInsert. Ở `outside`, operator nhận error và rollback trước, sau đó fallback mới làm caller thấy completion.

Trong bộ code mục 6, ta test trực tiếp:
- `recoverInsideTransaction` → đếm thấy **1 row**.
- `recoverOutsideTransaction` → đếm thấy **0 row**.

**Giới hạn của kết luận:** ví dụ phát lỗi Java có chủ đích sau một SQL thành công, không phải lỗi JDBC/R2DBC từ database. Một constraint violation thực có thể khiến transaction/resource rơi vào rollback-only/aborted state; `onErrorResume` bên trong khi ấy **không đảm bảo** commit được. Đừng làm sai domain policy bằng cách nuốt mọi `DataAccessException` chỉ để pipeline không phát lỗi.

### 10.1. onErrorComplete còn nguy hiểm hơn khi dùng bừa

`onErrorComplete()` biến error thành completion. Nếu đặt trước boundary transaction, bạn có thể vô tình giữ một phần thay đổi đã thành công. Nếu use case là all-or-nothing, hãy để exception đi qua operator/interceptor rồi xử lý phản hồi ở **bên ngoài**.

### 10.2. doOnError chỉ quan sát

`doOnError(log::warn)` không tự nuốt error; error vẫn được truyền đi và transaction vẫn có cơ hội rollback theo rules. Khác hoàn toàn `onErrorResume` hay `onErrorComplete`. Logging cũng không thay thế StepVerifier/error assertions.

### 10.3. Retry và transaction boundaries

Một `retryWhen` có thể tạo **subscription mới** sau lỗi. Nếu retry đặt **ngoài** `TransactionalOperator`, mỗi lần retry thường là một attempt có transaction riêng; nếu đặt **bên trong**, semantics có thể khác và transaction sau DB failure không còn usable. Hãy xác định mục tiêu:
- Mỗi attempt cần một transaction mới, không chứa side effects đã commit từ attempt trước.
- Retry chỉ những lỗi transient được phân loại rõ, có backoff/budget.
- Dùng idempotency key và giới hạn retry khi thao tác có thể ghi ra hệ thống ngoài SQL.

Không bật retry vô hạn cho transfer tài chính rồi kỳ vọng rollback DB là đủ: email/Kafka/HTTP call đã được phát ở attempt trước không tự được undo.

## 11. Cancellation: onCancel khác onComplete

Reactive Streams cho phép subscriber **cancel**: không còn muốn nhận các phần tử còn lại. Một số toán tử có thể phát cancellation:
- `take(1)` hoặc `next()` trên `Flux` nhiều giá trị.
- `timeout(Duration)` khi upstream không hoàn tất kịp.
- HTTP client ngắt kết nối và downstream cancellation được truyền ngược.
- Một subscriber chủ động `cancel()`.

Spring Framework từ dòng 5.3 coi cancellation của transactional publisher là tín hiệu **rollback**. Điều đó có thể bất ngờ khi code phát một `Flux` trong transaction nhưng downstream chỉ đọc phần tử đầu tiên.

Ví dụ cần suy nghĩ kỹ:

```java
Flux<Item> items =
        streamAndWriteItems()
                .as(tx::transactional);

Mono<Item> first = items.next();
```

Đây là đoạn minh họa, không phải source code độc lập. `next()` có thể cancel publisher upstream sau phần tử đầu tiên; transaction có thể bị rollback thay vì commit, ngay cả khi client đã thấy một item. Đừng tự suy ra `Mono<Item>` đã complete nghĩa là toàn bộ `Flux` bên trong transaction đã complete.

**Thiết kế tốt hơn:** khi muốn đảm bảo all-or-nothing cho một batch write, hãy chạy toàn bộ write pipeline đến completion trong một transaction, **sau đó** mới stream các kết quả cho client, hoặc dùng cấu trúc use case tách ranh giới rõ. Với streaming rất dài, không giữ một DB transaction mở suốt thời gian người dùng đọc; dùng transactions ngắn theo batch/command và xác định consistency semantics.

**Không viết test cancellation theo kiểu sleep cố định** rồi mong operation đã chạy tới một dòng cụ thể. Nếu cần test behavior này, dùng `StepVerifier`, publisher có tín hiệu đồng bộ hóa và kiểm tra DB state sau transaction cleanup/rollback thực tế.

## 12. Context propagation qua publishOn/subscribeOn và khi nào nó bị mất

Một hiểu lầm phổ biến: “đổi thread thì reactive transaction mất như JDBC”. Điều đó **không đúng tổng quát**. `Reactor Context` gắn với subscription và được Reactor operators duy trì.

```java
return writeA()
        .publishOn(Schedulers.parallel())
        .then(writeB())
        .as(tx::transactional);
```

Đoạn là ví dụ trong scope có `Mono<Void>`, `Schedulers` và tx operator. Bài test `schedulerSwitchWithinPipelineKeepsTransaction` xác nhận trong setup R2DBC/H2, cả A/B hoàn tất thành công dưới transaction operator.

**Những gì dễ làm mất boundary hơn đổi scheduler:**
- Gọi `subscribe()` thủ công để tạo một subscription rời rạc.
- Gọi `block()` lồng bên trong một pipeline, tạo subscription mới và chặn thread.
- Tách công việc sang `CompletableFuture`, callback callback-based hoặc custom `Executor` mà không có cơ chế đưa lại dữ liệu vào Reactor chain đúng.
- Lấy publisher ở ngoài rồi tự subscribe ở một bean khác, khiến transaction operator không còn bao publisher cần commit/rollback.
- Gán `contextWrite` sai vị trí và cho rằng nó tự đặt một R2DBC transaction resource; không thể tự tạo transaction hợp lệ chỉ bằng cách `context.put("transaction", true)`.

**Điểm tinh tế:** Context là **per subscriber**. Hai request cùng chạy trên một event-loop thread vẫn có thể sở hữu hai Reactor Context/transactions hoàn toàn độc lập. Đây là lý do không nên cất “current transaction id” vào một global static field hoặc ThreadLocal tự chế để phục vụ nhiều request reactive.

## 13. Cơ chế rollback của @Transactional trong Reactive

Với Spring declarative transaction, mặc định `RuntimeException` hoặc `Error` làm rollback; checked exceptions có thể cần `rollbackFor` theo policies đã khai báo. Trong reactive path, transaction interceptor quan sát **error signal** trên publisher và quyết định rollback tương ứng.

| Kết quả publisher | Tác động thông thường khi bên trong operator transaction |
|---|---|
| `onComplete` bình thường | Commit nếu transaction/resource khỏe mạnh |
| `onError(RuntimeException)` chưa được phục hồi | Rollback |
| `onError(checked Exception)` theo policy annotation | Quy tắc rollback/commit phụ thuộc cấu hình |
| `cancel` | Rollback trong Spring reactive hiện đại |
| `onErrorResume` nuốt error **trước operator** | Operator thấy completion; có thể commit phần trước |
| `onErrorResume` **sau operator** | Operator có cơ hội rollback, caller mới được fallback |
| Lỗi database làm transaction rollback-only | Commit không bảo đảm; DB/provider quyết định |
| Chưa có subscription | Chưa có SQL execution/transaction tương ứng |

Đừng viết test chỉ assert `Mono.error(...)` đúng exception rồi kết luận dữ liệu đã rollback: **đọc DB sau error** để chứng minh những row trước đó đã bị xóa. Đặc biệt khi chạy multi-database, một operation có thể dùng connection manager khác và không nằm dưới cùng reactive transaction.

### 13.1. `@Transactional(readOnly=true)` không phải hàng rào cấm ghi tuyệt đối

Cấu hình read-only có thể được driver/DB áp dụng như hint hoặc enforcement tùy transaction manager/dialect. Không nên viết `@Transactional(readOnly=true)` rồi khẳng định mọi `INSERT` sẽ bị cấm ở mọi R2DBC driver. Kiểm tra behavior trên database production-like nếu yêu cầu đó quan trọng.

### 13.2. Multiple ReactiveTransactionManager beans

Nếu ứng dụng có nhiều `ConnectionFactory` hoặc nhiều `ReactiveTransactionManager`, cần:
- Chọn `@Transactional(transactionManager="...")` đúng bean.
- Inject operator với qualifier phù hợp.
- Xác nhận từng `DatabaseClient` dùng connection factory được manager đó quản lý.
- Không giả định transaction của PostgreSQL A sẽ tự bao Cassandra/Mongo/Redis hoặc HTTP call B.

Một giao dịch R2DBC tiêu chuẩn thường quản lý **một database connection factory**; nó không tự thành distributed transaction.

## 14. R2DBC repositories, entity templates và SQL transaction

Spring Data R2DBC có `R2dbcEntityTemplate` và reactive repositories; chúng cũng trả `Mono`/`Flux` và tham gia transaction khi được subscribe trong Reactor Context phù hợp.

```java
public Mono<Void> changeTwoEntities() {
    return entityTemplate.update(first)
            .then(entityTemplate.update(second))
            .then()
            .as(tx::transactional);
}
```

Đoạn là minh họa bên trong class có entity template, entities và tx. Nếu tách hai lời gọi thành `.subscribe()` độc lập, không còn một transaction chung.

**R2DBC không phải JPA reactive.** Nó không có JPA `EntityManager`/first-level persistence context và dirty checking theo cùng kiểu Hibernate ORM. Vì vậy, các suy luận “entity tự flush khi transaction commit” từ JPA không áp dụng nguyên xi cho Spring Data R2DBC. Muốn sửa row, gọi update/save operation thật và subscribe nó.

Với `@DataR2dbcTest`, test slice tập trung repository/template và hạ tầng database phù hợp, thường không quét ordinary `@Service` như full context. Nếu muốn kiểm tra service `@Transactional`, có thể `@Import` đúng service/manager configuration hoặc dùng `@SpringBootTest` như ví dụ mục 6. **Dùng slice không làm tự xuất hiện TestContext rollback**.

## 15. Kiểm thử reactive transaction nên đặt những assertion nào?

Một bộ test bảo vệ nghiệp vụ nên trả lời được:

1. **Có subscription thật không?** Nếu chỉ tạo `Mono` nhưng không subscribe, không có bằng chứng SQL được thực thi.
2. **Khi success, DB cuối cùng có đúng rows?** Sau `verifyComplete()`, dùng publisher SELECT độc lập.
3. **Khi error, DB có giữ lại row trước lỗi không?** Test rollback bằng query sau error.
4. **Khi fallback nằm bên trong, có vô tình commit không?** Test vị trí `onErrorResume`.
5. **Khi declarative @Transactional, có đi qua Spring proxy không?** Test bean từ context, không gọi `new Service(...)` trực tiếp.
6. **Khi chuyển scheduler, Context còn đi qua chain không?** Test `publishOn` trong pipeline.
7. **Khi một publisher bị subscribe hai lần, side effect có lặp không?** Dùng primary key/idempotency.
8. **Khi cancel Flux giữa chừng, DB state như thế nào?** Đừng suy đoán commit từ việc client đã nhận một item.
9. **Test có giữ state giữa methods không?** `@DataR2dbcTest` không rollback mặc định; cleanup bằng publisher đã subscribe.
10. **Có đang test đúng DB dialect không?** H2 giúp test cơ chế cơ bản, production-like DB cho locking/isolation/constraint-specific.

### 15.1. Tại sao StepVerifier phù hợp hơn chỉ assert một Mono object?

`StepVerifier` **subscribe** publisher và kiểm tra từng loại tín hiệu:
- `expectNext(...)` cho kết quả.
- `verifyComplete()` cho kết thúc bình thường.
- `expectErrorMatches(...)` cho lỗi theo predicate.
- `thenCancel().verify()` cho cancellation khi thiết kế test có đồng bộ hóa phù hợp.

`assertNotNull(service.save(...))` chỉ kiểm tra Java reference tới `Mono` không null; nó **không chạy SQL**, không commit và không chứng minh rollback.

### 15.2. Không dùng @Transactional test method để che logic cần kiểm tra

Nếu bạn thử đặt `@Transactional` trên JUnit test `void` với `@DataR2dbcTest`, điều đó không tạo một reactive test-managed transaction cho các subscriptions phía sau. Các ví dụ khuyến nghị:
- Test plain JUnit/slice + gọi **service reactive transactional thật**.
- Hoặc bọc pipeline cần kiểm chứng bằng `TransactionalOperator` trong test.
- Dọn dữ liệu ngoài transaction bằng R2DBC publisher rõ ràng.

Không nên ép `TestTransaction.end()/start()` của imperative TestContext vào R2DBC test để tái tạo cách test JDBC: nó làm việc với loại transaction context khác.

## 16. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
|---|---|---|
| `@Transactional` không rollback R2DBC | Method trả void, không qua proxy, hoặc không có reactive manager | Trả `Mono/Flux`, gọi qua bean proxy, kiểm tra manager |
| Test thấy `Mono` nhưng DB trống | Chưa subscribe | Dùng `StepVerifier`/framework subscription |
| DB có row dù test failure | Lỗi bị nuốt bởi `onErrorResume` **trước** transaction boundary | Chuyển fallback ra ngoài hoặc điều khiển rollback policy rõ |
| DB có row dù test kết thúc | `@DataR2dbcTest` không auto rollback | Cleanup độc lập, DB cô lập |
| `TestTransaction.isActive()` false trong R2DBC test | Đây là API test-managed ThreadLocal, không phản ánh Reactor Context | Dùng test query/Reactive TSM khi cần chẩn đoán |
| `TransactionSynchronizationManager` static không báo active | Import nhầm imperative `support` package | Reactive class `org.springframework.transaction.reactive` |
| `block()` fail trên event-loop | Blocking disallowed hoặc deadlock/latency | Compose `then/flatMap`, tránh block trong handler |
| Lỗi không đến caller | Có `.subscribe()` rời rạc / fire-and-forget | Return publisher, không subscribe thủ công |
| Transaction mất khi gọi async task ngoài chain | Tạo subscription độc lập hoặc context không được bridge | Compose trong Reactor pipeline, kiểm soát boundary |
| Nghĩ `publishOn` luôn làm mất tx | Nhầm Reactor Context với ThreadLocal | Test compose pipeline và DB state, không dựa tên thread |
| Cùng Mono chạy SQL hai lần | Publisher được subscribe hai lần | Idempotency key, kiểm soát số lần subscription |
| `take(1)`/timeout làm mất commit | Upstream bị cancel | Đọc hết transaction publisher hoặc tách streaming khỏi write transaction |
| Concurrency statements trên cùng tx connection fail | `flatMap`/when chạy SQL song song trên một connection | Dùng `then/concatMap` khi cần tuần tự |
| Test rollback xanh nhưng H2 và PostgreSQL khác | Dialect/constraints/locking/isolation khác | Testcontainers với database production-like |
| Transaction marker có nhưng sai database | Nhiều connection factories/managers không khớp | Kiểm tra qualifiers, Spring Data client resource |
| `@Transactional` self-invocation không kích hoạt | Gọi `this.method()` bỏ qua proxy AOP | Gọi qua proxied bean hoặc `TransactionalOperator` |
| `onErrorComplete` che lỗi, data còn một phần | Error chuyển thành completion trong operator | Không nuốt lỗi trước transaction boundary nếu cần all-or-nothing |
| Retry gây ghi lặp | Retry tạo subscription/attempt mới | Idempotency, retry policy và transaction per attempt |
| Reactive transaction kéo dài gây lock | Giữ transaction khi stream HTTP dài | Chia writes thành bounded units, commit trước stream |
| R2DBC write không nằm trong tx | Client tự lấy connection không qua Spring utilities | Dùng Spring `DatabaseClient`/repository hoặc TransactionAwareConnectionFactoryProxy |
| SQL side effects bên ngoài DB không rollback | Kafka/email/Redis/HTTP không thuộc R2DBC tx | Outbox/compensation và integration tests riêng |
| Test không chạy mà build vẫn xanh | Runner bỏ qua JUnit class/NO-SOURCE | Đọc reports, đếm test thực thi |

## 17. Mô hình thời gian: subscribe, onComplete, onError, cancel

```text
Caller nhận Mono<Void> từ service
              |
       [chưa subscribe]
              |
              v
       StepVerifier.subscribe()
              |
              v
     TransactionalOperator
       mở R2DBC transaction T1
              |
              v
     INSERT A -- then --> INSERT B
              |
       +------+---------+
       |                |
    onComplete        onError
       |                |
     COMMIT T1       ROLLBACK T1
       |                |
    verifyComplete   verifyError
       |                |
       +-------+--------+
               |
   SELECT bằng subscription khác
   để quan sát row sau boundary

cancel giữa chừng -> rollback (Spring reactive hiện đại)
```

**Ranh giới nằm quanh publisher được subscribe**, không quanh “thời điểm Java method được gọi để dựng Mono”. Đây là khác biệt quan trọng nhất so với tư duy transaction dùng ThreadLocal.

## 18. Lưu ý phiên bản Boot 3.5 / Boot 4

Code hoàn chỉnh trong bài dùng Spring Boot **3.5.x**, trong đó:
- R2DBC/Spring Data Redis? **Không**: bài này chỉ R2DBC, không dùng Redis/JDBC transaction.
- `R2dbcTransactionManager` thuộc Spring Framework `org.springframework.r2dbc.connection`.
- `ReactiveTransactionManager` thuộc `org.springframework.transaction`.
- `TransactionalOperator` thuộc `org.springframework.transaction.reactive`.
- `DatabaseClient` thuộc `org.springframework.r2dbc.core`.
- `@DataR2dbcTest` (khi dùng slice) thuộc `org.springframework.boot.test.autoconfigure.data.r2dbc`.

Trong **Spring Boot 4.x**, các test slices tách thành modules chuyên biệt; `@DataR2dbcTest` tương ứng thuộc module `spring-boot-data-r2dbc-test`, package `org.springframework.boot.data.r2dbc.test.autoconfigure`. Không copy import Boot 4 vào một runtime Boot 3.5 hoặc trộn Spring Framework 6 và 7 chỉ để hết lỗi IDE.

Các nguyên tắc giữ nguyên: Reactive transaction cần manager và publisher, Reactor Context theo subscriber, cancellation/error semantics phải được kiểm tra, và `@DataR2dbcTest` không tự thay thế explicit transaction/cleanup. Luôn dùng **BOM/version** của project để xác định API cụ thể.

## 19. Checklist cuối bài

- [ ] Chọn đúng loại transaction manager: `PlatformTransactionManager` (JDBC/JPA) hay `ReactiveTransactionManager` (R2DBC).
- [ ] Với R2DBC, `@Transactional` nằm trên method public trả `Mono/Flux`, được gọi qua Spring proxy.
- [ ] Publisher chứa **toàn bộ** những thao tác cần atomicity và được bao bằng operator/transactional advice.
- [ ] Không dùng `subscribe()` thủ công để khởi chạy một nửa use case rồi bỏ lỗi.
- [ ] Không `block()` bên trong WebFlux event-loop hay reactive transaction để giả lập JDBC.
- [ ] Với một tx connection, tránh chạy SQL song song nếu driver/semantics không hỗ trợ.
- [ ] Hiểu `publishOn/subscribeOn` đổi thread không đồng nghĩa Reactor Context biến mất.
- [ ] Nhớ **mỗi subscription** có thể tạo một execution/transaction riêng.
- [ ] Test `onErrorResume` **bên trong** và **bên ngoài** operator; xác minh DB state, không chỉ tín hiệu hoàn tất.
- [ ] Với `Flux`, cân nhắc cancel từ `take/next/timeout` có thể dẫn tới rollback.
- [ ] Dùng `StepVerifier` để tiêu thụ publisher và xác minh completion/error.
- [ ] Không mặc định `@DataR2dbcTest` rollback dữ liệu sau method; có cleanup/isolated database.
- [ ] Test commit/rollback bằng **query bên ngoài transaction** sau khi operator hoàn tất.
- [ ] Nếu ứng dụng có nhiều managers, chọn đúng datasource/connection factory.
- [ ] Nếu lỗi phụ thuộc dialect/locking, dùng PostgreSQL/MySQL Testcontainers thay vì chỉ H2.
- [ ] Đã chạy thật test runner và kiểm tra reports trước khi kết luận runtime PASS.

## 20. Tài liệu chính thức và hướng đào sâu

- [Spring Framework 6.2 — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html): phân biệt thread-bound `PlatformTransactionManager` và Reactor Context của `ReactiveTransactionManager`.
- [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `TransactionalOperator`, rollback do cancellation, operator và callback styles.
- [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `ConnectionFactory`, `DatabaseClient`, `R2dbcTransactionManager` và subscriber-bound connections.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataR2dbcTest` mặc định không transactional, so sánh với JDBC/JPA slices.
- [Spring Boot 3.5 — SQL Databases / R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): R2DBC ConnectionFactory, R2DBC embedded H2, DatabaseClient.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): SQL schema initialization cho JDBC/R2DBC.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context per subscriber và `deferContextual/contextWrite`.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` assertions và kiểm thử publisher.

**Kết luận:** Giao dịch Reactive của Spring gắn với **Reactor Context và một subscription**, không dựa vào ThreadLocal JDBC/JPA. `@Transactional` chỉ đúng phạm vi khi nó bao một `Mono/Flux` được thực thi qua proxy, hoặc khi code dùng `TransactionalOperator` để compose toàn bộ R2DBC work. Thành công, lỗi và cancellation quyết định commit/rollback; recovery đặt sai ranh giới có thể khiến **partial writes được commit**. Khi kiểm thử, hãy dùng `StepVerifier`, một R2DBC database thật, quan sát dữ liệu sau transaction và cleanup rõ ràng — đặc biệt vì `@DataR2dbcTest` không tự rollback như `@DataJpaTest`.