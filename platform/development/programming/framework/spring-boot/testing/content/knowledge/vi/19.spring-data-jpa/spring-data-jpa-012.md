# Giới hạn rollback mặc định đối với các hành vi cần commit thật trong Spring Data JPA

## 1. Vì sao chủ đề này quan trọng?

Trong Spring Boot, một bài kiểm thử repository có thể xanh hoàn toàn khi chạy với `@DataJpaTest`: entity được `save`, `flush`, query lại bằng repository, mọi assertion đều đúng. Tuy nhiên, luồng production có thể thất bại **tại thời điểm transaction commit** hoặc một hành vi quan trọng **chỉ xuất hiện sau commit**. Nếu test luôn rollback, những hành vi đó có thể chưa từng được chạy.

Ví dụ điển hình:

- Listener `@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ thực thi khi transaction **commit thành công**.
- Một số ràng buộc database, đặc biệt **DEFERRABLE constraints** ở PostgreSQL, được kiểm vào lúc commit, không nhất thiết ở lần `flush` trước đó.
- Transaction khác, consumer khác hoặc connection khác **không nhất thiết nhìn thấy** dữ liệu vừa `flush` nhưng chưa commit.
- Outbox/CDC, audit bên ngoài, notification hoặc job phụ thuộc committed row thường cần commit mới được quan sát từ một tiến trình khác.
- Một phương thức `@Transactional(propagation = REQUIRES_NEW)` có thể commit giao dịch riêng **ngay cả khi** giao dịch của test sau đó rollback.
- Một HTTP request tới ứng dụng thực trong `@SpringBootTest(webEnvironment = RANDOM_PORT)` chạy ở luồng/server transaction khác; annotation `@Transactional` trên test method **không bảo đảm** rollback những thay đổi phía server.

Bài học này giúp người học trả lời: **rollback mặc định bảo vệ test khỏi dữ liệu dư ở đâu, và nó có thể che khuất những điều gì mà production thực sự cần commit?**

### Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích **test-managed transaction** của Spring TestContext khác với transaction do service/application quản lý.
2. Xác định khi nào `@DataJpaTest` rollback mặc định, còn `@SpringBootTest` có/không có test transaction.
3. Phân biệt `save`, `flush`, `saveAndFlush`, `commit` và `rollback`.
4. Kiểm một dòng dữ liệu **thực sự đã commit và nhìn thấy ngoài test transaction** bằng `@Commit`, `@Rollback(false)`, `TestTransaction` và `@AfterTransaction`.
5. Kiểm sự khác nhau giữa `@TransactionalEventListener(AFTER_COMMIT)` và `AFTER_ROLLBACK`/`BEFORE_COMMIT`.
6. Nhận biết những trường hợp rollback không bao trùm `REQUIRES_NEW`, asynchronous threads, request tới real HTTP server và external side effects.
7. Thiết kế cleanup/idempotency để một test commit thật **không làm bẩn** test kế tiếp.
8. Sử dụng H2 cho ví dụ độc lập, đồng thời hiểu khi nào phải dùng **PostgreSQL/Testcontainers** để kiểm transaction isolation, deferred constraints, triggers hoặc dialect thực.
9. Chạy dự án **Java 17+ / Spring Boot 3.5.16 / Spring Data JPA / JUnit Jupiter / Maven** có nhiều test phân biệt rollback và commit.

**Thông điệp cốt lõi:** `flush` làm SQL đi tới database connection hiện tại; **`commit` mới kết thúc giao dịch thành công, cho giao dịch khác nhìn thấy dữ liệu theo isolation rules và kích hoạt các hook sau commit**. Không nên coi `saveAndFlush` là phép thay thế cho commit.

## 2. Ba tầng transaction cần phân biệt

### 2.1. Test-managed transaction

Spring TestContext sử dụng `TransactionalTestExecutionListener` để tạo transaction bao quanh một test method **khi test được khai báo `@Transactional` và có `PlatformTransactionManager` phù hợp**.

`@DataJpaTest` trong Spring Boot 3.5 có test transaction mặc định: mỗi test chạy trong transaction, và sau test Spring **rollback** transaction đó. Bài test có thể thêm `@Commit` hoặc `@Rollback(false)` để thay đổi kết quả kết thúc.

```text
Spring TestContext
  |
  +-- begin TEST transaction (T1)
  |      |
  |      +-- @BeforeEach
  |      +-- @Test body
  |      |      +-- repository.save(...)
  |      |      +-- repository.flush()
  |      |      +-- repository.findBy...
  |      +-- @AfterEach
  | 
  +-- default: ROLLBACK T1
  +-- optional: COMMIT T1 with @Commit/@Rollback(false)
  |
  +-- @AfterTransaction (chạy ngoài T1)
```

Dòng thời gian này quan trọng: `@BeforeEach` và `@AfterEach` của JUnit Jupiter trong transactional test thông thường **chạy bên trong** test-managed transaction. Để quan sát trạng thái database trước/sau transaction, dùng `@BeforeTransaction` và `@AfterTransaction`, hoặc kiểm soát ranh giới bằng `TestTransaction`.

### 2.2. Spring-managed transaction ở tầng service

Một service có:

```java
@Service
public class PurchaseService {
    @Transactional
    public void create(...) {
        repository.save(...);
    }
}
```

Khi gọi service thông qua **Spring proxy**, `@Transactional` mặc định dùng propagation `REQUIRED`. Nếu **đã có** test-managed transaction trong cùng luồng, service thường **tham gia giao dịch đó**; kết thúc phương thức service **không commit một giao dịch riêng**.

Vì vậy, test sau có thể đánh lừa người đọc:

```java
@DataJpaTest
@Import(PurchaseService.class)
class PurchaseServiceTest {
    @Autowired PurchaseService service;

    @Test
    void create() {
        service.create(...);
        // Không có bằng chứng về commit tại đây.
    }
}
```

Đây là minh họa, `create(...)` cần được định nghĩa trong project thật. Trong một test transaction, service `REQUIRED` thường chỉ tham gia transaction đang có. Test kết thúc thì outer test transaction rollback, mặc dù service method đã return thành công.

### 2.3. Application-managed transaction

Ứng dụng cũng có thể dùng `TransactionTemplate` hoặc trực tiếp `PlatformTransactionManager` để mở/commit/rollback transaction. Những giao dịch đó có thể tham gia test transaction hoặc tạo ranh giới riêng tùy cấu hình và propagation.

**Không mặc định “mọi transaction đều bị test rollback”.** Spring-managed/application-managed transaction chỉ thường tham gia test transaction khi propagation và thread/context phù hợp. `REQUIRES_NEW`, `NOT_SUPPORTED`, async/new threads và HTTP server-side transactions có thể hoàn toàn độc lập.

### 2.4. Bảng trách nhiệm

| Loại | Ai tạo/đóng? | Mặc định khi test có `@Transactional` | Khi nào commit? |
| --- | --- | --- | --- |
| Test-managed transaction | `TransactionalTestExecutionListener` | Được rollback sau test | `@Commit`, `@Rollback(false)`, `TestTransaction.flagForCommit()` |
| Service `@Transactional(REQUIRED)` | Spring transaction interceptor | Tham gia T1 nếu cùng thread và compatible transaction | Khi T1 commit, không đơn giản khi method return |
| Service `@Transactional(REQUIRES_NEW)` | Spring interceptor | Tạm suspend T1, mở T2 | Khi service method kết thúc và T2 commit |
| `TransactionTemplate` | Application code | Phụ thuộc propagation/config | Khi callback/transaction manager hoàn tất |
| HTTP request trên real server thread | Server-side transaction manager | Không kế thừa test ThreadLocal | Khi server xử lý xong transaction của nó |
| External message/file/email | Hệ thống ngoài database transaction | Thường không rollback cùng T1 | Theo cơ chế riêng, thường không thể đảo ngược tự động |

## 3. Mặc định của @DataJpaTest và @SpringBootTest

### 3.1. @DataJpaTest: rollback mặc định

Spring Boot 3.5 Javadoc khẳng định `@DataJpaTest`:
- Chỉ tải JPA entities và repositories cùng hạ tầng JPA/test cần thiết, không tải toàn bộ application.
- Có transaction cho từng test và **rollback mặc định**.
- Thường dùng **embedded in-memory database** thay cho datasource của app, trừ khi có chỉ định khác.
- Có thể dùng `@AutoConfigureTestDatabase` điều chỉnh database replacement.

```java
@DataJpaTest
class PurchaseRepositoryTest {
    @Autowired PurchaseRepository repository;

