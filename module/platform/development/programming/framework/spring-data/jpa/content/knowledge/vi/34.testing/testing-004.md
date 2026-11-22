# Rollback trong kiểm thử và lỗi bị che khuất bởi giao dịch thử nghiệm

Một integration test có thể chạy qua service, repository và database mà vẫn không phát hiện lỗi chỉ xuất hiện tại thời điểm commit. Nguyên nhân thường gặp là Spring TestContext mở một transaction bao quanh test method và mặc định rollback transaction đó khi test kết thúc. Các service dùng propagation `REQUIRED` tham gia transaction của test, nên khi service trả về, transaction thực tế vẫn chưa commit.

Điều này có thể che khuất constraint được kiểm tra tại commit, lỗi chỉ xuất hiện khi transaction hoàn tất, `UnexpectedRollbackException` và listener yêu cầu `AFTER_COMMIT`. Muốn kiểm thử đúng ranh giới transaction, cần phân biệt test-managed transaction với transaction do ứng dụng quản lý, chủ động flush khi cần phát hiện lỗi SQL sớm và thực hiện commit thật khi cần kiểm tra hành vi sau commit.

## 1. Hai loại transaction trong Spring test

### Test-managed transaction

Spring TestContext hỗ trợ transaction cho test thông qua `TransactionalTestExecutionListener`. Khi test class hoặc test method được đánh dấu `@Transactional` và có transaction manager phù hợp, framework bắt đầu một test-managed transaction trước khi test method chạy.

Các đặc điểm thường gặp:

- Transaction được mở trước test method.
- `@BeforeEach`, test method và `@AfterEach` thông thường chạy trong transaction đó.
- Mặc định transaction bị rollback khi test hoàn tất.
- Có thể thay đổi kết quả kết thúc transaction bằng `@Commit`, `@Rollback` hoặc API `TestTransaction`.
- Các callback `@BeforeTransaction` và `@AfterTransaction` chạy bên ngoài test-managed transaction, tương ứng trước khi transaction bắt đầu và sau khi transaction kết thúc.

`@DataJpaTest` mặc định được cấu hình theo hướng transactional và rollback sau mỗi test. `@SpringBootTest` không tự động làm mọi test method có transaction; test chỉ có test-managed transaction khi có cấu hình phù hợp, chẳng hạn `@Transactional` trên class hoặc method.

### Application-managed transaction

Đây là transaction do code ứng dụng mở qua Spring transaction interceptor, thường bằng `@Transactional` trên service method.

```java
@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        // Kiểm tra nghiệp vụ và lưu aggregate.
        orders.save(Order.create(command));
    }
}
```

Nếu test không có transaction bao quanh, lời gọi `createOrder()` đi qua Spring proxy sẽ mở transaction, thực hiện công việc và commit trước khi method trả về thành công. Lỗi xảy ra trong quá trình commit có thể được ném ngay ra caller, vì vậy test có thể dùng `assertThrows` quanh lời gọi service.

Nếu test đã mở transaction và service dùng propagation mặc định `REQUIRED`, service tham gia transaction đang tồn tại. Khi service trả về, nó không commit transaction vật lý vì transaction thuộc test vẫn đang hoạt động.

## 2. Vì sao rollback mặc định có thể che khuất lỗi?

Xét một test kiểu repository:

```java
@DataJpaTest
class UserRepositoryTest {

    @Autowired
    private UserRepository users;

    @Test
    void duplicateEmailShouldFail() {
        users.save(new User("same@example.com"));
        users.save(new User("same@example.com"));

        // Test kết thúc; Spring mặc định rollback test transaction.
    }
}
```

Nếu database chỉ kiểm tra unique constraint khi SQL được gửi hoặc tại thời điểm commit, test trên có thể chưa phát hiện lỗi. JPA có thể giữ thay đổi trong persistence context và trì hoãn SQL cho tới flush hoặc commit. Vì test transaction mặc định rollback, framework có thể kết thúc transaction bằng rollback thay vì commit; lỗi chỉ xuất hiện khi commit sẽ không được quan sát theo cách test mong muốn.

Một tình huống khác là service có transaction lồng theo propagation `REQUIRED`:

1. Test mở transaction.
2. Test gọi service `@Transactional`; service tham gia transaction của test.
3. Service gọi một service con `REQUIRED`.
4. Service con thất bại, interceptor đánh dấu transaction dùng chung là rollback-only.
5. Service cha bắt exception và trả về bình thường.
6. Test assertion có thể vẫn chạy mà chưa có commit ở ranh giới service.
7. Khi test kết thúc, framework rollback test transaction. Không có lần commit của service ngoài cùng để ném `UnexpectedRollbackException` tại vị trí test đang quan sát.

