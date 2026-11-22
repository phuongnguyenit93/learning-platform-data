# Chọn DataSource và transaction manager cho script

Spring TestContext Framework hỗ trợ chạy SQL script trước hoặc sau test method thông qua **@Sql**. Cơ chế này thường dùng để tạo dữ liệu ban đầu, chuẩn bị trạng thái cho repository test hoặc dọn dữ liệu sau khi kiểm thử. Để script chạy đúng database và đúng ranh giới transaction, Spring cần biết **DataSource** nào cung cấp kết nối JDBC và **PlatformTransactionManager** nào quản lý transaction cho script.

Trong ứng dụng đơn giản chỉ có một database, Spring thường có thể tự suy ra hai bean này. Nhưng khi ApplicationContext có nhiều DataSource hoặc nhiều transaction manager, việc suy luận có thể mơ hồ hoặc chọn nhầm database. Khi đó, **@SqlConfig** cho phép chỉ định rõ bean cần dùng.

Bài học này giải thích vai trò của DataSource và transaction manager, cách cấu hình chúng cho **@Sql**, cách xử lý nhiều database, sự khác nhau giữa transaction mode **INFERRED** và **ISOLATED**, cũng như cách lựa chọn phù hợp cho script setup và cleanup.

## 1. @Sql thực thi script bằng DataSource nào?

**@Sql** yêu cầu Spring TestContext chạy một hoặc nhiều câu lệnh SQL trong một test class hoặc test method. Ví dụ:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql("/sql/orders-before-test.sql")
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsPreparedOrder() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

Khi xử lý annotation, Spring cần thực thi script qua JDBC. **DataSource** là thành phần cung cấp kết nối tới database. Script được chạy bằng kết nối lấy từ DataSource được chọn trong ApplicationContext.

Ví dụ file orders-before-test.sql:

~~~sql
INSERT INTO customers (id, name)
VALUES ('customer-test-18', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('order-test-188', 'customer-test-18', 'PENDING');
~~~

DataSource quyết định các câu lệnh trên tác động vào database nào. Nếu ứng dụng có database đơn hàng và database thanh toán, việc chọn nhầm DataSource có thể khiến script thất bại vì thiếu bảng hoặc ghi dữ liệu vào một database không thuộc kịch bản test.

Vì vậy, khi có nhiều DataSource, hãy chỉ định bean name thay vì trông cậy vào suy luận tự động.

## 2. Transaction manager chịu trách nhiệm gì?

**PlatformTransactionManager** quản lý transaction cho một tài nguyên hoặc một nhóm tài nguyên. Với JDBC, implementation thường gặp là **DataSourceTransactionManager**. Với JPA, thường dùng **JpaTransactionManager**.

DataSource và transaction manager có vai trò khác nhau:

- DataSource cung cấp kết nối JDBC để chạy SQL.
- Transaction manager bắt đầu, commit, rollback hoặc tham gia transaction.
- @SqlConfig liên kết script với DataSource và transaction manager phù hợp.
- @Transactional trên test class hoặc method chọn transaction manager cho test-managed transaction.

Ví dụ cấu hình JDBC:

~~~java
@Configuration
class OrderDatabaseTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://localhost:5432/orders_test");
        dataSource.setUsername("orders_test_user");
        dataSource.setPassword("test-only-password");
        return dataSource;
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Đây là ví dụ minh họa wiring. Trong dự án thực tế, thông tin kết nối nên được đưa vào property source phù hợp; credential thật không nên hard-code trong test configuration hoặc commit vào repository.

Với JPA, transaction manager thường gắn với EntityManagerFactory tương ứng:

~~~java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Không nên ghép một DataSource của database này với transaction manager của database khác. Nếu script chạy trên DataSource A nhưng transaction manager quản lý DataSource B, script có thể không tham gia transaction mà test đang rollback. Kết quả là dữ liệu được commit hoặc giữ lại ngoài dự kiến.

## 3. Chỉ định DataSource bằng @SqlConfig

**@SqlConfig** có thuộc tính **dataSource** để chọn bean DataSource theo tên trong ApplicationContext.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(dataSource = "ordersDataSource")
)
class OrderRepositoryTest {
}
~~~

Trong ví dụ, Spring dùng bean tên ordersDataSource để lấy kết nối và chạy script.

Có thể cấu hình nhiều script trong một annotation:

