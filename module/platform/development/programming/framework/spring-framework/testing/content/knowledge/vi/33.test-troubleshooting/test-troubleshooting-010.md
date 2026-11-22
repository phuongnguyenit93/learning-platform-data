# Giao dịch rollback che lỗi flush hoặc dữ liệu kiểm thử bị rò

Spring Test thường chạy test method có `@Transactional` trong một transaction riêng và rollback transaction đó khi test kết thúc. Cơ chế này giúp dữ liệu do test tạo ra không tồn tại sau test. Tuy nhiên, rollback cũng có thể làm test bỏ qua những hành vi chỉ xảy ra khi SQL được flush hoặc transaction được commit. Ngoài ra, một số thao tác database có thể chạy ngoài transaction do Spring Test quản lý và để lại dữ liệu dù test đã kết thúc.

Hai vấn đề cần phân biệt:

- **Lỗi flush bị che:** test thay đổi entity trong persistence context nhưng chưa đẩy SQL xuống database. Test kết thúc và rollback, nên constraint hoặc lỗi SQL chưa từng được thực thi.
- **Dữ liệu bị rò:** thao tác ghi dữ liệu chạy trong transaction độc lập, thread khác, request đến server thật hoặc một transaction đã commit. Rollback của test không thể hoàn tác thao tác đó.

Muốn kiểm thử persistence đáng tin cậy, cần hiểu rõ vòng đời transaction, thời điểm JPA flush, phạm vi thread-bound của transaction và những thao tác nằm ngoài transaction test.

## 1. Transaction test của Spring hoạt động thế nào?

Spring TestContext Framework hỗ trợ quản lý transaction cho test thông qua `TransactionalTestExecutionListener`. Khi test class hoặc test method được đánh dấu `@Transactional`, Spring bắt đầu một test-managed transaction trước khi chạy test method và mặc định rollback transaction sau khi test hoàn tất.

Ví dụ:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        customerRepository.save(new Customer("alice@example.test"));

        assertThat(customerRepository.findByEmail("alice@example.test"))
                .isPresent();
    }
}
```

`@DataJpaTest` được cấu hình để chạy trong transaction và rollback sau mỗi test method theo mặc định. Dữ liệu được tạo trong transaction này thường không còn sau khi test kết thúc.

Với test dùng `@SpringBootTest`, transaction test không tự động có chỉ vì annotation này được sử dụng. Cần đánh dấu class hoặc method bằng `@Transactional` nếu muốn Spring Test quản lý transaction cho test.

### Vòng đời transaction

Với một test transactional thông thường, trình tự khái quát là:

```text
Spring Test bắt đầu test-managed transaction
                  |
                  v
             @BeforeEach
                  |
                  v
              @Test
                  |
                  v
              @AfterEach
                  |
                  v
         Rollback transaction
                  |
                  v
      @AfterTransaction callback