    @Test
    void repositoryCanStoreAndQuery() {
        PurchaseRecord saved = repository.saveAndFlush(
                new PurchaseRecord("T-101", "NEW"));

        assertThat(repository.findByReferenceCode("T-101"))
                .isPresent();

        // Khi test kết thúc, Spring rollback.
    }
}
```

Bài test này chứng minh JPA mapping/query tương ứng **trong một transaction**; nó không chứng minh transaction đã commit.

### 3.2. @SpringBootTest không tự bật rollback cho mọi test

`@SpringBootTest` chỉ chỉ thị tải application context cho test. Nó **không mặc định** gắn `@Transactional` lên test method. Nếu test:

```java
@SpringBootTest
class PurchaseIntegrationTest {
    @Autowired PurchaseService service;

    @Test
    void createsPurchase() {
        service.create("INT-101");
        // Nếu service @Transactional(REQUIRED) và không có
        // test transaction, transaction của service có thể commit.
    }
}
```

Đây là snippet theo API của project mục 9. Khi không có test-managed transaction bên ngoài, phương thức `@Transactional` của service thường tự tạo/commit transaction của chính nó. Dữ liệu có thể tồn tại sau test, nên cần cleanup.

Chỉ khi test/class có `@Transactional` và test infrastructure phù hợp, Spring TestContext mới mở test transaction. Đừng đọc `@SpringBootTest` rồi tự suy luận “mọi write đều rollback”.

### 3.3. @Transactional ở test method không hoàn toàn giống @Transactional ở service

Trong Spring Framework TestContext, một số thuộc tính trên `@Transactional` **không được test-managed transaction hỗ trợ** như khi khai báo trên application method:

| Thuộc tính `@Transactional` trên test | Test-managed transactions |
| --- | --- |
| `value` / `transactionManager` | Có hỗ trợ chọn transaction manager |
| `propagation=NOT_SUPPORTED`, `NEVER` | Có hỗ trợ để chạy test **không** trong transaction |
| `propagation=REQUIRED` / `SUPPORTS` | Thường là cách kích hoạt mặc định; không dùng để suy luận mọi propagation setting khác sẽ có semantics app |
| `isolation` | Không áp dụng như mong đợi cho test-managed transaction |
| `timeout` | Không áp dụng như mong đợi |
| `readOnly` | Không áp dụng như mong đợi |
| `rollbackFor` / `noRollbackFor` | Không quyết định test-managed commit/rollback; dùng `TestTransaction` hoặc `@Commit`/`@Rollback` |

Muốn test service method thật với `REQUIRES_NEW`, đặt propagation trên **service method**, không thử ép TestContext chạy `@Transactional(propagation=REQUIRES_NEW)` trên test method rồi mặc định xem như transaction thứ hai.

## 4. save(), flush(), saveAndFlush() và commit khác nhau thế nào?

### 4.1. save() — quản lý entity trong persistence context

`repository.save(entity)` có thể gọi `EntityManager.persist` hoặc `merge`. Thời điểm SQL `INSERT`/`UPDATE` được gửi phụ thuộc ID generation, flush mode, persistence context và operations. Với `GenerationType.IDENTITY`, provider có thể INSERT sớm để có generated ID.

**Không** dùng “chưa gọi flush nên chắc chắn chưa có SQL” làm quy tắc tuyệt đối.

### 4.2. flush() — đồng bộ SQL pending

`repository.flush()` hoặc `EntityManager.flush()` yêu cầu JPA provider đồng bộ pending changes với database. Có thể kích hoạt:
- SQL INSERT/UPDATE/DELETE.
- Ràng buộc database kiểm ngay, như unique/not-null/foreign-key không deferred.
- JPA lifecycle callbacks xảy ra ở pha persistence/flush.
- SQL lỗi nếu không hợp lệ.

Nhưng transaction vẫn **đang mở**. Một connection khác chưa chắc thấy changes theo isolation. Cũng không có `AFTER_COMMIT` event chỉ vì flush hoàn thành.

### 4.3. saveAndFlush()

`saveAndFlush(entity)` tương đương ý tưởng save rồi flush trong transaction repository. Có ích khi muốn database báo lỗi constraint sớm. Nhưng không đồng nghĩa với:
- `Connection.commit()`.
- Trigger/hook chỉ chạy ở commit.
- `@TransactionalEventListener(AFTER_COMMIT)`.
- Dữ liệu được connection khác nhìn thấy.
- Durable write đã hoàn tất theo hợp đồng database.

### 4.4. commit()

Commit:
1. Hoàn tất transaction thành công nếu không có lỗi/rollback-only.
2. Database đánh giá những quy tắc phải chờ tới commit (ví dụ deferred constraints khi DB hỗ trợ).
3. Thay đổi trở nên visible theo isolation và điều kiện snapshot của các transaction khác.
4. Spring kích hoạt các synchronization và transactional event listener tương ứng phase sau commit.
5. Các external observers như CDC/outbox processor có cơ sở đọc committed rows (còn tùy hệ thống/độ trễ).

Commit **cũng có thể thất bại** vì lỗi constraint, connection, deadlock, serialization failure hoặc DB shutdown. Trong trường hợp đó, test chỉ chạy đến `flush` chưa thể chứng minh luồng commit thành công.

### 4.5. Timeline so sánh

```text
Transaction T1:
  begin
   |
   +-- repository.save(entity)       -> entity được quản lý
   |
   +-- repository.flush()            -> SQL được gửi, T1 chưa commit
   |
   +-- repository.findById(id)       -> có thể thấy row từ T1
   |
   +-- publishEvent(PurchaseCreated)-> AFTER_COMMIT listener chờ
   |
   +-- test assertion PASS           -> vẫn chưa đủ
   |
   +-- ROLLBACK (mặc định @DataJpaTest)
          -> row biến mất; AFTER_COMMIT listener không chạy
```

Trường hợp muốn kiểm commit:

```text
Transaction T1:
  begin -> save -> flush -> event scheduled -> COMMIT
                                              |
                                              +-- row committed
                                              +-- AFTER_COMMIT listener chạy
                                              +-- @AfterTransaction kiểm ngoài T1
```

## 5. Những hạn chế khi mọi test luôn rollback

### 5.1. Listener AFTER_COMMIT không thực thi

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` mặc định lắng nghe khi transaction **commit**, thường đồng bộ trong thread transaction khi không cấu hình `@Async`.

```java
@Component
class PurchaseCreatedListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onCreated(PurchaseCreated event) {
        // chỉ chạy sau commit thành công
    }
}
```

Nếu test nằm trong outer test transaction bị rollback, event có thể đã được publish, nhưng listener **không được gọi**.

Không viết test “publish event xong verify listener chạy ngay” khi listener có `AFTER_COMMIT`. Test phải đóng/commit transaction trước khi assert callback, ví dụ `@AfterTransaction` hoặc `TestTransaction.end()`.

### 5.2. Dữ liệu chỉ nhìn thấy bên trong transaction hiện tại

Một query cùng persistence context có thể đọc được entity vừa save/flush. Điều đó **không** chứng minh một transaction khác nhìn thấy row. Với `READ_COMMITTED`, một connection mới thường không đọc được uncommitted changes của T1. Với snapshot-based isolation, còn phải lưu ý thời điểm snapshot của transaction đọc.

Để kiểm “người dùng khác đọc được sau commit”, thực hiện query **ngoài test transaction** hoặc trong transaction mới bắt đầu **sau commit**, không chỉ `findById` trong T1.

### 5.3. Database deferred constraints có thể fail tại commit

PostgreSQL hỗ trợ ràng buộc `DEFERRABLE INITIALLY DEFERRED` cho một số constraint như unique/foreign key. Dù `flush` gửi SQL, constraint có thể được đánh giá **tại commit**, nên test rollback sẽ không mô phỏng lỗi commit.

Ví dụ SQL PostgreSQL (không thuộc H2 demo):

