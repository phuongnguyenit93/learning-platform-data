# Kiểm thử after-commit event và tác vụ chỉ chạy sau commit

## 1. Bối cảnh, mục tiêu và phạm vi

Trong Spring Boot, một nghiệp vụ thường ghi dữ liệu vào database rồi mới phát thông báo, ghi audit, xóa cache, đẩy công việc vào hàng đợi hoặc gửi domain event. Rủi ro xuất hiện nếu tác vụ bên ngoài được thực hiện **trước khi transaction commit thành công**: transaction có thể rollback nhưng khách hàng đã nhận email xác nhận đơn hàng không tồn tại.

Spring Framework cung cấp `@TransactionalEventListener` để liên kết việc xử lý event với vòng đời transaction. Phase `TransactionPhase.AFTER_COMMIT` cho phép xử lý event **sau khi database transaction commit thành công**. Tuy nhiên, bản thân cơ chế này không lưu event bền vững: ứng dụng vẫn có thể crash sau commit nhưng trước khi phát thông báo. Vì vậy bài học phải tách rõ:

- **Đúng thời điểm**: listener không chạy khi rollback và không chạy trước commit.
- **Đúng dữ liệu**: tác vụ nhận event/ID tương ứng, đọc được trạng thái đã commit.
- **Đúng transaction tiếp theo**: thao tác ghi database bên trong after-commit cần transaction mới khi phù hợp.
- **Đúng mức tin cậy**: retry, idempotency, durable outbox nếu không thể chấp nhận mất hoặc lặp event.
- **Đúng kiểm thử**: `@DataJpaTest` rollback mặc định không tự kiểm được after-commit happy path.

Bạn sẽ học cách dùng `@TransactionalEventListener(AFTER_COMMIT)`, `@Commit`, `@Rollback(false)`, `TestTransaction`, `@BeforeTransaction`/`@AfterTransaction` và `@SpringBootTest` để kiểm những trường hợp này. Bài có project Maven Java 17 với Spring Boot 3.5.16, Spring Data JPA, H2, JUnit Jupiter và những lớp test chỉ ra rõ commit/rollback timeline.

**Điểm cốt lõi:** `save()` hay `saveAndFlush()` thành công chưa phải transaction đã commit. Test phải kiểm ở một thời điểm **sau commit thực sự** hoặc chứng minh side effect không xảy ra khi rollback.

## 2. Cơ chế @TransactionalEventListener

### 2.1. Event được phát khi nào?

Một service có thể phát domain event khi vẫn đang trong transaction:

~~~java
@Service
class CheckoutService {
    private final ApplicationEventPublisher publisher;

    @Transactional
    public void placeOrder(String id) {
        // repository.save(...)
        publisher.publishEvent(new OrderPlaced(id));
    }
}
~~~

Đây là snippet minh họa, không phải Java file biên dịch độc lập. `publishEvent` truyền event tới event infrastructure. Listener thông thường gắn `@EventListener` có thể chạy ngay khi publish; `@TransactionalEventListener` đăng ký callback theo phase của transaction hiện tại.

Sơ đồ đơn giản:

~~~text
service @Transactional
  |
  +-- begin T1
  +-- INSERT business row
  +-- publishEvent(OrderPlaced)
  |     |
  |     +-- @TransactionalEventListener đăng ký synchronization
  |
  +-- BEFORE_COMMIT callbacks
  +-- database COMMIT T1
  +-- AFTER_COMMIT callbacks
  +-- AFTER_COMPLETION callbacks
  +-- cleanup transaction resources
  |
  +-- service caller tiếp tục
~~~

Trình tự biểu diễn **ý nghĩa lifecycle**. Chi tiết callback/interceptor và thời điểm tài nguyên được giải phóng có thể khác tùy transaction manager. Không dùng nó để khẳng định mọi loại listener, executor hay remote side effect hoàn thành cùng một thời điểm.

### 2.2. Bốn phase cần nhớ

| Phase | Điều kiện | Ý nghĩa dùng trong test |
| --- | --- | --- |
| `BEFORE_COMMIT` | Transaction chuẩn bị commit | Chưa được phép kết luận transaction thành công |
| `AFTER_COMMIT` | Transaction đã commit thành công | Có thể bắt đầu post-commit work |
| `AFTER_ROLLBACK` | Transaction rollback | Chứng minh success task không được kích hoạt |
| `AFTER_COMPLETION` | Transaction hoàn tất, dù commit hay rollback | Cleanup/metrics cho cả hai đường |

`AFTER_COMMIT` là phase **mặc định** của `@TransactionalEventListener`. Viết rõ `phase = TransactionPhase.AFTER_COMMIT` khi business requirement cần đọc một cách tường minh.

### 2.3. @EventListener khác gì?

~~~java
@EventListener
void immediate(OrderPlaced event) {
    // Handler thông thường; không tự đợi transaction commit.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void committed(OrderPlaced event) {
    // Handler theo phase, chỉ sau successful commit.
}
~~~

Cả hai đều là snippets mô tả. Nếu ứng dụng cấu hình event multicaster hoặc `@Async` đặc biệt, thời điểm callback có thể khác. Test phải dựa trên cấu hình thật, không coi mọi listener được gọi đồng bộ trong mọi trường hợp.

### 2.4. Không có active transaction?

Theo Spring Framework 6.2, `@TransactionalEventListener` mặc định có `fallbackExecution = false`. Khi publish event **ngoài transaction**, listener không xử lý event vì không có một commit boundary để liên kết.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = false)
void afterCommit(OrderPlaced event) {
    // Không gọi khi publish bên ngoài transaction.
}
~~~

Nếu business cần xử lý event ngay cả khi không có transaction, có thể dùng `fallbackExecution = true`. Khi đó test phải phân biệt **fallback không có transaction** với **AFTER_COMMIT có transaction**; không gọi fallback là commit đã thành công.

### 2.5. Transaction imperative và reactive

Bài này dùng Spring Data JPA và `PlatformTransactionManager`: transaction context gắn với thread, thường qua `ThreadLocal`. Spring Framework 6.1+ cũng hỗ trợ reactive transaction event với `ReactiveTransactionManager`, nhưng transaction context nằm trong Reactor Context; cần dùng cách publish event mang transaction context thích hợp, chẳng hạn `TransactionalEventPublisher`. Không áp trực tiếp `TestTransaction` JPA sang reactive publishers.