```

`@BeforeTransaction` chạy trước khi test-managed transaction bắt đầu; `@AfterTransaction` chạy sau khi transaction đã kết thúc. Hai callback này hữu ích khi cần chuẩn bị hoặc kiểm tra dữ liệu ở ngoài transaction của test.

Mặc định, `@Rollback` có giá trị `true`. Có thể dùng `@Commit` hoặc `@Rollback(false)` để yêu cầu commit thay vì rollback, nhưng khi đó test phải có chiến lược dọn dữ liệu rõ ràng.

## 2. Flush không đồng nghĩa với commit

JPA duy trì persistence context để theo dõi entity. Khi gọi `persist`, `merge` hoặc Spring Data JPA `save`, thay đổi có thể chỉ được ghi nhận trong persistence context mà chưa lập tức gửi SQL đến database.

**Flush** đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng cách thực thi các câu SQL cần thiết. **Commit** kết thúc transaction và làm các thay đổi được commit theo transaction manager/database.

Hai thao tác có quan hệ nhưng không giống nhau:

| Thao tác | Điều xảy ra | Dữ liệu có được commit không? |
| --- | --- | --- |
| `repository.save(entity)` | Đưa entity vào trạng thái được quản lý/lưu theo cơ chế repository; SQL có thể chưa chạy | Không |
| `entityManager.flush()` | Gửi các thay đổi đang chờ xuống database | Không, transaction vẫn có thể rollback |
| `repository.saveAndFlush(entity)` | Save rồi yêu cầu flush | Không, transaction vẫn có thể rollback |
| Transaction commit | Hoàn tất transaction theo database | Có, nếu commit thành công |
| Transaction rollback | Hoàn tác thay đổi transactional chưa commit | Không |

Vì vậy, một test có thể gọi `save()` thành công, assertion trên object trong bộ nhớ cũng thành công, rồi transaction rollback mà chưa từng gửi câu INSERT đến database.

### Vì sao lỗi database có thể bị che?

Giả sử cột email có unique constraint. Test tạo hai khách hàng trùng email nhưng chỉ gọi `save()` và không flush. Tùy provider và thời điểm flush, câu INSERT có thể chưa chạy trong phần thân test. Nếu transaction bị rollback trước khi commit, unique constraint có thể chưa bao giờ được kiểm tra.

Ví dụ test chưa đủ chặt:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void duplicateEmailIsRejected() {
        repository.save(new Customer("same@example.test"));
        repository.save(new Customer("same@example.test"));

        // Test kết thúc và transaction rollback.
        // Nếu chưa flush, database có thể chưa thực thi INSERT.
    }
}
```

Test trên không có assertion xác nhận constraint được áp dụng. Nó có thể xanh dù database sẽ từ chối dữ liệu khi transaction thực sự được flush/commit.

## 3. Dùng flush để buộc database thực thi SQL trong test

Khi mục tiêu là kiểm tra constraint, mapping hoặc câu lệnh SQL, hãy flush tại thời điểm phù hợp để lỗi xuất hiện ngay trong test.

Ví dụ entity:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

Test kiểm tra unique constraint:

```java
@DataJpaTest
class CustomerRepositoryConstraintTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmailWhenChangesAreFlushed() {
        repository.saveAndFlush(new Customer("same@example.test"));

        assertThatThrownBy(() ->
                repository.saveAndFlush(new Customer("same@example.test")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
```

`saveAndFlush` yêu cầu Spring Data JPA đồng bộ thay đổi xuống database. Với unique constraint được kiểm tra ngay khi thực thi INSERT, test có thể quan sát lỗi tại lời gọi thứ hai. Loại exception cụ thể có thể phụ thuộc JPA provider và cách Spring dịch lỗi; `DataIntegrityViolationException` là dạng thường gặp khi lỗi được Spring Data/Spring ORM chuyển đổi.

Có thể dùng `EntityManager.flush()` nếu test đang thao tác qua entity manager:

```java
entityManager.persist(new Customer("same@example.test"));
entityManager.flush();

entityManager.persist(new Customer("same@example.test"));

assertThatThrownBy(entityManager::flush)
        .isInstanceOf(PersistenceException.class);
```

Trong ví dụ thứ hai, loại exception có thể là exception của JPA provider hoặc được Spring dịch tùy cách gọi và vị trí bắt lỗi. Khi cần assertion chính xác, hãy căn cứ vào exception thực tế của provider/database đang được test.

### Flush không commit transaction

Sau khi `flush()` thành công, dữ liệu vẫn thuộc transaction hiện tại. Nếu test kết thúc với rollback, INSERT/UPDATE/DELETE transactional vẫn bị hoàn tác. Đây là điều mong muốn: test có thể kiểm tra SQL và constraint mà không để dữ liệu tồn tại sau test.

## 4. Dùng flush và clear để tránh assertion chỉ đọc lại bộ nhớ

Một test có thể đọc lại entity từ persistence context thay vì thực sự truy vấn database. Nếu entity vẫn được quản lý trong first-level cache, lời gọi `findById` có thể trả lại cùng object mà không phát sinh SELECT.

