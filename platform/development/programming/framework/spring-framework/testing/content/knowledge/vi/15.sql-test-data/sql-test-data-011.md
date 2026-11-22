# Giữ dữ liệu độc lập khi nhiều bài dùng cùng cơ sở dữ liệu

Khi nhiều test cùng sử dụng một cơ sở dữ liệu, dữ liệu do test này tạo ra có thể làm thay đổi kết quả của test khác. Một test chạy riêng có thể thành công nhưng cả suite lại thất bại vì bản ghi cũ, sequence đã tăng, dữ liệu bị xóa hoặc hai test cùng sửa một hàng. Những lỗi này thường khó tái hiện vì kết quả phụ thuộc thứ tự chạy, số worker hoặc trạng thái database còn sót lại từ lần chạy trước.

Trong Spring Framework Testing, giữ dữ liệu độc lập nghĩa là mỗi test có một trạng thái đầu vào xác định và không để thay đổi của nó làm sai lệch test khác. Có thể đạt mục tiêu này bằng transaction rollback, dữ liệu có định danh riêng, setup và cleanup có kiểm soát, schema/database riêng hoặc một môi trường database mới cho mỗi suite.

Không có một kỹ thuật duy nhất phù hợp với mọi loại test. Test repository đồng bộ thường tận dụng transaction rollback. Test kiểm tra commit, bất đồng bộ hoặc nhiều kết nối có thể cần database riêng và cleanup rõ ràng. Khi chạy song song, phải thiết kế cả dữ liệu lẫn tài nguyên để không tranh chấp.

## 1. Vì sao dùng chung database dễ làm test phụ thuộc nhau?

Giả sử hai test cùng thao tác trên bảng customer:

~~~java
@Test
void createsCustomer() {
    customerRepository.save(new Customer("ada@example.test"));
    assertEquals(1, customerRepository.count());
}

@Test
void startsWithNoCustomers() {
    assertEquals(0, customerRepository.count());
}
~~~

Nếu test đầu commit dữ liệu, test thứ hai có thể nhận kết quả 1 thay vì 0. Nếu thứ tự chạy đảo lại, cả hai có thể thành công. Kết quả suite vì thế không còn ổn định.

Các nguyên nhân thường gặp:

- **Dữ liệu tồn tại từ lần chạy trước:** test đã commit hoặc không cleanup đầy đủ.
- **Dùng chung khóa định danh:** hai test cùng tạo customer có email hoặc mã nghiệp vụ cố định, gây lỗi unique constraint.
- **Cleanup quá rộng:** một test xóa bảng hoặc truncate dữ liệu mà test khác đang sử dụng.
- **Sequence và auto-increment:** test giả định ID luôn bắt đầu từ một giá trị cố định.
- **Transaction không bao phủ mọi thao tác:** code chạy ở thread khác, dùng transaction riêng hoặc kết nối khác.
- **Chia sẻ trạng thái giữa test worker:** các test chạy đồng thời cùng sửa một bản ghi hoặc cùng dùng một schema.
- **Dữ liệu phụ thuộc thời gian:** test dùng ngày hiện tại, timestamp hoặc trạng thái hết hạn thay đổi theo thời điểm chạy.

Một test độc lập cần cho kết quả giống nhau khi chạy riêng, chạy cùng suite, chạy trước hoặc sau test khác và chạy lại nhiều lần trong môi trường được kiểm soát.

## 2. Các nguyên tắc thiết kế dữ liệu test

Trước khi chọn công cụ, nên áp dụng một số nguyên tắc cơ bản:

1. **Mỗi test tự chuẩn bị dữ liệu cần thiết.** Không phụ thuộc vào test khác đã tạo fixture.
2. **Dùng khóa định danh riêng.** Mã test, email và business key không xung đột với test khác.
3. **Chỉ xác nhận dữ liệu thuộc phạm vi test.** Tránh assertion dựa trên tổng số bản ghi toàn bảng nếu database có thể chứa dữ liệu khác.
4. **Dọn đúng dữ liệu do test tạo.** Không xóa toàn bộ bảng dùng chung.
5. **Xác định transaction boundary.** Biết thao tác nào tham gia transaction test và thao tác nào có thể commit riêng.
6. **Kiểm soát thời gian và dữ liệu ngẫu nhiên.** Dùng Clock có thể điều khiển hoặc seed ngẫu nhiên cố định khi cần.
7. **Thiết kế cho chạy song song.** Không dựa vào một thứ tự thực thi hoặc một bộ khóa cố định.