## 3. Vì sao test mặc định có thể đánh lừa?

### 3.1. @DataJpaTest rollback sau test

`@DataJpaTest` trong Spring Boot 3.5 cấu hình transactional test và **rollback mặc định**. Service `@Transactional(propagation = REQUIRED)` được gọi qua Spring proxy thường tham gia outer test-managed transaction, thay vì mở transaction độc lập.

~~~text
Spring TestContext mở T1
  |
  +-- test gọi service.placeOrder()
  |    +-- repository.saveAndFlush(...)
  |    +-- publisher.publishEvent(...)
  |
  +-- assert repository.findById -> có dữ liệu trong T1
  +-- assert listener AFTER_COMMIT -> chưa chạy
  |
  +-- TestContext rollback T1
       +-- AFTER_COMMIT không chạy
       +-- AFTER_ROLLBACK chạy (nếu có đăng ký)
~~~

Bài test trong T1 query thấy entity không chứng minh entity đã commit. Vì thế một test `@DataJpaTest` chỉ assert status của repository có thể xanh nhưng bỏ sót email/audit/outbox task bắt buộc phải chạy sau commit.

### 3.2. flush khác commit

- `repository.save(entity)` cập nhật trạng thái JPA persistence context; SQL có thể chạy trước hoặc sau tùy ID generation/flush.
- `repository.flush()` gửi các SQL thay đổi đang chờ tới database nhưng **không kết thúc transaction**.
- `saveAndFlush(entity)` thực hiện save rồi flush; có thể phát hiện ngay constraint violation.
- `commit` hoàn tất transaction và kích hoạt cơ chế sau commit.
- `rollback` hủy những thay đổi DB thuộc transaction đó; external side effects đã xảy ra thì không tự biến mất.

Một số deferred constraints ở PostgreSQL có thể chỉ báo lỗi **tại commit**, không phải flush. Nếu yêu cầu kiểm trường hợp đó, phải dùng database thật/Testcontainers và assert quanh commit; H2 demo không thay thế.

### 3.3. @SpringBootTest không tự rollback

`@SpringBootTest` tải application context nhưng **không tự gắn `@Transactional` lên test method**. Nếu test không có outer test transaction, một service `@Transactional(REQUIRED)` sẽ thường mở/commit transaction của nó khi method kết thúc. Callback AFTER_COMMIT đồng bộ có thể được kiểm sau service return.

Ngược lại, thêm `@Transactional` trên test `@SpringBootTest` lại tạo test-managed transaction, thường rollback cuối test. Chọn loại test theo mục tiêu, không theo ý nghĩ “integration test lúc nào cũng tự rollback”.

### 3.4. JUnit lifecycle nằm ở đâu?

Với Spring transactional test:
- `@BeforeEach` và `@AfterEach` thường chạy **bên trong** test-managed transaction.
- `@BeforeTransaction` chạy **trước** khi mở T1.
- `@AfterTransaction` chạy **sau** khi T1 đã hoàn tất.
- `@Commit`/`@Rollback(false)` thay đổi kết quả cuối T1; commit xảy ra **sau** test body.
- `TestTransaction.flagForCommit()` + `TestTransaction.end()` có thể commit T1 **ngay trong test**.

Do đó, assertion “listener đã chạy” trong `@AfterEach` của test có `@Commit` vẫn có thể quá sớm. Dùng `@AfterTransaction` hoặc `TestTransaction.end()`.

## 4. Các chiến lược kiểm thử AFTER_COMMIT

### 4.1. Full context, không có outer test transaction

~~~java
@SpringBootTest
class CheckoutIntegrationTest {
    @Autowired CheckoutService checkout;

    @Test
    void committed() {
        checkout.place("purchase-1");
        // Nếu listener đồng bộ, test kết quả sau khi method trả về.
    }
}
~~~

Snippet này cần service thật; project đầy đủ xuất hiện ở phần 7. Không có test `@Transactional`, nên service tự quản transaction của nó. Test phải cleanup dữ liệu đã commit.

### 4.2. @DataJpaTest + @Commit + @AfterTransaction

~~~java
@DataJpaTest
class CommitTest {
    @Test
    @Commit
    void creates() {
        // Ghi data và publish event trong test transaction.
    }

    @AfterTransaction
    void verifies() {
        // Đã kết thúc T1, có thể kiểm callback và committed rows.
    }
}
~~~

Nếu class cần service/listener `@Component` thông thường, thêm `@Import(...)` có chọn lọc: `@DataJpaTest` không tự scan toàn bộ business service graph. Sau test commit, dữ liệu đã lưu **không tự bị xóa**; cleanup phải dùng transaction riêng, thường trong `@AfterTransaction`/`finally`.

### 4.3. @Rollback(false) thay cho @Commit

`@Rollback(false)` có cùng mục đích thay đổi default rollback thành commit đối với test-managed transaction. Dùng `@Commit` khi muốn intent rõ; không đặt cả hai annotation trên cùng method nếu không cần. Ở class-level `@Commit`, có thể override method-level với `@Rollback`.

### 4.4. TestTransaction.commit ngay giữa method

~~~java
checkout.place("purchase-2");
TestTransaction.flagForCommit();
TestTransaction.end();

// Assert committed row và listener, sau đó cleanup.
~~~

`TestTransaction` chỉ dùng khi test-managed transaction đang active. Nếu muốn mở T2 sau khi commit T1, gọi `TestTransaction.start()` và kiểm data trong transaction đọc mới; lưu ý T2 có thể rollback nhưng row đã commit từ T1 vẫn tồn tại và vẫn cần cleanup.

### 4.5. Ma trận