Khi muốn xác nhận dữ liệu đã được ghi và có thể tải lại từ database, hãy flush rồi clear persistence context trước khi đọc:

```java
@DataJpaTest
class CustomerRepositoryPersistenceTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void reloadsCustomerAfterFlushAndClear() {
        Customer saved = repository.save(new Customer("alice@example.test"));

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = repository.findById(saved.getId()).orElseThrow();

        assertThat(reloaded.getEmail()).isEqualTo("alice@example.test");
    }
}
```

`flush()` đẩy thay đổi xuống database. `clear()` detach các entity khỏi persistence context hiện tại. Khi gọi `findById`, JPA cần tải entity lại, nên test xác nhận được trạng thái đã lưu trong database thay vì chỉ kiểm tra object cũ còn nằm trong bộ nhớ.

`TestEntityManager` là tiện ích do Spring Boot cung cấp cho JPA test slice. Với test Spring/JPA không dùng Boot, có thể inject `EntityManager` phù hợp.

Không cần `clear()` cho mọi test. Chỉ dùng khi mục tiêu là xác nhận dữ liệu được đọc lại hoặc muốn tránh persistence context che mất lỗi truy vấn.

## 5. Những thời điểm JPA có thể tự flush

Ngoài gọi `flush()` trực tiếp, JPA provider có thể tự flush trong một số tình huống, tùy `FlushMode` và loại thao tác.

Với `FlushModeType.AUTO` thường dùng mặc định, provider phải bảo đảm các thay đổi có ảnh hưởng đến kết quả truy vấn được đồng bộ trước khi thực thi query tương ứng. Vì vậy, một truy vấn có thể làm lỗi constraint xuất hiện dù code không gọi `flush()` tường minh.

Một số thời điểm thường gặp:

- Gọi `EntityManager.flush()`.
- Gọi `JpaRepository.flush()` hoặc `saveAndFlush()`.
- Trước khi thực thi query khi flush mode yêu cầu đồng bộ thay đổi liên quan.
- Khi transaction commit, provider thường flush các thay đổi còn chờ trước khi commit.

Thời điểm cụ thể có thể phụ thuộc provider, flush mode, loại query và database. Không nên viết test dựa vào giả định rằng mọi lời gọi `save()` đều phát SQL ngay.

## 6. Constraint được kiểm tra lúc flush hay lúc commit?

Nhiều constraint như `NOT NULL`, unique thông thường hoặc foreign key không trì hoãn sẽ được database kiểm tra khi câu SQL liên quan được thực thi. Flush thường đủ để phát hiện lỗi.

Một số database hỗ trợ constraint trì hoãn (deferred constraint), được kiểm tra khi transaction commit. Với constraint loại này, flush có thể thành công dù transaction sau đó thất bại khi commit.

Điều đó có nghĩa:

- Nếu muốn xác nhận SQL được phát và constraint tức thời hoạt động, flush là đủ.
- Nếu muốn xác nhận hành vi chỉ xảy ra tại commit, cần một test thực sự commit transaction.
- Rollback test mặc định không thể chứng minh commit thành công hoặc thất bại.

Ví dụ, PostgreSQL hỗ trợ một số constraint khai báo `DEFERRABLE`, có thể được kiểm tra ở thời điểm commit. Test dùng H2 hoặc database khác có thể không tái hiện cùng hành vi; hãy dùng đúng hệ quản trị database khi tính năng phụ thuộc dialect.

## 7. Kiểm tra hành vi commit có chủ đích

Nếu cần xác nhận transaction commit, có thể dùng `@Commit` hoặc `@Rollback(false)`:

```java
@DataJpaTest
class CommittedCustomerTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    @Commit
    void commitsCustomer() {
        repository.save(new Customer("committed@example.test"));
    }
}
```