Đây là lý do một test có thể xanh dù cùng lời gọi service trong production sẽ ném exception khi transaction của service cố commit.

## 3. Phân biệt flush và commit

`flush()` và `commit()` là hai thời điểm khác nhau.

| Thao tác | Điều gì xảy ra? | Có kết thúc transaction? |
|---|---|---|
| `EntityManager.flush()` | Đồng bộ các thay đổi đang chờ thành SQL trong transaction hiện tại | Không |
| `EntityTransaction.commit()` / transaction manager commit | Hoàn tất transaction; provider đồng bộ thay đổi còn lại trước khi database commit | Có |
| Rollback | Hủy các thay đổi thuộc transaction theo cơ chế database | Có |

### Flush giúp phát hiện nhiều lỗi sớm

Trong test JPA, gọi flush sau thao tác persist/update có thể làm SQL được thực thi ngay, từ đó phát hiện các lỗi như:

- Unique constraint violation.
- NOT NULL hoặc foreign key constraint violation.
- Lỗi SQL hoặc kiểu dữ liệu.
- Optimistic locking failure khi câu lệnh update được thực thi.

Ví dụ với `TestEntityManager`:

```java
@DataJpaTest
class UserRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private UserRepository users;

    @Test
    void duplicateEmailViolatesUniqueConstraint() {
        users.save(new User("same@example.com"));
        users.save(new User("same@example.com"));

        assertThrows(
            RuntimeException.class,
            () -> entityManager.flush()
        );
    }
}
```

Đây là ví dụ minh họa vị trí kiểm tra lỗi. Trong test thực tế, hãy dùng exception cụ thể mà database/provider và lớp exception translation của ứng dụng trả về, chẳng hạn exception constraint violation phù hợp. Không nên giữ `RuntimeException` làm kiểu kỳ vọng cuối cùng nếu có thể xác định exception chính xác.

Test vẫn rollback sau khi hoàn tất. Flush chỉ làm SQL chạy sớm để lỗi được phát hiện bên trong test method; nó không kiểm tra được mọi điều kiện chỉ được xác nhận tại commit.

### Flush không phát hiện mọi lỗi commit-time

Một số lỗi chỉ được database kiểm tra khi commit, ví dụ constraint được khai báo deferred. Một số hành vi khác cũng chỉ xảy ra khi transaction hoàn tất:

- Transaction manager phát hiện transaction đã bị đánh dấu rollback-only và ném `UnexpectedRollbackException`.
- `@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ chạy sau commit thành công.
- Transaction synchronization callback ở phase hoàn tất.
- Lỗi hoặc phản hồi từ thao tác commit của database.

Do đó, nếu mục tiêu là kiểm tra commit thật, phải có một transaction thực sự commit.

## 4. Cách 1: Để service tự quản lý transaction

Cách rõ ràng nhất để kiểm tra lỗi ở ranh giới service là không mở test-managed transaction. Gọi một service method có `@Transactional` từ test không transactional.

```java
@SpringBootTest
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Test
    void shouldExposeCommitFailureAtServiceBoundary() {
        assertThrows(
            UnexpectedRollbackException.class,
            () -> orderService.processOrder()
        );
    }
}
```

Trong ví dụ này, test method không có `@Transactional`. Khi `processOrder()` kết thúc, transaction interceptor của service thực hiện commit. Nếu transaction đã rollback-only, `UnexpectedRollbackException` có thể được ném ngay tại lời gọi proxy và được `assertThrows` bắt lại.

Cách này phù hợp để kiểm thử:

- Transaction boundary của service.
- Lỗi khi transaction commit.
- Rollback rule và propagation giữa các service.
- Listener chạy sau commit.
- Hành vi thực tế mà caller của service quan sát được.

Nếu dùng `@DataJpaTest`, test slice thường đã có transaction mặc định. Có thể tách test service transaction sang `@SpringBootTest` không có `@Transactional`, hoặc cấu hình test method không tham gia test-managed transaction bằng propagation được Spring Test hỗ trợ, chẳng hạn `NOT_SUPPORTED`. Cần bảo đảm service được gọi qua Spring proxy.

## 5. Cách 2: Chủ động kết thúc test transaction bằng TestTransaction

Khi cần giữ test-managed transaction cho phần setup hoặc kiểm tra repository, Spring cung cấp `TestTransaction` trong package `org.springframework.test.context.transaction`.

API thường dùng:

- `TestTransaction.isActive()`: kiểm tra test-managed transaction hiện có đang hoạt động.
- `TestTransaction.flagForCommit()`: yêu cầu transaction hiện tại commit khi kết thúc.
- `TestTransaction.flagForRollback()`: yêu cầu transaction hiện tại rollback khi kết thúc.
- `TestTransaction.end()`: kết thúc transaction hiện tại theo cờ đã đặt.
- `TestTransaction.start()`: bắt đầu test-managed transaction mới nếu cấu hình test hỗ trợ.

Ví dụ kiểm tra listener chỉ chạy sau commit:

```java
@SpringBootTest
@Transactional
class OrderAfterCommitTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderEventProbe eventProbe;

    @Test
    void listenerRunsAfterExplicitCommit() {
        orderService.createAndConfirm();

        assertFalse(eventProbe.wasCalled());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertTrue(eventProbe.wasCalled());
    }
}
```

Trong ví dụ, `orderService` tham gia test-managed transaction bằng `REQUIRED`. Listener được cấu hình với `@TransactionalEventListener(AFTER_COMMIT)`, nên chưa chạy trước khi test kết thúc transaction. `TestTransaction.end()` thực hiện commit theo cờ đã đặt; sau khi commit thành công, listener mới được gọi.

Nếu cần kiểm tra exception phát sinh khi commit, có thể đặt assertion quanh `TestTransaction.end()`:

```java
@Test
@Transactional
void commitFailureIsVisibleWhenEndingTestTransaction() {
    service.performOperationThatMarksTransactionRollbackOnly();

    TestTransaction.flagForCommit();

    assertThrows(
        UnexpectedRollbackException.class,
        TestTransaction::end
    );
}
```

Exception cụ thể cần được điều chỉnh theo lỗi và transaction manager thực tế. Khi commit thất bại, transaction test đã được yêu cầu kết thúc; không giả định nó vẫn hoạt động để tiếp tục các thao tác persistence. Hãy kiểm tra trạng thái transaction và dọn dữ liệu bằng một transaction riêng nếu cần.

## 6. Cách 3: Dùng @Commit hoặc @Rollback(false)

Spring TestContext mặc định rollback test-managed transaction. Có thể yêu cầu commit khi test kết thúc:

```java
@SpringBootTest
@Transactional
@Commit
class CommitTest {
    // Test transaction được commit khi kết thúc.
}
```

`@Rollback(false)` cũng có tác dụng yêu cầu commit thay vì rollback:

```java
@Test
@Transactional
@Rollback(false)
void persistsData() {
    repository.save(new User("commit@example.com"));
}
```

Các annotation này hữu ích khi muốn xác nhận dữ liệu thực sự được commit hoặc dùng dữ liệu sau test. Tuy nhiên, commit xảy ra trong giai đoạn teardown sau khi test method đã trả về. Vì vậy, nếu commit phát sinh exception, test method thường không thể đặt `assertThrows` trực tiếp quanh chính thời điểm commit đó.

Khi cần bắt và kiểm tra exception commit trong thân test, dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` để kết thúc transaction ngay tại vị trí có thể assertion.

Không nên dùng `@Commit` một cách tùy tiện vì dữ liệu có thể tồn tại sau test và ảnh hưởng test khác. Dùng database riêng cho test, dữ liệu có khóa duy nhất hoặc cơ chế cleanup tường minh.

## 7. Kiểm tra @TransactionalEventListener và các callback

Một test transaction mặc định rollback không kích hoạt listener `AFTER_COMMIT`. Đây là hành vi đúng: transaction không commit thì listener không được chạy.

Ví dụ listener:

```java
@Component
public class OrderListener {

    private final NotificationService notifications;

    public OrderListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmed event) {
        notifications.send(event.orderId());
    }
}
```

Có thể viết các test riêng:

| Kịch bản | Kỳ vọng |
|---|---|
| Test transaction kết thúc bằng rollback | Listener AFTER_COMMIT không chạy |
| Test transaction được commit | Listener AFTER_COMMIT chạy |
| Listener dùng BEFORE_COMMIT | Chạy trước commit trong transaction |
| Listener dùng AFTER_ROLLBACK | Chạy khi transaction rollback |
| Listener dùng AFTER_COMPLETION | Chạy sau khi transaction kết thúc ở cả hai kết quả |

Nếu muốn kiểm thử listener chạy sau commit trong test-managed transaction, hãy kết thúc transaction rõ ràng bằng `TestTransaction.end()` sau khi gọi `flagForCommit()`.

