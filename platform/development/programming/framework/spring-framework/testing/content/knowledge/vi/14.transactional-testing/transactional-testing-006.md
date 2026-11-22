# Các thuộc tính @Transactional được hỗ trợ trong test-managed transaction

Spring TestContext Framework có thể mở một transaction bao quanh mỗi test method để các thay đổi dữ liệu được hoàn tác sau khi test kết thúc. Cơ chế này được gọi là **test-managed transaction** và thường được kích hoạt bằng annotation **@Transactional** trên test class hoặc test method.

Tuy nhiên, **@Transactional** trong test không áp dụng toàn bộ ngữ nghĩa như khi annotation được đặt trên service của ứng dụng. Spring Test chỉ hỗ trợ một tập thuộc tính cụ thể để điều khiển test-managed transaction. Một số thuộc tính quen thuộc như **isolation**, **timeout**, **readOnly** và các quy tắc **rollbackFor**/**noRollbackFor** không được áp dụng theo cách thông thường trong trường hợp này.

Hiểu chính xác thuộc tính nào có hiệu lực giúp tránh một bài test tưởng rằng đã chạy ở mức isolation hoặc timeout mong muốn, hoặc nghĩ rằng transaction sẽ commit/rollback theo loại exception trong khi Spring Test không sử dụng những quy tắc đó.

## 1. Test-managed transaction là gì?

Spring TestContext Framework sử dụng **TransactionalTestExecutionListener** để quản lý transaction cho test. Listener này được đăng ký mặc định trong cấu hình TestContext tiêu chuẩn, kể cả khi test class không tự khai báo **@TestExecutionListeners**.

Để kích hoạt transaction test, cần có hai điều kiện:

1. ApplicationContext của test có một bean triển khai **PlatformTransactionManager**.
2. Test class hoặc test method được đánh dấu **org.springframework.transaction.annotation.Transactional**.

Ví dụ:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.save(new Customer("CUS-01", "Lan"));

        assertTrue(repository.findById("CUS-01").isPresent());
    }
}
~~~

Spring bắt đầu transaction trước khi test method chạy. Theo mặc định, transaction được rollback khi test kết thúc, kể cả khi test thành công. Nhờ đó, dữ liệu do test tạo ra không còn trong database sau khi transaction kết thúc.

Cần phân biệt ba loại transaction:

| Loại | Ai quản lý? | Ví dụ |
|---|---|---|
| Test-managed transaction | Spring TestContext qua TransactionalTestExecutionListener hoặc TestTransaction | Transaction bao quanh test method |
| Spring-managed transaction | Spring transaction infrastructure trong ApplicationContext | @Transactional trên service/repository |
| Application-managed transaction | Code ứng dụng tự quản lý bằng API transaction | Code gọi TransactionTemplate hoặc API transaction trực tiếp |

Transaction do service tạo thường tham gia test-managed transaction nếu propagation phù hợp, phổ biến nhất là **REQUIRED** hoặc **SUPPORTS**. Cần thận trọng với các propagation khác vì chúng có thể tạo transaction độc lập hoặc tạm ngưng transaction của test.

## 2. Bảng thuộc tính @Transactional được hỗ trợ

Spring TestContext Framework công bố phạm vi hỗ trợ riêng cho test-managed transaction:

| Thuộc tính @Transactional | Hỗ trợ trong test-managed transaction | Cách hiểu |
|---|---|---|
| value và transactionManager | Có | Chọn transaction manager theo qualifier hoặc tên bean |
| propagation | Chỉ nhận diện NOT_SUPPORTED và NEVER | Hai giá trị này yêu cầu test chạy ngoài transaction |
| isolation | Không | Không dùng để đặt isolation level cho transaction test |
| timeout | Không | Không dùng để đặt timeout cho transaction test |
| readOnly | Không | Không dùng để cấu hình transaction test ở chế độ chỉ đọc |
| rollbackFor và rollbackForClassName | Không | Dùng TestTransaction.flagForRollback() khi cần điều khiển rollback bằng code |
| noRollbackFor và noRollbackForClassName | Không | Dùng TestTransaction.flagForCommit() khi cần điều khiển commit bằng code |

Bảng này nói về annotation **@Transactional** trên test class hoặc test method, tức transaction do Spring Test quản lý. Nó không có nghĩa các thuộc tính tương ứng mất tác dụng trong transaction do service của ứng dụng quản lý.

Ví dụ, **@Transactional(readOnly = true)** trên service vẫn có ý nghĩa theo transaction infrastructure của ứng dụng. Nhưng nếu đặt **readOnly = true** trên test method để yêu cầu test-managed transaction chỉ đọc, Spring Test không hỗ trợ thuộc tính đó.

## 3. value và transactionManager: chọn transaction manager

Hai thuộc tính **value** và **transactionManager** là alias của nhau trong **@Transactional**. Chúng cho phép chỉ định transaction manager cần dùng cho test.

Nếu ApplicationContext chỉ có một bean **PlatformTransactionManager** phù hợp, Spring Test thường có thể tìm và sử dụng bean đó theo quy tắc mặc định.

Nếu có nhiều transaction manager, cần chỉ rõ bean:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfiguration.class)
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // Test dùng transaction manager của database đơn hàng.
}
~~~

Hoặc viết tường minh:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
}
~~~

Tên được truyền vào là qualifier hoặc tên bean mà Spring dùng để tìm transaction manager phù hợp. Cách khai báo này hữu ích khi ứng dụng có nhiều database, chẳng hạn:

- ordersTransactionManager quản lý database đơn hàng.
- billingTransactionManager quản lý database thanh toán.
- auditTransactionManager quản lý database kiểm toán.

Test cần rollback dữ liệu ở database nào thì phải dùng đúng transaction manager quản lý tài nguyên đó. Chọn nhầm manager có thể khiến test không được rollback ở database mà repository thực sự sử dụng.

### Chọn transaction manager qua cấu hình chung

Nếu ứng dụng có nhiều PlatformTransactionManager và muốn xác định một manager mặc định, cấu hình có thể triển khai TransactionManagementConfigurer:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfiguration
        implements TransactionManagementConfigurer {

    private final PlatformTransactionManager transactionManager;

    TransactionConfiguration(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager
    ) {
        this.transactionManager = transactionManager;
    }

    @Override
    public PlatformTransactionManager annotationDrivenTransactionManager() {
        return transactionManager;
    }
}
~~~

Đây là cơ chế cấu hình chung cho transaction annotation. Với test cần dùng manager khác manager mặc định, khai báo **@Transactional(transactionManager = "...")** trên test thường rõ ràng hơn.

## 4. propagation: hai giá trị đặc biệt được hỗ trợ

Trong test-managed transaction, Spring Test chỉ hỗ trợ hai giá trị propagation để xác định test không chạy trong transaction:

- **Propagation.NOT_SUPPORTED**
- **Propagation.NEVER**

Hai giá trị này có ý nghĩa là test không được thực thi trong test-managed transaction.

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
class TransactionBoundaryTest {

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void runsWithoutTestManagedTransaction() {
        assertFalse(TestTransaction.isActive());
    }

    @Test
    @Transactional(propagation = Propagation.NEVER)
    void alsoRunsWithoutTestManagedTransaction() {
        assertFalse(TestTransaction.isActive());
    }
}
~~~

Có thể dùng các chế độ này khi test cần quan sát hành vi xảy ra ngoài transaction, hoặc cần kiểm tra dữ liệu đã commit từ một transaction khác.

Các propagation khác không phải cách cấu hình transaction test-managed. Đừng dùng **REQUIRES_NEW**, **MANDATORY**, **NESTED** hoặc **SUPPORTS** trên annotation của test với kỳ vọng Spring Test sẽ mở test transaction theo semantics của chúng.

Cần phân biệt điều đó với propagation trên service của ứng dụng. Một service dùng **@Transactional(propagation = REQUIRED)** thường tham gia transaction của test. Nếu service dùng **REQUIRES_NEW**, nó có thể tạm ngưng transaction test, chạy transaction độc lập và commit dữ liệu riêng. Dữ liệu đã commit trong transaction độc lập có thể vẫn còn sau khi transaction test rollback.

## 5. isolation, timeout và readOnly không được áp dụng cho test-managed transaction

Đây là nhóm thuộc tính dễ gây hiểu nhầm vì chúng là các thuộc tính hợp lệ của **@Transactional** trong ứng dụng.

### isolation

Trong transaction của service, isolation level mô tả mức độ cô lập giữa các transaction đồng thời. Ví dụ:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateInventory() {
    // Logic cập nhật tồn kho.
}
~~~

Khi đặt thuộc tính này trên service, transaction manager có thể sử dụng isolation level tương ứng khi tạo transaction mới, tùy khả năng của nền tảng dữ liệu và cấu hình.

Nhưng trên test method:

~~~java
@Test
@Transactional(isolation = Isolation.SERIALIZABLE)
void checksInventory() {
    // Không thể dựa vào annotation này để yêu cầu
    // test-managed transaction dùng SERIALIZABLE.
}
~~~

Spring Test không hỗ trợ **isolation** cho test-managed transaction. Nếu cần kiểm tra isolation, hãy thiết kế một bài kiểm thử transaction chuyên biệt dùng **TransactionTemplate** hoặc service transaction thực sự, tạo các transaction độc lập và xác nhận hành vi đồng thời trên database phù hợp.

### timeout

**timeout** trên transaction của ứng dụng là giới hạn thời gian mà transaction manager có thể áp dụng cho transaction. Tuy nhiên, thuộc tính này không được hỗ trợ trong test-managed transaction.

~~~java
@Test
@Transactional(timeout = 5)
void checksDatabaseOperation() {
    // Không được giả định transaction test sẽ có timeout 5 giây.
}
~~~

Nếu cần giới hạn thời gian chạy test, dùng timeout của framework kiểm thử theo cách phù hợp. Cần lưu ý timeout kiểu preemptive có thể chạy test method trong thread khác và làm mất liên kết với test-managed transaction; vấn đề này được giải thích ở phần sau.

### readOnly

**readOnly** có thể là gợi ý hoặc cấu hình cho transaction manager khi chạy transaction của ứng dụng:

~~~java
@Transactional(readOnly = true)
public List<Customer> findCustomers() {
    return repository.findAll();
}
~~~

Nhưng **readOnly = true** trên test method không biến test-managed transaction thành transaction chỉ đọc.

~~~java
@Test
@Transactional(readOnly = true)
void readsCustomers() {
    // Không dựa vào readOnly của annotation test để chặn ghi dữ liệu.
}
~~~

Nếu test phải bảo đảm code không ghi dữ liệu, hãy kiểm tra hành vi bằng quyền database, cấu hình transaction phù hợp hoặc assertion về trạng thái dữ liệu. Annotation trên test không cung cấp bảo đảm read-only trong test-managed transaction.

## 6. rollbackFor và noRollbackFor không được hỗ trợ

Trong transaction của ứng dụng, các thuộc tính rollback rule xác định exception nào làm transaction rollback hoặc vẫn commit.

Ví dụ trên service:

~~~java
@Transactional(rollbackFor = BusinessException.class)
public void processPayment() throws BusinessException {
    // ...
}
~~~

Hoặc:

~~~java
@Transactional(noRollbackFor = NotificationException.class)
public void completeOrder() {
    // ...
}
~~~

Những quy tắc này thuộc transaction do ứng dụng quản lý. Khi đặt trên test method để điều khiển test-managed transaction, Spring Test không hỗ trợ chúng:

~~~java
@Test
@Transactional(rollbackFor = IllegalArgumentException.class)
void testRollbackRule() {
    // rollbackFor trên annotation test không điều khiển
    // kết quả kết thúc test-managed transaction.
}
~~~

Để điều khiển kết quả của test-managed transaction, có hai lựa chọn chính:

- **@Rollback** hoặc **@Commit** để khai báo hành vi kết thúc.
- **TestTransaction.flagForRollback()** hoặc **TestTransaction.flagForCommit()** để quyết định bằng code.

### Dùng @Rollback

Mặc định, test-managed transaction được rollback. Có thể khai báo rõ:

~~~java
@Test
@Transactional
@Rollback
void rollsBackChanges() {
    repository.save(new Customer("CUS-02", "Minh"));
}
~~~

**@Rollback** cũng nhận boolean:

~~~java
@Test
@Transactional
@Rollback(false)
void commitsChanges() {
    repository.save(new Customer("CUS-03", "An"));
}
~~~

**@Rollback(false)** yêu cầu commit khi test kết thúc bình thường theo lifecycle transaction.

### Dùng @Commit

**@Commit** là cách diễn đạt rõ ý định commit:

~~~java
@Test
@Transactional
@Commit
void commitsCustomer() {
    repository.save(new Customer("CUS-04", "Hoa"));
}
~~~

Có thể đặt **@Rollback** hoặc **@Commit** ở cấp class để làm mặc định cho các test method. Annotation ở cấp method có thể ghi đè lựa chọn ở cấp class.

Chỉ commit trong test khi dữ liệu cần tồn tại sau test, chẳng hạn một bài kiểm tra cần xác nhận trạng thái đã commit ở giai đoạn sau. Test commit dữ liệu phải có chiến lược dọn dẹp riêng để không ảnh hưởng test khác hoặc môi trường dùng chung.

## 7. Dùng TestTransaction để điều khiển transaction bằng code

**TestTransaction** cung cấp API tĩnh để tương tác với test-managed transaction. API này sẵn sàng khi **TransactionalTestExecutionListener** được bật.

Các thao tác thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| isActive() | Kiểm tra test-managed transaction hiện tại có đang hoạt động không |
| flagForRollback() | Đánh dấu transaction hiện tại sẽ rollback khi kết thúc |
| flagForCommit() | Đánh dấu transaction hiện tại sẽ commit khi kết thúc |
| end() | Kết thúc transaction hiện tại theo cờ commit/rollback |
| start() | Bắt đầu test-managed transaction mới |
| isFlaggedForRollback() | Kiểm tra transaction hiện tại đang được đánh dấu rollback hay không |

Ví dụ, kết thúc transaction đầu bằng commit rồi bắt đầu transaction mới:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerTransactionTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsOnePhaseAndRollsBackTheNext() {
        repository.save(new Customer("CUS-10", "Mai"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(repository.findById("CUS-10").isPresent());

        TestTransaction.start();

        repository.save(new Customer("CUS-11", "Nam"));

        // Transaction mới sẽ rollback theo mặc định
        // khi test hoàn tất nếu không đổi cờ.
    }
}
~~~

**TestTransaction.end()** hoàn tất transaction hiện tại. Sau khi kết thúc, có thể kiểm tra trạng thái đã commit bằng một truy vấn phù hợp rồi gọi **start()** để mở transaction mới cho phần còn lại của test.

Cần bảo đảm truy vấn xác nhận trạng thái commit thực sự quan sát database sau commit, không chỉ đọc entity còn nằm trong persistence context cũ. Với JPA, có thể cần flush/clear hoặc dùng một kết nối/transaction đọc mới tùy mục tiêu.

### Khi nào dùng TestTransaction thay vì @Commit?

Dùng **@Commit** khi toàn bộ test cần commit khi kết thúc. Dùng **TestTransaction** khi test cần nhiều giai đoạn, ví dụ:

1. Tạo dữ liệu trong transaction đầu.
2. Commit transaction đầu để dữ liệu trở nên bền vững.
3. Bắt đầu transaction thứ hai.
4. Kiểm tra một hành vi tiếp theo.
5. Rollback transaction thứ hai khi test kết thúc.

Cách này hữu ích khi kiểm tra logic phụ thuộc vào dữ liệu đã commit hoặc một tiến trình khác chỉ nhìn thấy dữ liệu sau commit.

## 8. Chọn đúng transaction manager khi có nhiều database

Một ApplicationContext có thể chứa nhiều **PlatformTransactionManager**. Ví dụ ứng dụng có database đơn hàng và database báo cáo.

~~~java
@Configuration
class MultiDatabaseConfiguration {

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    PlatformTransactionManager reportsTransactionManager(
            @Qualifier("reportsDataSource") DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Test repository đơn hàng cần chọn đúng manager:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
    // Các thay đổi trên orders database thuộc transaction test.
}
~~~

Nếu test chọn **reportsTransactionManager** nhưng repository lại sử dụng **ordersDataSource**, thay đổi trên orders database không nằm trong transaction được test quản lý. Rollback của manager reports không thể hoàn tác dữ liệu ở database orders.

Khi nhiều manager cùng tồn tại, hãy xác định rõ:

- Repository sử dụng DataSource nào.
- Transaction manager nào quản lý DataSource đó.
- Test đang khai báo manager nào.
- Có service nào mở transaction độc lập trên manager khác hay không.

Một test dùng nhiều database không mặc nhiên có một transaction toàn cục bao trùm tất cả tài nguyên. Nếu ứng dụng không dùng distributed transaction, rollback của một manager chỉ điều khiển tài nguyên thuộc manager đó.

## 9. Lifecycle method nào chạy trong transaction?

Với một test method được quản lý transaction, thời điểm bắt đầu và kết thúc transaction ảnh hưởng đến setup và cleanup.

| Callback | Có nằm trong test-managed transaction? |
|---|---|
| @BeforeTransaction | Không, chạy trước khi transaction bắt đầu |
| JUnit Jupiter @BeforeEach | Có |
| Test method có @Transactional | Có |
| JUnit Jupiter @AfterEach | Có |
| @AfterTransaction | Không, chạy sau khi transaction kết thúc |
| JUnit Jupiter @BeforeAll | Không |
| JUnit Jupiter @AfterAll | Không |

**@Transactional** không được hỗ trợ trên các lifecycle method như **@BeforeAll**, **@BeforeEach**, **@AfterEach** hoặc **@AfterAll**. Hãy đặt annotation ở cấp test class hoặc test method để Spring Test quản lý transaction.

### @BeforeEach và @AfterEach

Các method **@BeforeEach** và **@AfterEach** chạy trong test-managed transaction của test method tương ứng.

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(new Customer("CUS-20", "Test"));
    }

    @Test
    void findsPreparedCustomer() {
        assertTrue(repository.findById("CUS-20").isPresent());
    }

    @AfterEach
    void verifyBeforeRollback() {
        assertEquals(1, repository.count());
    }
}
~~~

Dữ liệu được tạo trong setup và kiểm tra trong test đều thuộc transaction test. Sau khi test hoàn tất, transaction rollback theo mặc định.

### @BeforeTransaction và @AfterTransaction

Nếu cần kiểm tra trạng thái database trước khi transaction bắt đầu hoặc sau khi nó kết thúc, dùng hai annotation này:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerCommitTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById("CUS-30"));
    }

    @Test
    @Commit
    void commitsCustomer() {
        repository.save(new Customer("CUS-30", "Linh"));
    }

    @AfterTransaction
    void verifyCommittedState() {
        assertTrue(repository.existsById("CUS-30"));
    }
}
~~~

**@BeforeTransaction** và **@AfterTransaction** chỉ chạy cho test method có test-managed transaction. Chúng là vị trí phù hợp để kiểm tra trạng thái bên ngoài transaction test.

Với JUnit Jupiter và SpringExtension, các method này có thể nhận tham số được một JUnit ParameterResolver cung cấp, chẳng hạn bean có **@Autowired**. Trong ví dụ đơn giản, có thể dùng field đã inject.

### @BeforeAll và @AfterAll

Lifecycle cấp class chạy ngoài test-managed transaction. Nếu cần thực hiện thao tác transaction trong các method này, có thể inject **PlatformTransactionManager** và dùng **TransactionTemplate**:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
class DatabaseSuiteSetup {

    @Autowired
    private PlatformTransactionManager transactionManager;

    void performTransactionalSetup() {
        new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> {
                    // Thao tác dữ liệu trong transaction riêng.
                });
    }
}
~~~

Nếu dùng static **@BeforeAll**, method không thể truy cập trực tiếp instance field theo lifecycle mặc định. Có thể dùng JUnit lifecycle PER_CLASS hoặc một cách cấu hình phù hợp. Điểm chính là transaction cấp class phải được quản lý tường minh bằng API như **TransactionTemplate**.

## 10. Vì sao preemptive timeout có thể làm dữ liệu không rollback?

Spring Test gắn trạng thái test-managed transaction với thread hiện tại bằng **ThreadLocal**. Vì vậy, mọi thao tác database trong test method cần chạy trên thread đang giữ transaction đó.

Một số API timeout có thể chạy đoạn code được kiểm tra trong thread khác, ví dụ JUnit Jupiter:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> service.updateCustomer(customer)
);
~~~

Nếu callback được chạy trong thread mới, thread đó không có transaction context mà Spring Test đã gắn cho thread test ban đầu. Giao dịch database có thể được mở và commit độc lập theo cấu hình thông thường. Sau đó, Spring rollback transaction gắn với thread gốc nhưng dữ liệu do thread mới ghi vẫn còn.

Các trường hợp cần thận trọng gồm:

- JUnit Jupiter assertTimeoutPreemptively(...).
- JUnit 4 @Test(timeout = ...) và TimeOut rule.
- TestNG @Test(timeOut = ...).

Khi test phụ thuộc rollback tự động, hãy dùng timeout không preemptive nếu phù hợp với framework, hoặc kiểm tra và dọn dữ liệu theo cách tường minh. Đừng cho rằng rollback của Spring Test có thể hoàn tác mọi thao tác được thực hiện trên thread khác.

## 11. ORM có thể chưa gửi SQL dù test đã gọi save

Khi dùng JPA hoặc Hibernate, thao tác save có thể chỉ thay đổi persistence context trong bộ nhớ. SQL thật có thể được gửi khi flush hoặc khi transaction commit.

Vì test-managed transaction thường rollback ở cuối test, một số lỗi chỉ xuất hiện lúc flush có thể không được phát hiện nếu test chỉ gọi save rồi kết thúc.

Ví dụ:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void detectsConstraintViolationDuringFlush() {
        repository.save(new Customer("CUS-40", "Lan"));
        repository.save(new Customer("CUS-40", "Duplicate"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> entityManager.flush()
        );
    }
}
~~~

Ví dụ minh họa việc flush để lỗi constraint xuất hiện trong lúc test đang chạy. Loại exception thực tế phụ thuộc JPA provider, database và lớp dịch exception của Spring.

Có thể dùng **entityManager.flush()** hoặc **sessionFactory.getCurrentSession().flush()** để buộc ORM gửi SQL. Nếu cần xác nhận việc đọc lại từ database thay vì persistence context, có thể gọi **entityManager.clear()** sau flush rồi truy vấn lại.

Flush không phải commit. Dữ liệu vẫn nằm trong transaction hiện tại và có thể rollback khi test kết thúc.

Với entity lifecycle callback, flush cũng quan trọng. Một số callback như **@PostPersist**, **@PreUpdate** hoặc **@PostUpdate** chỉ được gọi khi persistence context được flush. Nếu cần kiểm tra callback đọc dữ liệu lại, đôi khi cần clear persistence context để tránh lấy lại entity đang được quản lý trong bộ nhớ.

## 12. Transaction của service có thể thoát khỏi transaction test

Mặc định, transaction của service với propagation **REQUIRED** thường tham gia transaction test hiện tại. Khi test kết thúc và rollback, các thay đổi trong transaction chung cũng rollback.

Nhưng nếu service dùng propagation tạo transaction riêng, hành vi sẽ khác.

Ví dụ:

~~~java
@Service
class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String action) {
        // Ghi audit trong transaction độc lập.
    }
}
~~~

Nếu test gọi record() trong lúc test-managed transaction đang hoạt động, Spring có thể tạm ngưng transaction test, mở transaction mới cho AuditService và commit transaction đó khi method hoàn tất. Sau đó transaction test tiếp tục. Khi test rollback, bản ghi audit đã commit trong transaction độc lập có thể vẫn tồn tại.

Điều này không phải lỗi của rollback. Đó là kết quả của ranh giới transaction khác nhau.

Tương tự, một lời gọi HTTP tới server chạy ở process/thread khác hoặc một message đã publish ra broker không tự được rollback cùng database transaction của test.

Khi kiểm thử các hành vi này, cần xác định rõ transaction nào đang quản lý tài nguyên và side effect nào cần cleanup. Có thể dùng database test riêng, namespace riêng hoặc xóa dữ liệu được tạo sau test.

## 13. Ví dụ tổng hợp: chọn manager, commit và kiểm tra ngoài transaction

Ví dụ sau minh họa nhiều thuộc tính và callback thường dùng:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional(transactionManager = "ordersTransactionManager")
@Commit
class OrderTransactionTest {

    @Autowired
    private OrderRepository repository;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById("ORD-50"));
    }

    @BeforeEach
    void prepare() {
        // Setup này chạy trong test-managed transaction.
    }

    @Test
    @Rollback
    void rollsBackThisTestDespiteClassLevelCommit() {
        repository.save(new Order("ORD-50"));
        assertTrue(repository.existsById("ORD-50"));
    }

    @Test
    void commitsByClassDefault() {
        repository.save(new Order("ORD-51"));
    }

    @AfterEach
    void verifyWithinTransaction() {
        // Có thể đọc dữ liệu trong transaction hiện tại.
    }

    @AfterTransaction
    void verifyAfterCompletion() {
        assertTrue(repository.existsById("ORD-51"));
        assertFalse(repository.existsById("ORD-50"));
    }
}
~~~

Class-level **@Commit** đặt mặc định commit cho test method. Method đầu tiên dùng **@Rollback** để ghi đè và rollback. Method thứ hai dùng mặc định class-level và commit. **@BeforeTransaction** chạy trước transaction; **@AfterTransaction** chạy sau khi transaction hoàn tất.

Trong thực tế, nếu hai test cùng ghi dữ liệu vào một database, cần bảo đảm chúng độc lập với thứ tự chạy. Ví dụ này tập trung vào semantics của annotation; test suite thực tế nên dùng ID duy nhất hoặc fixture riêng để tránh tranh chấp dữ liệu.

## 14. Những hiểu nhầm thường gặp

### Nghĩ mọi thuộc tính @Transactional đều có hiệu lực trên test

Test-managed transaction chỉ hỗ trợ tập thuộc tính được Spring Test công bố. **isolation**, **timeout**, **readOnly** và rollback rules không được áp dụng theo cách thông thường. Hãy dùng đúng API cho mục tiêu cần kiểm tra.

### Dùng rollbackFor để quyết định kết quả test transaction

**rollbackFor** và **noRollbackFor** không điều khiển test-managed transaction. Dùng **@Rollback**, **@Commit** hoặc **TestTransaction.flagForRollback()**/**flagForCommit()**.

