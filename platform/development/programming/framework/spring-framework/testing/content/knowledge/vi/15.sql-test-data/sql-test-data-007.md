# Chế độ giao dịch của script và phạm vi rollback

Spring TestContext Framework cho phép chạy SQL script để chuẩn bị dữ liệu trước kiểm thử hoặc dọn dữ liệu sau kiểm thử bằng **@Sql**. Một câu hỏi quan trọng là các câu lệnh trong script thuộc transaction nào. Nếu script tham gia transaction của test, thay đổi của nó có thể bị rollback cùng test. Nếu script chạy trong transaction độc lập và được commit ngay, dữ liệu có thể tồn tại sau khi test kết thúc.

Annotation **@SqlConfig** cung cấp thuộc tính **transactionMode** để điều khiển cách script tham gia giao dịch. Hai chế độ thường dùng là:

- **INFERRED:** Spring suy luận cách chạy script từ DataSource, PlatformTransactionManager và transaction đang hoạt động. Nếu có transaction của test, script thường tham gia transaction đó.
- **ISOLATED:** script chạy trong một transaction độc lập và transaction đó được commit ngay khi script hoàn tất thành công.

Chế độ giao dịch quyết định phạm vi rollback. Đây là điều cần nắm rõ khi dùng script seed dữ liệu, script cleanup, test có @Transactional, hoặc khi muốn xác minh dữ liệu sau commit. Một script được chạy thành công không đồng nghĩa dữ liệu của nó chắc chắn bị rollback khi test kết thúc.

## 1. @Sql dùng để làm gì?

@Sql là annotation của Spring TestContext Framework để khai báo SQL script cần chạy trong quá trình kiểm thử. Script thường chứa các câu lệnh INSERT, UPDATE hoặc DELETE nhằm chuẩn bị trạng thái database.

Ví dụ:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Sql("/db/test-data.sql")
class CustomerRepositoryTests {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void finds_customer_created_by_script() {
        assertThat(customerRepository.findById("C-100"))
            .isPresent();
    }
}
~~~

Script /db/test-data.sql thường được đặt trong **src/test/resources/db/test-data.sql** để có thể được tìm thấy qua classpath.

@Sql có thể được đặt ở:

- Cấp test class: áp dụng cho các test method trong class theo execution phase đã chọn.
- Cấp test method: áp dụng cho method cụ thể.
- Cùng với @SqlGroup hoặc khai báo lặp lại để chạy nhiều nhóm script.

Execution phase mặc định của @Sql là **BEFORE_TEST_METHOD**. Có thể dùng **AFTER_TEST_METHOD** để chạy script sau method:

~~~java
@Sql(
    scripts = "/db/cleanup-customer.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

@Sql chỉ xác định script và thời điểm thực thi. Cách script tham gia transaction được cấu hình riêng bằng @SqlConfig.

## 2. @SqlConfig và transactionMode

@SqlConfig cho phép cấu hình cách Spring chạy SQL script, bao gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| dataSource | Tên bean DataSource dùng để thực thi script |
| transactionManager | Tên bean PlatformTransactionManager dùng để quản lý transaction |
| transactionMode | Cách script tham gia hoặc tạo transaction |
| encoding | Encoding của file SQL |
| separator | Ký tự phân tách câu lệnh SQL |
| commentPrefix | Prefix của dòng comment |
| blockCommentStartDelimiter | Ký tự bắt đầu block comment |
| blockCommentEndDelimiter | Ký tự kết thúc block comment |
| errorMode | Cách xử lý lỗi khi thực thi script |

Thuộc tính quan trọng nhất trong bài học này là transactionMode.

~~~java
@Sql(
    scripts = "/db/seed-customers.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

SqlConfig.TransactionMode có ba giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| DEFAULT | Dùng chế độ mặc định được cấu hình toàn cục; nếu không có cấu hình toàn cục khác thì mặc định là INFERRED |
| INFERRED | Suy luận transaction từ cấu hình và trạng thái transaction hiện tại |
| ISOLATED | Chạy script trong transaction độc lập và commit transaction đó ngay khi hoàn tất thành công |

DEFAULT hữu ích khi test class có một @SqlConfig chung. Một khai báo @Sql riêng có thể dùng DEFAULT để tiếp tục áp dụng cấu hình chung. Nếu không có cấu hình toàn cục, chế độ mặc định cuối cùng là INFERRED.

## 3. INFERRED: để Spring suy luận transaction

INFERRED là chế độ mặc định của @SqlConfig nếu không có cấu hình toàn cục thay đổi. Spring xem xét DataSource, transaction manager và transaction hiện có để chọn cách thực thi script.

Quy tắc tổng quát:

1. Nếu có transaction manager và DataSource phù hợp, Spring thực thi script trong transaction do transaction manager quản lý.
2. Nếu đã có transaction đang hoạt động, script tham gia transaction hiện tại.
3. Nếu chưa có transaction đang hoạt động, Spring có thể tạo transaction cho script và commit transaction đó khi script hoàn tất.
4. Nếu chỉ có DataSource mà không có transaction manager, script được thực thi trực tiếp qua DataSource, không có transaction do Spring quản lý.
5. Nếu không thể xác định DataSource để chạy script, việc thực thi thất bại.

Vì vậy, INFERRED không có nghĩa là luôn rollback và cũng không có nghĩa là luôn commit. Kết quả phụ thuộc việc script có tham gia một transaction đang tồn tại hay phải chạy trong transaction riêng.

### 3.1. Script tham gia transaction của test

Đây là tình huống thường gặp khi test class hoặc test method có @Transactional.

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
@Sql("/db/seed-customers.sql")
class CustomerRepositoryTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void reads_seeded_customer() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = ?",
            Integer.class,
            "C-100"
        );

        assertThat(count).isEqualTo(1);
    }
}
~~~

Với cấu hình thông thường, TransactionalTestExecutionListener bắt đầu test-managed transaction trước khi test method chạy. Script @Sql ở phase BEFORE_TEST_METHOD được thực thi trong transaction đang hoạt động khi transactionMode là INFERRED. Các câu lệnh seed do đó tham gia transaction của test.

Sau khi test method kết thúc, Spring rollback transaction theo mặc định. Cả dữ liệu được tạo trong script và thay đổi do test method thực hiện đều bị rollback, miễn là chúng thực sự tham gia cùng transaction và database hỗ trợ rollback cho các câu lệnh đó.

Luồng khái quát:

~~~text
Spring bắt đầu test-managed transaction
                 |
                 v
       @Sql seed (INFERRED)
       tham gia transaction test
                 |
                 v
             @BeforeEach
                 |
                 v
             @Test method
                 |
                 v
       @AfterEach / @Sql sau test
       (nếu cùng transaction)
                 |
                 v
       Spring rollback transaction
                 |
                 v
      Dữ liệu trong transaction biến mất
~~~

Đây là lựa chọn thuận tiện khi dữ liệu script chỉ cần tồn tại trong phạm vi test và phải được dọn tự động bằng rollback.

### 3.2. INFERRED khi không có transaction đang hoạt động

Nếu test không có test-managed transaction nhưng Spring có thể xác định transaction manager và DataSource, script có thể được chạy trong transaction mới và commit khi script hoàn tất.

Ví dụ:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
class NonTransactionalSqlTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql("/db/seed-customer.sql")
    void reads_data_seeded_without_test_transaction() {
        assertThat(jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = 'C-200'",
            Integer.class
        )).isEqualTo(1);
    }
}
~~~

Trong tình huống này, không có test-managed transaction để script tham gia. Với transaction manager và DataSource được suy luận thành công, script được chạy trong transaction riêng và commit sau khi thực thi thành công. Dữ liệu có thể còn lại sau test.

Nếu test suite dùng database chung, cần cleanup hoặc định danh dữ liệu riêng. Không nên cho rằng chỉ vì test không có @Transactional thì script sẽ tự biến mất.

### 3.3. INFERRED khi chỉ có DataSource

