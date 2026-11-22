# Điều kiện có PlatformTransactionManager và @Transactional

Spring TestContext Framework hỗ trợ chạy test trong một transaction do framework quản lý. Cơ chế này hữu ích khi kiểm thử repository, service hoặc luồng nghiệp vụ có ghi dữ liệu: test thực hiện thao tác như ứng dụng thật, đọc lại kết quả trong transaction, rồi Spring tự rollback sau khi test kết thúc.

Để transaction test thông thường hoạt động, test context cần có một bean **PlatformTransactionManager** phù hợp và test phải được đánh dấu bằng **@Transactional**. Spring Test sử dụng **TransactionalTestExecutionListener** để phát hiện annotation, tìm transaction manager, bắt đầu transaction trước test method và hoàn tất transaction sau test.

Hai điều kiện này đảm nhiệm hai vai trò khác nhau:

- **PlatformTransactionManager** cung cấp khả năng bắt đầu, commit và rollback transaction cho một loại tài nguyên, chẳng hạn JDBC hoặc JPA.
- **@Transactional** yêu cầu test chạy trong transaction do Spring Test quản lý.

Chỉ có transaction manager trong context không có nghĩa mọi test tự động chạy trong transaction. Ngược lại, một test có @Transactional nhưng không tìm được transaction manager phù hợp sẽ không thể khởi tạo test-managed transaction.

## 1. PlatformTransactionManager là gì?

PlatformTransactionManager là interface transaction imperative của Spring. Nó định nghĩa các thao tác cốt lõi để quản lý transaction:

- getTransaction(...): lấy transaction hiện tại hoặc bắt đầu transaction theo thuộc tính được yêu cầu.
- commit(...): commit transaction.
- rollback(...): rollback transaction.

Các lớp triển khai kết nối Spring transaction abstraction với một công nghệ lưu trữ hoặc điều phối transaction cụ thể.

| Transaction manager | Tài nguyên thường quản lý | Khi thường dùng |
|---|---|---|
| DataSourceTransactionManager | Một JDBC DataSource | Ứng dụng dùng JDBC trực tiếp |
| JdbcTransactionManager | Một JDBC DataSource | JDBC transaction với hỗ trợ dịch exception theo Spring |
| JpaTransactionManager | Một JPA EntityManagerFactory | Ứng dụng dùng JPA/Hibernate |
| JtaTransactionManager | Transaction phân tán do JTA quản lý | Nhiều tài nguyên tham gia một giao dịch phân tán |

Chọn manager phù hợp với tài nguyên mà test đang sử dụng. Ví dụ, nếu repository dùng JPA, JpaTransactionManager thường là lựa chọn phù hợp. Nếu ứng dụng dùng JDBC thuần với một DataSource, DataSourceTransactionManager hoặc JdbcTransactionManager có thể đáp ứng.

Một test context có thể chứa nhiều transaction manager, ví dụ một manager cho database đơn hàng và một manager cho database báo cáo. Khi đó, test cần chỉ rõ manager muốn dùng thay vì để Spring phải đoán.

## 2. Điều kiện để Spring Test quản lý transaction

Với test transaction imperative, cần có các thành phần sau:

1. Test chạy với Spring TestContext Framework, thường thông qua @SpringJUnitConfig, @SpringBootTest hoặc một test slice.
2. TransactionalTestExecutionListener phải được đăng ký trong danh sách listener của test.
3. ApplicationContext phải cung cấp một PlatformTransactionManager có thể được Spring tìm thấy.
4. Test class hoặc test method được đánh dấu @Transactional.
5. Tài nguyên cần kiểm thử phải tham gia transaction do manager đó quản lý.

Spring TestContext đăng ký các listener mặc định, trong đó có TransactionalTestExecutionListener. Vì vậy, khi dùng cấu hình test tiêu chuẩn, thường không cần tự đăng ký listener này.

Ví dụ với Spring Framework:

~~~java
@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        // Test chạy trong transaction do Spring Test quản lý.
    }
}
~~~