Ví dụ, thay vì kiểm tra tổng số customer trong database:

~~~java
assertEquals(1, customerRepository.count());
~~~

có thể kiểm tra chính bản ghi mà test vừa tạo:

~~~java
Customer saved = customerRepository.save(
    new Customer("customer-test-42", "ada@example.test")
);

assertTrue(customerRepository.findById(saved.getId()).isPresent());
assertEquals(
    "ada@example.test",
    customerRepository.findById(saved.getId()).orElseThrow().getEmail()
);
~~~

Assertion theo định danh của fixture ít bị ảnh hưởng bởi dữ liệu không liên quan trong database.

## 3. Dùng transaction rollback cho test đồng bộ

Với test repository hoặc service thao tác database trong cùng thread, transaction test là cách đơn giản để cô lập thay đổi. Spring TestContext hỗ trợ test-managed transaction qua @Transactional. Theo mặc định, transaction này được rollback sau mỗi test method.

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesAndFindsCustomer() {
        Customer customer = new Customer(
            "customer-test-01",
            "ada@example.test"
        );

        Customer saved = customerRepository.save(customer);
        customerRepository.flush();

        Customer loaded = customerRepository.findById(saved.getId())
            .orElseThrow();

        assertEquals("ada@example.test", loaded.getEmail());
    }
}
~~~

Với test slice như @DataJpaTest, Spring Boot thường cấu hình transaction test và rollback mặc định. Khi dùng @SpringBootTest hoặc cấu hình Spring Framework thuần, cần có PlatformTransactionManager phù hợp và @Transactional trên class hoặc method.

Transaction rollback giúp:

- Không để bản ghi được tạo trong test tồn tại sau khi method hoàn tất.
- Giữ fixture setup và hành động kiểm tra trong cùng một transaction.
- Giảm nhu cầu viết cleanup cho các thao tác database tham gia transaction.
- Cho phép test xác nhận dữ liệu trước khi transaction rollback.

Tuy nhiên, rollback không phải một lớp cô lập tuyệt đối cho mọi thao tác. Cần kiểm tra ranh giới thực tế của database và code ứng dụng.

### 3.1. Những trường hợp rollback không đủ

Rollback của test không tự hoàn tác:

- Thao tác được commit trong transaction REQUIRES_NEW.
- Ghi dữ liệu qua thread khác không tham gia transaction của test.
- Ghi vào một datasource do transaction manager khác quản lý.
- Thao tác dùng connection độc lập hoặc transaction được quản lý thủ công.
- Gửi message, gọi HTTP service hoặc ghi file bên ngoài database.
- Dữ liệu đã commit trước khi test bắt đầu.

Ví dụ, một service có method dùng REQUIRES_NEW có thể commit độc lập với transaction test bên ngoài. Nếu test mong dữ liệu đó biến mất sau rollback, kỳ vọng này không đúng. Cần cleanup riêng hoặc dùng database/schema riêng cho test.

### 3.2. Flush không phải commit

Với JPA, save có thể chỉ cập nhật persistence context và SQL được gửi xuống database ở thời điểm flush. Khi cần kiểm tra unique constraint hoặc foreign key, gọi flush để lỗi xuất hiện ngay trong test:

~~~java
repository.save(new Customer("same@example.test"));
repository.flush();

assertThrows(
    DataIntegrityViolationException.class,
    () -> {
        repository.save(new Customer("same@example.test"));
        repository.flush();
    }
);
~~~

Flush đồng bộ persistence context với database trong transaction hiện tại. Nó không commit transaction. Sau khi test kết thúc, transaction vẫn có thể được rollback.

## 4. Tạo dữ liệu có định danh riêng

Transaction rollback hữu ích, nhưng không phải test nào cũng chạy trong một transaction duy nhất. Để giảm xung đột, hãy tạo khóa định danh riêng cho mỗi test hoặc mỗi lần chạy.

Có thể dùng UUID:

~~~java
String testRunId = UUID.randomUUID().toString();
String email = "customer-" + testRunId + "@example.test";