| Test setup | Khi nào commit? | Assert thích hợp | Data cleanup |
| --- | --- | --- | --- |
| `@SpringBootTest` không `@Transactional` | Service kết thúc transaction | Sau service return nếu callback đồng bộ | Bắt buộc |
| `@DataJpaTest` mặc định | Rollback cuối test | Kiểm AFTER_COMMIT không chạy | Dữ liệu T1 tự rollback |
| `@DataJpaTest + @Commit` | Sau test body và JUnit after callbacks | `@AfterTransaction` | Bắt buộc |
| `@DataJpaTest + @Rollback(false)` | Giống `@Commit` | `@AfterTransaction` | Bắt buộc |
| `@DataJpaTest + TestTransaction.end()` | Ngay khi gọi `end` với commit flag | Ngay sau `end` | Bắt buộc |
| `@SpringBootTest(RANDOM_PORT)` | Trong server thread theo service transaction | Theo HTTP result/async outcome | Không dựa vào test rollback |

## 5. Thiết kế post-commit task đúng transaction boundary

### 5.1. Event chỉ mang dữ liệu tối thiểu

~~~java
public record PurchasePlaced(String purchaseId) {}
~~~

Tránh chuyển cả JPA entity lazy-loading vào event. Khi listener chạy sau commit, EntityManager/transaction lifecycle có thể đã đổi; truy cập lazy association dễ lỗi. Dùng ID bất biến và dữ liệu tối thiểu, truy vấn lại bằng new transaction khi cần.

### 5.2. Listener hậu commit đồng bộ

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void send(PurchasePlaced event) {
    notificationGateway.send(event.purchaseId());
}
~~~

Đây là snippet minh họa, không có `notificationGateway` trong project thực hành. Test có thể fake gateway, assert **không gửi khi rollback** và **gửi sau commit**. Tuy nhiên callback chạy không bảo đảm provider đã thực sự deliver qua network.

### 5.3. Ghi DB sau commit: cần cẩn thận

Javadoc Spring Framework lưu ý transaction đã hoàn thành nhưng resources có thể vẫn gắn với thread trong callback hậu commit. Nếu listener gọi repository write với propagation `REQUIRED`, thao tác có thể tham gia resource cũ và **không có commit tiếp theo**.

Giải pháp thường gặp:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(PurchasePlaced event) {
        auditRepository.save(new AuditEntry(event.purchaseId(), "DONE"));
    }
}

@Component
class CommitListener {
    private final AuditWriter auditWriter;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onPlaced(PurchasePlaced event) {
        auditWriter.writeAudit(event);
    }
}
~~~

Đây là snippets kiến trúc (thiếu constructors). Đặt `AuditWriter` là **một Spring bean riêng** để lời gọi đi qua AOP proxy. Đặt `@Transactional(REQUIRES_NEW)` trên private method rồi gọi `this.writeAudit(...)` trong cùng class thường không tạo transaction mới qua proxy.

### 5.4. REQUIRES_NEW cũng có chi phí

Nó có thể cần connection mới trong khi outer transaction vẫn giữ resources, tăng áp lực pool. Với nhiều callbacks đồng thời, phải tính pool size, thời gian chờ, deadlocks và retry. Nếu audit bắt buộc phải atomic với order, **ghi audit hoặc outbox trong transaction gốc**, thay vì chỉ dựa vào write sau commit.

### 5.5. Không dùng BEFORE_COMMIT cho tác vụ không thể đảo ngược

`BEFORE_COMMIT` diễn ra khi database chưa xác nhận commit; commit vẫn có thể fail. Gửi email, gọi payment capture hoặc publish broker message ở phase này có thể tạo side effect dù T1 rollback. Dùng `AFTER_COMMIT` hoặc durable outbox tùy độ tin cậy.

## 6. Thiết kế project runnable

Project minh họa cả callback và transaction mới bằng:
- `PurchaseRecord`: dữ liệu business ở table `purchase_records`.
- `PurchasePlaced`: domain event.
- `CheckoutService`: ghi purchase, publish event trong `@Transactional`.
- `LifecycleLog`: probe trong memory ghi nhận BEFORE/AFTER_COMMIT/AFTER_ROLLBACK.
- `AuditWriter`: ghi `AuditEntry` trong `REQUIRES_NEW`.
- `CommitListener`: các handler theo phase.
- Bốn lớp JUnit tests: full-context successful commit/rollback/no-tx; slice default rollback; slice explicit `@Commit`; slice `TestTransaction` commit giữa test.

Demo không dùng SMTP, Kafka hoặc external service. Probe và audit table giúp assertions deterministic; production reliability được phân tích ở các phần sau.

### 6.1. Cấu trúc thư mục

~~~text
after-commit-event-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/aftercommit/
│   ├── AfterCommitApplication.java
│   ├── PurchaseRecord.java
│   ├── PurchaseRepository.java
│   ├── AuditEntry.java
│   ├── AuditEntryRepository.java
│   ├── PurchasePlaced.java
│   ├── CheckoutService.java
│   ├── LifecycleLog.java
│   ├── AuditWriter.java
│   └── CommitListener.java
└── src/test/java/com/example/aftercommit/
    ├── RealCommitLifecycleTest.java
    ├── DefaultRollbackSliceTest.java
    ├── ExplicitCommitSliceTest.java
    └── ManualCommitSliceTest.java
~~~

Mọi class có package `com.example.aftercommit`. JUnit test classes kết thúc bằng `Test` nên Maven Surefire tự nhận.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>after-commit-event-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot parent/BOM quản lý Spring Framework, Hibernate, JUnit, AssertJ. Không pin riêng Spring transaction modules khiến versions lệch nhau.

### 6.3. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:after_commit_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 và `ddl-auto=create-drop` chỉ dành cho lab/test. Test source có @DataJpaTest có thể được thay datasource bằng embedded database riêng theo auto-configuration; đó là hành vi bình thường của slice.

### 6.4. AfterCommitApplication.java

~~~java
package com.example.aftercommit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AfterCommitApplication {
    public static void main(String[] args) {
        SpringApplication.run(AfterCommitApplication.class, args);
    }
}
~~~

### 6.5. PurchaseRecord.java

~~~java
package com.example.aftercommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @Column(name = "purchase_id", length = 80)
    private String id;

    @Column(nullable = false, length = 32)
    private String state;

    protected PurchaseRecord() {}

    public PurchaseRecord(String id, String state) {
        this.id = id;
        this.state = state;
    }

    public String getId() {
        return id;
    }

    public String getState() {
        return state;
    }
}
~~~