Test này yêu cầu Spring commit transaction thay vì rollback. Tuy nhiên, dữ liệu có thể tồn tại sau test và ảnh hưởng đến lần chạy sau. Chỉ dùng cách này khi commit là hành vi cần kiểm tra và có cleanup rõ ràng.

Một lựa chọn khác là điều khiển test-managed transaction bằng `TestTransaction`:

```java
@DataJpaTest
class TransactionBoundaryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsAtAnExplicitPoint() {
        repository.save(new Customer("commit-check@example.test"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
    }
}
```

`TestTransaction.flagForCommit()` đánh dấu transaction hiện tại sẽ commit; `end()` kết thúc transaction và thực hiện commit/rollback theo cờ đã đặt. `TestTransaction` có thể bắt đầu transaction mới bằng `start()` nếu test cần tiếp tục thao tác trong transaction khác. Cần nhớ rằng commit thật có thể làm dữ liệu tồn tại sau test.

### Kiểm tra trạng thái sau transaction

Nếu cần xác nhận dữ liệu không còn sau rollback, hãy truy vấn từ một transaction độc lập sau khi transaction test đã kết thúc. Không thể chứng minh rollback chỉ bằng cách đọc lại trong chính transaction trước khi nó kết thúc.

Spring Test cung cấp `@AfterTransaction` để thực hiện kiểm tra sau khi test-managed transaction đã kết thúc:

```java
@DataJpaTest
class RollbackVerificationTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void writesTemporaryRecordInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into audit_note(message) values (?)",
                "temporary");

        assertThat(jdbcTemplate.queryForObject(
                "select count(*) from audit_note where message = ?",
                Integer.class,
                "temporary")).isEqualTo(1);
    }

    @AfterTransaction
    void verifiesRollbackRemovedRecord() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from audit_note where message = ?",
                Integer.class,
                "temporary");

        assertThat(count).isZero();
    }
}
```

Ví dụ giả định bảng `audit_note` đã được tạo trong test database. `@AfterTransaction` chạy ngoài transaction test, nên truy vấn quan sát trạng thái sau rollback. Trong ứng dụng thực tế, nên dùng một khóa dữ liệu duy nhất để test không đụng đến dữ liệu của test khác.

## 8. Những trường hợp rollback của test không thể dọn dữ liệu

Transaction rollback chỉ hoàn tác các thao tác thuộc transaction mà nó rollback. Nó không tự động hoàn tác mọi thay đổi database được thực hiện trong thời gian test chạy.

### Propagation.REQUIRES_NEW

Một phương thức được gọi qua Spring transaction proxy với `Propagation.REQUIRES_NEW` sẽ chạy trong transaction mới. Transaction bên ngoài bị tạm ngưng; transaction mới có thể commit độc lập. Sau đó, dù transaction test bên ngoài rollback, dữ liệu đã commit bởi transaction mới vẫn tồn tại.