~~~java
@Sql(
    scripts = {
        "/sql/orders-schema.sql",
        "/sql/orders-before-test.sql"
    },
    config = @SqlConfig(dataSource = "ordersDataSource")
)
~~~

Thứ tự resource trong danh sách được giữ khi thực thi. Điều này hữu ích khi script đầu tạo schema hoặc bảng, còn script sau chèn dữ liệu fixture.

### Khi chỉ có một DataSource

Nếu context chỉ có một bean DataSource phù hợp, Spring thường có thể suy luận DataSource đó khi không khai báo dataSource. Tuy vậy, khai báo tường minh có lợi khi cấu hình test được chia sẻ với module khác hoặc có thể phát triển thành context nhiều database.

Khi có nhiều candidate, hãy dùng bean name trong @SqlConfig. Không dựa vào thứ tự khai báo bean hoặc giả định rằng bean được tạo trước sẽ luôn được chọn.

## 4. Chỉ định transaction manager bằng @SqlConfig

Thuộc tính **transactionManager** của **@SqlConfig** chọn bean PlatformTransactionManager dùng để quản lý transaction khi chạy script.

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
class OrderRepositoryTest {
}
~~~

Việc chỉ định cả hai bean làm rõ rằng script dùng DataSource của database đơn hàng và transaction manager quản lý database đó.

Nếu test class cũng được đánh dấu @Transactional, hãy chọn cùng transaction manager:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
class OrderRepositoryTransactionalTest {
}
~~~

Cách khai báo này giúp test-managed transaction và SQL script dùng cùng transaction manager. Khi transaction mode là INFERRED, script có thể tham gia transaction đang hoạt động và dữ liệu fixture được rollback cùng test.

Với Spring Framework hiện đại, có thể dùng thuộc tính transactionManager của @Transactional; dạng giá trị chuỗi rút gọn như trên thường được dùng để chỉ định bean name. Nếu ứng dụng có nhiều manager, đừng bỏ qua bước xác định manager nào quản lý repository đang được kiểm tra.

## 5. Cơ chế suy luận DataSource và transaction manager

Khi không khai báo dataSource hoặc transactionManager, Spring TestContext cố gắng tìm bean phù hợp trong ApplicationContext. Cơ chế suy luận thuận tiện cho cấu hình đơn giản, nhưng có thể trở nên mơ hồ khi ứng dụng có nhiều database.

Các quy tắc lựa chọn có thể xét đến bean name, kiểu bean, qualifier và primary theo cơ chế tìm dependency của Spring TestContext. Vì vậy:

- Một DataSource duy nhất thường được suy luận dễ dàng.
- Một transaction manager duy nhất thường được suy luận dễ dàng.
- Nếu có nhiều bean cùng loại, Spring cần một candidate rõ ràng hoặc thông tin định danh.
- Nếu không thể xác định bean phù hợp, việc thực thi script có thể thất bại với lỗi phân giải dependency hoặc lỗi khởi tạo SQL execution.

Tên bean mặc định như dataSource hoặc transactionManager thường xuất hiện trong ứng dụng Spring, nhưng không nên dựa vào quy ước đó khi context có nhiều candidate.

**Quy tắc thực hành:** nếu test có nhiều hơn một DataSource hoặc transaction manager, hãy chỉ định bean name trong @SqlConfig. Cấu hình tường minh giúp người đọc thấy script đang tác động đến database nào và transaction nào bảo vệ nó.

## 6. Ứng dụng có nhiều DataSource

Một ứng dụng có thể tách dữ liệu theo module hoặc loại nghiệp vụ, ví dụ:

- ordersDataSource: đơn hàng và khách hàng.
- billingDataSource: hóa đơn và thanh toán.
- reportingDataSource: dữ liệu báo cáo.

Mỗi DataSource có thể có transaction manager riêng. Khi test cần chuẩn bị dữ liệu cho một database, hãy chỉ định đúng cặp bean.

Ví dụ cấu hình hai database:

~~~java
@Configuration
class MultiDatabaseTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        return createTestDataSource("jdbc:postgresql://localhost:5432/orders_test");
    }

    @Bean("billingDataSource")
    DataSource billingDataSource() {
        return createTestDataSource("jdbc:postgresql://localhost:5432/billing_test");
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    private DataSource createTestDataSource(String url) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(url);
        dataSource.setUsername("test_user");
        dataSource.setPassword("test_password");
        return dataSource;
    }
}
~~~