Nếu Spring có thể tìm DataSource nhưng không có transaction manager phù hợp, script có thể được thực thi trực tiếp qua DataSource mà không có transaction do Spring quản lý.

Khi đó, khả năng rollback phụ thuộc cách JDBC connection được cấp và semantics của database. Nếu connection ở chế độ auto-commit, mỗi câu lệnh có thể được commit riêng. Không nên dựa vào rollback của test để dọn script trong cấu hình này.

Nếu cần rollback có kiểm soát, hãy cấu hình transaction manager phù hợp hoặc dùng một chiến lược database cleanup rõ ràng.

## 4. ISOLATED: chạy script trong transaction độc lập

ISOLATED yêu cầu script chạy trong một transaction mới, độc lập với transaction hiện tại, và commit transaction đó ngay khi script hoàn tất thành công.

Ví dụ:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class IsolatedSqlTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql(
        scripts = "/db/seed-customer.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void can_read_data_seeded_in_isolated_transaction() {
        // Script đã chạy trong transaction riêng và được commit.
        assertThat(jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = 'C-300'",
            Integer.class
        )).isEqualTo(1);
    }
}
~~~

Khi test-managed transaction đang hoạt động, Spring tạm ngưng transaction đó để chạy script trong transaction độc lập. Sau khi script hoàn tất thành công, transaction riêng được commit và transaction của test tiếp tục.

Khi test method kết thúc, rollback test-managed transaction không thể hoàn tác dữ liệu đã được commit trong transaction ISOLATED. Đây là khác biệt quan trọng nhất giữa ISOLATED và INFERRED khi có transaction của test.

### 4.1. ISOLATED cần cả DataSource và transaction manager

Để chạy transaction độc lập, Spring cần:

- DataSource để thực thi SQL.
- PlatformTransactionManager quản lý transaction cho DataSource đó.

Nếu không xác định được hai thành phần phù hợp, script không thể chạy theo chế độ ISOLATED và test sẽ thất bại khi chuẩn bị hoặc thực thi script.

Khi ứng dụng có nhiều DataSource hoặc nhiều transaction manager, hãy khai báo rõ:

~~~java
@Sql(
    scripts = "/db/seed-audit.sql",
    config = @SqlConfig(
        dataSource = "auditDataSource",
        transactionManager = "auditTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

DataSource và transaction manager phải quản lý cùng database hoặc cùng tài nguyên giao dịch. Nếu chọn nhầm transaction manager, script có thể chạy trên connection không được transaction đó quản lý, làm phạm vi rollback/commit khác với mong muốn.

### 4.2. ISOLATED không bị rollback cùng test transaction

Giả sử:

1. Test transaction bắt đầu.
2. Script ISOLATED chèn một customer và commit.
3. Test method cập nhật customer trong transaction của test.
4. Spring rollback test transaction.

Kết quả:

- Customer được chèn bởi script ISOLATED vẫn tồn tại.
- Thay đổi cập nhật trong test transaction bị rollback.

Đây là hành vi đúng theo ranh giới transaction. Nếu test không muốn dữ liệu seed tồn tại sau khi chạy, cần có script cleanup riêng hoặc cơ chế dọn dữ liệu tương đương.

## 5. So sánh INFERRED và ISOLATED theo phạm vi rollback

| Bối cảnh | INFERRED | ISOLATED |
| --- | --- | --- |
| Test có transaction đang hoạt động | Script tham gia transaction hiện tại | Script chạy trong transaction mới, độc lập |
| Test transaction rollback | Script tham gia cùng transaction cũng rollback | Script đã commit vẫn tồn tại |
| Test transaction commit | Script tham gia cùng transaction được commit cùng test | Script đã được commit độc lập trước đó |
| Không có transaction đang hoạt động, có transaction manager và DataSource | Script chạy trong transaction riêng và commit khi hoàn tất | Script chạy trong transaction độc lập và commit |
| Chỉ có DataSource | Chạy trực tiếp không có Spring-managed transaction | Không đủ điều kiện để chạy isolated transaction |
| Cần seed chỉ tồn tại trong test transaction | Thường phù hợp | Không phù hợp nếu không có cleanup |
| Cần seed tồn tại ngoài test transaction | Có thể không phù hợp khi script tham gia transaction test | Phù hợp |

Hãy chọn theo thời gian tồn tại mong muốn của dữ liệu:

- Dữ liệu fixture cần rollback cùng test: thường chọn INFERRED trong test có @Transactional.
- Dữ liệu cần commit độc lập để test quan sát sau transaction: chọn ISOLATED.
- Dữ liệu script được tạo khi không có test transaction: kiểm tra transaction manager và semantics commit của INFERRED trước khi giả định dữ liệu sẽ được dọn.

## 6. Kết hợp script seed và cleanup

Một mẫu hữu ích là seed dữ liệu trong transaction độc lập và chạy cleanup trong một transaction độc lập sau test:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class CustomerSqlLifecycleTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql(
        scripts = "/db/seed-customer-c400.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    @Sql(
        scripts = "/db/cleanup-customer-c400.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void reads_customer_seeded_outside_test_transaction() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = ?",
            Integer.class,
            "C-400"
        );

        assertThat(count).isEqualTo(1);
    }
}
~~~