Lưu ý: `@EventListener` thông thường không chờ commit. Nó được gọi khi event được publish. Vì vậy, một test transaction cuối cùng rollback vẫn có thể đã chạy listener thông thường và thực hiện side effect. Nếu side effect chỉ được phép xảy ra khi commit, dùng `@TransactionalEventListener(AFTER_COMMIT)`.

## 8. @Rollback mặc định và các annotation liên quan

| Annotation/API | Ý nghĩa |
|---|---|
| `@Transactional` trên test | Yêu cầu Spring TestContext quản lý transaction cho test |
| `@Rollback` | Chọn rollback hay commit khi test transaction kết thúc; mặc định là `true` |
| `@Commit` | Tương đương yêu cầu `@Rollback(false)` |
| `@BeforeTransaction` | Chạy trước khi test-managed transaction bắt đầu |
| `@AfterTransaction` | Chạy sau khi test-managed transaction kết thúc |
| `TestTransaction` | Điều khiển transaction của test ngay trong test method |

`@BeforeEach` và `@AfterEach` thông thường chạy bên trong test-managed transaction khi transaction đó được mở. Nếu cần setup/cleanup bên ngoài transaction, dùng các callback transaction-specific như `@BeforeTransaction` và `@AfterTransaction`.

Không phải mọi thuộc tính của `@Transactional` đều được Spring TestContext áp dụng giống application transaction. Các thuộc tính như isolation, timeout và readOnly không được hỗ trợ đầy đủ cho test-managed transaction; hãy tham khảo tài liệu phiên bản Spring đang dùng khi cần cấu hình đặc biệt. Propagation `NOT_SUPPORTED` hoặc `NEVER` có thể dùng để yêu cầu test không chạy trong test-managed transaction.

## 9. Propagation và lỗi UnexpectedRollbackException trong test

Propagation mặc định của `@Transactional` là `REQUIRED`. Nếu test đã mở transaction, service và các repository thường tham gia transaction đó.

Giả sử service con ném unchecked exception và transaction interceptor đánh dấu transaction dùng chung là rollback-only. Service cha bắt exception và tiếp tục. Trong production, nếu service cha là chủ sở hữu transaction, khi nó kết thúc Spring thử commit và có thể ném `UnexpectedRollbackException`.

Nhưng trong test có transaction bao ngoài:

- Service cha tham gia transaction của test.
- Khi service cha trả về, transaction vật lý vẫn thuộc test.
- Test transaction mặc định rollback ở teardown.
- Exception tại ranh giới commit có thể không xuất hiện trong lời gọi service.

Để kiểm tra đúng lỗi này, dùng test không transactional gọi service qua proxy:

```java
@SpringBootTest
class UnexpectedRollbackIntegrationTest {

    @Autowired
    private ParentService parentService;

    @Test
    void exposesUnexpectedRollbackAtServiceCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            parentService::execute
        );
    }
}
```

Đảm bảo test không có `@Transactional` ở class hoặc method. Nếu dùng test slice có transaction mặc định, cấu hình lại transaction của test hoặc dùng `TestTransaction` để kết thúc transaction một cách tường minh.

### Cẩn trọng với REQUIRES_NEW

Một service con dùng `Propagation.REQUIRES_NEW` tạo transaction riêng. Transaction con có thể commit ngay cả khi test transaction bên ngoài cuối cùng rollback. Vì vậy, test mặc định rollback không bảo đảm dọn dữ liệu được ghi bởi transaction độc lập.

Nếu test có `REQUIRES_NEW`, cần kiểm soát dữ liệu bằng database cô lập, ID duy nhất và cleanup riêng. Đừng giả định rollback của test sẽ rollback mọi transaction được mở trong quá trình test.

## 10. Kiểm thử ràng buộc database và lỗi chỉ xảy ra khi commit

Khi test cần kiểm tra constraint:

1. Persist hoặc update entity.
2. Gọi `flush()` để buộc SQL được gửi xuống database.
3. Assertion exception tại flush nếu constraint được kiểm tra khi thực thi SQL.
4. Nếu constraint được kiểm tra deferred tại commit, hãy thực hiện commit thật và bắt lỗi tại ranh giới commit.
5. Kiểm tra trạng thái database sau khi transaction thất bại bằng transaction/context mới nếu cần.

Ví dụ kiểm tra unique constraint ở thời điểm flush:

```java
@DataJpaTest
class UserConstraintTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void duplicateEmailFailsWhenFlushed() {
        entityManager.persist(new User("duplicate@example.com"));
        entityManager.persist(new User("duplicate@example.com"));

        assertThrows(
            RuntimeException.class,
            () -> entityManager.flush()
        );
    }
}
```