Customer customer = customerRepository.save(
    new Customer("customer-" + testRunId, email)
);
~~~

Hoặc dùng tên test cùng mã worker:

~~~java
String namespace = "it-" + workerId + "-" + testCaseId;
String orderNumber = namespace + "-order-01";
~~~

UUID phù hợp khi chỉ cần tránh va chạm. Namespace có cấu trúc hữu ích hơn khi cần tìm và cleanup dữ liệu sau test. Có thể kết hợp cả hai: run id định danh toàn bộ lần chạy, còn tên test xác định chủ sở hữu dữ liệu.

### 4.1. Không giả định ID tự tăng bắt đầu từ 1

Không nên viết:

~~~java
assertEquals(1L, saved.getId());
~~~

Database có thể tăng sequence qua lần chạy trước, rollback không nhất thiết khôi phục sequence, và thứ tự insert có thể khác khi chạy song song. Hãy lấy ID từ entity được lưu hoặc truy vấn theo business key do test tạo.

~~~java
Customer saved = customerRepository.save(customer);

assertNotNull(saved.getId());
assertTrue(customerRepository.existsById(saved.getId()));
~~~

Nếu ID được sinh từ sequence, test nên kiểm tra sự tồn tại và quan hệ dữ liệu thay vì dựa vào một con số cố định.

### 4.2. Dùng builder hoặc factory cho fixture

Một factory giúp tạo dữ liệu hợp lệ và giảm việc lặp lại cấu hình:

~~~java
final class CustomerTestData {

    static Customer newCustomer(String namespace) {
        return new Customer(
            namespace,
            namespace + "@example.test",
            "Ada"
        );
    }
}
~~~

Test sử dụng:

~~~java
String namespace = "customer-" + UUID.randomUUID();
Customer customer = CustomerTestData.newCustomer(namespace);

Customer saved = customerRepository.save(customer);

assertTrue(customerRepository.existsById(saved.getId()));
~~~

Factory nên tạo dữ liệu có ý nghĩa và dễ tùy chỉnh. Tránh tạo một fixture khổng lồ có nhiều liên kết không cần thiết vì thay đổi một thuộc tính có thể ảnh hưởng nhiều test.

## 5. Setup và cleanup dữ liệu một cách có kiểm soát

Khi không thể dựa vào rollback, test cần chuẩn bị và dọn dữ liệu rõ ràng. Một chiến lược an toàn là ghi lại định danh các bản ghi do test tạo, sau đó xóa đúng các bản ghi đó.

~~~java
@SpringBootTest
class CustomerImportIntegrationTest {

    @Autowired
    private CustomerRepository customerRepository;

    private String testNamespace;

    @BeforeEach
    void setUp() {
        testNamespace = "import-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanUp() {
        customerRepository.deleteByTestNamespace(testNamespace);
    }

    @Test
    void importsCustomers() {
        // Import chỉ các bản ghi mang testNamespace.
    }
}
~~~

Ví dụ giả định bảng có cột test_namespace và repository có method xóa tương ứng. Cột namespace không nhất thiết phải có trong production schema; dự án có thể dùng một business key hoặc bảng fixture riêng phù hợp.

Cleanup cần có các đặc điểm:

- Chỉ xóa dữ liệu thuộc test hiện tại.
- Có thể chạy nhiều lần mà không gây lỗi.
- Xóa theo thứ tự tôn trọng foreign key.
- Được thực hiện ngay cả khi assertion thất bại.
- Không xóa dữ liệu do test khác hoặc người dùng khác tạo.

JUnit Jupiter chạy @AfterEach sau mỗi test method, kể cả khi test assertion thất bại. Tuy nhiên, nếu JVM bị dừng đột ngột hoặc tiến trình bị kill, callback cleanup không được bảo đảm chạy. Vì vậy, dữ liệu có namespace và cơ chế dọn theo run id vẫn hữu ích.

### 5.1. Xóa theo thứ tự quan hệ

Nếu bảng có quan hệ cha-con, cleanup cần tôn trọng foreign key:

~~~sql
DELETE FROM order_item
WHERE order_id IN (
    SELECT id FROM orders WHERE test_namespace = :namespace
);