seed-customer-c400.sql:

~~~sql
insert into customers(customer_id, customer_name)
values ('C-400', 'SQL test customer');
~~~

cleanup-customer-c400.sql:

~~~sql
delete from customers
where customer_id = 'C-400';
~~~

Script seed chạy trong transaction riêng và commit. Script cleanup được gọi ở AFTER_TEST_METHOD và cũng chạy trong transaction riêng. Vì vậy, cleanup được commit độc lập với test transaction.

Ví dụ này giả định ID C-400 dành riêng cho test. Trong suite chạy song song, hãy dùng ID duy nhất hoặc một cơ chế namespace để test không xóa dữ liệu của test khác hay dữ liệu dùng chung.

### 6.1. Vì sao cleanup cũng cần ISOLATED?

Nếu cleanup script tham gia transaction của test và transaction đó rollback sau khi test kết thúc, câu lệnh DELETE cũng có thể bị rollback. Khi đó, dữ liệu seed đã commit độc lập vẫn còn.

Đặt cleanup ở ISOLATED giúp câu lệnh DELETE được commit trong transaction riêng. Tuy nhiên, chỉ nên làm vậy khi test thật sự cần dữ liệu seed tồn tại ngoài transaction. Với seed INFERRED tham gia transaction test, rollback thường đã dọn cả seed và thay đổi test; không cần thêm cleanup độc lập.

### 6.2. Cleanup phải an toàn khi assertion thất bại

Nếu assertion trong test method thất bại, Spring vẫn thực hiện lifecycle kết thúc transaction và callback AFTER_TEST_METHOD theo cấu hình listener. Script cleanup có thể giúp dọn dữ liệu đã commit độc lập.

Tuy vậy, cleanup script cũng có thể thất bại vì database lỗi, khóa ngoại hoặc dữ liệu đã bị thay đổi. Hãy viết cleanup idempotent khi có thể, chẳng hạn DELETE theo khóa duy nhất, và bảo đảm nó không ảnh hưởng dữ liệu ngoài phạm vi test.

## 7. Cấu hình @SqlConfig toàn cục và cục bộ

@SqlConfig có thể được đặt ở cấp class để làm cấu hình chung cho các khai báo @Sql. Một @SqlConfig nằm trong thuộc tính config của @Sql có thể điều chỉnh cho script cụ thể.

Ví dụ:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@SqlConfig(
    dataSource = "testDataSource",
    transactionManager = "testTransactionManager",
    transactionMode = SqlConfig.TransactionMode.INFERRED
)
class SharedSqlConfigurationTests {

    @Test
    @Sql("/db/seed-default.sql")
    void uses_global_inferred_mode() {
        // ...
    }

    @Test
    @Sql(
        scripts = "/db/seed-independent.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void overrides_transaction_mode_for_this_script() {
        // ...
    }
}
~~~