Ví dụ dùng cùng helper để rút gọn cấu hình; các URL và credential chỉ là minh họa. Trong dự án thật, lấy chúng từ property hoặc secret source riêng.

Script cho database đơn hàng:

~~~java
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
~~~

Script cho database thanh toán:

~~~java
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
~~~

Nếu một test method cần chạy script trên cả hai database, có thể khai báo nhiều @Sql hoặc dùng @SqlGroup. Mỗi annotation cần chỉ định đúng DataSource và transaction manager tương ứng.

Lưu ý rằng hai transaction manager cục bộ không tự tạo thành một transaction phân tán. Nếu test cần tính nguyên tử trên nhiều database, phải có kiến trúc transaction phù hợp, chẳng hạn JTA/XA hoặc cơ chế nhất quán riêng của ứng dụng. Chạy hai script với hai manager riêng không đảm bảo cả hai database cùng commit hoặc cùng rollback.

## 7. Chạy script trên nhiều DataSource trong cùng test

Spring cho phép khai báo nhiều @Sql trên cùng class hoặc method. Mỗi script có thể dùng cấu hình riêng:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
class OrderBillingIntegrationTest {
}
~~~

Khi dùng nhiều annotation @Sql, hãy nhớ rằng mỗi script được thực thi theo transaction mode và transaction manager riêng. Nếu script thứ nhất thành công nhưng script thứ hai thất bại, thay đổi ở database thứ nhất có thể đã được commit tùy cấu hình transaction.

Nếu cần một trạng thái khởi tạo nhất quán trên nhiều database, hãy thiết kế setup và cleanup có khả năng chạy lại an toàn, hoặc dùng một chiến lược quản lý dữ liệu test ở cấp integration suite. Không nên giả định Spring tự tạo một transaction chung cho nhiều DataSource chỉ vì các script nằm trên cùng test class.

## 8. transactionMode INFERRED là gì?

**INFERRED** là transaction mode mặc định của @SqlConfig. Spring suy luận cách chạy script dựa trên transaction hiện tại và transaction manager có sẵn.

Về nguyên tắc:

- Nếu test-managed transaction đang hoạt động và script dùng cùng transaction manager, script có thể tham gia transaction đó.
- Nếu không có transaction đang hoạt động nhưng có transaction manager phù hợp, Spring có thể tạo transaction cho việc thực thi script.
- Nếu không có transaction manager phù hợp, script có thể được chạy trực tiếp trên DataSource mà không có transaction do Spring quản lý.

Vì vậy, INFERRED thường phù hợp với script setup chạy trong một test transactional. Script được chạy trong transaction của test và dữ liệu fixture sẽ rollback cùng test theo mặc định.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
class OrderRepositoryTest {
}
~~~

Ở đây, script dùng cùng transaction manager với test. Dữ liệu được chèn trước test method có thể được nhìn thấy trong transaction và bị rollback sau khi test kết thúc.

Có thể bỏ thuộc tính transactionMode vì INFERRED là mặc định. Viết tường minh có ích khi tài liệu hóa ý định hoặc khi so sánh với script khác dùng ISOLATED.

## 9. transactionMode ISOLATED là gì?

**ISOLATED** yêu cầu Spring chạy script trong một transaction độc lập, tách khỏi transaction hiện tại. Transaction độc lập được commit ngay sau khi script thực thi thành công.

