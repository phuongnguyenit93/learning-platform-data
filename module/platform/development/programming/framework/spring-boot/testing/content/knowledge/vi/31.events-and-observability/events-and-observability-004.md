# @EventListener, @TransactionalEventListener và thời điểm commit

## 1. Vì sao “đã publish event” không có nghĩa “đã commit”?

Trong **Spring Boot - testing**, nhóm **Sự kiện và observability**, một tình huống dễ gây lỗi là ứng dụng lưu giao dịch rồi phát sự kiện để gửi email, cập nhật audit, xóa cache hoặc publish message sang hệ thống khác. Lập trình viên thường đặt `ApplicationEventPublisher.publishEvent(...)` bên trong method `@Transactional` và nghĩ rằng mọi listener chỉ chạy khi dữ liệu đã commit.

Điều đó **không đúng với `@EventListener` thông thường**. Với cấu hình mặc định, `@EventListener` chạy **đồng bộ ngay khi sự kiện được publish**, tức là *trước khi* transaction chứa lời gọi đó commit. Nếu sau đó transaction rollback, side effect mà listener đã thực hiện bên ngoài DB (gửi email, gọi API, gửi Kafka message) **không tự rollback**.

Ngược lại, `@TransactionalEventListener` có thể gắn việc thực thi listener vào một **pha của transaction**. Pha mặc định là `AFTER_COMMIT`, giúp chỉ chạy khi transaction thực sự hoàn tất thành công. Các pha còn lại là `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.

Bài này tập trung trả lời bằng kiểm thử chứ không chỉ qua mô tả:

1. Listener nào đã chạy ngay khi gọi `publishEvent`?
2. Listener nào chỉ chạy **sau commit**, không chạy nếu rollback?
3. Listener nào chạy trước commit, sau rollback hoặc sau mọi trạng thái hoàn tất?
4. Nếu publish sự kiện khi **không có transaction**, chuyện gì xảy ra?
5. Tại sao một listener `AFTER_COMMIT` gọi `repository.save(...)` chưa chắc tạo bản ghi durable nếu không mở **transaction mới**?
6. Làm sao kiểm thử đúng commit boundary mà không để `@Transactional` trên JUnit test làm tất cả rollback?
7. Vì sao Spring application events không tự thay thế message broker, transactional outbox hay reliable event delivery?

Ví dụ hoàn chỉnh sử dụng **Java 17, Spring Boot 3.3.0, Spring JDBC, H2 in-memory database, JUnit Jupiter**. Nó có `@EventListener`, bốn `TransactionPhase`, `fallbackExecution=true`, một `AuditWriter` dùng `Propagation.REQUIRES_NEW`, và **9 integration test methods** xác minh database + event observations thực. Không cần Docker hoặc server HTTP.

## 2. Kết quả học tập

Sau bài, bạn có thể:

- Giải thích `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener` và `ApplicationEventMulticaster`.
- Biết POJO/record Java 17 có thể được publish làm event payload, không nhất thiết extends `ApplicationEvent`.
- Hiểu synchronous vs asynchronous multicasting; publication mặc định thường đồng bộ trong thread của publisher.
- Phân biệt thời điểm gọi method, thời điểm publish và thời điểm transaction commit.
- Sử dụng `@TransactionalEventListener(phase=TransactionPhase.AFTER_COMMIT)` để chỉ xử lý sau commit thành công.
- Kiểm tra `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Giải thích vì sao `BEFORE_COMMIT` không bảo đảm commit sau đó sẽ thành công.
- Biết `fallbackExecution=false` mặc định làm transactional listener bỏ qua sự kiện publish ngoài transaction.
- Dùng `fallbackExecution=true` khi muốn cho phép nontransactional execution, nhưng không ngầm gọi đó là commit.
- Biết tại sao `@Transactional` trên service cần đi qua Spring AOP proxy và cần transaction manager.
- Hiểu vấn đề `AFTER_COMMIT` tài nguyên transaction có thể còn bound nhưng công việc ghi DB mới không được commit.
- Tách một Spring bean `@Transactional(propagation=REQUIRES_NEW)` để ghi audit durable sau commit.
- Phân biệt `REQUIRES_NEW` với `REQUIRED` và `NESTED`; không coi `@Transactional` mới trên cùng object self-invocation có hiệu lực.
- Viết tests cho commit, rollback, no-tx, phase order và multiple events trong một transaction.
- Tránh `@Transactional` mặc định rollback của Spring TestContext gây false negative cho AFTER_COMMIT.
- Dùng `TestTransaction.flagForCommit()`/`TestTransaction.end()` khi thật sự cần test-managed transaction.
- Cô lập DB và in-memory event observations giữa test methods, không phụ thuộc thứ tự chạy.
- Không suy luận từ một event handler được gọi rằng durable DB row hoặc remote message đã tồn tại.
- Chọn transactional outbox khi cần reliable delivery qua process/message broker.
- Nắm rõ khác biệt giữa imperative `PlatformTransactionManager` và reactive `ReactiveTransactionManager`/Reactor Context.
- Dùng logs, traces và metrics để quan sát event lifecycle mà không ghi thông tin nhạy cảm vào tags.

## 3. Hai đường xử lý sự kiện

```text
External request / scheduled command
              |
              v
Spring @Service proxy
              |
              +-- begins JDBC transaction
              |
              v
INSERT purchases(...)  [not committed]
              |
              v
ApplicationEventPublisher.publishEvent(
    new PurchaseCreatedEvent(ref))
              |
              +--> @EventListener
              |       runs NOW, usually synchronously
              |       may see current uncommitted transaction
              |
              +--> @TransactionalEventListener
                      registers transaction synchronization
              |
              v
Service returns to transaction interceptor
              |
              +--> BEFORE_COMMIT listener callbacks
              |
              +--> Commit database transaction
                      |
                      +--> AFTER_COMMIT callbacks
                      |       audit writer with REQUIRES_NEW
                      |
                      +--> AFTER_COMPLETION callbacks
```

Nếu code ném unchecked exception trước commit:

```text
publishEvent()
     |
     +--> @EventListener runs now
     |
     +--> transactional callbacks registered
     |
     v
throw RuntimeException
     |
     v
transaction rollback
     |
     +--> AFTER_ROLLBACK
     +--> AFTER_COMPLETION
     |
     -X-> AFTER_COMMIT not called
     -X-> BEFORE_COMMIT not normally called
```

**Lưu ý về thứ tự:** `AFTER_COMPLETION` chạy sau transaction hoàn tất với cả commit và rollback. Không tùy tiện assert thứ tự chi tiết giữa hai listeners trong cùng completion phase vì nó có thể phụ thuộc registration/`@Order`. Bài chỉ assert chắc chắn **IMMEDIATE < BEFORE_COMMIT < AFTER_COMMIT** cho commit bình thường.

## 4. @EventListener: nhận ngay, không gắn vào kết quả commit

Một listener đơn giản:

```java
@Component
public class PurchaseNoticeListener {
    @EventListener
    public void onPurchase(PurchaseCreatedEvent event) {
        System.out.println("Published: " + event.ref());
    }
}
```

Đây là snippet minh họa; project runnable dùng `PurchaseEventListeners` với `EventProbe` thay cho stdout. Spring phát hiện các listener methods trong managed beans khi khởi tạo ApplicationContext.

### 4.1. Synchronous by default

Với `SimpleApplicationEventMulticaster` mặc định, các synchronous event listeners thường được gọi trong **thread của publisher** và `publishEvent` không trở về cho tới khi chúng xử lý xong. Nếu listener throw unchecked exception, exception có thể propagate tới caller; khi caller ở một `@Transactional` method, transaction có thể rollback theo rules.

**Không gán tính chất này cho mọi cấu hình:** nếu ứng dụng thay ApplicationEventMulticaster executor, dùng `@Async`, hoặc custom error handler, hành vi thread/exception/lifecycle thay đổi. Test cần dựa vào cấu hình của ứng dụng.

### 4.2. @EventListener nằm trong transaction đang mở

Khi `publishEvent` được gọi trong một method đã thực sự có Spring transaction, synchronous listener có thể tham gia cùng context của thread đó. Nó có thể đọc dữ liệu vừa được flush nhưng chưa commit, hoặc gọi repository/JdbcTemplate tham gia transaction hiện tại.

Điều đó **không chứng minh transaction đã commit**. Một email/API call trong listener vẫn có thể đi ra ngoài trước commit và không tự được hoàn tác nếu transaction rollback.

### 4.3. Kết quả quan sát có thể sai nếu chỉ kiểm tra handler được gọi

Test:

```java
service.placeAndFail("ORDER-1");
assertEquals(1, eventProbe.count("IMMEDIATE", "ORDER-1"));
```

Nếu không assert database rollback và AFTER_COMMIT absence, rất dễ kết luận nhầm rằng xử lý thành công. Listener được gọi chỉ có nghĩa **sự kiện đã được publish tới listener tại thời điểm đó**.

## 5. @TransactionalEventListener và bốn pha

Spring Framework hỗ trợ `@TransactionalEventListener` gắn listener vào transaction lifecycle. Default `phase` là `AFTER_COMMIT`.

| Pha | Thời điểm | Khi transaction commit | Khi transaction rollback |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước commit; còn trong transaction | Thường chạy | Thường không chạy với rollback trực tiếp |
| `AFTER_COMMIT` | Sau commit thành công | Chạy | Không chạy |
| `AFTER_ROLLBACK` | Sau rollback | Không chạy | Chạy |
| `AFTER_COMPLETION` | Sau hoàn tất bất kể trạng thái | Chạy | Chạy |

### 5.1. AFTER_COMMIT (mặc định)

```java
@TransactionalEventListener
public void afterCommit(PurchaseCreatedEvent event) {
    // Work only after successful commit.
}
```

Tương đương `phase=TransactionPhase.AFTER_COMMIT`. Nếu transactional method rollback, callback không thực thi.

**Không đồng nghĩa reliable remote delivery:** commit xong, process có thể crash ngay trước callback; hoặc callback gửi tới Kafka/email bị lỗi. Original transaction vẫn đã commit và không thể rollback để đồng bộ external side effect.

### 5.2. BEFORE_COMMIT

```java
@TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(PurchaseCreatedEvent event) {
    // Validation or in-transaction work, if appropriate.
}
```

Có thể dùng cho công việc cần thực hiện trước commit trong transaction. Nhưng **BEFORE_COMMIT không bảo đảm commit thành công**: database flush, constraints, deadlock hoặc commit failure vẫn có thể xảy ra sau callback. Không gửi irreversible side effect và gọi nó là confirmed-committed.

### 5.3. AFTER_ROLLBACK

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
public void afterRollback(PurchaseCreatedEvent event) {
    // Record a rollback observation or compensate when safe.
}
```

Dùng để quan sát/fallback/compensation khi transaction không được commit. Nếu cần lưu bản ghi audit trong database sau rollback, **cần transaction riêng** như `REQUIRES_NEW`, vì transaction gốc đã rollback. Không coi `AFTER_ROLLBACK` là một phương thức đảo mọi remote side effect tùy ý.

### 5.4. AFTER_COMPLETION

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION)
public void afterCompletion(PurchaseCreatedEvent event) {
    // Cleanup/observe after either commit or rollback.
}
```

Callback chạy sau khi transaction hoàn tất, kể cả commit lẫn rollback. Bản thân annotation ở phase này không có nghĩa business outcome là success. Nếu cần phân biệt, dùng separate callbacks `AFTER_COMMIT`/`AFTER_ROLLBACK` hoặc TransactionSynchronization status chuyên biệt.

### 5.5. Một event có thể kích hoạt nhiều callbacks

Trong runnable lab, một `PurchaseCreatedEvent` được nhiều methods cùng lắng nghe. Ví dụ commit sẽ có IMMEDIATE, BEFORE_COMMIT, AFTER_COMMIT và AFTER_COMPLETION. Không được kết luận “một event chỉ gọi một listener” hoặc “mỗi phase tương ứng một business event duy nhất”.

## 6. Không có transaction: fallbackExecution

Mặc định:

```java
@TransactionalEventListener
public void afterCommit(PurchaseCreatedEvent event) {
    // Not invoked if event published without a transaction.
}
```

Nếu gọi `publisher.publishEvent(new PurchaseCreatedEvent("A"))` ngoài transaction, callback này **không chạy**, bởi không có commit phase để đợi. Trong khi đó `@EventListener` thường vẫn nhận ngay sự kiện.

Nếu muốn xử lý cả nontransactional events:

```java
@TransactionalEventListener(fallbackExecution = true)
public void onPing(NoTxPingEvent event) {
    // Runs after commit in a transaction;
    // runs immediately if no transaction is active.
}
```

Đó là một **lựa chọn nghiệp vụ**, không nên bật đại trà để che việc service transaction bị thiếu. Khi không có transaction, fallback callback chạy ngay; nó **không tạo ra một commit giả**.

**Quan trọng:** Một listener bật fallback có thể xử lý một event ngoài transaction, trong khi listener khác của cùng event type có fallback=false không làm gì. Test cần kiểm tra chính xác các nhánh.

## 7. Sự khác biệt giữa publish và commit boundary

Một method:

```java
@Transactional
public void create(String ref) {
    jdbc.update(
            "insert into purchases(ref) values (?)",
            ref);
    events.publishEvent(new PurchaseCreatedEvent(ref));
}
```

sẽ thực sự chạy trong transaction khi được gọi **qua Spring proxy**. Thứ tự khái niệm:

1. Spring transaction interceptor mở transaction.
2. `jdbc.update` gửi INSERT trong transaction.
3. `publishEvent` gọi synchronous `@EventListener` và đăng ký transactional callbacks.
4. Target method trả về.
5. Transaction interceptor hoàn tất commit/rollback.
6. Sau commit thành công mới chạy `AFTER_COMMIT` callbacks.

### 7.1. Self-invocation làm @Transactional không được áp dụng

Nếu bean gọi `this.create(...)` từ method nội bộ khác trong cùng object, lời gọi có thể bypass Spring AOP proxy. Khi đó có thể không có outer transaction như kỳ vọng. Một JPA repository/JdbcTemplate operation riêng vẫn có thể chạy theo auto-commit/transaction khác, nhưng event không có cùng commit boundary. Đây là nguồn lỗi khó phát hiện bằng unit test gọi `new Service()`.

Trong lab, test inject Spring-managed `PurchaseService` và gọi public transactional methods từ bên ngoài bean.

### 7.2. Proxy method visibility

Ưu tiên public service methods và gọi qua injected Spring bean. Không giả định annotation trên private method hoặc method được gọi trực tiếp trong constructor luôn tạo transactional advice. Với nhiều PlatformTransactionManager beans, phải chọn đúng manager/qualifier.

### 7.3. Default rollback rules

Với Spring declarative transactions thông thường, unchecked `RuntimeException`/`Error` dẫn tới rollback; checked exception mặc định có thể không rollback nếu không cấu hình `rollbackFor`. Test rollback trong lab dùng `IllegalStateException` để loại bỏ ambiguity. Không khẳng định mọi exception luôn rollback.

## 8. Điểm khó: AFTER_COMMIT vẫn có thể thấy resources bound

Javadoc của `@TransactionalEventListener` cảnh báo: ở `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`, transaction đã hoàn tất nhưng tài nguyên của nó **có thể vẫn còn active/bound** tới thread trong quá trình cleanup. Data-access code thực thi lúc đó có thể trông như đang tham gia transaction cũ nhưng **thay đổi mới không được commit**.