TestDatabaseConfiguration phải cung cấp cả repository cần kiểm thử và một transaction manager phù hợp. Nếu cấu hình chỉ tạo repository nhưng không cung cấp PlatformTransactionManager, Spring không thể bắt đầu test-managed transaction.

Với Spring Boot, transaction manager có thể được auto-configure khi classpath và cấu hình ứng dụng đáp ứng điều kiện. Tuy nhiên, không nên giả định mọi test slice hoặc mọi cấu hình tùy chỉnh đều có manager. Khi test context bị rút gọn, cần kiểm tra các bean thực sự được nạp.

## 3. Khai báo transaction manager trong test configuration

Với JDBC, một cấu hình đơn giản có thể đăng ký DataSource và DataSourceTransactionManager:

~~~java
@Configuration
class JdbcTestConfiguration {

    @Bean
    DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .build();
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Test có thể dùng manager này:

~~~java
@SpringJUnitConfig({
    JdbcTestConfiguration.class,
    CustomerRepositoryConfiguration.class
})
@Transactional
class JdbcCustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void storesAndReadsCustomer() {
        Customer saved = customerRepository.save(
            new Customer("customer-01", "Ada")
        );

        Customer loaded = customerRepository.findById(saved.id())
            .orElseThrow();

        assertEquals("Ada", loaded.name());
    }
}
~~~

Ví dụ minh họa cấu trúc cấu hình; repository và schema phải được triển khai theo mô hình của dự án. Transaction manager được tạo từ chính DataSource mà repository sử dụng. Nếu repository và manager trỏ đến hai datasource khác nhau, transaction của test có thể không bao phủ thao tác ghi mà test đang kiểm tra.

Với JPA, cấu hình thường dùng JpaTransactionManager:

~~~java
@Bean
PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Trong Spring Boot, bean manager thường được cấu hình tự động cùng với DataSource hoặc EntityManagerFactory. Nếu đã có cấu hình transaction manager riêng, hãy xác nhận bean đó được đưa vào đúng test context.

## 4. Vai trò của @Transactional trên test class và test method

Spring Test cho phép đặt @Transactional ở cấp class hoặc method.

### 4.1. Đặt trên test class

Khi đặt trên class, các test method trong class được chạy trong test-managed transaction theo cấu hình đó:

~~~java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // ...
    }

    @Test
    void rejectsInvalidOrder() {
        // ...
    }
}
~~~

Đây là lựa chọn thuận tiện khi hầu hết test method trong class đều cần transaction. Mỗi method nhận một transaction test riêng theo lifecycle của Spring Test.

### 4.2. Đặt trên test method

Nếu chỉ một số test cần transaction, đặt annotation ở method:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    @Transactional
    void createsOrderWithinTestTransaction() {
        // ...
    }

    @Test
    void checksApplicationHealthWithoutTransaction() {
        // ...
    }
}
~~~

Method không có @Transactional và không kế thừa cấu hình transaction từ class sẽ không được Spring Test tự động bọc trong test-managed transaction.

### 4.3. Cấu hình method-level và class-level

Khi class và method cùng có annotation, cấu hình ở method được dùng cho method đó theo quy tắc tìm annotation của Spring Test. Điều này hữu ích khi một method cần transaction manager khác hoặc một chính sách transaction riêng.

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {

    @Test
    void usesOrdersDatabase() {
        // Dùng ordersTransactionManager.
    }

    @Test
    @Transactional(transactionManager = "auditTransactionManager")
    void usesAuditDatabase() {
        // Chọn manager dành cho audit.
    }
}
~~~

Trong ví dụ, cả hai manager phải tồn tại trong test context. Method-level annotation xác định manager cho test đó. Nếu chỉ có một manager, không cần chỉ định tên.

## 5. Spring tìm PlatformTransactionManager như thế nào?

Khi test có @Transactional, Spring Test phải tìm manager phù hợp trong ApplicationContext. Quy tắc thường gặp:

- Nếu annotation chỉ định tên hoặc qualifier qua transactionManager (hoặc alias value), Spring tìm manager tương ứng.
- Nếu không chỉ định, Spring ưu tiên bean có tên mặc định transactionManager.
- Nếu không có bean tên mặc định nhưng chỉ có một PlatformTransactionManager phù hợp, Spring có thể dùng manager duy nhất đó.
- Nếu có nhiều manager và không thể xác định manager phù hợp, quá trình chuẩn bị transaction thất bại.

Ví dụ chỉ định rõ tên:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
~~~

Hoặc dùng alias value:

~~~java
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
~~~

Tên trong annotation phải khớp với tên bean hoặc qualifier mà Spring có thể dùng để phân giải. Nếu dự án có nhiều database, hãy đặt tên manager có ý nghĩa theo tài nguyên và dùng tên đó nhất quán ở test cũng như service.

Nếu gặp lỗi không tìm được transaction manager, hãy kiểm tra:

- Bean manager có được đăng ký trong context hiện tại không?
- Bean có đúng kiểu PlatformTransactionManager không?
- Có nhiều manager cùng kiểu không?
- Manager mặc định có tên transactionManager không?
- transactionManager trong annotation có trỏ đúng bean không?
- Manager có quản lý đúng DataSource hoặc EntityManagerFactory mà repository sử dụng không?

## 6. TransactionalTestExecutionListener thực hiện những gì?

TransactionalTestExecutionListener là thành phần của Spring TestContext Framework chịu trách nhiệm tích hợp @Transactional với vòng đời test.

Ở mức khái quát, listener thực hiện các bước:

1. Đọc metadata @Transactional trên test class hoặc test method.
2. Xác định transaction manager phù hợp trong ApplicationContext.
3. Bắt đầu test-managed transaction trước khi test method thực thi.
4. Gắn thông tin transaction vào test context để các callback liên quan có thể truy cập.
5. Sau test method, xác định transaction phải rollback hay commit.
6. Hoàn tất transaction và thực hiện callback sau transaction khi phù hợp.

Vì listener tham gia vòng đời test, transaction không được tạo bởi một lệnh @Transactional proxy thông thường bao quanh test method. Spring Test chủ động bắt đầu và hoàn tất transaction để có thể áp dụng chính sách rollback mặc định.

Nếu dự án tùy chỉnh @TestExecutionListeners và thay thế danh sách listener mặc định, cần bảo đảm TransactionalTestExecutionListener vẫn được đăng ký. Có thể dùng chế độ merge với listener mặc định khi muốn bổ sung listener riêng mà vẫn giữ các chức năng Spring Test chuẩn.

## 7. Test-managed transaction và transaction của ứng dụng

Hai loại transaction này có liên quan nhưng có nguồn khởi tạo khác nhau:

- **Test-managed transaction:** do Spring TestContext bắt đầu trước test method và kết thúc sau test method.
- **Spring-managed transaction:** do transaction interceptor của Spring bắt đầu khi ứng dụng gọi method được đánh dấu @Transactional.
- **Application-managed transaction:** được code ứng dụng hoặc thư viện bắt đầu và hoàn tất theo API transaction tương ứng.

Ví dụ service:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        return repository.save(Order.from(command));
    }
}
~~~

Test:

~~~java
@SpringBootTest
@Transactional
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.create(validCommand());

        assertTrue(order.getId() != null);
    }
}
~~~

Nếu test-managed transaction đang hoạt động với propagation mặc định REQUIRED, lời gọi service thường tham gia transaction hiện tại. Khi test kết thúc và Spring rollback, thay đổi trong transaction đó cũng được rollback.

Để kiểm tra transaction của service trong điều kiện không có transaction bao quanh từ test, có thể bỏ @Transactional khỏi test method hoặc class. Khi đó, service proxy tự bắt đầu và hoàn tất transaction theo cấu hình của nó. Đây là cách kiểm tra commit hoặc rollback do chính service quyết định.