Trong ví dụ, class-level @SqlConfig cung cấp DataSource, transaction manager và chế độ chung. Script thứ nhất dùng cấu hình chung. Script thứ hai yêu cầu ISOLATED cho trường hợp riêng.

Giá trị DEFAULT trong cấu hình cục bộ cho phép dùng giá trị mặc định toàn cục. Nếu không có cấu hình toàn cục, DEFAULT cuối cùng tương ứng với chế độ mặc định INFERRED.

### 7.1. Khi có nhiều DataSource

Nếu ứng dụng có nhiều database, không nên dựa vào việc Spring tự suy luận một DataSource hoặc transaction manager duy nhất. Khai báo rõ tên bean:

~~~java
@SqlConfig(
    dataSource = "reportingDataSource",
    transactionManager = "reportingTransactionManager",
    transactionMode = SqlConfig.TransactionMode.ISOLATED
)
~~~

Điều này giúp script chạy đúng database và transaction manager. Hãy xác nhận hai bean quản lý cùng một resource. Một DataSource và một transaction manager không tương thích có thể làm cho script không nằm trong transaction mà người viết test tưởng rằng nó đang dùng.

### 7.2. Khi dùng nhiều script với chế độ khác nhau

Có thể khai báo nhiều @Sql với config riêng:

~~~java
@Test
@Sql(
    scripts = "/db/seed-reference-data.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/db/seed-temporary-data.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
void combines_independent_and_test_scoped_fixtures() {
    // ...
}
~~~

Script reference data được commit độc lập, còn temporary data có thể tham gia test transaction và rollback cùng test. Chỉ dùng cách kết hợp này khi vòng đời dữ liệu của hai nhóm thực sự khác nhau.

## 8. Script chạy trước hay sau test method?

Execution phase ảnh hưởng thời điểm script được gọi; transactionMode quyết định cách script tham gia transaction tại thời điểm đó.

| Execution phase | Thời điểm | Mục đích thường gặp |
| --- | --- | --- |
| BEFORE_TEST_METHOD | Trước mỗi test method | Seed fixture |
| AFTER_TEST_METHOD | Sau mỗi test method | Cleanup hoặc kiểm tra trạng thái bằng script |
| BEFORE_TEST_CLASS | Trước các test method của class | Chuẩn bị dữ liệu dùng chung cho class |
| AFTER_TEST_CLASS | Sau các test method của class | Dọn dữ liệu dùng chung của class |

BEFORE_TEST_CLASS và AFTER_TEST_CLASS được hỗ trợ trong các phiên bản Spring Framework mới hơn, bắt đầu từ Spring Framework 6.1. Với dự án dùng phiên bản cũ, hãy kiểm tra enum ExecutionPhase trong Javadoc của đúng phiên bản; hai phase theo class có thể chưa có.

Dù script chạy ở phase nào, đừng suy luận phạm vi rollback chỉ từ tên phase. Hãy xác định có transaction nào đang hoạt động, transaction manager nào được dùng và transactionMode là gì.

### 8.1. Script AFTER_TEST_METHOD không tự động chạy ngoài transaction

Một nhầm lẫn phổ biến là nghĩ script cleanup sau test method luôn nằm ngoài test transaction. Spring TestExecutionListener có thứ tự callback riêng. Script AFTER_TEST_METHOD có thể được thực thi khi test-managed transaction vẫn còn hoạt động, tùy thứ tự listener và cấu hình test.

Nếu cleanup phải được commit độc lập, hãy khai báo transactionMode = ISOLATED thay vì dựa vào phase AFTER_TEST_METHOD.

### 8.2. Script BEFORE_TEST_CLASS và transaction

Script chạy trước các method có thể không có test-managed transaction của từng method để tham gia. Khi INFERRED và transaction manager/DataSource phù hợp, script có thể được chạy trong transaction riêng và commit. Nếu muốn dữ liệu tồn tại xuyên suốt các test method, hãy xác định rõ chính sách cleanup ở cấp class.

## 9. Phạm vi rollback: điều gì được hoàn tác?

Rollback chỉ hoàn tác những thay đổi thuộc transaction đã rollback và được database/resource hỗ trợ rollback. Không nên coi rollback như thao tác khôi phục toàn bộ hệ thống.

### 9.1. Thay đổi trong cùng transaction

Nếu script INFERRED tham gia test-managed transaction, các câu lệnh DML của script và thao tác của test cùng thuộc transaction. Khi Spring rollback, các thay đổi đó thường bị hoàn tác cùng nhau.

### 9.2. Thay đổi trong transaction ISOLATED

Script ISOLATED chạy trong transaction riêng và commit. Rollback transaction test không ảnh hưởng đến thay đổi đã commit. Muốn xóa dữ liệu, cần cleanup riêng hoặc database được tạo mới theo vòng đời test.

### 9.3. Side effect bên ngoài database

Transaction JDBC/JPA không tự động rollback:

- Email đã gửi.
- HTTP request đã gửi tới hệ thống ngoài.
- Message đã publish vào broker nếu broker không tham gia cùng transaction.
- File đã ghi trên filesystem.
- Cache phân tán đã cập nhật.
- Giao dịch thanh toán đã được provider xác nhận.

Những tác động này cần test double, transaction coordination phù hợp, outbox pattern hoặc cleanup riêng. Không nên dùng @Sql transactionMode để suy luận về side effect không nằm trong database được transaction manager quản lý.

### 9.4. DDL và đặc tính của database

Một số database có quy tắc riêng với DDL như CREATE TABLE, ALTER TABLE hoặc TRUNCATE. Có hệ quản trị tự động commit một số câu lệnh hoặc không rollback chúng theo cách giống DML.

Vì vậy, dù script nằm trong transaction, không thể mặc định mọi DDL đều được rollback. Hãy kiểm tra semantics của database đang dùng và tách schema setup khỏi dữ liệu fixture khi phù hợp.

### 9.5. Sequence, identity và giá trị tự tăng

Một số database không hoàn tác việc cấp số sequence hoặc identity khi transaction rollback. Bản ghi có thể biến mất nhưng số thứ tự đã cấp không quay lại. Test không nên giả định ID tiếp theo phải liên tục hoặc bằng một giá trị cố định trừ khi database và cấu hình bảo đảm điều đó.

## 10. @Sql và test-managed transaction

Khi test class hoặc test method có @Transactional, Spring TestContext thường bắt đầu transaction trước khi test method chạy và rollback sau method. @Sql được tích hợp qua SqlScriptsTestExecutionListener.

Một cấu hình phổ biến:

~~~java
@SpringJUnitConfig(JpaTestConfig.class)
@Transactional
class ProductRepositorySqlTests {

    @Autowired
    ProductRepository repository;

    @Test
    @Sql(
        scripts = "/db/products.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void loads_product_seeded_by_sql() {
        assertThat(repository.findBySku("SKU-1"))
            .isPresent();
    }
}
~~~

Script chạy trong test transaction và dữ liệu được rollback sau test theo mặc định. Đây thường là cách đơn giản nhất để seed dữ liệu cho repository test.

Nếu test dùng @Commit:

~~~java
@Test
@Commit
@Sql("/db/products.sql")
void commits_test_transaction() {
    // ...
}
~~~

Script INFERRED tham gia transaction test và được commit cùng transaction đó. Nếu script ISOLATED, nó đã commit độc lập ngay khi script hoàn tất, không cần chờ @Commit.

## 11. Kết hợp với @Rollback, @Commit và @AfterTransaction

@Sql điều khiển script. @Transactional, @Rollback và @Commit điều khiển test-managed transaction. @AfterTransaction cho phép kiểm tra trạng thái sau khi transaction test kết thúc.

Ba cơ chế có thể phối hợp:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class SqlRollbackTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql("/db/seed-in-transaction.sql")
    void sees_seed_data_inside_test_transaction() {
        assertThat(countRows("TEST-1")).isEqualTo(1);
    }

    @AfterTransaction
    void verifies_seed_data_was_rolled_back() {
        assertThat(countRows("TEST-1")).isZero();
    }

    private int countRows(String id) {
        return jdbcTemplate.queryForObject(
            "select count(*) from sample_data where id = ?",
            Integer.class,
            id
        );
    }
}
~~~