### Đặt @Transactional trên @BeforeEach

Spring Test không hỗ trợ **@Transactional** trên lifecycle method. Đặt annotation ở cấp class hoặc test method. **@BeforeEach** và **@AfterEach** sẽ chạy trong transaction của test method đã được quản lý.

### Chọn sai transaction manager

Nếu có nhiều manager, rollback chỉ áp dụng cho tài nguyên do manager được chọn quản lý. Kiểm tra repository, DataSource và manager tương ứng; dùng **@Transactional("beanName")** khi cần.

### Nghĩ rollback sẽ hoàn tác cả transaction REQUIRES_NEW

Transaction độc lập có thể commit riêng. Rollback của transaction test không tự hoàn tác transaction đã commit độc lập.

### Nghĩ mọi thao tác trong test method đều nằm trong transaction

Transaction test được gắn với thread hiện tại. Code chạy trong thread khác, chẳng hạn callback timeout preemptive hoặc request xử lý trên server thread, có thể nằm ngoài transaction đó.

### Không flush khi kiểm tra JPA/Hibernate

ORM có thể giữ thay đổi trong persistence context. Nếu không flush, test có thể bỏ qua lỗi SQL hoặc constraint chỉ xuất hiện khi gửi câu lệnh tới database.

### Dùng @Commit mà không dọn dữ liệu