```sql
CREATE TABLE unique_codes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code text NOT NULL,
    CONSTRAINT uq_code UNIQUE (code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Hai INSERT cùng `code` trong một transaction có thể không báo lỗi ngay lúc flush, nhưng **commit sẽ fail** vì unique constraint. Muốn test kết luận này, cần **PostgreSQL thật/Testcontainers**, không giả định H2 hỗ trợ đúng tính năng/deferred semantics.

### 5.4. Trigger/outbox/CDC và integration ngoài transaction

Nhiều kiến trúc dùng transactional outbox:
- Business service ghi `orders` và `outbox_events` trong **cùng transaction**.
- Outbox worker hoặc CDC relay ở **connection/process khác**.
- Worker chỉ có thể tiêu thụ row sau khi giao dịch ghi đã commit và dữ liệu visible.
- Rollback test sẽ làm outbox row biến mất; relay không chạy.

Không thể tuyên bố outbox flow đã được tích hợp chỉ vì test repository tìm thấy một outbox row trước rollback. Dùng một số test commit thật với DB cô lập và relay/test consumer phù hợp.

### 5.5. Transaction callbacks và resource lifecycle

Spring `TransactionSynchronization` có callbacks `beforeCommit`, `afterCommit`, `afterCompletion`. Các bước sau commit/rollback có thể điều khiển cleanup, cache invalidation, audit, event dispatch. Một test rollback chỉ quan sát đường rollback, không bao phủ đường commit.

JPA `@PostPersist` hoặc `@PostUpdate` là lifecycle hooks liên quan persistence, **không** phải chứng cứ commit. Callback có thể chạy trước khi toàn bộ transaction hoàn tất; rollback vẫn xóa tác động DB.

### 5.6. Side effects không thuộc DB

Gửi email, HTTP call, message broker publish, ghi file hoặc gọi service khác có thể xảy ra trước commit. Test transaction rollback **không** thu hồi một email đã gửi hoặc message đã được ack. Kiến trúc cần thiết kế **outbox, retry, idempotency, compensation** phù hợp.

Một test dùng mocks có thể kiểm “email adapter được gọi” nhưng không chứng minh thời điểm gửi có an toàn với transaction. Khi quyết định gửi sau commit, kiểm callback/dispatcher tại đúng phase.

## 6. Ba cơ chế yêu cầu commit có chủ đích

### 6.1. @Commit

`@Commit` trên transactional test class/method yêu cầu TestContext commit thay cho rollback:

```java
@DataJpaTest
class RealCommitRepositoryTest {
    @Autowired PurchaseRepository repository;

    @Test
    @Commit
    void persistsAcrossTransactions() {
        repository.saveAndFlush(
                new PurchaseRecord("COMMIT-1", "NEW"));
        // Commit xảy ra SAU test method, trước @AfterTransaction.
    }

    @AfterTransaction
    void verifyCommitted() {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
        // Cần cleanup dữ liệu trong transaction riêng!
    }
}
```

Snippet này minh họa cách dùng; phần project đầy đủ có cleanup trong `finally` để không để lại dữ liệu.

**Quan trọng:** Assertion ngay trong `@Test` vẫn diễn ra **trước commit**. Muốn khẳng định “đã commit”, cần assert trong `@AfterTransaction`, hoặc tự kết thúc test transaction bằng `TestTransaction.end()` rồi assert sau đó.

### 6.2. @Rollback(false)

`@Rollback(false)` là cách tương đương về kết quả (commit test transaction khi kết thúc), viết tường minh cờ boolean:

```java
@Test
@Rollback(false)
void persistenceRequiresCommit() {
    // ...
}
```

`@Commit` về bản chất là sự diễn đạt dễ đọc cho “không rollback”. Có thể đặt ở class hoặc method; cấu hình method áp dụng cho test cụ thể. Không cần gắn cả `@Commit` và `@Rollback(false)` lên cùng method.

`@Rollback(true)` giúp khôi phục rollback cho một method trong class được đánh dấu `@Commit`, nhưng cần thiết kế scope rõ để không vô tình persist test data ở các methods khác.

### 6.3. TestTransaction.flagForCommit() và end()

Khi cần kiểm commit **ngay giữa test**:

```java
@Test
void canInspectDatabaseAfterCommit() {
    repository.saveAndFlush(
            new PurchaseRecord("MANUAL-1", "NEW"));

    TestTransaction.flagForCommit();
    TestTransaction.end(); // commit test-managed transaction ngay tại đây

    assertThat(TestTransaction.isActive()).isFalse();
    assertThat(repository.findByReferenceCode("MANUAL-1"))
            .isPresent();

    // Cleanup bằng repository transaction khác (ở finally).
}
```

`TestTransaction` chỉ có ý nghĩa khi `TransactionalTestExecutionListener` đã mở **test-managed transaction** (như trong `@DataJpaTest`). `end()` kết thúc transaction hiện tại theo commit/rollback flag. Không gọi nó từ plain JUnit test không có transaction hoặc test `NOT_SUPPORTED` rồi mong nó tự tạo transaction.

### 6.4. TestTransaction.start() và flagForRollback()

Sau khi kết thúc T1, có thể khởi động T2 để kiểm dữ liệu committed từ ranh giới giao dịch mới:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

TestTransaction.start();
try {
    assertThat(repository.findByReferenceCode("MANUAL-1"))
            .isPresent();
}
finally {
    TestTransaction.flagForRollback();
    TestTransaction.end();
}
```

Đây là snippet minh họa trong một test method thuộc class `@DataJpaTest`. **T2** dùng để đọc snapshot mới và chủ động rollback sau phép kiểm. Bởi vậy row commit của **T1 vẫn còn**; muốn không làm bẩn DB, vẫn phải xóa ở transaction riêng sau T2.

### 6.5. @BeforeTransaction và @AfterTransaction

`@BeforeTransaction` chạy trước khi mở test transaction; `@AfterTransaction` chạy sau khi test transaction đã kết thúc. Chúng chỉ được gọi cho những test method được cấu hình chạy trong test-managed transaction.

```java
@BeforeTransaction
void checkCleanStart() {
    assertThat(repository.findByReferenceCode("COMMIT-1"))
            .isEmpty();
}

@Test
@Commit
void save() {
    repository.saveAndFlush(
            new PurchaseRecord("COMMIT-1", "NEW"));
}

@AfterTransaction
void checkCommittedAndClean() {
    try {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
    }
    finally {
        repository.findByReferenceCode("COMMIT-1")
                .ifPresent(repository::delete);
    }
}
```

Các hook không chạy bên trong T1. Repository methods cần transaction riêng khi ghi/delete; Spring Data JPA `SimpleJpaRepository.delete` là transactional. Với complex cleanup, dùng một bean/service `@Transactional` hoặc `TransactionTemplate` có scope rõ.

## 7. Dọn dữ liệu sau test commit thật: trách nhiệm bắt buộc

### 7.1. Tại sao @Commit là nguy hiểm nếu dùng tùy tiện?

Một test commit row rồi không xóa có thể:
- Làm test kế tiếp fail vì unique constraint.
- Khiến count/list assertions phụ thuộc thứ tự chạy.
- Gây flaky CI giữa các nhóm chạy song song.
- Tác động shared test database, sandbox hoặc dữ liệu người khác.
- Tạo outbox events/job thật nếu application infrastructure không được cô lập.

Dùng `@Commit` không phải “sửa test đỏ” bằng mọi giá. Chỉ bật commit cho những test **thật sự kiểm commit-dependent behavior**, đồng thời có cleanup và DB isolation.

### 7.2. Dùng dữ liệu namespace riêng

Nên tạo `referenceCode` duy nhất cho từng test hoặc test run. Với fixture deterministic như `COMMIT-1`, bảo đảm test database mới/cô lập và cleanup sạch.

Đối với test chạy parallel, dùng UUID suffix/correlation ID được đưa vào log/report; không dùng một mã cố định nếu test có thể chạy đồng thời trong cùng database.

### 7.3. Cleanup trong finally

```java
@AfterTransaction
void afterCommit() {
    try {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
    }
    finally {
        repository.findByReferenceCode("COMMIT-1")
                .ifPresent(repository::delete);
    }
}
```

Nếu assertion fail vì row không được commit, `finally` vẫn thử cleanup. Tuy nhiên ngay cả `finally` cũng không chạy trong các trường hợp JVM crash/kill/CI terminated; đó là lý do cần **database test riêng**, không shared production-like dữ liệu quan trọng.

### 7.4. Cleanup khi test không transactional

Với `@SpringBootTest` không có test-managed tx hoặc `@Transactional(propagation=NOT_SUPPORTED)`, service có thể commit trong method. Cleanup cần chạy qua một **transaction độc lập**; repository `delete(...)` hoặc một cleanup service transactional có thể đảm nhận.

Nếu delete cần nhiều bảng theo foreign keys/outbox records, thực hiện đúng thứ tự và đảm bảo commit cleanup. Đừng chỉ gọi `EntityManager.remove` ngoài transaction rồi kỳ vọng database đã xóa.

### 7.5. @DirtiesContext không phải cleanup database

`@DirtiesContext` khiến Spring TestContext loại bỏ/cache context và tạo context mới, **không bảo đảm xóa dữ liệu** ở database bên ngoài. Với H2 in-memory có thể có hiện tượng data mất khi context/database bị đóng, nhưng không được xem đó là contract cleanup — nhất là khi chuyển sang PostgreSQL container hoặc DB dùng chung.

### 7.6. @Sql và isolated transactions

Spring `@Sql` có thể chuẩn bị/xóa fixtures; `@SqlConfig(transactionMode = ISOLATED)` yêu cầu SQL scripts chạy trong **transaction riêng** được commit, không cùng rollback scope của test.