Ví dụ:

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String message) {
        auditRepository.save(new AuditEntry(message));
    }
}
```

Nếu test gọi `auditService.record(...)` trong khi test-managed transaction đang mở, Spring tạo transaction độc lập cho `record`. Nếu transaction này commit, rollback transaction test không xóa bản ghi audit.

Lưu ý: `REQUIRES_NEW` chỉ hoạt động theo cơ chế proxy khi lời gọi đi qua Spring bean proxy. Tự gọi một method khác trong cùng object (self-invocation) thường không đi qua proxy và có thể không áp dụng propagation như mong đợi.

### Test method chạy trên thread khác

Spring transaction thường được gắn với thread hiện tại. Các cơ chế sau có thể chạy code trên thread khác:

- `@Async` hoặc `TaskExecutor`.
- `CompletableFuture` hoặc executor tùy chỉnh.
- Servlet container khi test gửi request qua HTTP đến embedded server.
- JUnit `assertTimeoutPreemptively`, vốn thực thi đoạn code trong một thread khác để có thể ngắt khi timeout.

Transaction của test không tự truyền sang thread khác. Nếu thread mới thực hiện thao tác ghi, nó có thể chạy trong transaction riêng hoặc auto-commit tùy cấu hình. Vì vậy, test có thể kết thúc rollback nhưng dữ liệu từ thread phụ vẫn còn.

#### Cẩn thận với assertTimeoutPreemptively

Ví dụ dễ gây rò dữ liệu:

```java
@Test
@Transactional
void mayWriteOutsideTestManagedTransaction() {
    assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
        repository.save(new Customer("timeout@example.test"));
    });
}
```

JUnit chạy executable trong thread khác. Transaction test do Spring quản lý được gắn với thread test ban đầu, nên thao tác repository trong thread thực thi preemptive timeout có thể không tham gia transaction đó. Nếu thao tác commit, rollback sau test không dọn được dữ liệu.

Nếu cần timeout cho test transactional, ưu tiên `assertTimeout(...)` không preemptive khi phù hợp; nó thực thi đoạn code trên cùng thread và báo nếu vượt thời gian sau khi hoàn tất. Nếu cần hủy tác vụ thật sự, phải thiết kế transaction và cleanup cho thread thực thi riêng.

### Request đến embedded server

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, test gửi HTTP request đến server đang chạy. Controller xử lý request trên server thread, không phải thread đang giữ transaction test. Do đó, transaction test ở phía client không bao bọc transaction mà controller sử dụng.

Một request POST có thể commit dữ liệu trong server transaction. Khi test method kết thúc, Spring rollback transaction của test thread nhưng dữ liệu đã commit trên server vẫn còn.

Đối với test HTTP server thật, hãy tạo dữ liệu riêng, cleanup rõ ràng hoặc dùng database/container riêng cho test. Không dựa vào `@Transactional` trên test method để tự động rollback thao tác được thực hiện bởi request server.

## 9. Dữ liệu bị rò từ @Commit, @Rollback(false) và transaction độc lập

Các cách sau cố ý thay đổi hành vi rollback mặc định:

```java
@Test
@Commit
void persistsData() {
    // Transaction sẽ commit.
}