Ví dụ dễ gây sai:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onPurchase(PurchaseCreatedEvent event) {
    auditRepository.save(new AuditRecord(event.ref()));
}
```

Đây là snippet cảnh báo, không thuộc project runnable. Nếu repository method với propagation `REQUIRED` tham gia resource context đã commit, một INSERT phát sinh sau commit có thể không có commit tiếp theo như bạn mong đợi. Test chỉ kiểm tra Java method `save()` được gọi **không chứng minh bản ghi tồn tại durable**.

### 8.1. Giải pháp có chủ đích: transaction mới

Tách một Spring-managed bean:

```java
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(PurchaseCreatedEvent event) {
        jdbc.update(
                "insert into audit_entries(ref, phase) values (?, ?)",
                event.ref(), "AFTER_COMMIT");
    }
}
```

Snippet trên rút gọn; full class có constructor injection ở phần lab. `REQUIRES_NEW` yêu cầu Spring suspend outer resource context (nếu còn bound) rồi mở transaction vật lý mới, commit riêng trước khi callback trả về.

**Không** viết `@Transactional(REQUIRES_NEW)` trên private method rồi gọi `this.write(...)`; self-invocation sẽ bỏ qua proxy. Lab đặt `AuditWriter` thành bean riêng và inject vào event listener.

### 8.2. AFTER_COMMIT exception không undo transaction gốc

Nếu `AuditWriter.write(...)` thất bại, **purchase transaction đã commit**. Tùy synchronization callback/exception handling, exception vẫn có thể đi ra caller, nhưng không thể biến purchase thành chưa commit. Đừng viết retry code mù quáng chỉ dựa vào exception của service rồi tạo duplicate purchase.

Nếu nghiệp vụ cần *exactly once-looking* processing, phải có idempotency keys, deduplication hoặc transactional outbox — in-process callback không là distributed transaction.

### 8.3. Connection pool

`REQUIRES_NEW` có thể cần thêm một DB connection khi outer connection vẫn bound. Pool quá nhỏ hoặc high concurrency có thể gây deadlock/pool exhaustion. Test H2/Hikari đủ cho một thread, nhưng production cần sizing và monitoring theo tải.

## 9. Không phải Spring event nào cũng có transaction

Spring application events không yêu cầu transaction. Một publisher có thể chạy từ:

- `@Scheduled` job không có `@Transactional`.
- REST controller gọi `ApplicationEventPublisher` trực tiếp.
- Startup listener/runner.
- Message listener xử lý ngoài transaction.
- Async/background callback tách khỏi thread-bound transaction.
- Test method gọi `publishEvent` ngoài Spring transactional service.

Khi không có active transaction:

| Listener | Có chạy? |
| --- | --- |
| `@EventListener` (default synchronous) | Có |
| `@TransactionalEventListener(AFTER_COMMIT)`, fallback=false | Không |
| `@TransactionalEventListener(BEFORE_COMMIT)`, fallback=false | Không |
| `@TransactionalEventListener(AFTER_ROLLBACK)`, fallback=false | Không |
| `@TransactionalEventListener(AFTER_COMPLETION)`, fallback=false | Không |
| `@TransactionalEventListener(..., fallbackExecution=true)` | Có; chạy ngay theo fallback |

Đừng dùng `fallbackExecution=true` chỉ vì test thiếu transaction; hãy xác định chính sách business khi không có transaction.

## 10. Chọn kiến trúc test

| Mục tiêu | Test phù hợp | Điều chưa chứng minh |
| --- | --- | --- |
| Listener xử lý event payload đúng | Unit test listener method trực tiếp | Spring registration/phase |
| `@EventListener` được Spring phát hiện | `@SpringBootTest` và publisher | DB commit |
| Transactional listener phase | Spring transaction + event publisher + real DB | Remote broker delivery |
| Bản ghi audit AFTER_COMMIT durable | DB query ngoài transaction sau callback | Exactly-once external effects |
| Rollback không ghi audit | Service throw + DB zero rows + phase probe | Có thể hoàn tác email đã gửi |
| Event ngoài transaction | Publisher trong nontransactional test | Transactions của request thật |
| Test-managed @Transactional | `TestTransaction.flagForCommit()/end()` | External systems nếu không gọi |
| Kafka/email reliable dispatch | Outbox + broker/emulator/Testcontainers | Production availability mọi failure |
| Reactive transaction phases | Reactor TransactionalEventPublisher integration | Imperative thread-bound semantics |

**Đây là bài kiểm thử transaction timing, không cần chạy web server.** Chúng ta dùng `@SpringBootTest(webEnvironment=NONE)`, H2/JdbcTemplate và transaction manager thật thay vì Mockito giả lập commit.

## 11. Dự án runnable: Spring Boot 3.3 + H2 + JDBC

### 11.1. Cây thư mục

```text
transaction-events-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/events/
    │   │   ├── EventLabApplication.java
    │   │   ├── PurchaseCreatedEvent.java
    │   │   ├── NoTxPingEvent.java
    │   │   ├── PurchaseService.java
    │   │   ├── AuditWriter.java
    │   │   ├── EventProbe.java
    │   │   └── PurchaseEventListeners.java
    │   └── resources/
    │       └── schema.sql
    └── test/java/example/events/
        └── PurchaseEventIntegrationTest.java
```

### 11.2. settings.gradle

```groovy
rootProject.name = 'transaction-events-lab'
```

### 11.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Vì starter JDBC có `spring-tx`/JDBC, Spring Boot auto-configures an embedded H2 datasource, JdbcTemplate và PlatformTransactionManager khi đủ điều kiện. Trong main class, lab bật `@EnableTransactionManagement` tường minh để rõ proxy boundary.

**Không cần JPA** cho bài này: JDBC/H2 làm commit/rollback và độc lập connection rõ ràng. Nếu ứng dụng dùng JPA, thay bằng repository nhưng giữ logic transaction phases tương ứng; khi cần test flush/constraints phải làm rõ `EntityManager.flush()`.

### 11.4. schema.sql

**src/main/resources/schema.sql**

```sql
create table if not exists purchases (
    id bigint generated by default as identity primary key,
    ref varchar(120) not null
);

create table if not exists audit_entries (
    id bigint generated by default as identity primary key,
    ref varchar(120) not null,
    phase varchar(40) not null
);
```

Spring Boot SQL initialization với embedded H2 áp dụng schema.sql khi tạo application. Không có foreign key để giữ cleanup ở test dễ hiểu.

Trong một production app có Flyway/Liquibase, **không** dùng schema.sql khởi tạo lại DB thật như lab; dùng migrations và cấu hình schema initialization phù hợp môi trường.

## 12. Main application + event payload records

### 12.1. EventLabApplication.java

**src/main/java/example/events/EventLabApplication.java**

```java
package example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class EventLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                EventLabApplication.class, args);
    }
}
```

### 12.2. PurchaseCreatedEvent.java

**src/main/java/example/events/PurchaseCreatedEvent.java**

```java
package example.events;

public record PurchaseCreatedEvent(String ref) {}
```

### 12.3. NoTxPingEvent.java

**src/main/java/example/events/NoTxPingEvent.java**

```java
package example.events;