```java
@Sql(
    scripts = "/sql/seed-purchase.sql",
    config = @SqlConfig(transactionMode =
            SqlConfig.TransactionMode.ISOLATED))
class DatabaseFixtureTest {
    // ...
}
```

Đây là snippet minh họa, cần có file SQL thật và imports phù hợp. Nó có thể giúp tạo committed fixture nhưng cũng tạo nguy cơ dữ liệu tồn tại sau test; phải có cleanup, thường qua `@Sql` AFTER_TEST_METHOD hoặc cleanup callback có transaction riêng. Đừng cho rằng `@Sql` mặc định luôn chạy ngoài test transaction — semantics phụ thuộc cấu hình và test transaction state.

### 7.7. Testcontainers cho DB có đời sống xác định

Với integration test dùng PostgreSQL:
- Dùng database/schema/container riêng cho suite hoặc test group.
- Không trỏ vào production, dù chỉ là đọc.
- Cấu hình `@AutoConfigureTestDatabase(replace = NONE)` nếu muốn `@DataJpaTest` **không thay datasource** bằng embedded DB.
- Khi dùng Spring Boot `@ServiceConnection` với Testcontainers, bảo đảm container lifecycle và connection details thuộc môi trường test.
- Test các deferred constraints, real dialect, locks/isolation ở database thật, không H2 mô phỏng.
- Cleanup bằng truncate/delete trong DB cô lập hoặc loại bỏ container sau suite.

## 8. Những transaction ranh giới rollback không bao phủ

### 8.1. REQUIRES_NEW: transaction bên trong có thể commit độc lập

```java
@Service
class IndependentWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record() {
        // repository.save(...)
    }
}
```

Khi outer test T1 đang active, gọi method qua Spring proxy sẽ tạm suspend T1, mở T2. Nếu T2 commit thành công, sau đó T1 rollback **không undo T2**. Những thay đổi T2 vẫn còn trong database.

Đây là failure mode nguy hiểm nếu team tin “@DataJpaTest nên mọi write chắc chắn rollback”. Test cần xác định transaction boundary và cleanup row do T2 tạo.

**Cạm bẫy:** Self-invocation (`this.record()` từ method cùng class) có thể bỏ qua Spring AOP proxy, khiến annotation `REQUIRES_NEW` không tạo transaction mới như kỳ vọng. Test phải gọi qua bean/proxy hoặc kiến trúc service khác.

### 8.2. NOT_SUPPORTED: chạy test mà không có test transaction

```java
@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJpaTest {
    // ...
}
```

Đây là cách TestContext hỗ trợ **không chạy test method trong transaction**. Các repository/service methods tự quản lý transaction của chúng (hoặc fail nếu thao tác yêu cầu transaction). Dùng khi muốn test một transaction service commit lúc method return. Phải cleanup vì không có outer rollback.

### 8.3. Async/new threads

Spring JPA transactions thông thường gắn với thread qua `ThreadLocal`. Khi code dùng `@Async`, `CompletableFuture`, tự tạo thread, executor hoặc callback chạy ở thread khác, transaction test thread **không tự đi theo**.

Một test có `@Transactional` rồi gọi async service có thể commit dữ liệu ngoài transaction của test. Để kiểm async effects:
- Chờ future/queue completion deterministically.
- Dùng real test DB cô lập.
- Dọn external side effects.
- Không dựa vào `Thread.sleep(1000)` để đoán đã commit.
- Kiểm idempotency và error handling độc lập.

### 8.4. JUnit assertTimeoutPreemptively có thể phá ranh giới

`assertTimeoutPreemptively(...)` chạy code trong thread khác để có thể interrupt/timeout. Spring TestContext document cảnh báo: transactional state do ThreadLocal **không được truyền** vào thread này; DB writes bên trong có thể commit thay vì rollback cùng outer test transaction.

```java
// KHÔNG dùng mẫu này để tin vào rollback của test:
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    service.create("PREEMPTIVE-1");
});
```

Với transactional test, cân nhắc `assertTimeout(...)` (không preemptive) hoặc cách đo timeout khác an toàn với cùng thread, đồng thời bảo đảm timeout của operation bên trong. JUnit `@Timeout` behavior phụ thuộc cấu hình thread mode; luôn biết code thật chạy ở thread nào.

### 8.5. @SpringBootTest(RANDOM_PORT): server transaction ở thread khác

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class RealHttpPurchaseTest {
    // HTTP client gửi POST tới server thật.
}
```

Đây là snippet minh họa. Transaction của test method ở thread JUnit **không bao trùm** transaction xử lý request trên web server thread. Nếu controller/service lưu dữ liệu và commit, dữ liệu có thể tồn tại sau khi test transaction rollback.

Ngược lại, `@SpringBootTest(webEnvironment=MOCK)` kết hợp `MockMvc` thường thực thi MVC request **trong cùng test thread**, và service `REQUIRED` có thể tham gia outer test transaction. Hai setup này **không tương đương** về visibility/commit, dù cùng request path/assertion.

### 8.6. Multi-transaction-manager và chained resources

Nếu application có nhiều transaction managers, `@Transactional("ordersTxManager")` và `@Transactional("billingTxManager")` có thể dùng các resources khác nhau. Test transaction được chọn qua `@Transactional(transactionManager="...")` không tự rollback resources thuộc transaction manager khác.

Với Kafka transaction, JMS, file, email, remote DB hoặc multi-datasource, transaction coordination có giới hạn; đừng tuyên bố một rollback xóa toàn bộ side effects nếu chưa có cơ chế điều phối/compensation.

## 9. Project thực hành có thể chạy: Spring Boot 3.5.16, Java 17

Project cố ý nhỏ, không cần Docker, dùng **H2 embedded database** và JPA để minh họa rollback/commit. Các bài kiểm thử gồm:
1. `saveAndFlush` trong `@DataJpaTest` rồi rollback, `@AfterTransaction` kiểm row không tồn tại.
2. `@Commit` rồi `@AfterTransaction` kiểm row tồn tại và cleanup.
3. `TestTransaction.flagForCommit()`, `end()` để commit ngay giữa method.
4. Listener `AFTER_COMMIT` **không** chạy ở default rollback.
5. Listener `AFTER_COMMIT` chạy **sau** `@Commit`.
6. `@Transactional(propagation=NOT_SUPPORTED)` để service tự commit.
7. `REQUIRES_NEW` ghi dữ liệu được commit ngoài outer rollback.

### 9.1. Cây thư mục

```text
jpa-commit-boundary-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/commitlab/
│   ├── CommitLabApplication.java
│   ├── PurchaseRecord.java
│   ├── PurchaseRepository.java
│   ├── PurchaseCreated.java
│   ├── PurchaseService.java
│   ├── PurchaseCreatedListener.java
│   └── IndependentWriter.java
└── src/test/java/com/example/commitlab/
    ├── DefaultRollbackTest.java
    ├── ExplicitCommitTest.java
    ├── ManualTestTransactionTest.java
    ├── RollbackDoesNotFireEventTest.java
    ├── CommitFiresEventTest.java
    ├── NoTestTransactionTest.java
    └── RequiresNewSurvivesRollbackTest.java
```

Mọi class Java có package `com.example.commitlab`. Để đơn giản, các test dùng **mã reference khác nhau**, tự cleanup dữ liệu committed và không chia sẻ state cố ý. Các tests không dùng network hoặc external system.

### 9.2. pom.xml

```xml
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
  <artifactId>jpa-commit-boundary-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

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
```

H2 giúp project chạy cục bộ không cần DB ngoài; Spring Boot parent quản lý các dependency versions. Không thêm Spring Web starter: bài demo chỉ kiểm JPA transactions, không cần HTTP server. Khi chuyển sang PostgreSQL để test deferred constraints/locking, cấu hình DB thật/Testcontainers riêng và bỏ giả định H2 có giống production dialect.

### 9.3. application.properties

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:commitlab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
```

Vì project chỉ có H2 và không có database ngoài, `@DataJpaTest` dùng embedded datasource. `ddl-auto=create-drop` hợp lý cho demo **chỉ ở môi trường thực hành**, không dùng như migration strategy cho production. Khi ứng dụng thật có Flyway/Liquibase, cần test migrations đúng với database được chọn.

### 9.4. CommitLabApplication.java

`src/main/java/com/example/commitlab/CommitLabApplication.java`:

```java
package com.example.commitlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CommitLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CommitLabApplication.class, args);
    }
}
```

### 9.5. PurchaseRecord.java

`src/main/java/com/example/commitlab/PurchaseRecord.java`:

```java
package com.example.commitlab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false,
            unique = true, length = 80)
    private String referenceCode;

    @Column(nullable = false, length = 32)
    private String state;

    protected PurchaseRecord() {
        // JPA constructor
    }

    public PurchaseRecord(String referenceCode, String state) {
        this.referenceCode = referenceCode;
        this.state = state;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getState() {
        return state;
    }
}
```