~~~java
@Sql(
    scripts = "/sql/orders-baseline.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

Mode này cần transaction manager phù hợp. Spring tạm dừng transaction hiện tại nếu có, mở transaction độc lập để chạy script, rồi commit transaction đó.

Một số tình huống phù hợp:

- Tạo dữ liệu baseline phải tồn tại ngoài test-managed transaction.
- Chuẩn bị dữ liệu đã commit để một transaction khác có thể đọc.
- Chạy cleanup cần commit ngay cả khi transaction của test sẽ rollback.
- Tạo trạng thái ban đầu cho một luồng xử lý chạy ở thread hoặc transaction khác.

### Tác động của ISOLATED lên rollback mặc định

Giả sử test method có @Transactional và script setup dùng ISOLATED:

~~~text
@BeforeTestMethod
    |
    v
Test transaction bắt đầu
    |
    v
@Sql với ISOLATED
    |
    +--> Tạm dừng test transaction
    |
    +--> Mở transaction riêng
    |
    +--> Chạy script và commit
    |
    v
Tiếp tục test transaction
    |
    v
@Test và @AfterEach
    |
    v
Test transaction rollback
~~~

Dữ liệu do script ISOLATED tạo đã được commit trong transaction riêng, vì vậy rollback của test transaction không xóa dữ liệu đó. Test cần cleanup dữ liệu baseline này bằng một script hoặc cơ chế cleanup có phạm vi rõ ràng.

Không nên chọn ISOLATED chỉ vì muốn script “chạy chắc chắn”. Nếu mục tiêu là fixture chỉ tồn tại trong test và rollback cùng test, INFERRED thường phù hợp hơn.

## 10. So sánh INFERRED và ISOLATED

| Tiêu chí | INFERRED | ISOLATED |
|---|---|---|
| Vai trò | Suy luận transaction từ ngữ cảnh | Luôn yêu cầu transaction riêng |
| Tham gia test transaction đang hoạt động | Có thể, nếu cùng manager | Không |
| Cần transaction manager | Có thể không, nếu script chạy không transaction | Có |
| Kết quả khi script thành công | Theo transaction mà script tham gia hoặc transaction được suy luận | Transaction riêng được commit ngay |
| Dữ liệu có rollback cùng test không? | Có nếu script tham gia test transaction | Không, vì đã commit độc lập |
| Trường hợp thường dùng | Fixture gắn với vòng đời test | Baseline cần tồn tại ngoài transaction test |

Chọn mode theo vòng đời dữ liệu:

- Dữ liệu chỉ phục vụ một test và nên biến mất sau rollback: dùng INFERRED với test transaction phù hợp.
- Dữ liệu cần tồn tại sau khi test transaction rollback: dùng ISOLATED và lập kế hoạch cleanup.
- Script cần chạy khi không có test transaction nhưng vẫn cần transaction riêng: cân nhắc ISOLATED.
- Script không cần transaction hoặc database không hỗ trợ transaction cho thao tác đó: hiểu rõ giới hạn trước khi dùng mode mặc định.

## 11. Cấu hình mặc định ở cấp class bằng @SqlConfig

Nếu nhiều script trong một test class dùng cùng DataSource và transaction manager, có thể khai báo @SqlConfig ở cấp class để đặt mặc định:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@SqlConfig(
    dataSource = "ordersDataSource",
    transactionManager = "ordersTransactionManager",
    transactionMode = SqlConfig.TransactionMode.INFERRED
)
class OrderRepositoryTest {

    @Test
    @Sql("/sql/orders-before-test.sql")
    void findsOrder() {
        // Test body
    }

    @Test
    @Sql("/sql/orders-with-lines.sql")
    void findsOrderWithLines() {
        // Test body
    }
}
~~~

Class-level @SqlConfig cung cấp cấu hình mặc định cho các khai báo @Sql trong class. Nếu một script cần DataSource hoặc transaction manager khác, có thể cấu hình riêng trên annotation @Sql tương ứng:

~~~java
@Test
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
void loadsBillingData() {
}
~~~

Cách tổ chức này giảm lặp lại nhưng vẫn cho phép một test method chọn database riêng. Hãy giữ cấu hình class-level phù hợp với phần lớn script; nếu mỗi method đều cần override, cấu hình chung có thể không còn giúp ích.

## 12. Dùng @Sql ở phase setup và cleanup

@Sql có thuộc tính executionPhase để chỉ định khi nào script chạy:

- **BEFORE_TEST_METHOD**: trước từng test method; đây là mặc định.
- **AFTER_TEST_METHOD**: sau từng test method.

Ví dụ setup:

~~~java
@Test
@Sql(
    scripts = "/sql/orders-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
void findsOrder() {
}
~~~

Ví dụ cleanup với transaction độc lập:

~~~java
@Test
@Sql(
    scripts = "/sql/orders-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void cleansCommittedFixture() {
}
~~~

Cleanup script dùng ISOLATED khi cần commit thao tác dọn độc lập với transaction của test. Nếu cleanup chạy trong transaction test rồi test rollback, thao tác xóa có thể cũng bị rollback. Hãy chọn mode theo trạng thái dữ liệu sau test.

Một cách khác là dùng script setup ISOLATED và script cleanup ISOLATED để quản lý fixture đã commit. Cả hai cần giới hạn chính xác các ID hoặc namespace thuộc test.

## 13. @SqlGroup và nhiều script có cấu hình khác nhau

Khi cần nhiều khai báo @Sql với cấu hình khác nhau, có thể lặp annotation trên Java hiện đại hoặc dùng @SqlGroup để nhóm chúng:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfig.class)
@SqlGroup({
    @Sql(
        scripts = "/sql/orders-before-test.sql",
        config = @SqlConfig(
            dataSource = "ordersDataSource",
            transactionManager = "ordersTransactionManager"
        )
    ),
    @Sql(
        scripts = "/sql/billing-before-test.sql",
        config = @SqlConfig(
            dataSource = "billingDataSource",
            transactionManager = "billingTransactionManager"
        )
    )
})
class CrossDatabaseTest {
}
~~~

**@SqlGroup** hữu ích khi cần thể hiện một nhóm script setup hoặc cleanup. Mỗi @Sql vẫn có thể có config riêng. Việc nhóm annotation không gộp transaction manager hoặc tạo transaction phân tán.

Nếu script có phụ thuộc thứ tự, hãy khai báo thứ tự rõ ràng và đặt tên resource thể hiện vai trò. Tránh để script ở nhiều nơi cùng sửa một bảng mà không biết thứ tự thực thi.

## 14. Cấu hình script parser và lỗi thực thi

Chủ đề chính của bài là chọn DataSource và transaction manager, nhưng @SqlConfig còn có thuộc tính kiểm soát cách Spring phân tích và chạy script:

| Thuộc tính | Vai trò |
|---|---|
| encoding | Charset của file SQL |
| separator | Dấu phân cách câu lệnh |
| commentPrefix | Tiền tố dòng comment |
| blockCommentStartDelimiter | Dấu bắt đầu block comment |
| blockCommentEndDelimiter | Dấu kết thúc block comment |
| errorMode | Cách xử lý lỗi khi thực thi câu lệnh |
| dataSource | Bean DataSource dùng để chạy script |
| transactionManager | Bean transaction manager dùng cho script |
| transactionMode | Cách quản lý transaction khi chạy script |

Ví dụ:

~~~java
@Sql(
    scripts = "/sql/orders-seed.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--",
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR
    )
)
~~~