ID do test cung cấp để assertions có giá trị cố định. Production có thể dùng UUID/idempotency key, nhưng phải validate input và không dựa vào một ID hard-coded dùng chung cho nhiều tenants.

### 6.6. PurchaseRepository.java

~~~java
package com.example.aftercommit;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<PurchaseRecord, String> {
}
~~~

### 6.7. AuditEntry.java

~~~java
package com.example.aftercommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_entries")
public class AuditEntry {

    @Id
    @Column(name = "purchase_id", length = 80)
    private String id;

    @Column(nullable = false, length = 32)
    private String action;

    protected AuditEntry() {}

    public AuditEntry(String id, String action) {
        this.id = id;
        this.action = action;
    }

    public String getId() {
        return id;
    }

    public String getAction() {
        return action;
    }
}
~~~

Dùng purchase ID làm primary key để lab hạn chế duplicate row. Production audit nên có event ID riêng và thường lưu nhiều records với unique idempotency key thay vì overwrite theo purchase ID.

### 6.8. AuditEntryRepository.java

~~~java
package com.example.aftercommit;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditEntryRepository
        extends JpaRepository<AuditEntry, String> {
}
~~~

### 6.9. PurchasePlaced.java

~~~java
package com.example.aftercommit;

public record PurchasePlaced(String purchaseId) {}
~~~

Record immutable chỉ chứa ID, không mang JPA lazy entity hoặc thông tin cá nhân.

### 6.10. CheckoutService.java

~~~java
package com.example.aftercommit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            PurchaseRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void place(String id) {
        saveAndPublish(id);
    }

    @Transactional
    public void placeAndFail(String id) {
        saveAndPublish(id);
        throw new IllegalStateException("simulated failure");
    }

    private void saveAndPublish(String id) {
        repository.saveAndFlush(new PurchaseRecord(id, "PLACED"));
        events.publishEvent(new PurchasePlaced(id));
    }
}
~~~

Public methods `place` và `placeAndFail` được gọi qua Spring bean proxy. Private helper `saveAndPublish` không có annotation transaction độc lập, nên không dùng self-invocation để mở transaction. `placeAndFail` ném RuntimeException **trước commit**, Spring rollback và AFTER_ROLLBACK callback có thể chạy; AFTER_COMMIT không chạy.

### 6.11. LifecycleLog.java

~~~java
package com.example.aftercommit;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import org.springframework.stereotype.Component;

@Component
public class LifecycleLog {

    private final ConcurrentLinkedQueue<String> before =
            new ConcurrentLinkedQueue<>();

    private final ConcurrentLinkedQueue<String> committed =
            new ConcurrentLinkedQueue<>();

    private final ConcurrentLinkedQueue<String> rolledBack =
            new ConcurrentLinkedQueue<>();

    public void recordBefore(String id) { before.add(id); }
    public void recordCommitted(String id) { committed.add(id); }
    public void recordRolledBack(String id) { rolledBack.add(id); }

    public List<String> before() { return List.copyOf(before); }
    public List<String> committed() { return List.copyOf(committed); }
    public List<String> rolledBack() { return List.copyOf(rolledBack); }

    public void clear() {
        before.clear();
        committed.clear();
        rolledBack.clear();
    }
}
~~~

Probe chỉ phục vụ test, không là durable audit hoặc production event store. Queue thread-safe cho thao tác add/snapshot, nhưng `clear()` có thể race với callback nếu test chạy parallel; lab mặc định chạy tuần tự, mỗi test reset state rõ ràng.

### 6.12. AuditWriter.java