Đây là khung minh họa. Trong dự án thật, thay `RuntimeException` bằng exception cụ thể do provider và lớp exception translation trả về. Test transaction sẽ được rollback sau test.

Nếu muốn kiểm tra lỗi chỉ xuất hiện ở commit, không thể thay commit bằng flush. Hãy dùng test không có transaction bao ngoài để service tự commit, hoặc dùng `TestTransaction.end()` sau `flagForCommit()`.

## 11. Cleanup và tính cô lập giữa các test

Rollback mặc định giúp test dữ liệu sạch mà không cần xóa từng bản ghi, nhưng chỉ có tác dụng với dữ liệu thuộc chính transaction test.

Một số thao tác không được rollback cùng test transaction:

- Transaction độc lập từ `REQUIRES_NEW`.
- Giao dịch được thực hiện trên thread khác.
- Gửi email, gọi HTTP, ghi file hoặc side effect bên ngoài database.
- Dữ liệu được ghi bởi hệ thống khác trong quá trình test.

Với các test commit thật hoặc có side effect, hãy:

- Dùng database riêng hoặc schema/container dùng riêng cho test suite.
- Tạo dữ liệu có định danh duy nhất để tránh đụng dữ liệu test khác.
- Dọn dữ liệu trong transaction riêng hoặc reset database sau test.
- Dùng fake/mock cho hệ thống ngoài nếu mục tiêu test chỉ là logic ứng dụng.
- Không phụ thuộc vào thứ tự thực thi test.

`@Sql` có thể dùng để chạy script setup/cleanup; cần chọn execution phase và transaction mode phù hợp để cleanup được thực thi ngoài transaction đã rollback hoặc commit.

## 12. Checklist chọn cách kiểm thử

| Mục tiêu kiểm thử | Cách phù hợp |
|---|---|
| Kiểm tra repository persist/query cơ bản | `@DataJpaTest` với rollback mặc định |
| Phát hiện SQL constraint được kiểm tra khi flush | Gọi `TestEntityManager.flush()` hoặc `EntityManager.flush()` |
| Bắt lỗi ở commit của service | Test không có `@Transactional` bao ngoài, gọi service proxy |
| Kiểm tra listener AFTER_COMMIT | Commit test transaction bằng `TestTransaction` hoặc gọi service từ test không transactional |
| Kiểm tra listener không chạy khi rollback | Giữ rollback mặc định và xác nhận listener không nhận event |
| Kiểm tra transaction bị rollback-only | Gọi service ở ranh giới transaction thực và assertion `UnexpectedRollbackException` |
| Test có REQUIRES_NEW | Dùng database cô lập và cleanup riêng |
| Kiểm tra constraint deferred | Commit transaction thật, không chỉ flush |

## 13. Quy trình điều tra test xanh nhưng production lỗi

Khi test pass nhưng production gặp lỗi ở commit:

1. Kiểm tra test class/method có `@Transactional`, hoặc test slice có transaction mặc định như `@DataJpaTest`, hay không.
2. Xác định service có propagation `REQUIRED` và đang tham gia transaction của test hay không.
3. Tìm các thao tác chỉ được đồng bộ khi flush/commit, chẳng hạn unique constraint, foreign key, optimistic locking hoặc transaction synchronization.
4. Thử flush tường minh để phát hiện lỗi SQL sớm.
5. Nếu lỗi vẫn chỉ xảy ra tại commit, chạy test không có transaction bao ngoài hoặc kết thúc test transaction bằng `TestTransaction`.
6. Kiểm tra listener có đang dùng `@EventListener` trong khi nghiệp vụ yêu cầu `AFTER_COMMIT` hay không.
7. Xem xét các transaction độc lập và side effect ngoài database; rollback mặc định không tự dọn chúng.

## Kết luận

Test-managed transaction của Spring TestContext mặc định rollback sau test. Khi service dùng `REQUIRED`, service có thể chỉ tham gia transaction của test và không thực sự commit tại ranh giới service. Vì vậy, lỗi commit-time, `UnexpectedRollbackException` và listener `AFTER_COMMIT` có thể bị che khuất.

Dùng flush để phát hiện sớm lỗi SQL có thể xảy ra khi thực thi câu lệnh; dùng test không transactional hoặc `TestTransaction` để kiểm tra commit thật. Chọn `@Commit` khi muốn commit ở teardown và nhớ cleanup dữ liệu. Luôn thiết kế test theo đúng ranh giới transaction mà ứng dụng chạy trong production.
