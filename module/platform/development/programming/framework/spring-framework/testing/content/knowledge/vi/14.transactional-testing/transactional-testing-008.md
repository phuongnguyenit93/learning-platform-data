# @BeforeTransaction và @AfterTransaction ngoài giao dịch

Trong kiểm thử Spring có sử dụng giao dịch, nhiều test method được chạy bên trong một **test-managed transaction**. Mặc định, Spring thường rollback giao dịch này sau khi test kết thúc để dữ liệu kiểm thử không ảnh hưởng đến test tiếp theo. Tuy nhiên, có những hành vi chỉ có thể kiểm tra trước khi giao dịch bắt đầu hoặc sau khi giao dịch đã commit/rollback.

Spring TestContext Framework cung cấp hai callback chuyên biệt:

- **@BeforeTransaction:** chạy trước khi test-managed transaction bắt đầu.
- **@AfterTransaction:** chạy sau khi test-managed transaction đã kết thúc, dù giao dịch được commit hay rollback.

Hai callback này giúp chuẩn bị dữ liệu nền nằm ngoài giao dịch của test, kiểm tra trạng thái thực tế sau khi giao dịch hoàn tất và xác minh những hành vi phụ thuộc ranh giới commit/rollback. Chúng không có nghĩa mọi thao tác trong callback đều tuyệt đối không có giao dịch. Chúng chỉ nằm ngoài giao dịch do Spring TestContext quản lý cho test method; một service hoặc repository được gọi trong callback vẫn có thể mở giao dịch riêng.

## 1. Test-managed transaction là gì?

Spring TestContext Framework có thể quản lý giao dịch cho một test method khi test được cấu hình bằng @Transactional và có transaction manager phù hợp. Việc quản lý này thường do **TransactionalTestExecutionListener** thực hiện.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class AccountRepositoryTests {

    @Autowired
    AccountRepository accountRepository;

    @Test
    void creates_account() {
        accountRepository.save(new Account("A-100"));

        assertThat(accountRepository.findById("A-100"))
            .isPresent();
    }
}
~~~

Trong cấu hình thông thường, test method chạy trong một transaction do Spring Test bắt đầu. Khi test hoàn tất, transaction được rollback theo mặc định. Nhờ vậy, bản ghi được tạo trong test không tồn tại sau khi test kết thúc.

Đây là **test-managed transaction**. Cần phân biệt nó với:

- **Application-managed transaction:** transaction được mã ứng dụng bắt đầu bằng TransactionTemplate, PlatformTransactionManager hoặc cơ chế tương đương.
- **Spring-managed transaction trong ứng dụng:** transaction được mở khi gọi một bean qua proxy có @Transactional.
- **Transaction của hệ thống ngoài:** giao dịch hoặc side effect được thực hiện bởi database, broker hay dịch vụ khác.

@BeforeTransaction và @AfterTransaction được đặt ở hai phía của test-managed transaction. Chúng không tự quản lý mọi transaction khác trong ứng dụng.

### 1.1. Transaction mặc định được rollback

Với test method có @Transactional, Spring Test thường rollback transaction sau khi test hoàn tất. Có thể thay đổi kết quả bằng:

- @Commit: yêu cầu commit test-managed transaction.
- @Rollback(false): yêu cầu commit thay vì rollback.
- @Rollback: khai báo rõ hành vi rollback, mặc định là true.

Ví dụ:

~~~java
@Test
@Commit
void commits_created_account() {
    accountRepository.save(new Account("A-200"));
}
~~~

Khi transaction được commit, dữ liệu có thể tồn tại sau test và ảnh hưởng đến các test sau nếu không được dọn dẹp. Đây là một trường hợp phù hợp để dùng @AfterTransaction xác minh trạng thái sau commit rồi cleanup theo chiến lược của test.

## 2. @BeforeTransaction và @AfterTransaction hoạt động thế nào?

Hai annotation thuộc package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

TransactionalTestExecutionListener gọi các phương thức được đánh dấu ở những thời điểm tương ứng với test-managed transaction.

Luồng khái quát:

~~~text
Chuẩn bị test instance và inject dependency
                 |
                 v
       @BeforeTransaction
       (ngoài test transaction)
                 |
                 v
    Spring bắt đầu test transaction
                 |
                 v
       JUnit @BeforeEach
                 |
                 v
           @Test method
                 |
                 v
        JUnit @AfterEach
                 |
                 v
     Commit hoặc rollback transaction
                 |
                 v
        @AfterTransaction
        (sau test transaction)
                 |
                 v
             Test kết thúc
~~~

Sơ đồ mô tả thứ tự khái quát trong một test có giao dịch do Spring quản lý. Các callback JUnit và Spring có lifecycle riêng; điểm cần nhớ là @BeforeTransaction chạy trước khi test-managed transaction bắt đầu, còn @AfterTransaction chạy sau khi transaction đó hoàn tất.

### 2.1. Chỉ chạy khi test có test-managed transaction

@BeforeTransaction và @AfterTransaction không phải callback thay thế cho @BeforeEach và @AfterEach. Chúng được gọi khi test method được chạy trong một test-managed transaction.

Nếu test không có @Transactional ở method hoặc class, hoặc cấu hình khiến test không tham gia test-managed transaction, hai callback này không được gọi theo cơ chế thông thường.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfig.class)
class NonTransactionalTests {

    @BeforeTransaction
    void beforeTransaction() {
        // Không được gọi chỉ vì method có annotation này.
    }

    @Test
    void runs_without_test_managed_transaction() {
        // ...
    }
}
~~~

Trong trường hợp trên, test không khai báo @Transactional nên không có test-managed transaction để callback đứng trước hoặc sau.

### 2.2. Callback chạy trên test instance đã được chuẩn bị

Các callback có thể sử dụng dependency đã được Spring inject vào test instance, chẳng hạn JdbcTemplate, repository hoặc transaction manager. Vì vậy, có thể dùng chúng để chuẩn bị và kiểm tra trạng thái database.

Các method callback thường không nhận tham số và được khai báo như method của test class. Chúng có thể được kế thừa từ superclass theo quy tắc phát hiện method của Spring TestContext.

## 3. @BeforeTransaction: chuẩn bị trạng thái trước giao dịch

@BeforeTransaction được gọi ngay trước khi Spring bắt đầu test-managed transaction. Nó phù hợp để:

- Tạo dữ liệu nền mà test transaction không được rollback.
- Xác nhận database đang ở trạng thái ban đầu.
- Thiết lập một trạng thái bên ngoài transaction cần thiết cho test.
- Ghi nhận dữ liệu hoặc số đếm trước khi test thực hiện thao tác.
- Chuẩn bị một điều kiện cần tồn tại trước khi service bắt đầu transaction.

Ví dụ:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class OrderTransactionTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void prepare_baseline_data() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );

        jdbcTemplate.update(
            """
            insert into customers(customer_id, customer_name)
            values (?, ?)
            """,
            reference,
            "Transaction test customer"
        );
    }

    @Test
    void creates_order_for_existing_customer() {
        // Test chạy trong test-managed transaction.
    }
}
~~~

Các thao tác trong callback nằm ngoài test-managed transaction. Vì vậy, nếu callback ghi dữ liệu bằng một connection chạy autocommit hoặc qua một repository/service tự mở transaction, dữ liệu nền có thể đã được commit trước khi test method bắt đầu.

Không nên mặc định mọi thao tác JDBC bên ngoài test-managed transaction đều tự động commit trong mọi cấu hình. Kết quả còn phụ thuộc connection, DataSource, transaction manager và cách collaborator quản lý transaction. Nếu cần tính xác định, hãy dùng transaction boundary tường minh hoặc một API repository/service có semantics đã biết.

### 3.1. Dữ liệu tạo trong @BeforeTransaction không bị rollback cùng test transaction

Đây là điểm quan trọng khi dùng callback để seed dữ liệu. Test-managed transaction bắt đầu sau callback, vì vậy các thao tác đã hoàn tất trong callback không nằm trong transaction đó.

Ví dụ:

~~~java
@BeforeTransaction
void insert_customer() {
    customerRepository.save(new Customer("C-1"));
}