Trong ví dụ, script INFERRED tham gia transaction test. Sau rollback, @AfterTransaction xác nhận dữ liệu không còn.

Nếu đổi script sang ISOLATED, assertion sau transaction phải thay đổi vì dữ liệu seed đã được commit riêng. Nếu muốn dữ liệu không còn sau test, cần thêm cleanup ISOLATED hoặc một cơ chế cleanup khác.

### 11.1. Đừng dùng @AfterTransaction như cơ chế tự động dọn mọi script

@AfterTransaction là callback Java. Nó không tự động xóa dữ liệu do @Sql tạo. Có thể dùng callback để gọi repository hoặc JdbcTemplate cleanup, nhưng phải bảo đảm thao tác cleanup được commit ngoài test transaction.

Nếu muốn dùng SQL script cho cleanup, khai báo @Sql với executionPhase AFTER_TEST_METHOD và transactionMode phù hợp.

## 12. Những lỗi thường gặp

### Nghĩ INFERRED luôn rollback

INFERRED tham gia transaction đang hoạt động nếu có. Nếu không có transaction test, Spring có thể tạo transaction riêng và commit script. Hãy kiểm tra transaction thực tế trước khi dự đoán dữ liệu có còn sau test không.

### Nghĩ ISOLATED vẫn rollback cùng test

ISOLATED commit transaction riêng. Rollback test transaction không thể hoàn tác dữ liệu đã commit độc lập. Cần cleanup riêng nếu dữ liệu không được phép tồn tại sau test.

### Dùng ISOLATED nhưng không có transaction manager

ISOLATED cần DataSource và transaction manager phù hợp. Nếu thiếu, script không thể chạy theo chế độ yêu cầu.

### Chọn nhầm DataSource hoặc transaction manager

Khi ứng dụng có nhiều database, script có thể chạy trên một DataSource trong khi transaction manager quản lý DataSource khác. Hãy khai báo tên bean tương ứng trong @SqlConfig.

### Cho rằng AFTER_TEST_METHOD luôn nằm ngoài transaction

Phase chỉ xác định thời điểm gọi script. Nếu script tham gia transaction test, cleanup có thể bị rollback. Muốn commit cleanup độc lập, dùng ISOLATED.

### Cleanup dữ liệu dùng chung

Một script DELETE thiếu điều kiện có thể xóa dữ liệu của test khác hoặc dữ liệu môi trường. Dùng khóa riêng cho từng test, namespace hoặc database/schema riêng.

### Dựa vào rollback cho DDL

DDL và sequence có semantics riêng theo database. Hãy kiểm tra tài liệu của hệ quản trị và tách schema lifecycle khỏi DML fixture khi cần.

### Không kiểm tra side effect ngoài database

Rollback database không thu hồi email, HTTP request, message hoặc file. Hãy kiểm tra và cleanup những tác động đó bằng cơ chế phù hợp.

## 13. Quy trình chọn transactionMode

**Bước 1 – Xác định mục đích script.** Script dùng để seed fixture, tạo trạng thái nền, kiểm tra dữ liệu hay cleanup?

**Bước 2 – Xác định test có test-managed transaction không.** Kiểm tra @Transactional trên class/method và cấu hình propagation.

**Bước 3 – Xác định dữ liệu có nên rollback cùng test không.** Nếu có, INFERRED thường phù hợp khi script chạy trong transaction test.

**Bước 4 – Xác định dữ liệu có cần commit độc lập không.** Nếu có, chọn ISOLATED và bảo đảm có DataSource cùng transaction manager.

**Bước 5 – Chọn đúng database resource.** Khi có nhiều DataSource hoặc transaction manager, khai báo tên rõ ràng trong @SqlConfig.