public record NoTxPingEvent(String id) {}
```

Spring's `ApplicationEventPublisher.publishEvent(Object)` nhận event payload Java object, bao gồm records. Bạn không cần extends `ApplicationEvent` cho mỗi domain event. Chọn record immutable giúp tránh mutation giữa publication và callback, đặc biệt nếu event processing bị trì hoãn.

**Không đưa JPA entity với lazy-loaded mutable state vào event rồi đọc sau transaction** nếu không có lý do; record chứa business ID/reference/immutable data thường dễ test và giảm vấn đề detached entities.

## 13. PurchaseService.java — tạo transaction và publish event

**src/main/java/example/events/PurchaseService.java**

```java
package example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {

    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    public PurchaseService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void place(String ref) {
        insertAndPublish(ref);
    }

    @Transactional
    public void placeAndFail(String ref) {
        insertAndPublish(ref);
        throw new IllegalStateException(
                "forced rollback");
    }

    @Transactional
    public void placePair(String first, String second) {
        insertAndPublish(first);
        insertAndPublish(second);
    }

    @Transactional
    public void placePairAndFail(
            String first, String second) {
        insertAndPublish(first);
        insertAndPublish(second);
        throw new IllegalStateException(
                "forced rollback");
    }

    private void insertAndPublish(String ref) {
        jdbc.update(
                "insert into purchases(ref) values (?)",
                ref);
        events.publishEvent(
                new PurchaseCreatedEvent(ref));
    }
}
```

**Tại sao @Transactional đặt ở public methods?** JUnit inject `PurchaseService` bean và gọi public methods qua Spring proxy; transaction interceptor mở transaction trước `insertAndPublish`. Private method chỉ là helper **chạy bên trong active transaction đã được mở**, không tự cần annotation. Không có self-invocation của một annotated public method ở đây.

**Vì sao dùng unchecked exception?** `IllegalStateException` là RuntimeException, theo mặc định Spring sẽ rollback. Nếu test dùng checked exception mà quên `rollbackFor`, behavior có thể khác.

**Vì sao insert trước event?** Sự kiện mang reference của dữ liệu vừa được ghi trong transaction, nhưng chưa necessarily committed. Immediate listener có thể thấy event trước khi database commit. Transactional listener AFTER_COMMIT chỉ chạy khi commit kết thúc thành công.

## 14. EventProbe.java — quan sát pha và transaction status

**src/main/java/example/events/EventProbe.java**

```java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class EventProbe {

    public record Mark(
            String phase,
            String ref,
            boolean transactionActive,
            long threadId) {}

    private final List<Mark> marks =
            new CopyOnWriteArrayList<>();

    public void mark(String phase, String ref) {
        marks.add(new Mark(
                phase,
                ref,
                TransactionSynchronizationManager
                        .isActualTransactionActive(),
                Thread.currentThread().getId()));
    }

    public long count(String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .count();
    }

    public List<String> phases(String ref) {
        return marks.stream()
                .filter(mark -> mark.ref().equals(ref))
                .map(Mark::phase)
                .toList();
    }

    public boolean transactionActiveAt(
            String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .findFirst()
                .orElseThrow()
                .transactionActive();
    }

    public long threadIdAt(
            String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .findFirst()
                .orElseThrow()
                .threadId();
    }

    public void clear() {
        marks.clear();
    }
}
```

`EventProbe` chỉ là công cụ quan sát trong demo, không ghi DB hoặc HTTP. `CopyOnWriteArrayList` giúp tránh data race khi đọc observations nếu có thread khác, nhưng lab dùng synchronous event handlers.

### 14.1. Cẩn thận với transactionActiveAt ở AFTER_COMMIT

`TransactionSynchronizationManager.isActualTransactionActive()` phản ánh trạng thái transaction **được thread-bound tại thời điểm gọi**, không phải “commit thành công chưa?” ở mức business. Sau commit, resources có thể vẫn bound cho tới cleanup; đừng assert nó phải false ở AFTER_COMMIT.

Bài chỉ assert `IMMEDIATE` được gọi khi transaction active với `place(...)` và inactive khi publish trực tiếp ngoài transaction. Durable DB evidence ở AFTER_COMMIT được kiểm tra bằng JDBC query từ bên ngoài method.

### 14.2. Vì sao threadId được ghi?

Để kiểm tra đường mặc định synchronous: một `@EventListener` nhận event khi `publishEvent` đang chạy trên thread của test/publisher. Test không assert thread **name** (có thể đổi); nó so `Thread.currentThread().getId()` với mark do handler ghi. Nếu bạn bật `@Async` hoặc custom executor, assertion này không còn là contract.

## 15. AuditWriter.java — REQUIRES_NEW sau commit

**src/main/java/example/events/AuditWriter.java**

```java
package example.events;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {

    private final JdbcTemplate jdbc;

    public AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(PurchaseCreatedEvent event) {
        jdbc.update(
                "insert into audit_entries(ref, phase) " +
                "values (?, ?)",
                event.ref(),
                "AFTER_COMMIT");
    }
}
```

Spring AOP proxy có thể áp dụng `REQUIRES_NEW` vì `PurchaseEventListeners` inject **một Spring bean riêng** và gọi `auditWriter.write(event)`. Nếu chỉ đặt method private trên listener rồi gọi trực tiếp `this.write`, annotation transaction mới có thể bị bỏ qua.

Trong lab, event after_commit được xử lý khi original transaction đã hoàn tất. `REQUIRES_NEW` mở/commit transaction vật lý mới cho audit row. Test có thể truy vấn `audit_entries` sau khi `service.place(...)` trở về và thấy row durable.

**Điều không chứng minh:** Transaction mới vẫn có thể fail, connection pool có thể cạn; lab không giải quyết reliable remote event delivery hay idempotency.

## 16. PurchaseEventListeners.java — toàn bộ bốn pha

**src/main/java/example/events/PurchaseEventListeners.java**

```java
package example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PurchaseEventListeners {

    private final EventProbe probe;
    private final AuditWriter auditWriter;

    public PurchaseEventListeners(
            EventProbe probe,
            AuditWriter auditWriter) {
        this.probe = probe;
        this.auditWriter = auditWriter;
    }

    @EventListener
    public void immediate(PurchaseCreatedEvent event) {
        probe.mark("IMMEDIATE", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(PurchaseCreatedEvent event) {
        probe.mark("BEFORE_COMMIT", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreatedEvent event) {
        auditWriter.write(event);
        probe.mark("AFTER_COMMIT", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(PurchaseCreatedEvent event) {
        probe.mark("AFTER_ROLLBACK", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(PurchaseCreatedEvent event) {
        probe.mark("AFTER_COMPLETION", event.ref());
    }

    @TransactionalEventListener(fallbackExecution = true)
    public void ping(NoTxPingEvent event) {
        probe.mark("FALLBACK_PING", event.id());
    }
}
```

Trong lab không bật `@EnableAsync`, không thay custom ApplicationEventMulticaster và không cấu hình asynchronous executor. Do đó immediate listener chạy đồng bộ, còn transactional listeners được gọi theo các phase của JDBC transaction.

**Không assert một thứ tự duy nhất giữa AFTER_COMMIT và AFTER_COMPLETION**: cả hai liên quan completion và ordering chi tiết giữa listeners cùng phase có thể phụ thuộc registration/order. Nếu business cần thứ tự handlers, cần cân nhắc `@Order`/orchestration rõ ràng; không dùng thứ tự tình cờ trên máy dev làm contract.

### 16.1. Vì sao ping dùng event type riêng?

Listener có `fallbackExecution=true` thường vừa nhận event nếu transaction commit vừa nhận event trực tiếp khi không có transaction. Để unit/integration tests quan sát rõ “không có transaction vẫn chạy”, lab dùng `NoTxPingEvent` riêng, tránh nhầm số callbacks từ `PurchaseCreatedEvent`.

### 16.2. Không đưa remote side effect vào immediate listener

Trong mẫu, immediate listener chỉ ghi vào in-memory `EventProbe`. Nếu đưa email/webhook/Kafka send vào đó, rollback của DB **không hoàn tác** message đã rời process. Dùng after_commit cho best-effort notification, hoặc outbox pattern nếu yêu cầu delivery đáng tin cậy.

## 17. PurchaseEventIntegrationTest.java — chín tình huống

**src/test/java/example/events/PurchaseEventIntegrationTest.java**

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.sql.init.mode=always"
)
class PurchaseEventIntegrationTest {

    @Autowired
    PurchaseService service;

    @Autowired
    EventProbe probe;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ApplicationEventPublisher events;

    @BeforeEach
    void reset() {
        jdbc.update("delete from audit_entries");
        jdbc.update("delete from purchases");
        probe.clear();
    }

    @AfterEach
    void cleanUp() {
        jdbc.update("delete from audit_entries");
        jdbc.update("delete from purchases");
        probe.clear();
    }

    private long purchaseCount(String ref) {
        Long value = jdbc.queryForObject(
                "select count(*) from purchases where ref = ?",
                Long.class, ref);
        return value == null ? 0 : value;
    }

    private long auditCount(String ref) {
        Long value = jdbc.queryForObject(
                "select count(*) from audit_entries where ref = ?",
                Long.class, ref);
        return value == null ? 0 : value;
    }

    @Test
    void commitRunsCorrectPhasesAndPersistsAudit() {
        service.place("COMMIT-A");

        assertEquals(1L, purchaseCount("COMMIT-A"));
        assertEquals(1L, auditCount("COMMIT-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "COMMIT-A"));
        assertEquals(1L,
                probe.count("BEFORE_COMMIT", "COMMIT-A"));
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "COMMIT-A"));
        assertEquals(1L,
                probe.count("AFTER_COMPLETION", "COMMIT-A"));
        assertEquals(0L,
                probe.count("AFTER_ROLLBACK", "COMMIT-A"));

        assertTrue(probe.transactionActiveAt(
                "IMMEDIATE", "COMMIT-A"));
    }

    @Test
    void rollbackRunsRollbackNotCommitCallbacks() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.placeAndFail("ROLLBACK-A"));

        assertEquals("forced rollback",
                error.getMessage());
        assertEquals(0L, purchaseCount("ROLLBACK-A"));
        assertEquals(0L, auditCount("ROLLBACK-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "ROLLBACK-A"));
        assertEquals(0L,
                probe.count("BEFORE_COMMIT", "ROLLBACK-A"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "ROLLBACK-A"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "ROLLBACK-A"));
        assertEquals(1L,
                probe.count("AFTER_COMPLETION", "ROLLBACK-A"));
    }

    @Test
    void immediateRunsBeforeBeforeCommitAndAfterCommit() {
        service.place("ORDERING-A");

        List<String> phases = probe.phases("ORDERING-A");

        int immediate = phases.indexOf("IMMEDIATE");
        int beforeCommit = phases.indexOf("BEFORE_COMMIT");
        int afterCommit = phases.indexOf("AFTER_COMMIT");

        assertTrue(immediate >= 0);
        assertTrue(beforeCommit > immediate);
        assertTrue(afterCommit > beforeCommit);

        // Do not assume a fixed relative order for
        // AFTER_COMMIT versus AFTER_COMPLETION.
    }

    @Test
    void outsideTransactionOnlyImmediateListenerRuns() {
        events.publishEvent(
                new PurchaseCreatedEvent("NO-TX-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "NO-TX-A"));
        assertFalse(probe.transactionActiveAt(
                "IMMEDIATE", "NO-TX-A"));

        assertEquals(0L,
                probe.count("BEFORE_COMMIT", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_ROLLBACK", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_COMPLETION", "NO-TX-A"));
        assertEquals(0L, auditCount("NO-TX-A"));
    }

    @Test
    void fallbackExecutionHandlesEventWithoutTx() {
        events.publishEvent(
                new NoTxPingEvent("PING-A"));

        assertEquals(1L,
                probe.count("FALLBACK_PING", "PING-A"));
        assertFalse(probe.transactionActiveAt(
                "FALLBACK_PING", "PING-A"));
    }

    @Test
    void afterCommitAuditIsDurableInNewTransaction() {
        service.place("AUDIT-A");

        assertEquals(1L, purchaseCount("AUDIT-A"));
        assertEquals(1L, auditCount("AUDIT-A"));

        Integer rows = jdbc.queryForObject(
                "select count(*) from audit_entries " +
                "where ref = ? and phase = ?",
                Integer.class,
                "AUDIT-A", "AFTER_COMMIT");

        assertEquals(Integer.valueOf(1), rows);
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "AUDIT-A"));
    }

    @Test
    void twoEventsInOneCommitProduceTwoAudits() {
        service.placePair("PAIR-A", "PAIR-B");

        assertEquals(1L, purchaseCount("PAIR-A"));
        assertEquals(1L, purchaseCount("PAIR-B"));

        assertEquals(1L, auditCount("PAIR-A"));
        assertEquals(1L, auditCount("PAIR-B"));

        assertEquals(1L,
                probe.count("AFTER_COMMIT", "PAIR-A"));
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "PAIR-B"));
    }

    @Test
    void rolledBackPairDoesNotWriteAudit() {
        assertThrows(
                IllegalStateException.class,
                () -> service.placePairAndFail(
                        "PAIR-X", "PAIR-Y"));

        assertEquals(0L, purchaseCount("PAIR-X"));
        assertEquals(0L, purchaseCount("PAIR-Y"));

        assertEquals(0L, auditCount("PAIR-X"));
        assertEquals(0L, auditCount("PAIR-Y"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "PAIR-X"));
        assertEquals(1L,
                probe.count("IMMEDIATE", "PAIR-Y"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "PAIR-X"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "PAIR-Y"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "PAIR-X"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "PAIR-Y"));
    }

    @Test
    void ordinaryListenerIsSynchronousByDefault() {
        long callerThreadId =
                Thread.currentThread().getId();

        events.publishEvent(
                new PurchaseCreatedEvent("SYNC-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "SYNC-A"));
        assertEquals(callerThreadId,
                probe.threadIdAt("IMMEDIATE", "SYNC-A"));
        assertEquals(0L, auditCount("SYNC-A"));
    }
}
```

### 17.1. Bằng chứng của từng test

| Test | Observable được assert | Lỗi có thể phát hiện |
| --- | --- | --- |
| `commitRunsCorrectPhasesAndPersistsAudit` | Purchase + audit rows, 4 pha commit | Listener phase sai hoặc missing proxy |
| `rollbackRunsRollbackNotCommitCallbacks` | Database rollback, immediate/rollback/completion đúng | Gửi event thành công dù rollback |
| `immediateRunsBeforeBeforeCommitAndAfterCommit` | Order IMMEDIATE < BEFORE_COMMIT < AFTER_COMMIT | Sự kiện bị xử lý quá sớm/muộn |
| `outsideTransactionOnlyImmediateListenerRuns` | No-tx event không kích hoạt default transactional listeners | Tưởng afterCommit chạy không cần tx |
| `fallbackExecutionHandlesEventWithoutTx` | Ping no-tx được xử lý khi fallback=true | Không hiểu fallback semantics |
| `afterCommitAuditIsDurableInNewTransaction` | Audit row đọc được bằng JDBC sau method trả về | REQUIRES_NEW thiếu, dữ liệu không durable |
| `twoEventsInOneCommitProduceTwoAudits` | Hai event cùng tx, hai callbacks sau một commit | Chỉ xử lý một event/lost event |
| `rolledBackPairDoesNotWriteAudit` | Hai events rollback, không có audit | Side effect trước commit |
| `ordinaryListenerIsSynchronousByDefault` | Same caller thread, immediate callback trước publishEvent returns | Đổi multicaster async ngoài ý muốn |

### 17.2. Vì sao test class không có @Transactional?

Đây là **điểm quan trọng nhất của bài**. Không đặt `@Transactional` ở test class/method. `PurchaseService.place(...)` tự mở và commit transaction của **service proxy**, trước khi test method được tiếp tục. Vì vậy sau khi `service.place` trả, test có thể query DB và assert callbacks AFTER_COMMIT đã chạy.

Nếu đặt `@Transactional` lên JUnit test, Spring TestContext sẽ mặc định mở **test-managed transaction** rồi rollback sau test. Service propagation REQUIRED sẽ tham gia transaction đó; `AFTER_COMMIT` không được gọi trước assertion của test, và có thể không bao giờ được gọi khi test framework rollback. Những test “AFTER_COMMIT không chạy” kiểu này là **false negatives của test setup**, không phải code product.

### 17.3. Vì sao kiểm tra DB bên ngoài transaction service?

Sau khi `service.place` trả về, outer transaction interceptor đã hoàn tất. Query `JdbcTemplate` được thực hiện trong test không có @Transactional sẽ thấy dữ liệu committed, tránh việc test đọc “dữ liệu chưa commit của chính transaction đang mở” rồi gọi đó là durable.

### 17.4. Vì sao có cả rollback và commit?

Nếu test chỉ verify `@EventListener` được gọi, một rollback scenario vẫn pass vì listener chạy ngay. Nếu chỉ test `@TransactionalEventListener` commit path, một listener vô tình xử lý cả rollback có thể không bị phát hiện. Bài kiểm tra cả hai chiều.

### 17.5. Vì sao có test outside-transaction?

Có nhiều entry points không mở transaction. Với default transactional listeners, publish trực tiếp ngoài transaction sẽ không có callback. Đây là behavior đúng theo annotation contract, không phải event publisher không hoạt động.

## 18. Lệnh chạy dự án

Yêu cầu JDK 17 và Gradle Wrapper tương thích Spring Boot 3.3 (ví dụ Gradle 8.7). Nếu chưa có wrapper, tạo bằng Gradle phù hợp và commit wrapper artifacts; không giả định lệnh `./gradlew` tự xuất hiện khi chỉ copy source.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.events.PurchaseEventIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.events.PurchaseEventIntegrationTest
```

**Kết quả mong đợi:** 9 JUnit tests pass nếu source được đặt đúng package, Spring Boot 3.3 dependencies và embedded H2 hoạt động. Không có Docker hoặc external broker. Mẫu không in stdout cố định; đừng tạo log giả “BUILD SUCCESSFUL” như thể đã chạy. Cần xem Gradle test report thật để báo executed/pass/fail/skipped.

Lưu ý H2 sử dụng database in-memory và schema.sql để học về JDBC commit boundary. Nó không kiểm chứng PostgreSQL isolation level, MySQL replication, SQL Server triggers hoặc broker ack semantics. Nếu ứng dụng thực dùng một DB khác, cần bổ sung provider-specific integration tests (Testcontainers khi thích hợp).

## 19. Nếu bắt buộc dùng @Transactional trên JUnit test thì sao?

Spring TestContext mặc định rollback test-managed transactions. Nếu bạn cần kiểm soát commit ngay trong test, Spring có `TestTransaction`.

Ví dụ hướng dẫn (không nằm trong runnable class):

```java
@Transactional
@Test
void commitExplicitlyDuringTest() {
    service.place("CONTROLLED-A");

    // AFTER_COMMIT is not expected to run yet
    // while the test-managed transaction is active.

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Now the test transaction has ended with commit.
    // AFTER_COMMIT may be asserted here.
    assertEquals(1L, auditCount("CONTROLLED-A"));
}
```

Imports cần `org.springframework.test.context.transaction.TestTransaction`, `org.springframework.transaction.annotation.Transactional` và JUnit Test. Đoạn giả định service/probe/query helpers đã được inject từ Spring context và test-managed transactions được bật. Nếu cần tiếp tục làm việc trong một transaction test mới, dùng `TestTransaction.start()` theo contract.

### 19.1. @Commit và @Rollback(false)

`@Commit` hoặc `@Rollback(false)` khiến test transaction commit **khi test method kết thúc**; nếu assert AFTER_COMMIT **bên trong** method trước lúc kết thúc, callback chưa chạy. Có thể dùng `@AfterTransaction` để assert sau khi test transaction kết thúc, hoặc điều khiển bằng `TestTransaction.end()`.

### 19.2. @BeforeEach và @AfterEach trong transactional tests

Nếu test method có test-managed transaction, JUnit `@BeforeEach`/`@AfterEach` thường chạy **bên trong** test transaction. Đừng dùng chúng rồi giả định đã quan sát committed DB data ở ngoài transaction. Dùng `@BeforeTransaction`/`@AfterTransaction` khi cần boundary ngoài test transaction.

### 19.3. @DataJpaTest không giống full application

`@DataJpaTest` thường dùng test-managed rollback và chỉ nạp JPA slice. Nó có thể không scan service/event listener beans như full `@SpringBootTest`. Nếu test @TransactionalEventListener AFTER_COMMIT bằng JPA slice, cần import appropriate beans và chủ động commit boundary. Bài lab chọn JDBC + full context để tránh nhầm setup.

## 20. Thứ tự listener: phase order khác listener order

Trong một commit bình thường:

1. `@EventListener` synchronous nhận event ngay lúc publish.
2. `BEFORE_COMMIT` chạy trước commit.
3. Transaction manager commit database.
4. `AFTER_COMMIT` được gọi.
5. `AFTER_COMPLETION` liên quan hoàn tất.

Nhưng thứ tự **giữa hai listeners cùng phase** có thể bị ảnh hưởng bởi Spring listener ordering. Nếu cần thứ tự cụ thể, xem `@Order`, chính sách xử lý và phụ thuộc. `@Order` không biến hai transaction synchronizations thành một distributed atomic workflow.

### 20.1. Listener A publish lại event B

`@EventListener` có thể return event object để Spring publish tiếp (với các giới hạn nhất định; async listeners có caveats). Điều đó tạo chuỗi events. Trong hệ thống phức tạp, nested event publication có thể làm event count tăng hoặc listener order khó hiểu; test nên assert expected event graph, không chỉ number of business calls.

### 20.2. Listener exceptions

- Synchronous `@EventListener` throw unchecked exception trước commit có thể làm publisher method fail và rollback.
- `BEFORE_COMMIT` callback throw có thể abort commit/trigger rollback.
- `AFTER_COMMIT` failure xảy ra **sau commit**; original DB transaction không thể bị undo.
- `AFTER_COMPLETION` errors có thể được log thay vì propagate tùy transaction synchronization implementation; không giả định mọi exception callback đều xuất hiện với caller.
- Async `@EventListener` exception thường không propagate về publisher như synchronous listener.

Không thiết kế tests chỉ dựa vào một chuỗi exception text mà bỏ qua database final state.

## 21. @Async thay đổi tính chắc chắn của kiểm thử

Mặc định Spring event multicaster synchronous. Nếu dùng:

```java
@Async
@EventListener
public void asyncHandle(PurchaseCreatedEvent event) {
    // Executes on an executor thread when @Async is enabled.
}
```

đây là snippet minh họa, yêu cầu `@EnableAsync`/executor configuration tương ứng. Nó **không** là code runnable của lab, và có những khác biệt:

- Test không được assert callback xong **ngay sau** `publishEvent` nếu async.
- Context/ThreadLocal transaction từ publisher **không tự truyền** sang executor thread.
- Exceptions không được propagate về publisher như synchronous callbacks.
- Dùng synchronization primitives/awaitility với timeout hữu hạn và event observations thread-safe.
- Không dùng `Thread.sleep(2000)` làm bằng chứng callback đã chạy; CI có thể chậm.
- Không nhầm async in-process processing với reliable durable message processing.

Với `@TransactionalEventListener`, cần hiểu Spring transaction-bound listener registration/execution và tính tương thích executor; không đơn giản trộn `@Async` để “khỏi chặn thread commit” mà không test thread/transaction boundaries.

## 22. TransactionalEventListener trong reactive transaction

Bài lab dùng **imperative JDBC**, `PlatformTransactionManager` và thread-bound transaction synchronizations.

Từ Spring Framework 6.1, transactional event listeners cũng có hỗ trợ cho **reactive transactions** sử dụng `ReactiveTransactionManager`, nhưng transaction context của Reactor không giống ThreadLocal. Khi publish trong reactive pipeline, cần dùng cơ chế tương ứng (ví dụ `TransactionalEventPublisher`) để mang transaction context trong event source khi cần.

**Không copy JDBC test này sang R2DBC/WebFlux rồi mặc định transaction callback hoạt động y hệt.**

### 22.1. Reactor Context không phải Servlet ThreadLocal

Reactive transaction state được truyền qua Reactor Context, không đi theo một Java thread cố định. Gọi `publishEvent` trực tiếp ở một callback chạy trên scheduler bất kỳ có thể không truyền đúng transaction context. Phải thiết kế context propagation, publishing trong reactive chain và test với Reactor `StepVerifier` cùng reactive transaction manager.

### 22.2. Một test hoàn chỉnh cho R2DBC cần gì?

- R2DBC connection factory/database với transaction support.
- `R2dbcTransactionManager` hoặc reactive transaction manager phù hợp.
- Reactive repository/DatabaseClient operations.
- `TransactionalEventPublisher`/publisher logic đúng version.
- Assert events sau commit/rollback của reactive publisher, không chỉ sau khi tạo Mono.
- Multi-subscription isolation và virtual/real scheduler considerations.
- Negative tests cho missing transaction context.

Không tuyên bố `@TransactionalEventListener` bị giới hạn chỉ ở JDBC kể từ Spring Framework 6.1; vấn đề là **cách mang transaction context khác nhau**.

## 23. Events và observability

Vì nhóm cha là **Sự kiện và observability**, cần quan sát lifecycle bằng metrics/logs/traces thay vì chỉ test business row.

Ví dụ metric contract:

| Metric | Loại | Tags bounded | Ý nghĩa |
| --- | --- | --- | --- |
| `purchase.events.published` | Counter | `event=created` | Số lần publish trong process |
| `purchase.events.committed` | Counter | `event=created` | Số lần AFTER_COMMIT callback |
| `purchase.events.rollback` | Counter | `event=created` | Số lần AFTER_ROLLBACK callback |
| `purchase.events.handler.duration` | Timer | `phase=after_commit|rollback` | Listener processing latency |
| `purchase.events.failures` | Counter | `phase,exception_type` với set hữu hạn | Callback failures |

**Không đồng nhất số published với số committed.** Published tăng ngay trước commit; transaction có thể rollback. Không đặt `ref`, `orderId`, email hoặc requestId làm metric tags vì cardinality rất cao; dùng structured logs/traces nếu cần đối chiếu một event cụ thể.

### 23.1. Không ghi sensitive payload vào logs

Chỉ log event ID, reference đã được masking theo policy, phase và correlation IDs an toàn. Không log token, PII hoặc full payload payment/customer. Khi cần diagnose AFTER_COMMIT failure, log event ID + exception type + correlation trace, tránh message có secrets.

### 23.2. Metrics không chứng minh durable event delivery

Counter sau commit là một **in-process observation**, không chứng minh downstream Kafka/email đã nhận và acknowledge event. Cần broker producer/consumer integration test hoặc outbox relay test phù hợp.

### 23.3. Trace boundary

Một synchronous listener thường nằm trong execution/correlation context của publisher. Khi chuyển async executor hoặc broker, cần explicit trace/context propagation; không tự giả định trace MDC ThreadLocal được chuyển qua mọi thread/queue. Test correlation ở boundaries theo observability stack thực.

## 24. Transactional outbox: khi afterCommit vẫn chưa đủ

Tình huống:

1. Purchase transaction commit.
2. `AFTER_COMMIT` callback chuẩn bị gửi Kafka.
3. JVM crash trước khi gửi.
4. Database có purchase nhưng không có Kafka event.

`@TransactionalEventListener(AFTER_COMMIT)` giúp **không gửi trước commit**, nhưng không giải quyết khoảng trống **commit xong nhưng chưa gửi**.

Transactional outbox thay bằng:

```text
Begin database transaction
    |
    +-- INSERT purchases(...)
    +-- INSERT outbox_event(
            id, type, payload, state='NEW')
    |
Commit both rows atomically
    |
    v
Outbox relay reads NEW events
    |
    +-- sends to broker with retry
    +-- marks processed/delivered
    |
    v
Idempotent consumer de-duplicates event id
```

Đây là design sketch, không có outbox code trong runnable lab. Nó yêu cầu thêm repository/schema, relay worker, backoff/retries, duplicate handling, dead-letter policy và monitoring. Không nói “outbox mặc định exactly once”: relay có thể gửi trùng khi crash sau broker send nhưng trước DB ack; consumer phải idempotent hoặc dùng cơ chế giao nhận phù hợp.

### 24.1. Khi nào dùng afterCommit đủ?

- Best-effort in-process cache invalidation.
- Optional notification có thể mất theo business policy.
- Noncritical local observation.
- Side effect có đường repair/periodic reconciliation.

### 24.2. Khi nào nên ưu tiên outbox?

- Tạo invoice/payment/shipping external command cần delivery.
- Đồng bộ dữ liệu business quan trọng sang message broker.
- Có legal/audit guarantee về event processing.
- Cần retry sau process restart và khả năng đối soát.

Đừng chỉ thay `@EventListener` bằng `@TransactionalEventListener` rồi coi mọi vấn đề consistency/distributed delivery đã giải xong.

## 25. Các kiểu sai lầm gây test xanh giả

### 25.1. @Transactional trên test method mặc định rollback

`@SpringBootTest @Transactional @Test` là một test-managed transaction. Service `@Transactional(REQUIRED)` tham gia transaction của test. `AFTER_COMMIT` không chạy cho tới khi transaction commit; test framework rollback mặc định. Vì vậy assert afterCommit ngay sau service call bên trong method thường sai.

**Khắc phục:** bỏ `@Transactional` khỏi commit integration test hoặc dùng `TestTransaction.flagForCommit()/end()`, `@Commit` + `@AfterTransaction`.

### 25.2. Mock ApplicationEventPublisher

Mockito `verify(events).publishEvent(...)` chỉ chứng minh service gọi method publisher, không chứng minh Spring đã đăng ký listener, transaction phase, JDBC commit hay callback order. Dùng real ApplicationContext và transaction manager khi mục tiêu là transaction-bound behavior.

### 25.3. Test gọi listener method trực tiếp

`listeners.afterCommit(event)` chạy Java method ngay, bypass Spring transactional synchronization. Unit test này chỉ kiểm tra handler business logic; **không** chứng minh annotation `@TransactionalEventListener` đã được áp dụng.

### 25.4. Test chỉ assert callback count

Số lần `afterCommit` tăng không chứng minh audit row durable nếu code ghi DB trong resource context sau commit mà không có `REQUIRES_NEW`. Test đọc audit row **sau khi service transaction đã hoàn tất**, bằng JDBC ngoài transaction.

### 25.5. Chỉ test commit mà không test rollback

Nếu dùng `@EventListener` cho external send, commit test vẫn pass. Rollback test mới cho thấy side effect có thể xảy ra trước khi DB rollback. Thêm cả positive và negative paths.

### 25.6. Quên fallbackExecution

Publish ngoài tx với transactional listener mặc định sẽ không gọi. Một test chờ callback mãi vì không có transaction là test setup sai. Nếu business cho phép no-tx event, bật `fallbackExecution=true` có chủ đích và test riêng.

### 25.7. @Transactional self-invocation

Gọi public annotated method từ chính class mà không qua proxy có thể không mở outer tx. Đưa transaction boundary ra Spring bean và test qua injected service.

### 25.8. Lẫn BEFORE_COMMIT với guaranteed commit

`BEFORE_COMMIT` có thể chạy trước DB commit failure. Không gửi irreversible external effects ở phase này rồi gọi là “chỉ sau commit”.

### 25.9. Mặc định mọi event đều bất đồng bộ

`@EventListener` mặc định synchronous. Nếu test phải chờ async callbacks, hãy kiểm tra xem app thực sự dùng custom executor/`@Async` không. Không thêm sleep tùy tiện vào test synchronous.

### 25.10. Quên method rollback rules

Checked exception mặc định có thể không rollback. Test throw `IllegalStateException` hoặc explicit `rollbackFor` theo contract. Không kết luận listener sai khi transaction thực sự commit bởi rollback rule khác.

### 25.11. Viết DB từ AFTER_COMMIT với REQUIRED

Callback có thể thấy resources vẫn bound dù original tx đã committed; write mới không chắc được commit. Separate `REQUIRES_NEW` bean và kiểm chứng bằng DB row, không chỉ Java mock call.

### 25.12. Rò state của EventProbe giữa tests

Spring ApplicationContext được cache; singleton `EventProbe` giữ marks từ test trước. Dùng `@BeforeEach`/`@AfterEach` clear và DB cleanup. Không dựa test execution order.

### 25.13. Parallel tests chung database/probe

Một test có thể xóa observation/row của test khác trong @AfterEach. Lab mặc định chạy test methods tuần tự. Nếu bật JUnit parallel, dùng isolation per test (DB schema/container, probe scope) hoặc `@Execution(SAME_THREAD)`, không “chữa” bằng sleep.

### 25.14. @Async làm mất ThreadLocal transaction

Nếu dùng executor, thread-bound tx của publisher không tự theo listener, và errors có thể không quay lại publisher. Không tự trộn `@Async` vào transactional callback mà không test propagation/side effects.

### 25.15. Dùng event in-process làm distributed queue

Spring application events chỉ giao tiếp giữa beans trong cùng ApplicationContext/process. Không có durable broker offset, delivery ack, retries hoặc persisted queue mặc định.

## 26. Debugging khi test không khớp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| IMMEDIATE không chạy | Listener không phải Spring bean, event type sai | @Component, scan package, publishEvent |
| IMMEDIATE chạy dù DB rollback | Đúng synchronous semantics | Dùng AFTER_COMMIT cho commit-dependent work |
| AFTER_COMMIT không chạy | Không có tx, rollback, test @Transactional auto rollback | Tx boundary, rollback rules, TestTransaction |
| AFTER_COMMIT chạy khi tưởng rollback | Checked exception không rollback, exception đã catch | Spring rollback rules/tx status |
| BEFORE_COMMIT không chạy | Rollback sớm hoặc không active transaction | Service proxy/transaction manager |
| AFTER_ROLLBACK không chạy | Transaction đã commit hoặc event ngoài tx | Kiểm tra actual outcome |
| AFTER_COMPLETION chạy cả rollback | Đúng semantics | Không coi completion là success |
| fallback listener chạy không tx | fallbackExecution=true | Expected contract |
| AuditWriter ghi row nhưng DB không thấy | Không có new tx từ AFTER_COMMIT | REQUIRES_NEW separate Spring bean |
| Audit row 2 lần | Event publish 2 lần, retries/duplicates | Event IDs, idempotency |
| Context test báo committed nhưng DB trống | Test-managed transaction chưa commit | @Transactional test, TestTransaction |
| Service @Transactional không kích hoạt | Self-invocation/private method/new object | Spring AOP proxy |
| Event không sang thread khác | @EventListener synchronous | Đúng default, dùng @Async nếu cần |
| Async listener không thấy transaction | ThreadLocal không propagate | Context propagation/design |
| AFTER_COMMIT error rồi retry tạo duplicate | Purchase đã commit trước callback fail | Idempotency/outbox |
| Test random failure khi parallel | Shared DB/Probe cleanup races | Disable parallel/isolate |
| H2 schema missing | schema.sql không init, datasource config sai | spring.sql.init.mode/Boot logs |
| Duplicate application contexts | TestContext cache, multiple beans | Component scan/configuration |
| Event value bị thay đổi trước callback | Mutable event payload shared | Immutable record/IDs |
| Kafka không nhận event dù AFTER_COMMIT chạy | Remote send failure/process crash | Outbox, broker integration test |

### 26.1. Log transaction debugging

Trong test profile (không phải production), có thể bật:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc=DEBUG
logging.level.org.springframework.context.event=DEBUG
```

Logs giúp xem commit/rollback và event multicaster flow. Không bật quá rộng trong production nếu chứa SQL params, event payload, PII hoặc secrets. Hãy kết hợp logs với DB final-state assertions thay vì thay thế assertions.

### 26.2. Vì sao không assert elapsed time cố định?

Ở synchronous tests, listener chạy ngay nhưng thời gian commit/callback phụ thuộc DB/JVM/CI scheduling. Test đo **observable phase counts và persisted data**, không dùng `Thread.sleep(100)` rồi tuyên bố callback chắc đã chạy.

## 27. Kiểm thử với nhiều transaction managers

Lab chỉ có một H2 DataSource/transaction manager. Trong ứng dụng lớn có thể có:

- Một database PostgreSQL và một Redis cache.
- Hai DataSources với hai PlatformTransactionManagers.
- JPA + Kafka transaction manager.
- Một reactive transaction manager riêng.

`@Transactional` cần chọn đúng manager, ví dụ `@Transactional(transactionManager="ordersTransactionManager")`; event transactional phase gắn với **transaction context hiện tại**, không có nghĩa mọi external resources được commit atomically.

Nếu service có nested method dùng `REQUIRES_NEW` trên transaction manager khác, callback có thể gắn với inner/outer transaction tùy nơi publish event. Test cần xác định **transaction được gắn với event** và không giả định mọi database/broker commit cùng lúc.

### 27.1. Propagation REQUIRED, REQUIRES_NEW và NESTED

| Propagation | Ý nghĩa khái quát | Ảnh hưởng tới events |
| --- | --- | --- |
| `REQUIRED` | Join existing tx hoặc tạo tx mới | Listener gắn với transaction bao quanh |
| `REQUIRES_NEW` | Suspend existing và mở transaction độc lập | Commit/rollback phase của inner tx khác outer |
| `NESTED` | Savepoint-based nested transaction nếu manager hỗ trợ | Savepoint rollback không luôn tương đương outer completion events |
| `SUPPORTS` | Có tx thì join, không có thì chạy no-tx | Event có thể không được transactional listener nhận |
| `NOT_SUPPORTED` | Suspend transaction, chạy ngoài tx | Default transactional listener bị skip |

Đây là khái niệm Spring transaction propagation; hỗ trợ cụ thể tùy transaction manager. Không dùng propagation chỉ để làm event test pass, mà cần design commit boundary theo business contract.

## 28. Bài tập thực hành

1. **Đổi AFTER_COMMIT thành @EventListener:** chạy rollback test, quan sát audit có thể được ghi dù purchase rollback nếu audit writer mở REQUIRES_NEW. Giải thích tại sao side effect trước commit nguy hiểm.
2. **Bỏ REQUIRES_NEW:** thay AuditWriter.write bằng propagation REQUIRED, chạy audit durability test; kiểm tra row thật sau commit, không chỉ handler được gọi.
3. **Thêm @Transactional lên test class:** commit test có thể không thấy AFTER_COMMIT trước assertion. Khôi phục hoặc dùng TestTransaction.
4. **Dùng TestTransaction:** tạo một test-managed tx, gọi service, `flagForCommit()/end()` và assert callbacks sau end.
5. **Đổi exception thành checked exception:** quan sát default rollback rules, thêm `rollbackFor` nếu business cần rollback.
6. **Bỏ @Transactional trên PurchaseService.place:** publish event không có enclosing transaction; immediate vẫn chạy, default transactional listeners skip.
7. **Bật fallbackExecution cho PurchaseCreatedEvent listener:** publish no-tx event và quan sát callback chạy ngay; cân nhắc rủi ro business.
8. **Throw trong immediate listener:** thử nghiệm trong sandbox và xem transaction rollback do unchecked exception; không làm trên môi trường production.
9. **Throw trong AFTER_COMMIT listener:** kiểm tra purchase đã committed dù caller có thể thấy exception; thêm retry/idempotency strategy.
10. **Đổi event record thành mutable class:** sửa fields sau publish trước commit, quan sát callback có thể thấy payload khác; khôi phục immutable record.
11. **Hai events một transaction:** kiểm tra cả hai chỉ tạo audit khi commit và không tạo audit khi rollback.
12. **Thêm @Order cho hai listeners cùng phase:** assert ordering khi đó thật sự là business contract; không dựa vào random registration order.
13. **Bật @Async cho listener:** viết test dùng CountDownLatch/timeout, kiểm tra propagation và exception policy.
14. **Dùng JPA thay JDBC:** thêm Spring Data JPA/H2, xử lý flush/transaction boundaries; không chỉ @DataJpaTest auto rollback.
15. **Thêm Micrometer counters:** phân biệt events.published với events.committed và events.rollback, tag bounded.
16. **Bổ sung outbox:** lưu purchase và outbox rows trong cùng SQL transaction, viết relay idempotent và crash/retry integration tests.
17. **Multi-data-source:** xác định event gắn với transaction manager nào, mô phỏng commit A/rollback B.
18. **Reactive R2DBC:** dùng TransactionalEventPublisher với Reactor context và StepVerifier.
19. **Publish sau transaction trong service caller:** phân biệt “code nằm sau service.place returns” với callback scheduled bởi transaction synchronization.
20. **Test provider DB thật:** chạy PostgreSQL Testcontainers để xác minh transaction isolation/constraints của provider production.

## 29. Checklist QA

- [ ] Biết event đang publish ở trong hay ngoài transaction.
- [ ] Đã xác minh `@EventListener` immediate behavior trong cấu hình synchronous.
- [ ] Default `@TransactionalEventListener` hiểu là AFTER_COMMIT.
- [ ] Đã test cả commit và rollback, không chỉ success.
- [ ] BEFORE_COMMIT không bị xem là commit guaranteed.
- [ ] AFTER_ROLLBACK chỉ chạy khi rollback thực.
- [ ] AFTER_COMPLETION chạy cả commit và rollback.
- [ ] No-tx event với fallback=false không có transactional callbacks.
- [ ] fallbackExecution=true được dùng có chủ đích khi cho phép no-tx.
- [ ] Service @Transactional được gọi qua Spring-managed bean proxy.
- [ ] Không self-invocation/private transaction method để mở tx.
- [ ] Checked/unchecked exception rollback rules được hiểu rõ.
- [ ] Audit viết sau commit dùng REQUIRES_NEW riêng, test DB durable.
- [ ] Không gọi repository.save trong AFTER_COMMIT rồi mặc định được commit.
- [ ] Không coi AFTER_COMMIT failure rollback được original purchase.
- [ ] Test không có @Transactional auto rollback nếu đang assert real commit.
- [ ] Nếu test-managed transaction, dùng TestTransaction hoặc @AfterTransaction đúng lúc.
- [ ] DB rows và event probe được reset giữa tests.
- [ ] Test không phụ thuộc method order.
- [ ] Parallel tests không xóa chung DB/probe ngoài ý muốn.
- [ ] Bài kiểm thử phân biệt in-process events và durable broker delivery.
- [ ] Không dùng Thread.sleep làm oracle cho synchronous callbacks.
- [ ] @Async/custom multicaster được test riêng khi có sử dụng.
- [ ] Transaction-bound listeners trong reactive flow có Reactor context đúng.
- [ ] Không gắn user/order ID trực tiếp vào metrics tags vô hạn.
- [ ] Production event processing có idempotency/retry/outbox khi cần.
- [ ] Test report ghi số executed/passed/failed/skipped thực, không tuyên bố expected là đã chạy.
- [ ] Không đưa H2 test thành bằng chứng mọi database/broker transaction hoạt động giống nhau.

## 30. Quy tắc chọn listener và kiểm thử

```text
Sự kiện cần phản ứng lúc nào?
      |
      +-- Ngay khi method publish?
      |      -> @EventListener.
      |         Test synchronous invocation + rollback case.
      |
      +-- Chỉ nếu transaction commit?
      |      -> @TransactionalEventListener(AFTER_COMMIT).
      |         Test commit/rollback and durability.
      |
      +-- Trước commit?
      |      -> BEFORE_COMMIT.
      |         Test no guarantee commit succeeds afterward.
      |
      +-- Chỉ khi rollback?
      |      -> AFTER_ROLLBACK.
      |
      +-- Sau bất kỳ completion?
      |      -> AFTER_COMPLETION.
      |
      +-- Event có thể publish ngoài tx?
      |      -> fallbackExecution=true if business approves,
      |         otherwise require transaction and test missing-tx.
      |
      +-- Cần ghi DB từ completion callback?
      |      -> Separate @Transactional(REQUIRES_NEW) bean.
      |
      +-- Cần message giao được sau crash?
             -> Transactional outbox + relay + idempotency.
```

**Kết luận:** `@EventListener` xác nhận **sự kiện đã được publish**, không xác nhận database commit. `@TransactionalEventListener` cho phép gắn xử lý vào các transaction phases, với `AFTER_COMMIT` mặc định. Để kiểm thử đúng, dùng **transaction thật**, cả commit/rollback/no-tx paths, đọc **database state đã committed** và tránh test-managed auto-rollback che mất commit callbacks. Nếu ghi dữ liệu sau commit, dùng `REQUIRES_NEW` trên Spring bean riêng. Với thông điệp quan trọng vượt process, kết hợp outbox/idempotency thay vì chỉ dựa vào listener nội bộ.

## 31. Tài liệu chính thức

- Spring Framework — Transaction-bound Events và bốn pha: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.1 Javadoc — @TransactionalEventListener, fallback, after-commit resource caveat: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — Annotation-based Event Listeners, sync/async behavior: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Declarative Transactions và propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation REQUIRED, REQUIRES_NEW, NESTED: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — TestContext transaction management, @Commit, @Rollback, TestTransaction: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TransactionSynchronizationManager API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — TransactionSynchronization API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — ApplicationEventPublisher API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Reactive TransactionalEventPublisher: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — SQL database initialization: https://docs.spring.io/spring-boot/3.3/reference/how-to/data-initialization.html
- JUnit Jupiter — Lifecycle and integration testing: https://docs.junit.org/current/user-guide/