@Test
void updates_customer() {
    Customer customer = customerRepository.findById("C-1").orElseThrow();
    customer.rename("Updated");
}
~~~

Nếu save trong @BeforeTransaction được thực hiện bởi repository có transaction riêng và đã commit, bản ghi C-1 vẫn tồn tại sau khi test transaction rollback. Thay đổi tên trong test transaction sẽ bị rollback theo mặc định.

Nếu không muốn dữ liệu nền tồn tại lâu dài, cần cleanup ở @AfterTransaction hoặc dùng dữ liệu định danh riêng và dọn dẹp trong chiến lược phù hợp.

### 3.2. Dùng @BeforeTransaction để ghi nhận trạng thái ban đầu

Callback cũng có thể đọc trạng thái trước giao dịch:

~~~java
private long ordersBefore;

@BeforeTransaction
void capture_initial_order_count() {
    ordersBefore = jdbcTemplate.queryForObject(
        "select count(*) from orders",
        Long.class
    );
}
~~~

Test method có thể tạo hoặc cập nhật dữ liệu. Sau transaction, @AfterTransaction so sánh trạng thái để xác minh commit/rollback. Cách này hữu ích khi cần kiểm tra tác động của giao dịch lên một bảng hoặc aggregate.

Tuy nhiên, nếu test suite chạy song song hoặc các test khác cùng ghi vào bảng, số đếm toàn bảng có thể thay đổi vì hoạt động không liên quan. Dùng một business key riêng cho mỗi test thường đáng tin cậy hơn.

## 4. @AfterTransaction: kiểm tra sau commit hoặc rollback

@AfterTransaction được gọi sau khi test-managed transaction đã kết thúc. Đây là thời điểm phù hợp để kiểm tra điều gì còn tồn tại trong database sau khi giao dịch được commit hoặc rollback.

Các trường hợp sử dụng:

- Xác nhận dữ liệu đã biến mất sau rollback mặc định.
- Xác nhận dữ liệu tồn tại sau @Commit hoặc @Rollback(false).
- Kiểm tra một trạng thái chỉ quan sát được sau khi transaction hoàn tất.
- Cleanup dữ liệu được tạo ngoài test-managed transaction.
- Kiểm tra một thao tác REQUIRES_NEW đã commit độc lập.

### 4.1. Xác nhận rollback mặc định

Ví dụ sau tạo một bản ghi trong test transaction và kiểm tra nó không còn sau khi Spring rollback:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class RollbackVerificationTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void clean_previous_data() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }

    @Test
    void inserted_order_is_visible_inside_test_transaction() {
        jdbcTemplate.update(
            """
            insert into orders(order_id, external_reference, status)
            values (?, ?, ?)
            """,
            UUID.randomUUID().toString(),
            reference,
            "CREATED"
        );

        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isEqualTo(1);
    }

    @AfterTransaction
    void verifies_rollback() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isZero();
    }
}
~~~

Trong test method, bản ghi nhìn thấy được vì nó nằm trong transaction hiện tại. Sau khi method kết thúc, Spring rollback transaction. @AfterTransaction đọc lại database sau khi rollback và xác nhận bản ghi không còn.

Ví dụ giả định JdbcTemplate dùng cùng DataSource được transaction manager quản lý. Khi callback chạy ngoài test-managed transaction, truy vấn sau rollback sẽ lấy trạng thái bên ngoài transaction đã kết thúc.

### 4.2. Xác nhận dữ liệu sau commit

Nếu test dùng @Commit, @AfterTransaction có thể kiểm tra dữ liệu đã được commit:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class CommitVerificationTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void remove_old_record() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }

    @Test
    @Commit
    void commits_order() {
        jdbcTemplate.update(
            """
            insert into orders(order_id, external_reference, status)
            values (?, ?, ?)
            """,
            UUID.randomUUID().toString(),
            reference,
            "CREATED"
        );
    }

    @AfterTransaction
    void verifies_committed_order_and_cleans_up() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isEqualTo(1);

        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }
}
~~~

Test xác nhận bản ghi tồn tại sau commit rồi xóa nó để không ảnh hưởng test khác. Việc cleanup diễn ra ngoài test-managed transaction, vì vậy cần hiểu transaction của thao tác cleanup và bảo đảm nó thực sự được lưu.