**Bước 6 – Chọn execution phase.** Dùng BEFORE_TEST_METHOD để seed trước method, AFTER_TEST_METHOD để cleanup sau method, hoặc phase cấp class khi phiên bản Spring hỗ trợ và vòng đời dữ liệu phù hợp.

**Bước 7 – Xác định cleanup.** Nếu seed được commit độc lập, lên kế hoạch cleanup độc lập. Dùng khóa dữ liệu riêng để cleanup an toàn.

**Bước 8 – Xem xét database semantics.** Kiểm tra DDL, sequence, identity và các câu lệnh có thể tự commit.

**Bước 9 – Xác minh sau transaction.** Dùng @AfterTransaction hoặc một truy vấn mới để xác nhận dữ liệu còn hay đã rollback theo kỳ vọng.

**Bước 10 – Chạy test độc lập và trong suite.** Đảm bảo script không phụ thuộc thứ tự, không xóa dữ liệu ngoài phạm vi và không để lại fixture đã commit ngoài ý muốn.

## 14. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn thường phù hợp |
| --- | --- |
| Script phải rollback cùng test-managed transaction? | INFERRED |
| Script phải tồn tại sau khi test transaction rollback? | ISOLATED |
| Script cleanup phải được commit độc lập sau test? | AFTER_TEST_METHOD kết hợp ISOLATED |
| Test không có transaction nhưng có transaction manager và DataSource? | INFERRED có thể tạo transaction riêng và commit script |
| Chỉ có DataSource, không có transaction manager? | INFERRED chạy không có Spring-managed transaction; không dựa vào rollback |
| Ứng dụng có nhiều database? | Khai báo dataSource và transactionManager tường minh |
| Chỉ muốn dùng cấu hình @SqlConfig chung? | DEFAULT ở khai báo cục bộ hoặc không khai báo config riêng |
| Script có DDL hoặc sequence? | Kiểm tra semantics cụ thể của database |

## 15. Nguyên tắc thực hành

- Luôn xác định transaction nào đang hoạt động khi @Sql chạy.
- Dùng INFERRED khi muốn script tham gia transaction test và rollback cùng test.
- Dùng ISOLATED khi script cần transaction riêng được commit ngay.
- Nhớ ISOLATED yêu cầu DataSource và transaction manager tương ứng.
- Phân biệt executionPhase với transactionMode: một cái chọn thời điểm, một cái chọn phạm vi giao dịch.
- Nếu seed ISOLATED, cần nghĩ đến cleanup ISOLATED.
- Dùng @SqlConfig toàn cục để chia sẻ cấu hình và cấu hình cục bộ cho ngoại lệ có chủ đích.
- Khi có nhiều DataSource, chọn đúng DataSource và transaction manager.
- Không giả định rollback database thu hồi side effect ngoài database.
- Kiểm tra semantics DDL, sequence và identity theo hệ quản trị thực tế.
- Dùng khóa dữ liệu riêng để test chạy song song an toàn.

## Kết luận

transactionMode của @SqlConfig quyết định script SQL tham gia transaction hiện có hay chạy trong transaction độc lập. INFERRED để Spring suy luận: nếu có test-managed transaction phù hợp, script thường tham gia và bị rollback cùng test; nếu không có transaction đang hoạt động nhưng có transaction manager và DataSource, script có thể chạy trong transaction riêng rồi commit. ISOLATED luôn yêu cầu transaction độc lập được commit ngay khi script hoàn tất thành công.

Hãy tách rõ thời điểm chạy script và phạm vi rollback. BEFORE_TEST_METHOD hoặc AFTER_TEST_METHOD không tự quyết định dữ liệu có tồn tại sau test. Điều đó phụ thuộc transactionMode, transaction manager, DataSource và semantics của database. Khi chọn đúng chế độ, seed và cleanup có thể được kiểm soát rõ ràng, test tránh để lại dữ liệu ngoài ý muốn và assertion phản ánh chính xác trạng thái sau commit hoặc rollback.