@Test
@Rollback(false)
void alsoPersistsData() {
    // Transaction không rollback.
}
```

Đây là lựa chọn hợp lệ khi test cần xác nhận commit hoặc kiểm tra dữ liệu từ transaction khác. Nhưng nếu dùng mà không cleanup, dữ liệu sẽ tồn tại và có thể làm test chạy lại thất bại vì unique key, số lượng record hoặc trạng thái cũ.

Ngoài ra, dữ liệu có thể tồn tại do:

- Một transaction độc lập đã commit, ví dụ `REQUIRES_NEW`.
- Test setup chạy ngoài transaction, chẳng hạn code trong `@BeforeTransaction` ghi dữ liệu.
- SQL script hoặc migration chạy với transaction mode độc lập.
- Tác vụ async ghi dữ liệu trên thread khác.
- Request đến embedded server commit transaction riêng.
- Database sequence hoặc các đối tượng không transactional có trạng thái không rollback theo cách thông thường.

Đừng giả định mọi thay đổi database đều có thể rollback chỉ vì test class có `@Transactional`.

## 10. Database sequence và các side effect ngoài transaction

Rollback database không nhất thiết khôi phục mọi thứ về trạng thái byte-for-byte ban đầu.

Ví dụ, nhiều database dùng sequence hoặc identity generator có bộ đếm không rollback theo transaction. Một test insert rồi rollback vẫn có thể làm ID tiếp theo nhảy số. Test không nên giả định ID tự sinh luôn bắt đầu từ 1 hoặc không có khoảng trống.

Các side effect ngoài transaction cũng không được rollback:

- Gửi email hoặc HTTP request.
- Publish message vào broker nếu message đã được broker nhận và commit.
- Ghi file hoặc object storage.
- Gửi event đến hệ thống ngoài.
- Cập nhật cache hoặc search index bên ngoài transaction database.

Nếu cần kiểm tra các side effect này, dùng fake/mock trong unit test hoặc môi trường tích hợp có khả năng reset dữ liệu. Với message broker/database cần tính nhất quán, kiểm tra cơ chế transactional messaging hoặc outbox riêng; rollback test database không thể thu hồi một message đã được gửi thành công đến broker độc lập.

## 11. Chiến lược cleanup dữ liệu bị rò

Nếu test thực sự cần commit hoặc chạy qua thread/transaction độc lập, hãy chủ động quản lý dữ liệu.

### Dùng dữ liệu riêng cho từng test

Tạo email, mã đơn hàng hoặc correlation key duy nhất để test không xung đột. Lưu lại ID do test tạo và cleanup đúng các record đó.

### Dọn dữ liệu bằng transaction độc lập

Có thể dùng `@AfterTransaction` để xóa dữ liệu đã commit sau khi test transaction kết thúc. Nếu cleanup chạy trong transaction mới, cần bảo đảm nó commit thành công.

### Dùng @Sql cho setup/cleanup

Spring Test hỗ trợ `@Sql` để chạy script trước hoặc sau test. Khi cần script chạy trong transaction độc lập, có thể cấu hình `transactionMode = ISOLATED`:

```java
@Test
@Sql(scripts = "/sql/cleanup-audit.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void verifiesCommittedAuditRecord() {
    // Thực hiện test.
}
```

`ISOLATED` yêu cầu script chạy trong transaction riêng và commit transaction đó. Hãy dùng script cleanup có phạm vi hẹp, dựa trên khóa dữ liệu riêng của test; tránh `DELETE` hoặc `TRUNCATE` toàn bảng nếu database được chia sẻ với test khác.

### Dùng database hoặc schema riêng

Với integration test ghi dữ liệu độc lập, một database/schema riêng cho mỗi test suite hoặc mỗi worker giúp giảm xung đột. Testcontainers có thể khởi chạy database dùng riêng cho suite. Nếu nhiều test chạy song song, vẫn cần dữ liệu riêng hoặc schema riêng ở phạm vi phù hợp.

### Không dùng @DirtiesContext để thay thế cleanup database

`@DirtiesContext` đóng/loại application context khỏi cache; nó không đảm bảo xóa record đã commit trong database dùng chung. Dùng nó cho context bị thay đổi không thể khôi phục, không phải làm sạch dữ liệu persistence.

## 12. Cách kiểm tra một test có thật sự rollback

Để chứng minh dữ liệu đã được rollback, cần quan sát từ một transaction độc lập sau khi test transaction kết thúc.

Một quy trình thực tế:

1. Tạo một bản ghi có khóa duy nhất trong test transaction.
2. Flush để chắc chắn INSERT đã được gửi đến database.
3. Xác nhận bản ghi tồn tại trong transaction hiện tại.
4. Kết thúc transaction bằng rollback mặc định hoặc `TestTransaction.flagForRollback()` và `end()`.
5. Mở transaction mới hoặc truy vấn ngoài transaction test.
6. Xác nhận bản ghi không còn.

Ví dụ với `@AfterTransaction`:

```java
@DataJpaTest
class RollbackBehaviorTest {

    private static final String TEST_EMAIL = "rollback-check@example.test";

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsInsideTransactionBeforeRollback() {
        repository.save(new Customer(TEST_EMAIL));
        entityManager.flush();

        assertThat(repository.findByEmail(TEST_EMAIL)).isPresent();
    }