Nếu assertion trong @AfterTransaction thất bại trước khi cleanup chạy, dữ liệu có thể còn lại. Với test quan trọng, có thể dùng cleanup trong finally hoặc một cơ chế cleanup độc lập được thiết kế phù hợp.

## 5. Phân biệt với @BeforeEach và @AfterEach

JUnit Jupiter cung cấp @BeforeEach và @AfterEach cho lifecycle của từng test method. Khi test được Spring quản lý transaction, các callback này thường chạy trong test-managed transaction.

| Callback | Thời điểm tương đối với test-managed transaction | Mục đích thường gặp |
| --- | --- | --- |
| @BeforeTransaction | Trước khi transaction bắt đầu | Seed dữ liệu bên ngoài transaction, kiểm tra baseline |
| @BeforeEach | Sau khi transaction được bắt đầu | Chuẩn bị dữ liệu thuộc transaction của test |
| @Test | Bên trong transaction | Thực hiện hành vi cần kiểm thử |
| @AfterEach | Trước khi transaction kết thúc | Assertion hoặc cleanup nằm trong transaction |
| @AfterTransaction | Sau commit/rollback | Xác minh trạng thái cuối cùng bên ngoài transaction |

Không nên thay @BeforeEach bằng @BeforeTransaction chỉ vì muốn setup chạy sớm hơn. Hai callback có semantics khác nhau đối với rollback.

### 5.1. Khi nào dùng @BeforeEach?

Dùng @BeforeEach nếu dữ liệu setup nên thuộc test transaction và được rollback cùng test. Ví dụ, tạo một entity để kiểm tra repository trong cùng transaction.

### 5.2. Khi nào dùng @BeforeTransaction?

Dùng @BeforeTransaction nếu dữ liệu phải tồn tại trước khi test transaction bắt đầu, hoặc test cần kiểm tra trạng thái database trước khi transaction được mở.

### 5.3. Khi nào dùng @AfterEach?

Dùng @AfterEach cho thao tác cần thực hiện trước khi test transaction hoàn tất, chẳng hạn kiểm tra dữ liệu đang nằm trong transaction. Nếu test transaction rollback sau đó, các assertion này không chứng minh dữ liệu đã được commit.

### 5.4. Khi nào dùng @AfterTransaction?

Dùng @AfterTransaction khi cần biết kết quả sau khi Spring đã commit hoặc rollback test transaction. Đây là điểm thích hợp để xác nhận trạng thái bền vững của database sau giao dịch.

## 6. Tương tác với @Transactional, @Commit và @Rollback

Hai callback chỉ có ý nghĩa khi có test-managed transaction. Vì vậy, cần hiểu cách annotation transaction quyết định việc transaction được mở và kết thúc.

### 6.1. @Transactional ở cấp class

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class TransactionalRepositoryTests {

    @BeforeTransaction
    void before() {
    }

    @Test
    void first_test() {
    }

    @Test
    void second_test() {
    }

    @AfterTransaction
    void after() {
    }
}
~~~

Khi cấu hình class-level @Transactional áp dụng cho các test method, mỗi test method có test-managed transaction riêng. Các callback trước/sau giao dịch được gọi cho từng test method có transaction.

### 6.2. @Transactional ở cấp method

~~~java
@SpringJUnitConfig(TestConfig.class)
class MixedTransactionTests {

    @Test
    @Transactional
    void runs_with_test_transaction() {
    }

    @Test
    void runs_without_test_transaction() {
    }
}
~~~

Trong ví dụ này, chỉ method được đánh dấu @Transactional yêu cầu test-managed transaction. Không nên kỳ vọng @BeforeTransaction hoặc @AfterTransaction chạy cho method không có transaction.

### 6.3. @Commit

@Commit yêu cầu Spring commit test-managed transaction sau test method. @AfterTransaction được gọi sau khi commit hoàn tất, do đó có thể đọc dữ liệu đã được lưu.

### 6.4. @Rollback

@Rollback mặc định là true. Khi test không khai báo @Commit hoặc @Rollback(false), Spring thường rollback transaction sau test. @AfterTransaction có thể xác nhận các thay đổi thuộc transaction đó không còn.