Không nên luôn đặt @Transactional lên mọi integration test mà không xem xét mục tiêu. Test có transaction bên ngoài có thể che khuất hành vi commit thực tế của service.

## 8. Rollback mặc định và cách yêu cầu commit

Mặc định, test-managed transaction được rollback sau test method. Điều này giúp dữ liệu test không tồn tại sang test khác:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void insertsCustomer() {
        repository.save(new Customer("customer-02", "Lin"));
        repository.flush();

        assertEquals(1, repository.count());
    }
}
~~~

Sau khi test kết thúc, Spring rollback transaction. Các test khác không nhìn thấy bản ghi này nếu chúng sử dụng cùng database và transaction isolation phù hợp.

Nếu cần commit transaction của test, có thể dùng @Commit:

~~~java
@Test
@Transactional
@Commit
void persistsFixtureForFollowingVerification() {
    repository.save(new Customer("customer-03", "Mina"));
}
~~~

Hoặc dùng @Rollback(false):

~~~java
@Test
@Transactional
@Rollback(false)
void commitsTestTransaction() {
    repository.save(new Customer("customer-04", "Noah"));
}
~~~

@Commit biểu đạt ý định commit rõ ràng; @Rollback(false) tắt hành vi rollback mặc định. Chỉ dùng commit khi test thực sự cần dữ liệu tồn tại sau transaction. Nếu commit vào database dùng chung, phải có chiến lược dữ liệu riêng và cleanup để tránh ảnh hưởng các lần chạy sau.

## 9. Điều khiển transaction bằng TestTransaction

Trong một số test, cần kết thúc transaction giữa method, xác nhận dữ liệu đã commit rồi tiếp tục một transaction khác. Spring Test cung cấp TestTransaction để điều khiển test-managed transaction:

- isActive() kiểm tra transaction test hiện có đang hoạt động.
- flagForRollback() yêu cầu rollback khi transaction kết thúc.
- flagForCommit() yêu cầu commit khi transaction kết thúc.
- end() kết thúc transaction hiện tại theo cờ commit/rollback.
- start() bắt đầu một test-managed transaction mới nếu lifecycle hỗ trợ.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class CommittedOrderTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void commitsThenStartsAnotherTestTransaction() {
        Order order = orderRepository.save(validOrder());
        orderRepository.flush();

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());

        TestTransaction.start();
        Order stored = orderRepository.findById(order.getId())
            .orElseThrow();
        assertEquals(order.getId(), stored.getId());
    }
}
~~~

Ví dụ minh họa điều khiển transaction; nếu test commit dữ liệu, cần cleanup dữ liệu đã commit sau khi xác nhận. TestTransaction chỉ điều khiển transaction do Spring Test quản lý, không phải API tổng quát để điều khiển mọi transaction do ứng dụng tự tạo.

## 10. @BeforeEach, @AfterEach và callback ngoài transaction

Khi test method chạy trong test-managed transaction, callback JUnit @BeforeEach và @AfterEach thông thường cũng chạy trong transaction đó:

~~~java
@SpringBootTest
@Transactional
class InventoryRepositoryTest {

    @BeforeEach
    void prepareData() {
        // Thao tác repository trong callback này tham gia test transaction.
    }

    @Test
    void updatesStock() {
        // ...
    }

    @AfterEach
    void inspectStateBeforeRollback() {
        // Vẫn nằm trong transaction của test method.
    }
}
~~~

Nếu cần chạy logic trước hoặc sau transaction test, Spring Test cung cấp:

- @BeforeTransaction: chạy trước khi test-managed transaction bắt đầu.
- @AfterTransaction: chạy sau khi test-managed transaction kết thúc.

~~~java
@SpringBootTest
@Transactional
class TransactionBoundaryTest {

    @BeforeTransaction
    void beforeTransaction() {
        // Kiểm tra trạng thái database trước transaction test.
    }

    @Test
    void performsDatabaseWork() {
        // Chạy bên trong test-managed transaction.
    }