FAIL_ON_ERROR làm test thất bại khi một câu lệnh SQL gặp lỗi. Đây thường là lựa chọn rõ ràng cho fixture bắt buộc phải tạo đầy đủ. Nếu chọn mode bỏ qua lỗi, hãy hiểu rằng test có thể tiếp tục với dữ liệu thiếu và thất bại ở một assertion khác khó chẩn đoán hơn.

Dấu phân cách và comment prefix nên khớp định dạng script. Với stored procedure hoặc script có dấu chấm phẩy bên trong block, có thể cần cấu hình separator phù hợp với parser. Đừng thay đổi parser setting nếu script đơn giản đã chạy đúng với mặc định.

## 15. Tương tác với @Transactional trên test

Khi test class hoặc method được đánh dấu @Transactional, Spring TestContext thường mở một transaction trước khi chạy test method. Script @Sql ở phase BEFORE_TEST_METHOD được xử lý trong vòng đời test; với mode INFERRED và transaction manager tương ứng, script có thể tham gia transaction đang hoạt động.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
class TransactionalOrderTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void seesScriptData() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

Nếu test transaction rollback mặc định, script fixture tham gia transaction cũng rollback. Test khác có thể dùng lại cùng ID vì dữ liệu không còn sau khi transaction kết thúc.

Nếu script dùng ISOLATED, fixture được commit riêng và có thể tồn tại sau khi test rollback. Hãy dùng ID riêng hoặc cleanup script để tránh dữ liệu cũ ảnh hưởng lần chạy sau.

### Script và transaction manager phải cùng database

Một lỗi thường gặp là test dùng ordersTransactionManager nhưng script lại dùng DataSource hoặc manager của database khác. Khi đó, dữ liệu script tạo có thể không nằm trong transaction mà test dự kiến rollback.

Hãy đồng bộ ba thành phần:

1. Repository đang được test sử dụng database nào?
2. @Transactional của test dùng transaction manager nào?
3. @SqlConfig dùng DataSource và transaction manager nào?

Nếu ba câu trả lời không cùng một ranh giới tài nguyên, hãy giải thích rõ vì sao test cần điều đó và cách cleanup dữ liệu.

## 16. Tương tác với JPA và persistence context