Commit khiến dữ liệu tồn tại sau test. Nếu test chạy lại hoặc chạy song song, dữ liệu có thể làm thay đổi kết quả. Dùng dữ liệu duy nhất và cleanup rõ ràng.

## 15. Chọn thuộc tính và API theo mục tiêu kiểm thử

| Mục tiêu | Cách thực hiện |
|---|---|
| Dùng transaction manager mặc định | @Transactional |
| Chọn một trong nhiều transaction manager | @Transactional(transactionManager = "...") |
| Test không cần test-managed transaction | propagation = NOT_SUPPORTED hoặc NEVER |
| Dùng isolation level cụ thể | Kiểm thử transaction của ứng dụng hoặc dùng TransactionTemplate |
| Đặt timeout cho transaction ứng dụng | Cấu hình trên service transaction; không dựa vào test-managed timeout |
| Yêu cầu read-only ở service | Đặt readOnly trên transaction ứng dụng và kiểm tra bằng cơ chế phù hợp |
| Mặc định rollback | @Transactional không kèm @Commit hoặc @Rollback(false) |
| Commit test | @Commit hoặc @Rollback(false) |
| Quyết định commit/rollback trong lúc test | TestTransaction.flagForCommit() hoặc flagForRollback() |
| Bắt đầu/kết thúc transaction giữa test | TestTransaction.end() và TestTransaction.start() |
| Kiểm tra trạng thái trước/sau transaction | @BeforeTransaction và @AfterTransaction |
| Chạy transaction trong @BeforeAll/@AfterAll | TransactionTemplate với manager được inject |
| Buộc ORM gửi SQL trước assertion | EntityManager.flush() hoặc Hibernate Session flush |

Khi dùng **@Transactional** trong Spring Framework Testing, hãy xác định trước test có cần transaction hay không, transaction manager nào quản lý dữ liệu và kết quả cuối cùng cần rollback hay commit. Sau đó chỉ dựa vào những thuộc tính Spring Test thực sự hỗ trợ. Với isolation, timeout, read-only và rollback rule của transaction ứng dụng, hãy kiểm tra ở ranh giới transaction phù hợp. Với test-managed transaction, dùng **@Commit**, **@Rollback** hoặc **TestTransaction** để điều khiển kết quả; đặt kiểm tra ngoài transaction ở **@BeforeTransaction** và **@AfterTransaction**; đồng thời chú ý thread-bound context, transaction độc lập và thời điểm flush của ORM.

## Tài liệu tham khảo

- [Spring Framework Reference — Transaction Management in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [TransactionalTestExecutionListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html)