DELETE FROM orders
WHERE test_namespace = :namespace;
~~~

Xóa bản ghi con trước bản ghi cha nếu database không cấu hình cascade phù hợp. Dùng transaction cho cleanup nếu muốn toàn bộ thao tác xóa thành công hoặc rollback cùng nhau.

### 5.2. Tránh truncate bảng dùng chung

Truncate toàn bộ bảng có thể nhanh nhưng nguy hiểm khi nhiều test hoặc worker dùng chung database. Nó có thể:

- Xóa fixture mà test khác đang cần.
- Làm test đang chạy thất bại ngẫu nhiên.
- Reset identity/sequence theo cách khác giữa các database.
- Bị chặn bởi foreign key hoặc yêu cầu quyền đặc biệt.

Chỉ truncate khi test có database hoặc schema riêng, hoặc khi toàn bộ suite được đảm bảo chạy độc quyền trên database đó.

## 6. Dùng @Sql để chuẩn bị và dọn dữ liệu

Spring Test hỗ trợ @Sql để chạy script SQL ở các thời điểm trong vòng đời test. Cách này phù hợp khi fixture cần nhiều bảng, cần dữ liệu quan hệ rõ ràng hoặc muốn lưu setup/cleanup dưới dạng file SQL có thể đọc và quản lý.

Ví dụ:

~~~java
@SpringBootTest
@Sql(
    scripts = "/sql/customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup-customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class CustomerQueryIntegrationTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsActiveCustomer() {
        Customer customer = customerRepository
            .findByEmail("active-customer@example.test")
            .orElseThrow();

        assertTrue(customer.isActive());
    }
}
~~~

Script setup có thể chèn fixture cần thiết; script cleanup xóa đúng fixture của test. Các file đặt trong src/test/resources/sql để được tìm trên classpath.

### 6.1. Chọn execution phase

@Sql hỗ trợ các phase:

| Phase | Thời điểm |
|---|---|
| BEFORE_TEST_METHOD | Trước mỗi test method |
| AFTER_TEST_METHOD | Sau mỗi test method |
| BEFORE_TEST_CLASS | Trước test class |
| AFTER_TEST_CLASS | Sau test class |

Các phase class-level có từ những phiên bản Spring Framework hỗ trợ tương ứng; kiểm tra API của phiên bản dự án nếu dùng chúng. Với fixture cần làm mới cho từng test, BEFORE_TEST_METHOD và AFTER_TEST_METHOD là lựa chọn thường gặp.

### 6.2. Transaction mode của @Sql

@SqlConfig có thuộc tính transactionMode để xác định script chạy trong transaction như thế nào:

- **INFERRED:** Spring suy luận transaction từ transaction đang hoạt động hoặc transaction manager có sẵn. Đây là chế độ mặc định.
- **ISOLATED:** script chạy trong transaction riêng, được commit độc lập sau khi hoàn tất.

Ví dụ:

~~~java
@Sql(
    scripts = "/sql/seed-customer.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    ),
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

Dùng ISOLATED khi setup cần được commit để test nhìn thấy dữ liệu từ transaction khác hoặc khi muốn script có ranh giới transaction riêng. Vì dữ liệu setup được commit độc lập, transaction rollback của test không tự xóa fixture đó. Cần có script cleanup hoặc namespace riêng để dọn dữ liệu.

Nếu setup và test cùng tham gia transaction test, INFERRED thường giúp rollback cả dữ liệu được tạo bởi script cùng các thao tác trong method. Hãy kiểm tra chính xác transaction manager và datasource mà script sử dụng.

### 6.3. Dùng namespace trong SQL script

Không nên chèn cùng một email cố định vào database dùng chung nếu test có thể chạy đồng thời. Có thể dùng mã fixture riêng được truyền qua cơ chế tham số phù hợp, hoặc tạo dữ liệu bằng repository/factory trước khi gọi SQL. Nếu script không hỗ trợ biến động theo cách dự án cần, dùng bảng fixture tĩnh chỉ trong database riêng của suite.

Khi fixture là cố định và chỉ có một suite chạy độc quyền, dữ liệu có tên rõ ràng như active-customer-fixture có thể đủ. Khi nhiều worker dùng chung database, cần phân biệt dữ liệu theo worker hoặc run id.

## 7. Dùng database hoặc schema riêng cho từng suite

Một cách cô lập mạnh là cấp database hoặc schema riêng cho mỗi lần chạy test. Khi đó, các suite không chia sẻ bảng và dữ liệu.

Các lựa chọn:

| Chiến lược | Phạm vi cô lập | Ưu điểm | Chi phí |
|---|---|---|---|
| Database riêng cho mỗi suite | Toàn bộ suite | Cô lập rõ ràng, dễ dọn | Tốn tài nguyên khởi tạo |
| Schema riêng cho mỗi suite | Các bảng và sequence | Nhanh hơn khi database hỗ trợ schema | Cần cấu hình schema/search path |
| Database riêng cho mỗi worker | Các test trong một worker | Hỗ trợ chạy song song | Quản lý nhiều database |
| Một database chung, namespace theo test | Theo nhóm dữ liệu | Nhẹ, dễ chia sẻ hạ tầng | Cần cleanup và tránh xung đột |
| Transaction rollback | Theo transaction/thread | Nhanh, ít cleanup | Không bao phủ mọi thao tác |

Schema riêng có thể được chọn bằng cấu hình JDBC URL, schema search path hoặc thuộc tính kết nối tùy database. Đảm bảo Flyway/Liquibase và ORM tạo schema vào đúng namespace.

Nếu các worker dùng chung một database server nhưng có schema riêng, mỗi worker có thể chạy migration và cleanup độc lập. Không nên để nhiều worker cùng chạy migration hoặc drop schema chung mà không có cơ chế đồng bộ.

## 8. Dùng Testcontainers để tạo môi trường database mới

Testcontainers có thể khởi chạy database trong container cho integration test. Một container hoặc database riêng giúp test không phụ thuộc database local hoặc một instance dùng chung từ các lần chạy trước.

Ví dụ với PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class CustomerDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Ví dụ cần các dependency Testcontainers phù hợp với phiên bản dự án và cấu hình vòng đời container đúng với test framework. @DynamicPropertySource đưa URL, username và password được sinh ra vào Spring Environment trước khi ApplicationContext được tạo.

Một container dùng chung cho cả class có thể tiết kiệm thời gian, nhưng các method vẫn phải độc lập về dữ liệu. Container mới không tự bảo đảm mỗi method có database trống nếu các method commit dữ liệu.

Có thể tăng mức cô lập bằng cách:

- Dùng transaction rollback cho test đồng bộ.
- Tạo schema/database riêng cho từng worker.
- Dùng namespace riêng cho fixture và cleanup.
- Khởi tạo container mới cho suite hoặc nhóm test cần môi trường sạch.

Không cần khởi chạy một container cho từng method nếu transaction và fixture đã đủ cô lập. Cân bằng giữa độ cô lập, thời gian khởi động và chi phí tài nguyên.

## 9. Chạy test song song trên database chung

Khi JUnit hoặc build tool chạy test song song, hai test có thể truy cập database cùng lúc. Việc mỗi method có transaction riêng không ngăn xung đột nếu chúng sửa cùng bản ghi hoặc cùng một khóa unique.

Ví dụ hai test cùng cập nhật một hàng:

~~~java
@Test
void enablesFeature() {
    settingsRepository.updateEnabled("checkout", true);
}

@Test
void disablesFeature() {
    settingsRepository.updateEnabled("checkout", false);
}
~~~

Kết quả cuối phụ thuộc thứ tự commit. Nếu test chỉ kiểm tra giá trị cuối cùng của cùng một record, chạy song song có thể khiến assertion không ổn định.

### 9.1. Mỗi test sở hữu dữ liệu riêng

Ưu tiên tạo bản ghi riêng cho từng test thay vì cùng sửa một fixture dùng chung. Dùng UUID, worker id hoặc test namespace trong business key.

~~~java
String key = "feature-" + UUID.randomUUID();
settingsRepository.save(new FeatureSetting(key, false));

settingsRepository.updateEnabled(key, true);
assertTrue(settingsRepository.findByKey(key).orElseThrow().isEnabled());
~~~

### 9.2. Đồng bộ khi tài nguyên thật sự phải dùng chung

Nếu test bắt buộc cùng thao tác trên một tài nguyên, có thể:

- Tắt parallel execution cho nhóm test đó.
- Dùng JUnit @ResourceLock để khóa tài nguyên logic trong cùng JVM.
- Dùng lock ở database nếu cần đồng bộ giữa nhiều tiến trình.
- Tách database/schema theo worker.

Ví dụ dùng ResourceLock:

~~~java
@ResourceLock(
    value = "shared-reference-data",
    mode = ResourceAccessMode.READ_WRITE
)
class ReferenceDataIntegrationTest {
    // Các test trong class truy cập dữ liệu dùng chung.
}
~~~

ResourceLock điều phối test trong phạm vi JUnit execution tương ứng. Nó không khóa một database cho các tiến trình Gradle khác, JVM khác hoặc CI job khác. Với nhiều tiến trình, cần khóa ở tầng database hoặc tách tài nguyên.

### 9.3. Không dùng @Order để sửa lỗi phụ thuộc dữ liệu

Đặt thứ tự chạy test có thể che giấu vấn đề nhưng không làm dữ liệu độc lập. Nếu test B chỉ thành công sau test A vì A tạo fixture, test B không thể chạy riêng và dễ thất bại khi thứ tự thay đổi.

Mỗi test cần tự chuẩn bị fixture của nó hoặc dùng một fixture bất biến được tạo trước suite và không bị test thay đổi.

## 10. Quản lý dữ liệu tham chiếu và fixture bất biến

Một số bảng chứa dữ liệu tham chiếu như quốc gia, loại tiền, trạng thái đơn hàng hoặc danh mục. Các test có thể cùng đọc dữ liệu này nếu nó được tạo một lần và không bị sửa.

Có thể tạo dữ liệu tham chiếu bằng migration hoặc script setup cấp suite:

~~~sql
INSERT INTO currency(code, display_name)
VALUES ('VND', 'Vietnamese Dong')
ON CONFLICT (code) DO NOTHING;
~~~

Cú pháp upsert khác nhau theo database. Dùng script phù hợp với hệ quản trị đang chạy test.

Quy tắc với fixture dùng chung:

- Dữ liệu chỉ đọc trong các test.
- Không test nào được cập nhật hoặc xóa fixture chung.
- Nếu test cần biến thể, hãy tạo bản sao có khóa riêng.
- Cấu hình setup phải chạy trước khi test cần fixture bắt đầu.
- Không phụ thuộc dữ liệu còn lại từ lần chạy trước; script phải có tính lặp an toàn hoặc database được tạo mới.

Nếu fixture tham chiếu có thể thay đổi theo nghiệp vụ, hãy version hóa dữ liệu test hoặc tạo nó từ migration/fixture có kiểm soát thay vì lấy dữ liệu trực tiếp từ production.

## 11. Kiểm soát thời gian và dữ liệu sinh tự động

Dữ liệu phụ thuộc thời gian dễ gây lỗi khi test chạy qua ngày mới, múi giờ khác hoặc thời điểm daylight saving. Ví dụ, một test kiểm tra đơn hàng hết hạn bằng LocalDate.now() có thể cho kết quả khác khi chạy vào ngày khác.

Thay vì gọi trực tiếp thời gian hệ thống trong logic nghiệp vụ, inject Clock:

~~~java
@Service
class SubscriptionService {

    private final Clock clock;

    SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
~~~

Test dùng fixed clock:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Khi thời gian ổn định, dữ liệu hết hạn và truy vấn theo ngày có thể được kiểm tra lặp lại. Với ID ngẫu nhiên, hãy dùng seed cố định nếu test cần tái tạo chính xác một bộ dữ liệu; nếu chỉ cần tránh xung đột, UUID là lựa chọn phù hợp.

## 12. Cleanup an toàn khi test thất bại

Cleanup nên được thiết kế để chạy độc lập với assertion thành công hay thất bại. Với JUnit Jupiter, có thể lưu namespace hoặc ID được tạo trong @BeforeEach và xóa trong @AfterEach.

~~~java
class OrderImportTest {

    private String namespace;

    @BeforeEach
    void prepareNamespace() {
        namespace = "order-import-" + UUID.randomUUID();
    }

    @AfterEach
    void removeImportedData() {
        orderItemRepository.deleteByNamespace(namespace);
        orderRepository.deleteByNamespace(namespace);
    }
}
~~~

Để tránh lỗi cleanup che mất lỗi gốc:

- Cleanup phải có thể chạy khi không có dữ liệu.
- Dùng delete theo namespace thay vì truy vấn toàn bảng.
- Dọn bảng con trước bảng cha.
- Ghi log lỗi cleanup nếu cần nhưng vẫn giữ exception gốc của test.
- Nếu cleanup cần transaction riêng, khai báo ranh giới rõ ràng.

Khi test dùng database riêng cho suite, có thể dọn toàn bộ database/schema ở cuối suite. Điều này đơn giản hơn vì không có test khác cùng sở hữu dữ liệu trong namespace đó.

## 13. Các lỗi thường gặp

### 13.1. Dùng dữ liệu cố định trong database dùng chung

Email hoặc mã đơn hàng cố định có thể tồn tại từ lần chạy trước hoặc bị test song song tạo trùng. Dùng namespace duy nhất cho từng test hoặc dọn fixture đúng phạm vi.

### 13.2. Giả định rollback xóa mọi thứ

Rollback chỉ tác động đến thao tác tham gia transaction tương ứng. Kiểm tra REQUIRES_NEW, async thread, datasource khác và commit độc lập.

### 13.3. Cleanup toàn bảng

TRUNCATE hoặc DELETE không có điều kiện có thể phá dữ liệu của test khác. Chỉ dùng thao tác này trên database/schema dành riêng cho suite.

### 13.4. Kiểm tra tổng số bản ghi

Count toàn bảng bị ảnh hưởng bởi fixture và test khác. Kiểm tra theo ID hoặc namespace do test tạo.

### 13.5. Phụ thuộc thứ tự chạy

Test không tự tạo fixture mà dựa vào test khác sẽ thất bại khi chạy riêng hoặc chạy song song. Đưa setup vào chính test hoặc helper của test.

### 13.6. Dùng ID tự tăng cố định

Sequence có thể không reset khi rollback và có thể tăng do test khác. Lấy ID từ kết quả insert, không hard-code giá trị.

### 13.7. Cleanup chạy trong transaction bị rollback

Nếu cleanup chạy trong cùng transaction test và transaction đó rollback, thao tác cleanup có thể cũng bị rollback. Xác định cleanup cần tham gia transaction nào và dùng transaction mode phù hợp.

### 13.8. Dùng fixture chung có thể thay đổi

Một test cập nhật fixture dùng chung có thể ảnh hưởng test khác. Hãy coi dữ liệu tham chiếu dùng chung là bất biến hoặc tạo bản sao riêng.

### 13.9. Chạy song song nhưng chỉ khóa trong một JVM

ResourceLock không đồng bộ nhiều JVM hoặc CI job. Dùng schema/database riêng hoặc cơ chế khóa ở cấp database nếu có nhiều tiến trình.

### 13.10. Để dữ liệu rác sau khi tiến trình bị dừng

@AfterEach không chạy nếu JVM bị kill. Namespace theo run id giúp phát hiện và dọn dữ liệu tồn đọng theo chính sách riêng.

## 14. Chọn chiến lược theo loại test

| Loại test | Chiến lược thường phù hợp |
|---|---|
| Repository test đồng bộ | @DataJpaTest hoặc @JdbcTest với rollback mặc định |
| Service integration test dùng một datasource | @Transactional nếu muốn rollback toàn bộ thao tác trong test |
| Kiểm tra service commit thật | Không bọc test trong transaction bên ngoài; dùng dữ liệu riêng và cleanup |
| Test dùng REQUIRES_NEW | Namespace riêng hoặc cleanup sau commit |
| Test bất đồng bộ | Chờ công việc hoàn tất, dùng dữ liệu riêng và cleanup rõ ràng |
| Test nhiều datasource | Chỉ định transaction manager; cô lập từng datasource hoặc dùng cơ chế transaction phân tán phù hợp |
| Test chạy song song | Khóa riêng, schema/database riêng hoặc namespace duy nhất |
| Test kiểm tra migration/schema | Database hoặc schema mới cho mỗi suite |
| Test API qua embedded server | Database riêng cho suite, fixture rõ ràng và cleanup |

Một chiến lược tốt có thể kết hợp nhiều lớp: database mới cho mỗi suite, transaction rollback cho từng method, namespace riêng cho dữ liệu được commit và cleanup cho các tài nguyên ngoài transaction.

## 15. Mẫu tổ chức test repository với dữ liệu riêng

Ví dụ dưới đây dùng namespace để test không phụ thuộc tổng số bản ghi trong bảng:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        String namespace = UUID.randomUUID().toString();
        String email = "customer-" + namespace + "@example.test";

        Customer customer = new Customer(namespace, email, "Ada");
        customerRepository.saveAndFlush(customer);

        Optional<Customer> found = customerRepository.findByEmail(email);

        assertTrue(found.isPresent());
        assertEquals(namespace, found.orElseThrow().getExternalId());
    }
}
~~~