`GenerationType.IDENTITY` cho phép provider INSERT để lấy ID khi cần; điều đó **không phải commit**. Entity có no-argument constructor theo yêu cầu JPA. Unique index là immediate constraint thông thường của H2 demo, **không phải DEFERRABLE**.

### 9.6. PurchaseRepository.java

`src/main/java/com/example/commitlab/PurchaseRepository.java`:

```java
package com.example.commitlab;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<PurchaseRecord, Long> {

    Optional<PurchaseRecord> findByReferenceCode(String referenceCode);
}
```

Spring Data JPA tạo bean repository trong `@DataJpaTest`. Query `findByReferenceCode` dùng property Java `referenceCode` (không phải SQL tên cột `reference_code`). Phương thức `delete` của `JpaRepository` thực thi trong transaction theo implementation `SimpleJpaRepository`, nên có thể dùng cho cleanup từ `@AfterTransaction`.

### 9.7. PurchaseCreated.java

`src/main/java/com/example/commitlab/PurchaseCreated.java`:

```java
package com.example.commitlab;

public record PurchaseCreated(
        Long id,
        String referenceCode) {}
```

Event là immutable Java record. Việc **publish** event khác với việc event listener **được gọi**; listener phase AFTER_COMMIT sẽ đợi transaction commit trước khi xử lý.

### 9.8. PurchaseService.java

`src/main/java/com/example/commitlab/PurchaseService.java`:

```java
package com.example.commitlab;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher events;

    public PurchaseService(
            PurchaseRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public Long create(String referenceCode) {
        PurchaseRecord saved = repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));

        events.publishEvent(new PurchaseCreated(
                saved.getId(), saved.getReferenceCode()));

        return saved.getId();
    }
}
```

Vì service dùng `@Transactional(REQUIRED)` mặc định:
- Trong `@DataJpaTest` transactional test, method thường tham gia outer test transaction.
- Trong test `NOT_SUPPORTED` (không outer test transaction), Spring proxy sẽ mở transaction mới và commit khi method trả về thành công.
- `saveAndFlush` gửi SQL nhưng listener AFTER_COMMIT **chưa** chạy cho tới khi transaction thật commit.

### 9.9. PurchaseCreatedListener.java

`src/main/java/com/example/commitlab/PurchaseCreatedListener.java`:

```java
package com.example.commitlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PurchaseCreatedListener {

    private final CopyOnWriteArrayList<PurchaseCreated> observed =
            new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreated event) {
        observed.add(event);
    }

    public List<PurchaseCreated> observed() {
        return List.copyOf(observed);
    }

    public void clear() {
        observed.clear();
    }
}
```

Listener lưu vào memory list để test đồng bộ không phải chạy email/broker. Đây **không phải audit storage production**. Nếu listener thật cần viết thêm dữ liệu DB sau commit, phải chú ý resources của transaction cũ vẫn có thể gắn thread; thường dùng **transaction mới** cho write (xem phần 11). Với event listener `@Async`, assertion phải chờ công việc hoàn thành thay vì tin đồng bộ.

### 9.10. IndependentWriter.java

`src/main/java/com/example/commitlab/IndependentWriter.java`:

```java
package com.example.commitlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentWriter {
    private final PurchaseRepository repository;

    public IndependentWriter(PurchaseRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String referenceCode) {
        repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));
    }
}
```

Đây là bean riêng để gọi qua Spring proxy, không phải self-invocation. `REQUIRES_NEW` tạm suspend transaction ngoài và commit transaction mới của service khi method return. Test sẽ dùng `@AfterTransaction` để kiểm row tồn tại dù outer test transaction đã rollback.

### 9.11. DefaultRollbackTest.java

`src/test/java/com/example/commitlab/DefaultRollbackTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DefaultRollbackTest {

    private static final String REF = "ROLLBACK-1";

    @Autowired
    PurchaseRepository repository;

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(repository.findByReferenceCode(REF)).isEmpty();
    }

    @Test
    void saveAndFlushIsNotCommit() {
        assertThat(TestTransaction.isActive()).isTrue();

        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        assertThat(repository.findByReferenceCode(REF))
                .isPresent();

        // Phép kiểm này ở trong T1 chưa chứng minh commit.
    }

    @AfterTransaction
    void afterTransaction() {
        // TestContext rollback T1 mặc định.
        assertThat(repository.findByReferenceCode(REF)).isEmpty();
    }
}
```

**Kỳ vọng:** Trong method, row được tìm thấy; sau method và rollback, `@AfterTransaction` xác nhận row không còn. Đây là phép kiểm rất trực tiếp để phá ngộ nhận `saveAndFlush == commit`.

### 9.12. ExplicitCommitTest.java