    @AfterTransaction
    void afterTransaction() {
        // Kiểm tra trạng thái sau khi transaction đã rollback/commit.
    }
}
~~~

Các callback này hữu ích khi muốn xác nhận dữ liệu chưa tồn tại trước test hoặc đã được commit/rollback đúng sau test. Chúng cần được đặt trong test class có transaction management phù hợp; nếu test không chạy trong test-managed transaction thì không có ranh giới transaction tương ứng để callback bám vào.

## 11. Những thuộc tính @Transactional cần chú ý trong test

@Transactional của Spring có nhiều thuộc tính, nhưng test-managed transaction không áp dụng tất cả theo cách giống transaction của method production.

Các điểm thường cần nhớ:

- value và transactionManager: dùng để chọn transaction manager cho test.
- propagation: test framework có quy tắc riêng cho propagation; các chế độ NOT_SUPPORTED và NEVER có thể được dùng để yêu cầu test không chạy trong test-managed transaction. Các propagation khác cần được cân nhắc theo giới hạn của Spring TestContext và mục tiêu test.
- isolation, timeout và readOnly: không được dùng như cách cấu hình đầy đủ transaction test tương tự một method nghiệp vụ thông thường.
- rollbackFor và noRollbackFor: không phải cơ chế điều khiển rollback test được khuyến nghị; dùng @Rollback, @Commit hoặc TestTransaction để thể hiện chính sách kết thúc transaction test.

Nếu cần kiểm tra isolation level, timeout hoặc rollback rule của service production, hãy tạo test gọi service qua proxy trong một transaction do service quản lý và quan sát hành vi ở ranh giới thích hợp. Đừng giả định annotation trên test method đã kiểm tra đầy đủ các thuộc tính transaction của service.

## 12. Transaction manager và nhiều datasource

Ứng dụng có thể có nhiều datasource và nhiều transaction manager. Ví dụ, đơn hàng và báo cáo được lưu ở hai database riêng:

~~~java
@Configuration
class MultiDatabaseConfiguration {

    @Bean
    @Primary
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Test cho repository đơn hàng:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional("ordersTransactionManager")
class OrdersRepositoryTest {
    // ...
}
~~~

Test cho repository audit:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional("auditTransactionManager")
class AuditRepositoryTest {
    // ...
}
~~~

@Primary giúp Spring chọn một manager mặc định trong những tình huống cần một ứng viên ưu tiên. Tuy nhiên, nếu test có ý định dùng database cụ thể, khai báo tên manager trực tiếp giúp thể hiện rõ tài nguyên được quản lý.

Một transaction manager thông thường chỉ quản lý tài nguyên mà nó được cấu hình để quản lý. Hai datasource độc lập với hai local transaction manager không tự động trở thành một transaction phân tán thống nhất. Nếu một test ghi vào cả hai database, rollback của manager thứ nhất không đảm bảo rollback thay đổi do manager thứ hai đã commit.

## 13. Điều kiện để transaction thực sự bao phủ thao tác database

Có PlatformTransactionManager và @Transactional chưa đủ nếu thao tác dữ liệu không tham gia transaction đó.

### 13.1. Repository phải dùng đúng tài nguyên

Nếu test transaction manager quản lý DataSource A nhưng repository ghi vào DataSource B, thao tác ghi có thể nằm ngoài transaction test. Khi đó, rollback của test không xóa dữ liệu đã ghi ở B.

Hãy xác nhận repository, EntityManagerFactory và transaction manager được cấu hình nhất quán.

### 13.2. Transaction propagation có thể tạo transaction riêng

Một method production dùng Propagation.REQUIRES_NEW có thể tạm ngưng transaction test hiện tại và chạy trong transaction mới. Transaction mới có thể commit độc lập; rollback của transaction test bên ngoài không hoàn tác được dữ liệu đã commit đó.

Với các method dùng REQUIRES_NEW, cần thiết kế cleanup riêng hoặc kiểm tra qua transaction boundary phù hợp.

### 13.3. Thread khác không tự tham gia transaction test

Transaction JDBC/JPA thông thường được gắn với thread hiện tại. Nếu test gọi code bất đồng bộ chạy trên executor hoặc thread khác, thao tác đó thường không tham gia transaction test của thread đang chạy JUnit.

Một task async có thể commit dữ liệu ngay cả khi transaction test bên ngoài rollback. Hãy chờ task hoàn tất và dọn dữ liệu ngoài transaction test nếu cần.

### 13.4. Preemptive timeout có thể làm mất transaction context

Một số assertion timeout kiểu preemptive chạy đoạn test trong thread riêng. Vì transaction test thường được gắn với thread thực thi test, code chạy ở thread mới có thể không tham gia transaction đó. Các thao tác ghi database trong thread mới có thể tồn tại sau khi test rollback.

Với test transactional, hãy thận trọng khi dùng preemptive timeout như assertTimeoutPreemptively. Nếu cần giới hạn thời gian, cân nhắc cơ chế timeout không chuyển execution sang thread khác hoặc dùng cách kiểm soát phù hợp với transaction của ứng dụng.

## 14. Flush để quan sát lỗi persistence đúng thời điểm

JPA có thể trì hoãn câu lệnh SQL cho đến khi flush hoặc commit. Vì test-managed transaction thường rollback sau method, một số lỗi constraint có thể không xuất hiện nếu test chưa flush.

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmail() {
        repository.save(new Customer("a@example.test"));
        repository.flush();

        repository.save(new Customer("a@example.test"));

        assertThrows(
            DataIntegrityViolationException.class,
            repository::flush
        );
    }
}
~~~