Transaction test mặc định rollback sau method. Namespace duy nhất vẫn có ích vì nó tránh xung đột với dữ liệu fixture hoặc test chạy đồng thời, đồng thời làm assertion tập trung vào bản ghi của test.

## 16. Mẫu tổ chức test cần commit và cleanup

Nếu test cần xác nhận một transaction được commit độc lập, không thể dựa vào rollback của transaction test để dọn dữ liệu đó. Có thể dùng namespace và cleanup có phạm vi:

~~~java
@SpringBootTest
class CommittedImportTest {

    @Autowired
    private ImportService importService;

    @Autowired
    private ImportRepository importRepository;

    private String namespace;

    @BeforeEach
    void createNamespace() {
        namespace = "import-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanCommittedRows() {
        importRepository.deleteByNamespace(namespace);
    }

    @Test
    void commitsImportedRows() {
        importService.importBatch(namespace, sampleRows());

        assertTrue(importRepository.existsByNamespace(namespace));
    }
}
~~~

Ví dụ giả định import service commit theo transaction riêng và repository cung cấp truy vấn/xóa theo namespace. Nếu cleanup cần commit độc lập để thực sự xóa dữ liệu, hãy cấu hình transaction cho cleanup một cách tường minh. Không để cleanup vô tình tham gia một transaction sẽ rollback sau đó.