### 6.5. @Rollback(false)

~~~java
@Test
@Transactional
@Rollback(false)
void persists_changes() {
    // ...
}
~~~

@Rollback(false) có hiệu lực tương tự yêu cầu commit trong ngữ cảnh test-managed transaction. Hãy cẩn trọng với dữ liệu được lưu lại và luôn có cleanup phù hợp.

### 6.6. Propagation không tạo test transaction

Nếu cấu hình test transaction dùng propagation như NOT_SUPPORTED hoặc NEVER theo cách được Spring TestContext hỗ trợ, test có thể không chạy trong test-managed transaction. Khi không có transaction được quản lý cho test, callback transaction không có điểm bắt đầu/kết thúc để thực hiện.

Hãy kiểm tra cấu hình @Transactional thực tế, transaction manager được chọn và log của TransactionalTestExecutionListener thay vì chỉ dựa vào việc annotation xuất hiện trên class.

## 7. Giao dịch do ứng dụng tự mở trong callback

Tên @BeforeTransaction có thể khiến người đọc nghĩ rằng callback tuyệt đối không có transaction. Ý nghĩa chính xác là callback chạy ngoài **test-managed transaction**.

Nếu callback gọi một service bean qua Spring proxy và service có @Transactional, service vẫn có thể mở transaction riêng:

~~~java
@Service
class CustomerSetupService {

    private final CustomerRepository repository;

    CustomerSetupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createCustomer(String id) {
        repository.save(new Customer(id));
    }
}
~~~

Test:

~~~java
@BeforeTransaction
void create_customer_before_test_transaction() {
    customerSetupService.createCustomer("C-100");
}
~~~

Lời gọi qua proxy có thể mở và commit transaction riêng trước khi test-managed transaction bắt đầu. Dữ liệu C-100 do đó có thể được test nhìn thấy.

Điều này khác với việc gọi trực tiếp một phương thức @Transactional trên cùng object bằng self-invocation. Nếu một method trong class gọi method khác cùng class, lời gọi nội bộ thường không đi qua Spring proxy, nên transaction advice có thể không được áp dụng.

### 7.1. Dùng TransactionTemplate để tạo ranh giới rõ ràng

Nếu callback cần ghi dữ liệu trong một transaction riêng, TransactionTemplate có thể làm ý định rõ ràng:

~~~java
@Autowired
TransactionTemplate transactionTemplate;

@BeforeTransaction
void prepare_data_in_own_transaction() {
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into customers(customer_id) values (?)",
            "C-200"
        );
    });
}
~~~

Vì callback chạy ngoài test-managed transaction, TransactionTemplate có thể mở một transaction riêng theo transaction manager được cấu hình. Khi callback kết thúc thành công, transaction riêng được commit theo propagation mặc định phù hợp.

Chỉ dùng cách này khi test thật sự cần một transaction riêng. Với fixture đơn giản, repository có transaction semantics rõ ràng hoặc thao tác JDBC phù hợp có thể đủ.

### 7.2. REQUIRES_NEW trong code ứng dụng

Một service có thể dùng propagation REQUIRES_NEW để ghi dữ liệu trong transaction độc lập với test transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(AuditRecord record) {
    auditRepository.save(record);
}
~~~

Khi service được gọi qua proxy từ test method đang có transaction, transaction mới có thể commit độc lập. Rollback test transaction bên ngoài không tự động rollback transaction REQUIRES_NEW đã commit.

@AfterTransaction rất hữu ích để xác nhận audit record còn tồn tại sau khi transaction test bên ngoài rollback. Đây là một hành vi có ý nghĩa nghiệp vụ, nhưng test cần thiết lập database và transaction manager phù hợp.

## 8. Ví dụ: kiểm tra REQUIRES_NEW không bị rollback cùng test

Giả sử service ghi audit bằng transaction riêng:

~~~java
@Service
class AuditService {

    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String reference) {
        repository.save(new AuditRecord(reference));
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class RequiresNewTransactionTests {

    @Autowired
    AuditService auditService;

    @Autowired
    AuditRepository auditRepository;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void remove_old_audit() {
        auditRepository.deleteByReference(reference);
    }

    @Test
    void records_audit_in_independent_transaction() {
        auditService.record(reference);

        assertThat(auditRepository.findByReference(reference))
            .isPresent();
    }

    @AfterTransaction
    void audit_record_survives_outer_rollback() {
        assertThat(auditRepository.findByReference(reference))
            .isPresent();

        auditRepository.deleteByReference(reference);
    }
}
~~~

Ví dụ giả định AuditRepository có các phương thức minh họa và deleteByReference thực hiện cleanup bằng transaction phù hợp. Trong test method, lời gọi REQUIRES_NEW commit audit record độc lập. Khi test transaction bên ngoài rollback, record vẫn còn; @AfterTransaction xác nhận điều đó.

Đây cũng là ví dụ cho thấy rollback mặc định không có nghĩa mọi dữ liệu phát sinh trong lúc test đều bị hoàn tác. Transaction propagation tạo ra các ranh giới độc lập cần được kiểm tra riêng.

## 9. Kết hợp với JPA và persistence context

Khi dùng JPA, cần phân biệt database state với trạng thái đang nằm trong persistence context.

Trong test-managed transaction:

- Entity có thể đang được quản lý trong persistence context.
- Một truy vấn có thể trả entity từ first-level cache.
- Flush đẩy thay đổi xuống database trong transaction nhưng chưa đồng nghĩa commit.
- Rollback hoàn tác thay đổi database thuộc transaction đó.
- Sau transaction, một EntityManager mới hoặc repository query ngoài transaction sẽ quan sát trạng thái đã commit/rollback.

### 9.1. Vì sao @AfterTransaction hữu ích với JPA?

Nếu test chỉ gọi findById ngay sau save trong cùng transaction, entity có thể được trả từ persistence context. Điều đó không chứng minh dữ liệu đã commit.

@AfterTransaction chạy sau khi test transaction kết thúc, nên có thể kiểm tra kết quả qua một persistence operation mới. Để bằng chứng rõ hơn, có thể dùng repository hoặc JdbcTemplate được cấu hình với cùng database.

Ví dụ:

~~~java
@AfterTransaction
void verifies_entity_is_not_persisted_after_rollback() {
    assertThat(orderRepository.findByExternalReference(reference))
        .isEmpty();
}
~~~

Không cần gọi EntityManager.clear() trong callback sau transaction chỉ để tránh first-level cache của transaction đã kết thúc. Tuy nhiên, nếu test đang dùng một persistence context hoặc transaction khác được mở thủ công, hãy xác định rõ nó có đang giữ state cũ hay không.

### 9.2. Flush không phải commit

Trong test JPA, có thể gọi entityManager.flush() để buộc SQL được gửi tới database và phát hiện constraint violation sớm. Nhưng flush vẫn diễn ra trong transaction hiện tại. Nếu test transaction rollback sau đó, dữ liệu không được commit.

Nếu mục tiêu là kiểm tra commit, hãy dùng @Commit hoặc @Rollback(false), rồi xác minh trong @AfterTransaction. Đừng xem flush thành bằng chứng giao dịch đã hoàn tất.

## 10. Kết hợp với SQL scripts

Spring TestContext hỗ trợ @Sql để chạy SQL script trước hoặc sau test method. Có thể kết hợp @Sql với transaction test, nhưng cần hiểu execution phase và transaction mode của script.

Nếu @Sql chạy trong transaction test, các thay đổi có thể bị rollback cùng test. Nếu script được cấu hình chạy ngoài transaction test hoặc dùng transaction mode riêng, dữ liệu có thể tồn tại sau test.

@BeforeTransaction và @AfterTransaction phù hợp khi cần logic Java để chuẩn bị hoặc kiểm tra dữ liệu ở hai phía của test-managed transaction. @Sql phù hợp khi dữ liệu fixture được mô tả tự nhiên bằng SQL script.

Không nên dùng cả hai cơ chế để tạo và xóa cùng một dữ liệu nếu không có lý do rõ ràng. Hãy chọn một chiến lược fixture dễ theo dõi và đảm bảo cleanup chạy ngay cả khi assertion thất bại.

## 11. Test chạy không có transaction hoặc transaction manager

Hai callback transaction không phải công cụ tổng quát cho mọi test:

- Nếu test method không chạy trong test-managed transaction, callback không được gọi.
- Nếu Spring không tìm thấy transaction manager cần thiết cho cấu hình @Transactional, context hoặc test setup có thể thất bại.
- Nếu test chỉ dùng object Java thuần, không cần Spring transaction lifecycle.
- Nếu test kiểm tra HTTP request qua server thật, transaction của test thread không tự động bao trùm transaction ở server thread.

Với test HTTP thật sử dụng @SpringBootTest(webEnvironment = RANDOM_PORT), request được xử lý trên server thread. Transaction do TestContext mở trên thread gọi test không tự động bao bọc thao tác database trong request. Vì vậy, @BeforeTransaction và @AfterTransaction đứng trước/sau test-managed transaction của test method, nhưng không phải callback trực tiếp trước/sau transaction của request server.

Nếu cần kiểm tra transaction của request, hãy quan sát dữ liệu sau khi HTTP request hoàn tất bằng một transaction mới hoặc repository operation phù hợp. Không suy luận rằng test-managed transaction của client thread sẽ rollback dữ liệu server đã commit.

## 12. Lỗi thường gặp

### Dùng @BeforeTransaction nhưng quên @Transactional

Không có test-managed transaction thì callback không được gọi. Hãy xác nhận test method hoặc class có transaction được Spring Test quản lý.

### Nghĩ dữ liệu seed trong @BeforeTransaction sẽ tự rollback

Callback chạy trước transaction test. Dữ liệu được ghi và commit trong callback có thể tồn tại sau test. Hãy cleanup rõ ràng hoặc dùng fixture riêng.

### Dùng @AfterEach để xác nhận commit

@AfterEach chạy trước khi test-managed transaction hoàn tất. Nó không chứng minh dữ liệu đã commit. Dùng @AfterTransaction khi cần xác minh trạng thái sau commit/rollback.

### Nghĩ @AfterTransaction luôn thấy dữ liệu đã commit

Mặc định test-managed transaction thường rollback. Chỉ khi dùng @Commit hoặc @Rollback(false), dữ liệu thuộc transaction mới được commit.

### Nghĩ mọi thao tác trong callback đều autocommit

Callback nằm ngoài test-managed transaction, nhưng service/repository có thể mở transaction riêng. JDBC connection cũng chịu ảnh hưởng cấu hình DataSource. Hãy xác định transaction boundary thực tế.

### Dùng @AfterTransaction để xóa dữ liệu nhưng cleanup lại bị rollback

Nếu cleanup gọi một service hoặc repository tham gia vào một transaction khác đang tồn tại, kết quả phụ thuộc propagation. Hãy bảo đảm cleanup được commit hoặc dùng cơ chế cleanup độc lập.

### Chỉ kiểm tra entity trong cùng persistence context

Entity có thể còn trong first-level cache. Để xác nhận commit/rollback, hãy đọc sau transaction bằng một operation mới phù hợp.

### Bỏ qua REQUIRES_NEW

Transaction độc lập có thể commit dù transaction test bên ngoài rollback. Nếu nghiệp vụ có REQUIRES_NEW, hãy kiểm tra side effect đó sau khi test transaction kết thúc.

### Dùng callback để kiểm tra mọi side effect ngoài database

@AfterTransaction chỉ xác định thời điểm sau test-managed transaction. Nó không tự rollback message, email, HTTP request hoặc file. Các side effect đó cần test double hoặc cleanup riêng.

## 13. Quy trình thực hành

**Bước 1 – Xác định test có test-managed transaction không.** Kiểm tra @Transactional ở method hoặc class, transaction manager và cấu hình propagation.

**Bước 2 – Xác định trạng thái cần chuẩn bị.** Nếu dữ liệu phải tồn tại trước khi transaction test bắt đầu, cân nhắc @BeforeTransaction. Nếu dữ liệu nên được rollback cùng test, dùng @BeforeEach hoặc setup trong test method.

**Bước 3 – Xác định kết quả transaction.** Test sẽ rollback mặc định, commit bằng @Commit hay dùng @Rollback(false)?

**Bước 4 – Chọn điểm assertion.** Kiểm tra dữ liệu trong transaction ở test method; kiểm tra trạng thái sau commit/rollback trong @AfterTransaction.

**Bước 5 – Xem xét transaction do ứng dụng mở.** Kiểm tra @Transactional trên service, propagation REQUIRES_NEW hoặc TransactionTemplate có tạo transaction độc lập không.

**Bước 6 – Chuẩn bị dữ liệu riêng.** Dùng business key duy nhất để tránh test chạy song song hoặc dữ liệu cũ ảnh hưởng kết quả.

**Bước 7 – Thiết kế cleanup.** Dọn dữ liệu đã commit hoặc seed ngoài transaction bằng thao tác có transaction semantics rõ ràng.

**Bước 8 – Kiểm tra đúng persistence boundary.** Với JPA, phân biệt flush, persistence context và commit. Với HTTP server thật, phân biệt transaction test thread và server thread.

**Bước 9 – Chạy test độc lập và trong suite.** Đảm bảo callback được gọi đúng, dữ liệu không rò rỉ và kết quả không phụ thuộc thứ tự.

## 14. Bảng chọn callback

| Mục tiêu | Callback hoặc cơ chế phù hợp |
| --- | --- |
| Seed dữ liệu tồn tại trước test transaction | @BeforeTransaction |
| Kiểm tra baseline trước khi transaction bắt đầu | @BeforeTransaction |
| Tạo fixture sẽ rollback cùng test | @BeforeEach hoặc test method |
| Kiểm tra trạng thái đang nằm trong transaction | Test method hoặc @AfterEach |
| Xác nhận dữ liệu đã rollback | @AfterTransaction |
| Xác nhận dữ liệu đã commit | @Commit kết hợp @AfterTransaction |
| Kiểm tra side effect REQUIRES_NEW | @AfterTransaction |
| Cleanup dữ liệu đã commit | @AfterTransaction hoặc cleanup mechanism phù hợp |
| Kiểm tra hành vi không dùng test-managed transaction | Test lifecycle thông thường, không dựa vào hai callback này |

## 15. Nguyên tắc sử dụng an toàn

- Hiểu @BeforeTransaction và @AfterTransaction theo ranh giới test-managed transaction.
- Chỉ kỳ vọng callback chạy khi test method có transaction do Spring Test quản lý.
- Dùng @BeforeTransaction cho trạng thái phải có trước khi transaction test bắt đầu.
- Dùng @AfterTransaction để xác minh kết quả sau commit hoặc rollback.
- Nhớ rằng rollback mặc định; dùng @Commit hoặc @Rollback(false) khi cần kiểm tra commit.
- Không giả định callback không thể mở transaction khác.
- Phân biệt transaction của test với transaction do service/repository tự mở.
- Dùng dữ liệu định danh riêng và cleanup cho dữ liệu được tạo ngoài test transaction.
- Với JPA, phân biệt flush, persistence context và commit.
- Với HTTP server thật, không giả định transaction test thread bao trùm server thread.
- Không dùng context cleanup để thay thế cleanup database hoặc side effect bên ngoài.

## Kết luận

@BeforeTransaction và @AfterTransaction giúp kiểm thử những hành vi nằm ở hai phía của test-managed transaction trong Spring TestContext. Callback trước giao dịch phù hợp để chuẩn bị hoặc kiểm tra trạng thái nền; callback sau giao dịch phù hợp để xác minh dữ liệu đã commit hay rollback và kiểm tra những tác động được thực hiện trong transaction độc lập.

Điều quan trọng là hiểu chính xác phạm vi: hai callback nằm ngoài transaction do Spring Test quản lý cho test method, nhưng code được gọi bên trong callback vẫn có thể mở transaction riêng. Kết hợp chúng với @Transactional, @Commit, @Rollback, repository và transaction manager đúng cách sẽ giúp test kiểm tra được ranh giới commit/rollback, tránh nhầm lẫn giữa trạng thái trong persistence context và dữ liệu đã bền vững, đồng thời giữ dữ liệu kiểm thử độc lập.