Ví dụ giả định database có unique constraint trên email và repository hỗ trợ flush. Việc gọi flush làm SQL được gửi xuống database trong transaction hiện tại để lỗi constraint xuất hiện ngay tại vị trí test kiểm tra.

Flush không đồng nghĩa commit. Dữ liệu vẫn nằm trong transaction và có thể được rollback sau test. Điều này giúp kiểm tra constraint mà không cần giữ dữ liệu lại trong database.

## 15. Khi nào test không nên dùng @Transactional?

Không phải mọi integration test đều phù hợp với transaction bao quanh test method.

Nên cân nhắc bỏ @Transactional khi mục tiêu là:

- Xác nhận service tự commit hoặc rollback transaction của nó.
- Kiểm tra dữ liệu đã thực sự tồn tại sau khi service kết thúc transaction.
- Kiểm tra hành vi của transaction propagation như REQUIRES_NEW.
- Kiểm tra công việc bất đồng bộ ghi dữ liệu ở thread khác.
- Kiểm tra ranh giới transaction giữa nhiều datasource.
- Kiểm tra callback hoặc sự kiện chỉ được phát sau commit.

Ví dụ, muốn xác nhận service commit dữ liệu:

~~~java
@SpringBootTest
class OrderCommitIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceCommitsOrder() {
        Order created = orderService.createAndCommit(validCommand());

        Order loaded = orderRepository.findById(created.getId())
            .orElseThrow();

        assertEquals(created.getId(), loaded.getId());
    }
}
~~~

Ví dụ này giả định service tự quản lý transaction và hoàn tất commit trước khi trả về. Test cần dữ liệu riêng hoặc cleanup để tránh để lại bản ghi giữa các lần chạy.

## 16. Lỗi thường gặp khi thiếu transaction manager hoặc @Transactional

### 16.1. Có @Transactional nhưng không có PlatformTransactionManager

Spring Test không thể bắt đầu test-managed transaction. Kiểm tra context có bean manager phù hợp không và cấu hình manager có được import vào test không.

### 16.2. Có transaction manager nhưng test không chạy trong transaction

Manager chỉ cung cấp khả năng quản lý transaction. Test method cần @Transactional hoặc một cơ chế transaction tương ứng để Spring Test bắt đầu transaction.

### 16.3. Có nhiều manager nhưng không chọn được