## 17. Quy trình thiết kế dữ liệu độc lập

Khi tạo test mới dùng chung database, hãy xác định:

1. Test có chạy trong test-managed transaction không?
2. Tất cả thao tác có dùng cùng transaction manager và datasource không?
3. Có code async, REQUIRES_NEW hoặc commit độc lập không?
4. Test cần fixture nào và fixture có thể được tạo riêng không?
5. Khóa định danh có xung đột với test khác hoặc dữ liệu cũ không?
6. Assertion có kiểm tra đúng dữ liệu do test tạo không?
7. Cleanup có giới hạn theo namespace và tôn trọng quan hệ foreign key không?
8. Test có thể chạy riêng, chạy lại và chạy song song không?
9. Có cần database/schema riêng cho suite hoặc worker không?
10. Nếu tiến trình bị dừng đột ngột, có thể nhận diện dữ liệu tồn đọng để dọn không?

Một quy ước đơn giản cho test suite có thể là:

- Dùng database/schema riêng cho mỗi suite.
- Dùng @Transactional rollback cho repository test đồng bộ.
- Dùng UUID hoặc run id cho dữ liệu cần commit.
- Dùng @Sql hoặc factory để tạo fixture rõ ràng.
- Cleanup theo namespace, không truncate database chung.
- Tắt parallel execution hoặc dùng schema riêng khi test phải thay đổi cùng tài nguyên.

## Kết luận

Giữ dữ liệu độc lập khi nhiều test dùng chung cơ sở dữ liệu đòi hỏi mỗi test tự tạo trạng thái đầu vào, sở hữu khóa định danh riêng và dọn đúng phần dữ liệu của mình. Transaction rollback là lựa chọn hiệu quả cho test đồng bộ, nhưng không bao phủ commit độc lập, thread bất đồng bộ hoặc datasource khác. Với các trường hợp đó, hãy dùng namespace, cleanup có kiểm soát, @Sql, database/schema riêng hoặc Testcontainers. Khi thiết kế thêm cho chạy song song và không phụ thuộc thứ tự, test suite sẽ ổn định hơn giữa máy phát triển và CI.