~~~java
package com.example.aftercommit;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {

    private final AuditEntryRepository repository;

    public AuditWriter(AuditEntryRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(PurchasePlaced event) {
        repository.saveAndFlush(
                new AuditEntry(event.purchaseId(), "AFTER_COMMIT"));
    }
}
~~~

New transaction có ý nghĩa khi callback chạy sau commit của purchase. Test sẽ assert `AuditEntry` tồn tại sau callback, không chỉ verify method được gọi.

### 6.13. CommitListener.java

~~~java
package com.example.aftercommit;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommitListener {

    private final LifecycleLog log;
    private final AuditWriter auditWriter;

    public CommitListener(LifecycleLog log, AuditWriter auditWriter) {
        this.log = log;
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(PurchasePlaced event) {
        log.recordBefore(event.purchaseId());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchasePlaced event) {
        auditWriter.record(event);
        log.recordCommitted(event.purchaseId());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(PurchasePlaced event) {
        log.recordRolledBack(event.purchaseId());
    }
}
~~~

Vì listener không gắn `@Async`, callbacks trong lab chạy đồng bộ khi transaction manager xử lý completion. Thứ tự giữa các loại callback có ý nghĩa như mô tả, nhưng đừng assert thứ tự tuyệt đối giữa nhiều listeners độc lập khi ứng dụng không có contract về `@Order`.

### 6.14. RealCommitLifecycleTest.java

`src/test/java/com/example/aftercommit/RealCommitLifecycleTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class RealCommitLifecycleTest {

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;
    @Autowired ApplicationEventPublisher events;

    @BeforeEach
    void prepare() {
        audits.deleteAll();
        purchases.deleteAll();
        log.clear();
    }

    @AfterEach
    void cleanup() {
        audits.deleteAll();
        purchases.deleteAll();
        log.clear();
    }

    @Test
    void afterCommitRunsOnlyAfterSuccessfulTransaction() {
        String id = "REAL-COMMIT-1";

        checkout.place(id);

        assertThat(purchases.findById(id)).isPresent();
        assertThat(audits.findById(id))
                .isPresent()
                .get()
                .extracting(AuditEntry::getAction)
                .isEqualTo("AFTER_COMMIT");

        assertThat(log.before()).containsExactly(id);
        assertThat(log.committed()).containsExactly(id);
        assertThat(log.rolledBack()).isEmpty();
    }

    @Test
    void rollbackNeverTriggersSuccessTask() {
        String id = "REAL-ROLLBACK-1";

        assertThatThrownBy(() -> checkout.placeAndFail(id))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("simulated failure");

        assertThat(purchases.findById(id)).isEmpty();
        assertThat(audits.findById(id)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).containsExactly(id);
    }

    @Test
    void publishingOutsideTransactionIsIgnoredByDefault() {
        events.publishEvent(new PurchasePlaced("NO-TX-1"));

        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).isEmpty();
        assertThat(audits.findById("NO-TX-1")).isEmpty();
    }
}
~~~

Lớp này **không có test-level `@Transactional`**, nên service thực thi transaction riêng và commit trước khi return (listener đồng bộ). `@BeforeEach`/`@AfterEach` cleanup thực tế qua repository transaction. Test rollback chứng minh purchase không commit và success callback không được gọi. Test no-transaction bảo vệ `fallbackExecution=false` mặc định.

### 6.15. DefaultRollbackSliceTest.java

`src/test/java/com/example/aftercommit/DefaultRollbackSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class DefaultRollbackSliceTest {

    private static final String ID = "SLICE-ROLLBACK-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    void defaultRollbackSkipsAfterCommit() {
        assertThat(TestTransaction.isActive()).isTrue();

        checkout.place(ID);

        assertThat(purchases.findById(ID)).isPresent();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).isEmpty();
    }

    @AfterTransaction
    void after() {
        assertThat(purchases.findById(ID)).isEmpty();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
        assertThat(log.rolledBack()).containsExactly(ID);
        log.clear();
    }
}
~~~

`@Import` thêm đúng các beans không được scan trong `@DataJpaTest`. `@AfterTransaction` chạy sau outer rollback và thấy `AFTER_ROLLBACK` đã được xử lý. Việc test có query thấy PurchaseRecord **trong T1** không chứng minh commit.

### 6.16. ExplicitCommitSliceTest.java

`src/test/java/com/example/aftercommit/ExplicitCommitSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class ExplicitCommitSliceTest {

    private static final String ID = "SLICE-COMMIT-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    @Commit
    void writesButHasNotCommittedInsideMethod() {
        checkout.place(ID);

        assertThat(purchases.findById(ID)).isPresent();
        assertThat(audits.findById(ID)).isEmpty();
        assertThat(log.before()).isEmpty();
        assertThat(log.committed()).isEmpty();
    }

    @AfterTransaction
    void afterCommitAndCleanup() {
        try {
            assertThat(purchases.findById(ID)).isPresent();
            assertThat(audits.findById(ID))
                    .isPresent()
                    .get()
                    .extracting(AuditEntry::getAction)
                    .isEqualTo("AFTER_COMMIT");
            assertThat(log.before()).containsExactly(ID);
            assertThat(log.committed()).containsExactly(ID);
            assertThat(log.rolledBack()).isEmpty();
        }
        finally {
            audits.deleteById(ID);
            purchases.deleteById(ID);
            log.clear();
        }
    }
}
~~~

Điều quan trọng: `@Commit` cho TestContext biết commit **sau khi method kết thúc**, không ngay lúc `checkout.place` return trong outer T1. Assert trong `@AfterTransaction` mới kiểm callback AFTER_COMMIT. Data committed phải cleanup ngoài T1.

### 6.17. ManualCommitSliceTest.java

`src/test/java/com/example/aftercommit/ManualCommitSliceTest.java`:

~~~java
package com.example.aftercommit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({
    CheckoutService.class, CommitListener.class,
    AuditWriter.class, LifecycleLog.class
})
class ManualCommitSliceTest {

    private static final String ID = "MANUAL-COMMIT-1";

    @Autowired CheckoutService checkout;
    @Autowired PurchaseRepository purchases;
    @Autowired AuditEntryRepository audits;
    @Autowired LifecycleLog log;

    @BeforeTransaction
    void before() {
        log.clear();
    }

    @Test
    void commitsAtChosenPoint() {
        assertThat(TestTransaction.isActive()).isTrue();

        try {
            checkout.place(ID);
            assertThat(log.committed()).isEmpty();

            TestTransaction.flagForCommit();
            TestTransaction.end();

            assertThat(TestTransaction.isActive()).isFalse();
            assertThat(purchases.findById(ID)).isPresent();
            assertThat(audits.findById(ID)).isPresent();
            assertThat(log.committed()).containsExactly(ID);
        }
        finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            audits.findById(ID).ifPresent(audits::delete);
            purchases.findById(ID).ifPresent(purchases::delete);
            log.clear();
        }
    }
}
~~~

`TestTransaction.end()` kết thúc active test-managed transaction theo commit flag. Trong finally, nếu lỗi xảy ra trước end, test rollback T1 trước khi xóa fixtures; nếu đã commit, cleanup bằng repository transaction khác. Không cần `@Commit` khi đã commit thủ công.

### 6.18. Chạy các lớp test

Trong `after-commit-event-lab`:

~~~bash
mvn -q clean test

mvn -q -Dtest=RealCommitLifecycleTest test
mvn -q -Dtest=DefaultRollbackSliceTest test
mvn -q -Dtest=ExplicitCommitSliceTest test
mvn -q -Dtest=ManualCommitSliceTest test
~~~

Yêu cầu JDK 17+, Maven và dependency repository truy cập được. Báo cáo nằm trong `target/surefire-reports`. Lớp test được thiết kế PASS với code/schema như trên; **không khẳng định Maven đã thực thi trong quá trình biên soạn**. Nếu fail, đọc root cause/stack trace, kiểm Spring context, transaction boundary và actual rows trước khi thay expected.

## 7. Bảng kết quả mong đợi

| Lớp test | Transaction boundary | Kiểm AFTER_COMMIT | Dữ liệu sau test |
| --- | --- | --- | --- |
| `RealCommitLifecycleTest` | Service tự commit/rollback | Chạy sau commit, không chạy sau rollback | Cleanup @AfterEach |
| `DefaultRollbackSliceTest` | Test T1 rollback mặc định | Không chạy; AFTER_ROLLBACK chạy | T1 rollback |
| `ExplicitCommitSliceTest` | T1 commit sau method nhờ @Commit | Chạy trước @AfterTransaction | Cleanup trong @AfterTransaction |
| `ManualCommitSliceTest` | Commit ngay khi TestTransaction.end() | Kiểm sau end | Cleanup trong finally |

Điểm chống false positive: mỗi test positive kiểm **row trong database** và **log hậu commit**; test rollback kiểm **không có row** và **không có audit**. Phân biệt `BEFORE_COMMIT` và `AFTER_COMMIT` ở phase đúng. Không dựa vào thứ tự JUnit methods.

## 8. Listener đồng bộ, @Async và chờ kết quả

### 8.1. Đồng bộ trong demo

`@TransactionalEventListener` trong lab không gắn `@Async`, nên callback được thực thi trong quá trình transaction completion của service. Sau `checkout.place(id)` trở về trong full-context test không có outer T1, có thể assert `LifecycleLog` và audit row.

Nhưng callback đồng bộ vẫn không bảo đảm email, SMS hoặc broker message đã được một hệ thống ngoài nhận thành công nếu callback chỉ enqueue/schedule một công việc.

### 8.2. Nếu thêm @Async

~~~java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void send(PurchasePlaced event) {
    emailGateway.send(event.purchaseId());
}
~~~

Đây là snippet, cần `@EnableAsync`, executor và fake/email gateway phù hợp. Khi transaction commit, callback có thể **được lên lịch**, không có nghĩa tác vụ async đã hoàn thành khi service return.

Test kiểu sau dễ flaky:

~~~java
checkout.place("P-ASYNC");
assertThat(fakeMail.sent()).isTrue();
~~~

Nếu `fakeMail` được ghi từ worker thread, assertion có thể chạy trước. Dùng `CountDownLatch`/`CompletableFuture` hoặc bounded await.

### 8.3. CountDownLatch cho fake outbound adapter

~~~java
CountDownLatch delivered = new CountDownLatch(1);
AtomicReference<String> sent = new AtomicReference<>();

// Trong fake gateway được async listener gọi:
// sent.set(event.purchaseId());
// delivered.countDown();

// Sau khi transaction gốc đã commit:
assertThat(delivered.await(3, TimeUnit.SECONDS)).isTrue();
assertThat(sent.get()).isEqualTo("P-ASYNC");
~~~

Snippet này cần imports và fake gateway/class fixture. Đừng dùng `Thread.sleep(500)` để đoán worker đã chạy. Nếu test cần chứng minh rollback không phát task, kiểm command scheduling/fake gateway theo đường rollback và bounded interval hợp lý, tránh assert chỉ dựa vào “chưa thấy ngay lập tức”.

### 8.4. “Đã enqueue” khác “đã thực thi”

Một listener AFTER_COMMIT gọi `taskExecutor.execute(job)`: assertion verify executor nhận job mới chỉ chứng minh **enqueue/scheduling**. Test riêng cần cho job handler xử lý và kiểm outcome. Nếu tác vụ chạy sau 30 giây, dùng fake clock/scheduler ở unit test thay vì chờ 30 giây thật.

## 9. Transactional outbox và độ tin cậy

### 9.1. Khoảng trống giữa commit và publish

~~~text
Database transaction COMMIT SUCCESS
        |
        |  <-- JVM crash tại đây:
        |      event chưa được gửi tới broker
        v
AFTER_COMMIT listener publish
        |
        v
Broker nhận message
~~~

`@TransactionalEventListener(AFTER_COMMIT)` giúp tránh gửi **trước** commit, nhưng không cung cấp bảo đảm **event không mất khi process crash**. Ngay cả khi callback chạy, broker retry/ACK lỗi có thể gây gửi trùng.

### 9.2. Transactional outbox

Thay vì chỉ phát event in-memory:
1. Trong **cùng transaction T1**, ghi business row và outbox row `PENDING`.
2. Commit T1; cả hai rows visible.
3. AFTER_COMMIT callback có thể đánh thức relay ngay.
4. Relay định kỳ cũng quét PENDING để xử lý rows sau restart.
5. Relay gửi message, cập nhật trạng thái hoặc retry có backoff.
6. Consumer deduplicate theo eventId/idempotency key.

~~~text
T1:
  INSERT purchase
  INSERT outbox(event_id, payload, status=PENDING)
  COMMIT
      |
      +-- wake relay (AFTER_COMMIT, tối ưu latency)
      |
      +-- relay có thể poll committed rows dù callback mất
          |
          +-- publish
          +-- mark delivered/retry
~~~

Khi business **không được mất notification**, outbox là một kiến trúc đáng cân nhắc hơn việc chỉ giữ event trong RAM.

### 9.3. Pseudocode service có outbox

~~~java
@Transactional
public void place(String id) {
    purchases.save(new PurchaseRecord(id, "PLACED"));
    outbox.save(new OutboxEvent(
            UUID.randomUUID().toString(),
            "PURCHASE_PLACED",
            id,
            "PENDING"));
    events.publishEvent(new OutboxReady(id));
}
~~~

Đây là snippet kiến trúc **không nằm trong runnable lab** vì chưa định nghĩa `OutboxEvent`, `OutboxReady` và repository. Đặc điểm quan trọng là **hai INSERT cùng T1**, không phải thao tác ghi outbox trong listener AFTER_COMMIT.

### 9.4. Kiểm thử outbox ở nhiều tầng

- Rollback T1: không có business row, không có outbox row.
- Commit T1: có cả hai rows, event ID/payload đúng.
- Relay ở transaction mới đọc được row đã commit.
- Broker tạm down: row còn pending, có retry policy.
- Crash sau publish trước update status: có thể gửi lại; consumer idempotent.
- Restart process: relay xử lý pending rows.
- Duplicate event/request: có unique constraint/idempotency key.

Đừng tuyên bố “exactly once” chỉ vì có `@TransactionalEventListener` hoặc `REQUIRES_NEW`.

## 10. Exception sau commit và failure boundaries

### 10.1. Khi listener thất bại, transaction gốc đã hoàn tất

Giả sử:

~~~text
T1: save purchase -> COMMIT thành công
AFTER_COMMIT: emailGateway.send -> network error
~~~

Purchase row **đã commit**. Listener exception không thể rollback transaction gốc sau khi commit. Việc exception có truyền lại caller hay chỉ được log tùy loại synchronization/event/executor; không viết test dựa vào giả định tất cả exceptions hậu commit đều được ném ra service method.

### 10.2. AuditWriter có thể thất bại độc lập

`AuditWriter.record` dùng `REQUIRES_NEW`. Nếu nó không commit được (unique constraint, database down, timeout), purchase gốc vẫn committed. Khi audit là nghiệp vụ bắt buộc atomic, ghi audit record hoặc outbox row **trong T1** thay vì chỉ trong callback hậu commit.

### 10.3. Retry và idempotency

Khi gửi external notification:
- Dùng eventId/operationId ổn định.
- Đặt maximum attempts/backoff.
- Phân biệt retryable transport error và permanent validation error.
- Lưu delivery state nếu không thể mất tác vụ.
- Không vô hạn retry trong transaction completion callback, làm block thread và tăng độ trễ.
- Nếu provider không hỗ trợ idempotency, consumer/business cần deduplication strategy.

### 10.4. Ghi metrics đúng

Đừng đếm “transaction success” chỉ vì `publishEvent` thành công. Đếm successful commit ở phase tương ứng, và delivery success riêng khi external adapter xác nhận. Có thể có commit success nhưng delivery fail; dashboard không nên đánh đồng.

## 11. Những bẫy ThreadLocal và AOP

### 11.1. Self-invocation làm @Transactional không có tác dụng

~~~java
public void place() {
    this.saveWithTransaction();
}

@Transactional
public void saveWithTransaction() {
    // ...
}
~~~

Trong Spring proxy-based AOP, gọi method qua `this.` có thể **bỏ qua proxy**, không mở transaction. Khi publish event ngoài transaction, listener AFTER_COMMIT mặc định không chạy. Nên gọi qua bean được Spring proxy hoặc dùng `TransactionTemplate` khi cần transaction tường minh.

### 11.2. REQUIRES_NEW phải đi qua proxy

Tương tự, annotation `@Transactional(propagation = REQUIRES_NEW)` trên method nằm cùng listener và gọi bằng `this.write(...)` không tự tạo new transaction. Demo tách `AuditWriter` thành bean riêng.

### 11.3. @Async/new thread

Spring transaction imperative thường dùng ThreadLocal. Công việc chạy trên thread của `@Async`, `CompletableFuture` hoặc executor không tự thừa hưởng test-managed transaction của JUnit thread. Event publish trong worker có thể gắn với transaction khác hoặc không có transaction; phải kiểm đúng boundary đó.

### 11.4. assertTimeoutPreemptively

Spring TestContext documentation cảnh báo JUnit `assertTimeoutPreemptively(...)` có thể chạy callback trên thread khác, không nằm trong test transaction gắn ThreadLocal. Database writes trong callback có thể commit ngoài outer rollback.

~~~java
// Mẫu cần cẩn thận, không thuộc runnable project.
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    checkout.place("P-TIMEOUT");
});
~~~

Tránh dùng preemptive timeout trong transactional tests khi dựa vào rollback để cleanup. Có thể dùng `assertTimeout` không preemptive, test-level database isolation và bounded operation timeout phù hợp.

### 11.5. @SpringBootTest(RANDOM_PORT)

Một real HTTP request:
- JUnit test thread có thể có test-managed transaction.
- HTTP server xử lý ở worker thread khác.
- Server-side service mở/commit transaction riêng.
- Test thread rollback **không undo** database writes ở server-side.

Ngược lại, `MockMvc` thường xử lý request cùng test thread và service `REQUIRED` có thể tham gia outer test transaction. Không suy cùng behavior từ hai setup. Với `RANDOM_PORT`, cleanup rows thật bằng repository/service sau request.

### 11.6. Multiple transaction managers

Khi có hai datasources, `@Transactional(transactionManager="orderTx")` không nhất thiết quản lý resources dùng `auditTx`. Một `@Commit` của test manager này không bảo đảm toàn bộ external/broker resources cũng commit. Test integration phải định nghĩa transaction manager và data source được chọn.

## 12. Một số case cần test riêng trên production-like environment

### 12.1. Commit-time constraints

PostgreSQL hỗ trợ một số `DEFERRABLE` constraints; lỗi có thể chỉ xuất hiện lúc commit. `saveAndFlush` trong H2 test rollback không chứng minh commit-time correctness. Dùng PostgreSQL/Testcontainers và assert exception ở `TestTransaction.end()` hoặc service transaction boundary.

### 12.2. Transaction isolation, read replica và index lag

Ngay sau commit trên primary DB, một read replica hay search index có thể chưa theo kịp. Khi test listener đọc từ replica, kết quả có thể eventually consistent. Không dùng H2 unit test để khẳng định real replica latency. Sử dụng bounded polling, test containers/cluster và SLA rõ.

### 12.3. External broker/email

Mock/fake giúp kiểm after-commit scheduling nhưng không xác minh TLS/auth/SDK behavior. Dùng sandbox/integration test được cấp phép cho broker, SMTP hoặc provider HTTP, không gửi email thanh toán hay giao dịch thật từ suite.

### 12.4. Listener làm DB write rồi deadlock

Nếu callback mở transaction mới khi transaction cũ còn giữ connection/resource, test đa luồng có thể làm lộ connection pool exhaustion hoặc locks. Bảo đảm pool size, timeout và tránh business workflows cần nested independent transaction khi có thể ghi outbox trong T1.

### 12.5. Listener nhận stale entity

Nếu event mang JPA entity với lazy fields và callback chạy sau commit, việc truy cập entity có thể gặp lazy loading/transaction issues. Gửi ID/immutable snapshot, rồi query lại trong `REQUIRES_NEW(readOnly=true)` nếu cần.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Listener không chạy trong `@DataJpaTest` | Test rollback mặc định | `@Commit`/`TestTransaction`, assert sau commit |
| `@Commit` nhưng listener rỗng trong test body | Commit chỉ sau method | `@AfterTransaction` hoặc `TestTransaction.end()` |
| Listener không chạy ở full context | Event ngoài transaction, proxy bị bypass, bean chưa scan | Kiểm transaction active, `@Transactional`, event type, imports |
| Listener chạy khi rollback | Có `@EventListener` hoặc gọi gateway trực tiếp trước commit | Chuyển đúng phase, thêm rollback test |
| Audit DB write sau commit không tồn tại | Dùng resources transaction cũ, không có new commit | Bean `REQUIRES_NEW` thực sự đi qua proxy |
| Lưu data trong test T1 nhưng test sau không thấy | Rollback/visibility | Kiểm post-commit ở transaction mới |
| Test khác fail vì duplicate key | `@Commit` để lại row | Cleanup ngoài T1 / DB cô lập |
| Async test flaky | Assert trước khi worker hoàn tất | Latch/future/await bounded |
| Service success nhưng email fail | Post-commit external error | Retry/outbox, kiểm delivery outcome riêng |
| Callback exception mà purchase vẫn tồn tại | Commit gốc đã thành công | Không kỳ vọng rollback sau commit |
| Event không xử lý ngoài transaction | `fallbackExecution=false` | Thiết kế transaction thật hoặc fallback có chủ đích |
| Event xử lý trùng | Retry/duplicate publish | Idempotency key, unique constraints, consumer dedupe |
| `@AfterTransaction` không chạy | Test không có test-managed transaction | Dùng đúng test `@Transactional` hoặc `@DataJpaTest` |
| `assertTimeoutPreemptively` leak rows | Thread khác không kế thừa T1 | Đổi timeout strategy/test cleanup |
| `RANDOM_PORT` test để lại DB row | Server transaction ở thread khác | Cleanup explicit/isolated DB |
| H2 pass, PostgreSQL commit fail | Engine/deferred constraints khác | Testcontainers với DB production |

Khi debug, ghi lại event type, transaction manager, active transaction tại nơi publish, phase annotation, listener bean có mặt trong context, test rollback/commit strategy và actual database rows. **Không** sửa expected theo actual nếu business yêu cầu chỉ chạy sau commit.

## 14. Bài tập thực hành

1. Viết `@TransactionalEventListener(AFTER_COMMIT)` và fake notification gateway. Test happy path/rollback.
2. Chạy `@DataJpaTest` mặc định rollback và giải thích vì sao callback AFTER_COMMIT không chạy.
3. Thêm `@Commit`, chuyển assertion từ `@Test` sang `@AfterTransaction` và cleanup.
4. Thay `@Commit` bằng `@Rollback(false)`, so sánh semantics.
5. Dùng `TestTransaction.flagForCommit()` và `end()` để commit giữa test, rồi query mới.
6. Thêm `BEFORE_COMMIT` và `AFTER_ROLLBACK` listeners, kiểm callback nào chạy mỗi đường.
7. Publish event bên ngoài transaction. Thử `fallbackExecution=true` và phân biệt fallback với successful commit.
8. Viết bean audit writer `REQUIRES_NEW`, kiểm audit row tồn tại sau commit thật.
9. Thử gọi writer bằng self-invocation và giải thích vì sao AOP proxy không áp dụng.
10. Đổi listener thành `@Async`, thay `Thread.sleep` bằng CountDownLatch.
11. Mô phỏng gateway lỗi sau commit. Kiểm business row vẫn tồn tại và delivery fail được ghi nhận.
12. Tạo outbox row trong cùng transaction với purchase, test rollback không còn outbox.
13. Giả lập crash sau commit trước publish, giải thích tại sao relay có thể retry pending outbox.
14. Thử `@SpringBootTest(RANDOM_PORT)` và đánh giá vì sao test-level rollback không bao trùm HTTP server thread.
15. Nếu database có DEFERRABLE constraint, lên kế hoạch test commit-time failure bằng PostgreSQL/Testcontainers.
16. Tạo test duplicate event với idempotency key, kiểm không phát thông báo trùng.
17. Viết checklist thứ tự callback và cleanup khi test chạy song song với nhiều transactions.

## 15. Checklist trước khi merge

- [ ] Event phát trong active transaction hay ngoài transaction?
- [ ] `@TransactionalEventListener` chọn đúng phase?
- [ ] `fallbackExecution` được hiểu và test khi cần?
- [ ] Service method được gọi qua Spring proxy?
- [ ] Không nhầm `saveAndFlush` với commit?
- [ ] Trong `@DataJpaTest`, đã tính rollback mặc định?
- [ ] Test commit có `@Commit`/`@Rollback(false)` hoặc `TestTransaction`?
- [ ] Assertion post-commit thực hiện ở `@AfterTransaction` hoặc sau end?
- [ ] Có test positive và rollback negative?
- [ ] Có assert DB committed state và post-commit outcome?
- [ ] Post-commit DB writer đi qua bean `REQUIRES_NEW`?
- [ ] Không tự ghi external side effect trước commit?
- [ ] Với async, test chờ completion có timeout?
- [ ] Phân biệt task enqueued với task completed?
- [ ] Dữ liệu đã commit được cleanup bằng transaction riêng?
- [ ] Không dùng `@DirtiesContext` thay DB cleanup?
- [ ] Có idempotency/retry/durable outbox nếu không thể mất event?
- [ ] Có phân biệt commit success và email/broker delivery success?
- [ ] Với real HTTP, không dựa vào test rollback để dọn server writes?
- [ ] Tránh preemptive timeout khi test dựa ThreadLocal transactions?
- [ ] Test production DB semantics bằng engine phù hợp khi cần?
- [ ] Đã chạy Maven/JUnit trong CI và xem báo cáo Surefire?

**Kết luận:** `@TransactionalEventListener(AFTER_COMMIT)` giúp bảo đảm listener chỉ được kích hoạt sau một transaction commit thành công, nhưng default rollback của `@DataJpaTest` có thể khiến test chưa bao giờ chạy được đường này. Dùng `@Commit`/`@AfterTransaction` hoặc `TestTransaction.end()` để tạo commit boundary thật. Nếu task hậu commit ghi database, cần cẩn trọng với resources của transaction cũ và thường tách writer sang `REQUIRES_NEW`. Nếu post-commit side effect là yêu cầu không thể mất, nên bổ sung transactional outbox, retry và idempotency, thay vì coi listener in-memory là bảo đảm delivery.

## 16. Tài liệu chính thức

- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2 — `TransactionSynchronization` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework 6.2 — TestTransaction API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 — `@AfterTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-aftertransaction.html
- Spring Framework 6.2 — `@Commit` và `@Rollback`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-commit.html
- Spring Boot 3.5 — `@DataJpaTest`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