    @AfterTransaction
    void verifiesRecordWasRolledBack() {
        assertThat(repository.findByEmail(TEST_EMAIL)).isEmpty();
    }
}
```

Ví dụ giả định repository có `findByEmail` và database schema đã được chuẩn bị. Truy vấn trong `@AfterTransaction` chạy sau khi test transaction đã kết thúc; Spring Data có thể mở transaction đọc phù hợp hoặc chạy theo cấu hình transaction hiện tại của test infrastructure. Nếu repository method yêu cầu transaction rõ ràng, hãy dùng `TransactionTemplate` để tạo transaction đọc mới.

## 13. Quy trình chẩn đoán lỗi flush và dữ liệu rò

Khi test database chạy xanh nhưng nghi ngờ constraint chưa được kiểm tra hoặc dữ liệu vẫn tồn tại sau test, thực hiện theo thứ tự:

1. Xác định test có `@Transactional` trực tiếp, qua class hay do test slice cung cấp.
2. Xác định transaction test được commit hay rollback; kiểm tra `@Commit`, `@Rollback(false)` và `TestTransaction`.
3. Tìm các lệnh `save`, `persist`, `merge` chưa flush.
4. Thêm `flush()`/`saveAndFlush()` ở vị trí cần xác nhận SQL và constraint.
5. Nếu cần xác nhận dữ liệu tải lại từ database, flush rồi `clear()` persistence context.
6. Nếu lỗi chỉ xuất hiện ở commit, tạo test commit có cleanup và dùng đúng database hỗ trợ constraint đó.
7. Tìm transaction `REQUIRES_NEW`, `NOT_SUPPORTED` hoặc thao tác chạy ngoài transaction.
8. Tìm thread khác: `@Async`, executor, future, preemptive timeout và request đến server thật.
9. Kiểm tra side effect ngoài database transaction và sequence/identity.
10. Dùng `@AfterTransaction` hoặc transaction độc lập để xác nhận dữ liệu sau khi test kết thúc.
11. Nếu có dữ liệu commit cần giữ trong test, cleanup theo ID/key do test sở hữu hoặc dùng database/schema riêng.

## 14. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Test duplicate key xanh dù dữ liệu vi phạm unique | Chưa flush nên SQL chưa chạy | Dùng `saveAndFlush()` hoặc `EntityManager.flush()` |
| Test đọc lại entity vẫn đúng dù database không có dữ liệu | Persistence context trả object đang quản lý | Flush rồi `clear()` trước khi đọc lại |
| Test rollback nhưng record vẫn còn | Transaction độc lập đã commit hoặc thao tác chạy thread khác | Kiểm tra `REQUIRES_NEW`, async, server thread, preemptive timeout |
| Test chạy lại lỗi unique key | Dữ liệu đã commit từ lần trước | Dùng ID riêng và cleanup sau test |
| Test `@SpringBootTest(RANDOM_PORT)` để lại dữ liệu | Request được xử lý trong server transaction riêng | Cleanup tường minh hoặc database riêng |
| ID tự sinh tăng dù test rollback | Sequence/identity không rollback theo transaction | Không assert ID liên tục hoặc reset sequence trong database test riêng |
| `@DirtiesContext` nhưng dữ liệu vẫn còn | Context cache không phải database cleanup | Dọn database bằng script hoặc transaction phù hợp |
| Test async ghi dữ liệu sau rollback | Worker thread chạy ngoài test transaction | Chờ task hoàn tất, quản lý transaction và cleanup riêng |

## 15. Kết luận

Rollback của Spring Test giúp cô lập dữ liệu chỉ khi thao tác thực sự tham gia test-managed transaction. JPA có thể trì hoãn SQL cho đến flush hoặc commit, vì vậy test cần gọi `flush()`/`saveAndFlush()` khi muốn xác nhận constraint và lỗi database. Flush gửi SQL xuống database nhưng không commit; transaction vẫn có thể rollback sau đó.

Dữ liệu vẫn có thể bị rò nếu thao tác được commit trong `REQUIRES_NEW`, chạy trên thread khác, đi qua embedded server, dùng preemptive timeout hoặc tạo side effect ngoài database transaction. Hãy xác định đúng ranh giới transaction, quan sát dữ liệu sau khi transaction kết thúc, và cleanup theo khóa dữ liệu riêng. Không dựa vào rollback mặc định để che việc SQL chưa từng được thực thi hoặc để hoàn tác những thay đổi nằm ngoài transaction mà Spring Test quản lý.