Nếu context có nhiều PlatformTransactionManager, hãy chỉ rõ transactionManager trong @Transactional, hoặc tổ chức bean mặc định bằng tên transactionManager/@Primary phù hợp.

### 16.4. Manager dùng sai DataSource

Rollback chạy thành công nhưng dữ liệu vẫn còn vì repository ghi sang datasource khác. Kiểm tra wiring của repository và manager, đặc biệt khi ứng dụng có nhiều database.

### 16.5. Nghĩ rằng @Transactional trên test kiểm tra transaction của service

Test-managed transaction có thể khiến service tham gia transaction đã được test bắt đầu. Điều đó hữu ích cho kiểm thử dữ liệu, nhưng không chứng minh service tự tạo và commit transaction trong một lời gọi độc lập.

### 16.6. Dùng REQUIRES_NEW và mong rollback bên ngoài xóa dữ liệu

Transaction riêng có thể commit độc lập. Hãy xác nhận propagation và tạo cleanup cho dữ liệu được commit bên trong transaction mới.

### 16.7. Ghi dữ liệu trong thread khác

Transaction test không tự lan truyền sang thread bất đồng bộ. Chờ công việc hoàn tất và dọn dữ liệu theo ranh giới transaction thực tế.

### 16.8. Không flush trước khi kiểm tra constraint

JPA có thể trì hoãn SQL. Gọi flush tại vị trí cần xác nhận lỗi database để test không bỏ sót constraint violation.

### 16.9. Tắt listener mặc định

Nếu tùy chỉnh danh sách @TestExecutionListeners và không giữ TransactionalTestExecutionListener, @Transactional có thể không được xử lý như mong đợi. Hãy merge với listener mặc định hoặc đăng ký listener cần thiết.

## 17. Quy trình thiết lập một transactional test

Khi tạo test dùng transaction, có thể làm theo trình tự:

1. Xác định tài nguyên cần kiểm tra: JDBC, JPA hay một hệ thống transaction khác.
2. Bảo đảm test context đăng ký đúng PlatformTransactionManager.
3. Nếu có nhiều manager, chỉ định tên manager trong @Transactional.
4. Đặt @Transactional ở cấp class khi phần lớn test method cần transaction, hoặc ở từng method khi chỉ một số test cần.
5. Xác nhận repository và manager dùng cùng datasource hoặc persistence unit.
6. Dùng rollback mặc định cho test dữ liệu thông thường; dùng @Commit, @Rollback(false) hoặc TestTransaction khi cần commit có chủ đích.
7. Gọi flush khi cần phát hiện lỗi SQL hoặc constraint ngay tại assertion.
8. Kiểm tra các ranh giới như REQUIRES_NEW, thread bất đồng bộ và nhiều datasource.
9. Chạy test riêng và trong suite để xác nhận dữ liệu không rò rỉ giữa các lần chạy.

Mẫu tối giản:

~~~java
@SpringBootTest
@Transactional
class RepositoryIntegrationTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private CustomerRepository repository;

    @Test
    void usesSpringManagedTestTransaction() {
        assertNotNull(transactionManager);

        Customer customer = repository.save(
            new Customer("customer-10", "Kai")
        );
        repository.flush();

        assertTrue(repository.findById(customer.id()).isPresent());
    }
}
~~~

Trong ví dụ, việc inject manager giúp test thể hiện rõ dependency của transaction infrastructure; chính @Transactional và TransactionalTestExecutionListener mới tạo test-managed transaction. Nếu repository dùng JPA, manager được inject phải là manager quản lý đúng persistence unit của repository.

## Kết luận

Transactional test thông thường của Spring cần một PlatformTransactionManager trong ApplicationContext và @Transactional trên test class hoặc method. Spring TestContext dùng TransactionalTestExecutionListener để bắt đầu transaction trước test và mặc định rollback sau test. Khi có nhiều manager, cần chọn đúng bean; khi kiểm tra commit, propagation, nhiều datasource hoặc công việc bất đồng bộ, phải xác định đúng ranh giới transaction và chọn cách xác nhận phù hợp.