`src/test/java/com/example/commitlab/ExplicitCommitTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ExplicitCommitTest {

    private static final String REF = "COMMIT-1";

    @Autowired
    PurchaseRepository repository;

    @Test
    @Commit
    void commitsAtEndOfTestMethod() {
        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        // Vẫn ở T1: chỉ biết row đã được flush.
        assertThat(repository.findByReferenceCode(REF))
                .isPresent();
    }

    @AfterTransaction
    void provesCommitAndCleansUp() {
        try {
            // @AfterTransaction: T1 đã COMMIT xong.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

`@Commit` ở method dùng để **chỉ commit test này**. `@AfterTransaction` kiểm visible data sau commit và cleanup. Không có cleanup, test này sẽ để lại row COMMIT-1 trong DB.

### 9.13. ManualTestTransactionTest.java

`src/test/java/com/example/commitlab/ManualTestTransactionTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ManualTestTransactionTest {

    private static final String REF = "MANUAL-1";

    @Autowired
    PurchaseRepository repository;

    @Test
    void endsTestTransactionAndSeesCommittedRow() {
        assertThat(TestTransaction.isActive()).isTrue();

        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();

        try {
            // Query ngoài T1 sau commit.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

Test này khác `@Commit`: commit xảy ra **bên trong test method**, nên assertion sau `TestTransaction.end()` là post-commit assertion ngay tại chỗ. Đây là công cụ hữu ích cho một workflow cần mở T1, commit, rồi đọc ở T2. Không cần thay toàn bộ repository tests sang manual transaction boundaries.

### 9.14. RollbackDoesNotFireEventTest.java

`src/test/java/com/example/commitlab/RollbackDoesNotFireEventTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
class RollbackDoesNotFireEventTest {

    private static final String REF = "EVENT-ROLLBACK-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeTransaction
    void clearObserved() {
        listener.clear();
    }

    @Test
    void eventWaitsForCommitButTestWillRollback() {
        service.create(REF);

        assertThat(repository.findByReferenceCode(REF))
                .isPresent();
        assertThat(listener.observed()).isEmpty();
    }

    @AfterTransaction
    void verifiesNoAfterCommitEvent() {
        assertThat(repository.findByReferenceCode(REF))
                .isEmpty();
        assertThat(listener.observed()).isEmpty();
    }
}
```

Test này cho thấy “service đã gọi `publishEvent`” không đồng nghĩa AFTER_COMMIT listener đã chạy. Vì outer test transaction rollback, listener không được gọi. `@Import` chỉ import service/listener cụ thể; `@DataJpaTest` không tự scan mọi `@Service`/`@Component`.

### 9.15. CommitFiresEventTest.java

`src/test/java/com/example/commitlab/CommitFiresEventTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
class CommitFiresEventTest {

    private static final String REF = "EVENT-COMMIT-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeTransaction
    void clearObserved() {
        listener.clear();
    }

    @Test
    @Commit
    void publishesEventButListenerWaitsUntilCommit() {
        Long id = service.create(REF);

        assertThat(id).isNotNull();
        assertThat(repository.findByReferenceCode(REF))
                .isPresent();

        // Transaction T1 chưa kết thúc.
        assertThat(listener.observed()).isEmpty();
    }

    @AfterTransaction
    void verifiesAfterCommitAndCleans() {
        try {
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();

            assertThat(listener.observed())
                    .extracting(PurchaseCreated::referenceCode)
                    .containsExactly(REF);
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
            listener.clear();
        }
    }
}
```

Test này thể hiện toàn bộ timeline: event được publish trong T1; listener chưa chạy tại assertion của test method; Spring TestContext commit T1 nhờ `@Commit`; callback AFTER_COMMIT thêm event vào list; `@AfterTransaction` xác minh và cleanup.

**Giới hạn:** Listener demo chạy đồng bộ trong memory; production listener có thể dùng `@Async`, broker hoặc external API. Khi đó `@AfterTransaction` có thể xảy ra trước khi async job hoàn thành; cần chờ outcome với timeout rõ và kiểm side effects độc lập.

### 9.16. NoTestTransactionTest.java

`src/test/java/com/example/commitlab/NoTestTransactionTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NoTestTransactionTest {

    private static final String REF = "NO-TEST-TX-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeEach
    void clearObserved() {
        listener.clear();
    }

    @Test
    void serviceOpensAndCommitsOwnTransaction() {
        assertThat(TestTransaction.isActive()).isFalse();

        try {
            Long id = service.create(REF);

            // Service @Transactional đã hoàn tất commit
            // trước khi trả kết quả, không có outer T1.
            assertThat(id).isNotNull();
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
            assertThat(listener.observed())
                    .extracting(PurchaseCreated::referenceCode)
                    .containsExactly(REF);
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
            listener.clear();
        }
    }
}
```

Điểm khác biệt: `@Transactional(propagation=NOT_SUPPORTED)` trên test tắt **test-managed transaction**. Do đó `PurchaseService.create` chạy qua Spring proxy mở transaction riêng và commit trước khi return. Cần cleanup ngay trong test vì không có rollback bao ngoài.

### 9.17. RequiresNewSurvivesRollbackTest.java

`src/test/java/com/example/commitlab/RequiresNewSurvivesRollbackTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import(IndependentWriter.class)
class RequiresNewSurvivesRollbackTest {

    private static final String REF = "REQUIRES-NEW-1";

    @Autowired IndependentWriter writer;
    @Autowired PurchaseRepository repository;

    @Test
    void commitsSeparateTransactionWhileTestTransactionIsOpen() {
        assertThat(TestTransaction.isActive()).isTrue();

        // T1 của TestContext đang mở (mặc định rollback).
        // Method chạy qua Spring proxy mở T2 REQUIRES_NEW.
        writer.write(REF);

        // Không assert visibility ở T1:
        // tùy isolation/snapshot, điều đó có thể khác nhau.
    }

    @AfterTransaction
    void seesInnerCommitAfterOuterRollbackAndCleans() {
        try {
            // T2 đã commit độc lập, T1 đã rollback.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

Ví dụ này là bằng chứng rằng outer rollback không bao phủ mọi giao dịch. Test cố ý không assert row visibility bên trong T1 sau T2: mỗi database/isolation level có thể khác. `@AfterTransaction` diễn ra sau outer rollback, giúp query committed row của T2 bằng transaction mới/connection phù hợp.

### 9.18. Chạy Maven

Tại thư mục `jpa-commit-boundary-lab` với JDK 17+ và Maven:

```bash
mvn -q clean test

mvn -q -Dtest=DefaultRollbackTest test
mvn -q -Dtest=ExplicitCommitTest test
mvn -q -Dtest=ManualTestTransactionTest test
mvn -q -Dtest=RollbackDoesNotFireEventTest test
mvn -q -Dtest=CommitFiresEventTest test
mvn -q -Dtest=NoTestTransactionTest test
mvn -q -Dtest=RequiresNewSurvivesRollbackTest test
```

Nếu các assertions đều đạt, Maven báo build/test success và exit code `0`. Không khẳng định một stdout cụ thể: Hibernate/JDBC/Maven logging và số lượng context được cache có thể khác. Kết quả chi tiết nằm trong `target/surefire-reports`.

**Kiểm soát môi trường:** Đây là project dạy semantics với H2, không phải xác thực PostgreSQL deferred constraints hay HTTP server transaction. Các class/cấu hình đã được trình bày để tự chạy sau khi tạo đúng file paths; trước khi dùng production cần chạy build thật trên dependency repository/JDK của nhóm.

## 10. Bảng kết quả kỳ vọng của bảy test

| Test class | Có test transaction? | Kết thúc đáng chú ý | Quan sát sau boundary |
| --- | --- | --- | --- |
| `DefaultRollbackTest` | Có T1 | Rollback mặc định | Row không tồn tại |
| `ExplicitCommitTest` | Có T1 | `@Commit` cuối test | Row tồn tại, sau đó cleanup |
| `ManualTestTransactionTest` | Có T1 ban đầu | `TestTransaction.end()` commit ngay | Query ngoài T1 thấy row |
| `RollbackDoesNotFireEventTest` | Có T1 | Rollback mặc định | Listener AFTER_COMMIT không chạy |
| `CommitFiresEventTest` | Có T1 | `@Commit` | Listener AFTER_COMMIT chạy sau commit |
| `NoTestTransactionTest` | Không có test T1 | Service mở/commit transaction riêng | Row và event quan sát được |
| `RequiresNewSurvivesRollbackTest` | Có outer T1 | Inner T2 commit; outer T1 rollback | Row của T2 vẫn tồn tại |

Lưu ý “row tồn tại” chỉ đúng **trước cleanup** của test. Tests sử dụng cleanup sau xác minh để không gây rò rỉ state sang lần chạy khác. Đối với test chạy song song trên cùng H2/database, dùng unique fixtures và context isolation; những đoạn test này được thiết kế cho chạy tuần tự mặc định của Maven Surefire.

## 11. Các lưu ý nâng cao về AFTER_COMMIT

### 11.1. AFTER_COMMIT listener không phải điểm viết DB an toàn một cách tự động

Spring Framework Javadoc của `@TransactionalEventListener` cảnh báo: khi phase là `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`, transaction đã hoàn thành nhưng một số resources vẫn có thể gắn với thread. Thao tác truy cập dữ liệu tại thời điểm đó có thể **vẫn tham gia resources của transaction cũ**, mà sẽ **không có commit tiếp theo**.

Do đó, nếu listener cần ghi audit row/database record, thường phải mở một transaction **mới**:

```java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(PurchaseCreated event) {
        // auditRepository.save(...)
    }
}

@Component
class PurchaseAuditListener {
    private final AuditWriter auditWriter;

    PurchaseAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreated event) {
        auditWriter.writeAudit(event);
    }
}
```

Đây là **mẫu minh họa**, không nằm trong runnable project vì thiếu `auditRepository`/entity. `AuditWriter` phải là Spring bean khác để `REQUIRES_NEW` chạy qua proxy; self-invocation trong cùng class có thể bỏ qua AOP.

### 11.2. AFTER_COMMIT listener có chạy khi publish ngoài transaction?

Mặc định `@TransactionalEventListener` có `fallbackExecution = false`. Nếu event được publish **không có active transaction**, listener sẽ không xử lý event. Có thể cấu hình `fallbackExecution=true` nếu business requirement cần fallback, nhưng lúc đó behavior khác khi có/không có transaction; phải test cả hai.

Ví dụ thực tế: Một phương thức không có `@Transactional` publish event rồi một listener AFTER_COMMIT không chạy. Không tự coi đó là bug Spring; cần xem event được publish ở boundary nào.

### 11.3. BEFORE_COMMIT và AFTER_ROLLBACK

`TransactionPhase.BEFORE_COMMIT` chạy trước commit; exception từ callback có thể ngăn transaction commit tùy handling. `AFTER_ROLLBACK` chạy khi transaction rollback. `AFTER_COMPLETION` chạy sau kết thúc, bất kể kết quả.

Nếu hệ thống cần một hành động **chỉ khi commit thành công**, chọn `AFTER_COMMIT` thay vì `AFTER_COMPLETION`. Nếu cần cleanup cả rollback/commit, chọn hook phù hợp nhưng tránh làm nghiệp vụ “đã thành công” trước khi commit xác nhận.

### 11.4. @Async kết hợp AFTER_COMMIT

Nếu listener vừa `@Async` vừa `@TransactionalEventListener(AFTER_COMMIT)`, callback dispatch có thể bất đồng bộ. Test không nên:

```java
service.create("ASYNC-1");
assertThat(emailGateway.sent()).isTrue(); // race
```

Mẫu này chỉ minh họa rủi ro, không thuộc project runnable. Muốn kiểm:
- Commit transaction thật.
- Chờ event processing completion bằng `CountDownLatch`/`CompletableFuture`/message receipt có timeout.
- Assert outcome trong hạn thời gian rõ.
- Dùng fake external adapter để không gửi email thật.
- Không dựa vào `Thread.sleep` với độ trễ cố định dễ flaky.

### 11.5. Không đảm bảo “exactly once” bởi AFTER_COMMIT

`@TransactionalEventListener(AFTER_COMMIT)` trong một JVM không tự cung cấp durable messaging hoặc guarantee exactly-once giữa database và broker. JVM có thể crash sau commit nhưng trước khi listener xử lý xong external side effect. Với yêu cầu không mất event, transactional outbox + relay có retry/idempotency thường phù hợp hơn. Test commit thật chỉ là một phần của kiểm chứng.

## 12. Kiểm ràng buộc và transaction isolation trên database thật

### 12.1. H2 và PostgreSQL có thể hành xử khác

H2 thích hợp cho JPA repository smoke tests và bài học nhỏ. Tuy nhiên khi production dùng PostgreSQL/MySQL/Oracle, những điểm sau cần integration test trên chính engine/version:
- Deferred constraints và transaction commit timing.
- Locking (`SELECT FOR UPDATE`), deadlock, serialization failures.
- Isolation levels, MVCC snapshots và phantom/non-repeatable reads.
- JSONB, native queries, stored procedures, database triggers.
- SQL dialect, identity/sequence generation, timezone/collation.
- Batch flush ordering, auto-generated IDs, transaction propagation effects.

Không suy từ `@DataJpaTest` với embedded H2 rằng application đã kiểm được engine production.

### 12.2. Testcontainers với @DataJpaTest

Với Testcontainers PostgreSQL, ví dụ annotation-level setup **minh họa**:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace =
        AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class PostgresCommitContractTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");
}
```

Cần thêm dependencies `org.testcontainers:postgresql`, `org.testcontainers:junit-jupiter` và `spring-boot-testcontainers` trong test scope, cùng container runtime. Không phải project H2 mục 9. Khi `@ServiceConnection` hoạt động, Spring Boot nhận connection details từ container; `replace=NONE` giúp ngăn test slice thay datasource bằng H2.

Version PostgreSQL image trong snippet là một ví dụ; project thật nên chọn version tương ứng production và kiểm chính sách bảo mật/supply chain.

### 12.3. Test commit thất bại bởi deferred constraint

Với PostgreSQL, setup table constraint deferred, insert dữ liệu vi phạm vào transaction, rồi ép commit bằng `TestTransaction.flagForCommit()` và `TestTransaction.end()`. **Assertion về exception phải bao quanh commit**, không chỉ `repository.flush()`. Đây là tình huống mà rollback test chỉ assert trạng thái trong transaction có thể bỏ qua.

```java
TestTransaction.flagForCommit();

assertThatThrownBy(TestTransaction::end)
        .isInstanceOf(RuntimeException.class);
```

Snippet này **chỉ minh họa vị trí exception**; loại exception cụ thể tùy Spring transaction manager/JDBC driver, và test cần schema/data vi phạm deferred constraint. Sau commit fail, transaction bị đánh dấu/đóng; không tái sử dụng như còn active. Cần thiết kế cleanup cho mọi dữ liệu ngoài transaction liên quan.

### 12.4. Kiểm visibility bằng connection/transaction khác

Nếu yêu cầu là “một consumer khác chỉ thấy row sau commit”, dùng:
1. T1 lưu và flush, giữ transaction chưa commit.
2. T2 trên **connection khác** thử đọc và assert chưa thấy (theo isolation đã cấu hình).
3. Commit T1.
4. T3 (transaction đọc mới) đọc lại và assert thấy.

Đây là integration scenario cần hai connections và orchestration có timeout. Không xây T2 trên cùng `EntityManager` rồi xem đó là transaction độc lập. Trong `READ_COMMITTED`, kết quả có thể khác các isolation levels/snapshot semantics khác; xác định contract trước.

## 13. Web layer và transactional test: một cạm bẫy lớn

### 13.1. MockMvc với test transaction

Một `@SpringBootTest` hoặc `@WebMvcTest` có `MockMvc` thường chạy request handling trong cùng thread test. Nếu controller gọi service `@Transactional(REQUIRED)`, nó có thể tham gia test transaction; rollback cuối test có thể undo writes. Điều này tiện cho integration test giả lập HTTP, nhưng có thể **che AFTER_COMMIT events**.

### 13.2. RANDOM_PORT với real HTTP

Khi dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`:
- JUnit test method ở test thread.
- HTTP client gửi request qua network loopback.
- Server xử lý ở worker thread riêng.
- Server transaction commit/rollback theo application code, không phải test-managed transaction.
- `@Transactional` trên test thread không bao trùm server-side transaction.

Nếu test POST tạo row mà không cleanup, row thường còn sau test. Đừng dùng test-level `@Transactional` như chiến lược cleanup cho real HTTP integration test.

### 13.3. @Transactional trên controller/service là điều kiện cần hiểu

Một HTTP request có thể gọi service không `@Transactional`, dẫn tới repository methods mở transaction riêng theo method semantics. Phải biết transaction boundary thực tại code được Spring proxy gọi. Không chỉ nhìn `@Transactional` trên test class rồi suy luận về service transaction ở server.

### 13.4. JPA và reactive pipelines

Spring Data JPA dùng imperative transaction manager và ThreadLocal model; reactive R2DBC dùng Reactor context/`ReactiveTransactionManager`. Bài này nói về JPA. Không áp thẳng `TestTransaction`/thread-bound JPA rollback sang R2DBC publishers như thể chúng chung cơ chế. Nếu ứng dụng WebFlux vẫn gọi blocking JPA (không khuyến nghị trên event loop), cần hiểu thread scheduling và transaction boundaries.

## 14. Các lỗi phổ biến và cách khắc phục

### 14.1. “Đã saveAndFlush nên chắc chắn commit”

**Sai:** `flush` gửi SQL trước commit. Kiểm bằng `@AfterTransaction` sau rollback/commit hoặc `TestTransaction.end()`. Nếu lỗi chỉ xảy ra ở commit, phải thực hiện commit thật trong test thích hợp.

### 14.2. @TransactionalEventListener không chạy trong @DataJpaTest

**Nguyên nhân thường gặp:** outer test transaction rollback. **Sửa:** test commit có chủ đích bằng `@Commit` hoặc `TestTransaction.flagForCommit()`; kiểm listener ở `@AfterTransaction`/sau end. Không sửa production listener sang `@EventListener` chỉ để test xanh nếu requirement là AFTER_COMMIT.

### 14.3. @Commit nhưng assertion bên trong @Test vẫn thấy listener rỗng

**Đúng kỳ vọng:** `@Commit` chỉ đổi thao tác khi test method **kết thúc**. Listener AFTER_COMMIT chưa được gọi trong body. Đặt assertion ở `@AfterTransaction` hoặc dùng `TestTransaction.end()` trước assertion.

### 14.4. @Commit làm test sau fail unique constraint

**Nguyên nhân:** committed row còn trong DB. **Sửa:** cleanup ở `@AfterTransaction`/finally hoặc dùng database/schema cô lập và unique fixtures. Không dựa vào thứ tự test execution.

### 14.5. REQUIRES_NEW ghi được dù outer test rollback

**Nguyên nhân:** T2 commit độc lập. **Sửa:** nếu cần test semantics đó, assert post-boundary và cleanup T2 row; nếu không muốn, đổi design propagation một cách có chủ đích, không coi đây là bug framework.

### 14.6. @SpringBootTest không rollback như @DataJpaTest

**Nguyên nhân:** `@SpringBootTest` không mặc định bật test transaction. **Sửa:** chỉ thêm test-level `@Transactional` nếu đúng mục đích; với test cần after-commit, giữ explicit real transaction + cleanup. Đừng thêm `@Transactional` vào full HTTP test rồi nhầm rollback server writes.

### 14.7. assertTimeoutPreemptively làm database bị bẩn

**Nguyên nhân:** code chạy ở thread mới, không có TestContext ThreadLocal transaction. **Sửa:** tránh preemptive timeout bên trong transactional tests hoặc cô lập DB/cleanup; ưu tiên bounded operations và timeout không đổi thread nếu phù hợp.

### 14.8. JPA constraint fail trên production nhưng H2 test PASS

**Nguyên nhân:** engine/dialect/constraint timing khác. **Sửa:** Testcontainers với DB/version production và migrate schema thật, đặc biệt khi test deferred constraints, isolation hoặc triggers.

### 14.9. @BeforeEach cleanup không giúp test sau commit

**Nguyên nhân:** `@BeforeEach` trong transactional test chạy **trong T1** và cleanup của nó cũng có thể rollback, không loại dữ liệu đã commit trước. **Sửa:** `@BeforeTransaction` hoặc cleanup service trong transaction riêng; tốt nhất test DB cô lập.

### 14.10. @DirtiesContext không xóa PostgreSQL data

**Nguyên nhân:** nó chỉ loại cache Spring context. **Sửa:** dùng scripts/SQL/repository cleanup có transaction commit hoặc drop schema/container. Không lạm dụng context reset vì làm test suite chậm.

### 14.11. Listener AFTER_COMMIT ghi audit row nhưng row không tồn tại

**Nguyên nhân:** after-commit callback có thể còn gắn resources cũ, không có commit tiếp. **Sửa:** gọi một bean `@Transactional(REQUIRES_NEW)` hoặc `TransactionTemplate` với propagation mới cho audit write; kiểm bằng separate transaction sau callback.

### 14.12. Test chạy parallel có kết quả không ổn định

**Nguyên nhân:** shared database rows, listener in-memory state, cùng reference codes và context caching. **Sửa:** unique fixtures, cleanup, container isolation, tránh shared mutable listener state và đừng cho những test đó chạy parallel khi chưa thiết kế concurrency.

### 14.13. Query thấy row trong outer transaction nhưng connection khác không thấy

**Nguyên nhân:** uncommitted data và isolation/MVCC. **Sửa:** test với hai transaction độc lập, commit T1, bắt đầu transaction đọc mới. Không gọi `EntityManager.clear()` rồi cho rằng vừa tạo transaction mới.

### 14.14. Test event bị flake vì async listener

**Nguyên nhân:** post-commit dispatch bất đồng bộ. **Sửa:** chờ completion/event receipt trong thời gian bounded, không `Thread.sleep`. Với in-memory listener trong project này, dispatch đồng bộ và dễ kiểm hơn.

### 14.15. Giao dịch kết thúc lỗi nhưng test vẫn muốn commit

**Nguyên nhân:** transaction rollback-only, commit-time constraint hoặc connection failure. **Sửa:** assert failure quanh commit boundary, không quanh `save` đơn thuần; kiểm root cause và state cleanup.

## 15. Quyết định dùng rollback hay commit: ma trận

| Mục tiêu test | Rollback mặc định? | Có cần commit thật? | Lý do |
| --- | --- | --- | --- |
| Entity mapping cơ bản, repository query | Phù hợp | Không nhất thiết | Kiểm trong transaction là đủ |
| Constraint được kiểm ngay lúc flush | Thường phù hợp | Không nhất thiết | `flush` có thể kích hoạt lỗi sớm |
| Deferred constraint ở DB production | Không đủ | Có | Lỗi có thể chỉ xuất hiện khi commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | Không đủ | Có | Callback chỉ chạy sau commit |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Phù hợp | Không | Phải kiểm đường rollback |
| Unique ID generation bằng IDENTITY | Thường phù hợp | Không nhất thiết | ID có thể cấp trước commit |
| Visibility giữa hai connections | Không đủ | Có | Cần đóng T1 và đọc từ T2/T3 |
| Outbox/CDC relay | Không đủ | Có, trong DB cô lập | Relay đọc committed row |
| `REQUIRES_NEW` có bị outer rollback? | Không bao phủ | Inner transaction commit | Cần kiểm propagation |
| Real HTTP POST với RANDOM_PORT | Không có test rollback bao trùm server | App tự commit | Dọn dữ liệu ngoài test |
| Unit test business calculations | Không cần Spring context | Không | Dùng pure JUnit/Mockito |
| Email/message side effects | DB rollback không đủ | Không nhất thiết để unit test adapter | Cần fake external services + idempotency |

Một test suite tốt kết hợp **nhiều rollback tests rẻ/cô lập** và **một nhóm commit/integration tests có mục tiêu rõ**. Không chuyển cả suite sang `@Commit` và không dùng full database thật cho mọi rule thuần Java.

## 16. Bài tập ôn luyện

1. Giải thích vì sao `repository.saveAndFlush(...)` có thể thành công trong `@DataJpaTest` nhưng `@AfterTransaction` lại không tìm thấy row.
2. Viết một test `@Commit`, assert committed data trong `@AfterTransaction` và cleanup dù assertion thất bại.
3. Viết lại test trên với `@Rollback(false)`; nêu thời điểm commit và phạm vi annotation.
4. Dùng `TestTransaction.flagForCommit()`/`end()` để commit giữa test, rồi bắt đầu một transaction đọc mới bằng `TestTransaction.start()`.
5. Một service `@Transactional(REQUIRED)` return sau `saveAndFlush` trong test T1. Service đã commit chưa? Phụ thuộc điều kiện nào?
6. Viết event listener `AFTER_COMMIT`. Vì sao nó không chạy khi test rollback?
7. Giải thích vì sao `AFTER_COMMIT` listener muốn ghi audit DB nên gọi service `REQUIRES_NEW`.
8. Dùng `REQUIRES_NEW` trong writer và thử outer test rollback. Kiểm row tồn tại sau outer rollback và xóa nó.
9. Chạy `@SpringBootTest(RANDOM_PORT)` POST tạo entity rồi kiểm transaction boundary; vì sao test-level `@Transactional` không xóa row được tạo từ server thread?
10. Nêu sự khác nhau giữa H2 immediate constraint và PostgreSQL DEFERRABLE constraint; exception có thể xảy ra ở đâu?
11. Viết một scenario T1/T2 kiểm visibility của uncommitted/committed data trên database thật có isolation được xác định.
12. Viết test outbox relay chỉ nhìn thấy event sau commit nhưng không gửi tới broker production.
13. Giải thích tại sao `@DirtiesContext` không là chiến lược cleanup cho PostgreSQL shared database.
14. Nếu JUnit dùng `assertTimeoutPreemptively` bên trong `@Transactional` test, dữ liệu nào có thể thoát khỏi rollback?
15. Liệt kê cách tránh một test commit thật làm hỏng test chạy sau hoặc chạy parallel.

Đạt yêu cầu khi người học biết chỉ ra **giao dịch nào đang mở, ai quản lý, khi nào kết thúc, bean nào tham gia, data/side effects nào sống sau rollback** trước khi viết assertion.

## 17. Checklist review cho bài test có transaction

- [ ] Test có thật sự cần commit để kiểm behavior không?
- [ ] Biết `@DataJpaTest` mặc định rollback; `@SpringBootTest` không tự bật `@Transactional`?
- [ ] Đã phân biệt `save`/`flush`/`saveAndFlush`/`commit`/`rollback`?
- [ ] Không suy từ query trong cùng persistence context rằng row đã committed?
- [ ] `@Commit`/`@Rollback(false)` chỉ dùng với test-managed transaction phù hợp?
- [ ] Assertions commit-dependent đặt ở `@AfterTransaction` hoặc sau `TestTransaction.end()`?
- [ ] Với `@TransactionalEventListener(AFTER_COMMIT)`, đã chờ commit thật?
- [ ] Listener có ghi DB sau commit không? Có cần `REQUIRES_NEW`?
- [ ] Với `REQUIRES_NEW`, đã tính transaction độc lập và cleanup?
- [ ] Với `NOT_SUPPORTED`, có hiểu service/repository tự commit transaction riêng?
- [ ] Với async hoặc HTTP server thread, không dựa vào test ThreadLocal rollback?
- [ ] Có tránh `assertTimeoutPreemptively` bên trong transactional tests?
- [ ] Dữ liệu commit thật được cleanup dù assertion lỗi?
- [ ] Database/schema/fixtures được cô lập, không viết vào production?
- [ ] Các tests chạy parallel có unique IDs và không chia sẻ mutable event state?
- [ ] H2 có phù hợp với rủi ro cần kiểm, hay phải dùng Postgres/Testcontainers?
- [ ] Deferred constraints/trigger/CDC/integration test có commit boundary thật?
- [ ] `@Sql` có cấu hình transaction mode/cleanup rõ?
- [ ] `@DirtiesContext` không bị nhầm là database cleanup?
- [ ] Đã chạy Maven/JUnit suite sạch và xem root cause của commit failures?

**Kết luận:** Rollback mặc định của `@DataJpaTest` là công cụ **cô lập test rất hữu ích**, nhưng nó không tự kiểm thử commit và có thể che hành vi chỉ xảy ra **sau commit**. `saveAndFlush` giúp kiểm SQL và constraints tức thời nhưng **không kết thúc transaction**. Khi mục tiêu là AFTER_COMMIT events, deferred constraints, visibility ở transaction khác hoặc outbox/CDC, hãy chủ động kiểm commit bằng `@Commit`/`TestTransaction`/`@AfterTransaction` với database và cleanup phù hợp. Đồng thời kiểm những giao dịch không nằm trong outer rollback như `REQUIRES_NEW`, HTTP server threads, async tasks và external side effects.

## 18. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — TestContext Transaction Management (test-managed vs Spring-managed transactions; rollback/commit; TestTransaction; lifecycle; preemptive timeouts): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Boot 3.5 Javadoc — `@DataJpaTest` (transactional + rollback mặc định): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `@Commit`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-commit.html
- Spring Framework 6.2 — `@Rollback`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-rollback.html
- Spring Framework 6.2 — `@BeforeTransaction` / `@AfterTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-beforetransaction.html
- Spring Framework 6.2 — TestTransaction API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Data JPA — Transactionality and Repository methods: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Data JPA — `JpaRepository.saveAndFlush` API: https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html
- PostgreSQL — Constraint Types / DEFERRABLE: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Boot Testcontainers — Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