Khi script SQL chèn dữ liệu trực tiếp vào database, JPA persistence context đang mở có thể không tự biết về thay đổi đó. Điều này đặc biệt quan trọng khi cùng một transaction đã tải entity trước khi script chạy, hoặc khi script được chạy trong một transaction độc lập.

Một số nguyên tắc:

- SQL script thao tác trực tiếp trên database qua JDBC.
- JPA EntityManager quản lý entity trong persistence context riêng.
- Entity đã được load có thể giữ trạng thái cũ trong first-level cache.
- Script ISOLATED commit ở transaction riêng; persistence context của test có thể cần refresh hoặc clear trước khi đọc lại.
- Nếu test ghi qua JPA rồi script SQL đọc dữ liệu, có thể cần flush để đẩy thay đổi pending xuống database.

Ví dụ:

~~~java
@Autowired
private EntityManager entityManager;

@Test
void reloadsEntityAfterDirectSqlChange() {
    OrderEntity order = entityManager.find(OrderEntity.class, "order-188");

    // A SQL script or JDBC operation updates the row.

    entityManager.refresh(order);
    assertEquals("PAID", order.getStatus());
}
~~~

Ví dụ chỉ minh họa việc refresh entity sau thay đổi JDBC. Trong test thực tế, phải bảo đảm script chạy đúng DataSource và transaction manager; nếu script dùng transaction độc lập, thay đổi đã commit trước khi refresh. Nếu thay đổi nằm trong transaction khác chưa commit, transaction hiện tại có thể không nhìn thấy nó tùy isolation level.

Không nên dùng EntityManager.clear() hoặc refresh() một cách máy móc. Chỉ cần khi test kết hợp trực tiếp JDBC script với entity đang được quản lý và cần đồng bộ trạng thái.

## 17. Những lỗi thường gặp khi chọn DataSource và transaction manager

### Không chỉ định bean khi có nhiều DataSource

Spring có thể không suy luận được DataSource hoặc chọn candidate không mong muốn. Hãy khai báo dataSource bằng bean name trong @SqlConfig.

### Chọn DataSource và transaction manager không cùng database

Script có thể chạy ngoài transaction dự kiến hoặc dữ liệu không được rollback. Hãy ghép đúng DataSource với manager quản lý nó.

### Dùng transaction manager của JPA cho sai persistence unit

Một ứng dụng có nhiều EntityManagerFactory có thể có nhiều JpaTransactionManager. Hãy chọn manager gắn với persistence unit chứa các bảng mà script thao tác.

### Nghĩ rằng INFERRED luôn rollback script

INFERRED phụ thuộc transaction hiện tại và manager được suy luận. Nếu không có test transaction, script có thể chạy trong transaction riêng và commit theo cơ chế thực thi. Hãy kiểm tra trạng thái transaction và manager thay vì chỉ dựa vào tên mode.

### Dùng ISOLATED nhưng không cleanup

Transaction độc lập được commit ngay sau script. Rollback của test không xóa dữ liệu đó. Hãy dùng ID riêng và script cleanup có phạm vi.

### Không có transaction manager nhưng mong ISOLATED hoạt động

ISOLATED yêu cầu transaction manager phù hợp. Hãy đăng ký manager hoặc chọn mode phù hợp với hạ tầng.

### Dùng @Transactional nhưng repository tham gia manager khác

Transaction test có thể không bao bọc thao tác của repository. Hãy chỉ định manager đúng ở test và kiểm tra cấu hình repository.

### Cleanup script chạy trong transaction sắp rollback

Nếu cleanup script tham gia test transaction rồi transaction rollback, thao tác xóa cũng rollback. Khi cần cleanup bền vững, dùng transaction độc lập và giới hạn chính xác dữ liệu.

### Dùng nhiều database nhưng mong một transaction nguyên tử

Hai transaction manager độc lập không tự phối hợp commit/rollback. Nếu yêu cầu tính nguyên tử xuyên database, cần giải pháp transaction phân tán hoặc thiết kế nhất quán khác.

### Script lỗi nhưng test tiếp tục

Nếu cấu hình bỏ qua lỗi, test có thể chạy trên fixture không đầy đủ. Với script quan trọng, hãy để lỗi SQL làm test thất bại và hiển thị câu lệnh/resource liên quan.

## 18. Quy trình chọn DataSource và transaction manager

Khi một test cần chạy SQL script, hãy quyết định theo thứ tự:

1. **Xác định database đích**: bảng mà script đọc hoặc ghi thuộc DataSource nào?
2. **Xác định bean DataSource**: lấy tên bean chính xác trong ApplicationContext.
3. **Xác định transaction manager**: manager nào quản lý cùng DataSource hoặc persistence unit?
4. **Đồng bộ với test transaction**: nếu test có @Transactional, hãy chọn cùng manager khi muốn script tham gia transaction của test.
5. **Chọn transaction mode**: dùng INFERRED cho fixture thuộc transaction test; dùng ISOLATED khi cần transaction riêng được commit ngay.
6. **Chọn phase**: BEFORE_TEST_METHOD cho setup, AFTER_TEST_METHOD cho cleanup.
7. **Giới hạn dữ liệu**: dùng ID hoặc namespace riêng, tránh xóa dữ liệu chung.
8. **Kiểm tra nhiều database**: mỗi script có cấu hình riêng; không giả định nhiều manager tạo một transaction phân tán.
9. **Xử lý persistence context**: flush, refresh hoặc clear khi kết hợp JDBC script với JPA entity đang được quản lý.
10. **Để lỗi script hiển thị rõ**: chọn error mode phù hợp, thường là fail khi fixture không tạo được.

## 19. Ví dụ tổng hợp: script setup và cleanup với database đơn hàng

Cấu hình database:

~~~java
@Configuration
class OrderSqlTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://localhost:5432/orders_test");
        dataSource.setUsername("orders_test_user");
        dataSource.setPassword("test-only-password");
        return dataSource;
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    OrderRepository orderRepository(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcOrderRepository(dataSource);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(OrderSqlTestConfig.class)
@Transactional("ordersTransactionManager")
class OrderSqlFixtureTest {

    @Autowired
    private OrderRepository repository;

    @Test
    @Sql(
        scripts = "/sql/order-188-before.sql",
        config = @SqlConfig(
            dataSource = "ordersDataSource",
            transactionManager = "ordersTransactionManager",
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void readsOrderCreatedByScript() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

Trong ví dụ này, script setup và repository dùng cùng database đơn hàng. Script chạy trong test-managed transaction theo mode INFERRED và dữ liệu được rollback sau test.

Nếu muốn kiểm tra dữ liệu đã commit độc lập:

~~~java
@Test
@Sql(
    scripts = "/sql/order-188-before.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/sql/order-188-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void readsCommittedBaseline() {
    assertTrue(repository.existsById("order-188"));
}
~~~

Script setup commit dữ liệu trong transaction độc lập. Script cleanup cũng chạy trong transaction độc lập sau test để xóa đúng fixture đã commit. Trong dự án thực tế, resource cleanup cần chỉ xóa ID do test sở hữu và phải chạy ngay cả khi test assertion thất bại.

## 20. Nguyên tắc cần nhớ

- DataSource quyết định script kết nối tới database nào.
- PlatformTransactionManager quyết định transaction nào quản lý script.
- Dùng dataSource trong @SqlConfig khi cần chọn DataSource tường minh.
- Dùng transactionManager trong @SqlConfig để chọn transaction manager tương ứng.
- Khi có nhiều database, chỉ định đúng cặp bean cho từng script.
- INFERRED dùng ngữ cảnh transaction hiện tại và manager phù hợp để quyết định cách chạy.
- ISOLATED chạy script trong transaction độc lập và commit khi script thành công.
- Script ISOLATED không bị rollback cùng test transaction; cần cleanup riêng.
- @Transactional của test và @SqlConfig nên cùng manager khi fixture cần tham gia test transaction.
- Nhiều transaction manager không tự tạo transaction nguyên tử xuyên nhiều database.
- Khi kết hợp JDBC script và JPA, chú ý persistence context, flush và refresh.
- Chọn phase setup/cleanup và phạm vi dữ liệu rõ ràng để test có thể chạy lặp lại.

Chọn đúng DataSource giúp script thao tác trên database dự kiến; chọn đúng transaction manager giúp dữ liệu được commit hoặc rollback theo ranh giới mà test mong muốn. Với context đơn giản, Spring có thể suy luận các bean phù hợp. Với ứng dụng nhiều database hoặc nhiều transaction manager, hãy khai báo bean name rõ ràng trong **@SqlConfig**, đồng bộ với **@Transactional** và chọn giữa **INFERRED** và **ISOLATED** theo vòng đời của fixture. Điều đó giúp script SQL có thể tái tạo, dễ chẩn đoán và không để lại dữ liệu ngoài ý muốn.

