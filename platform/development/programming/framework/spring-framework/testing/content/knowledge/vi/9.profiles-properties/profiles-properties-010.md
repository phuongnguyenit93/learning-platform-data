# Tách bí mật, môi trường và dữ liệu của mỗi bộ kiểm thử

Một bộ kiểm thử Spring thường cần ba nhóm thông tin khác nhau: cấu hình để chọn cách ứng dụng hoạt động, thông tin xác thực để kết nối dịch vụ và dữ liệu dùng làm đầu vào hoặc trạng thái ban đầu. Nếu trộn cả ba vào một file cấu hình hoặc dùng chung tài nguyên với môi trường chạy thật, test dễ phụ thuộc vào máy của người viết, có thể vô tình truy cập production và khó chạy ổn định trên CI.

Hãy tách rõ:

- **Cấu hình môi trường** mô tả cách test kết nối và hoạt động: profile, URL, cổng, timeout, feature flag, database và các tùy chọn runtime.
- **Bí mật** là thông tin xác thực hoặc khóa có thể cấp quyền truy cập: password, API token, private key, client secret, signing key và credential của dịch vụ.
- **Dữ liệu kiểm thử** là các bản ghi, fixture, request mẫu, file CSV/JSON hoặc trạng thái ban đầu mà test cần để xác minh hành vi.

Ba nhóm này có vòng đời và cách quản lý khác nhau. Profile giúp chọn bean và cấu hình phù hợp; property source cung cấp giá trị cấu hình; secret store hoặc biến môi trường cung cấp bí mật; fixture và cơ chế tạo dữ liệu giúp mỗi test có trạng thái riêng, tái tạo được.

## 1. Phân biệt cấu hình, bí mật và dữ liệu

Ví dụ một ứng dụng đặt hàng có thể cần:

| Nhóm | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| Cấu hình môi trường | URL của API sandbox, JDBC URL, timeout, profile | Profile và property source |
| Bí mật | API key của sandbox, mật khẩu database, signing key | Secret manager hoặc biến môi trường được cấp khi chạy |
| Dữ liệu kiểm thử | Đơn hàng mẫu, mã khách hàng giả, danh sách sản phẩm, payload JSON | Fixture, builder, SQL script hoặc factory trong test |

Một giá trị có thể thay đổi giữa local, CI và môi trường tích hợp thường là cấu hình. Một giá trị cấp quyền truy cập là bí mật, ngay cả khi nó chỉ dùng trong môi trường test. Một bản ghi được tạo để kiểm tra quy tắc nghiệp vụ là dữ liệu test.

Ví dụ:

- **payment.base-url** là cấu hình.
- **payment.api-key** là bí mật.
- Một đơn hàng có mã **order-test-17** và tổng tiền 250.000 đồng là dữ liệu test.

Không nên đặt API key trong fixture JSON chỉ vì test cần gửi một request có trường apiKey. Nếu đó là credential thật, nó phải được cấp từ nguồn bí mật. Nếu test chỉ cần xác minh cấu trúc request, dùng một giá trị giả không có quyền truy cập.

## 2. Dùng profile để tách môi trường kiểm thử

Spring Profile cho phép đăng ký bean hoặc cấu hình chỉ hoạt động khi profile tương ứng được kích hoạt. Một ứng dụng có thể có các profile như:

- **default**: cấu hình mặc định cho phát triển hoặc trường hợp đơn giản.
- **test**: cấu hình phục vụ test tự động.
- **integration**: cấu hình dùng khi kiểm tra nhiều thành phần phối hợp.
- **local**: cấu hình dành cho chạy ứng dụng trên máy phát triển.
- **staging** hoặc **production**: cấu hình cho môi trường triển khai tương ứng.

Tên profile là quy ước của dự án. Không cần tạo một profile cho từng test class; profile nên biểu diễn một nhóm cấu hình có ý nghĩa.

### Kích hoạt profile trong Spring TestContext

Với JUnit Jupiter và Spring TestContext Framework, có thể dùng **@ActiveProfiles**:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@ActiveProfiles("test")
class OrderServiceTest {
    // Test methods
}
~~~

Spring TestContext kích hoạt profile **test** khi tạo ApplicationContext cho test. Các bean có điều kiện profile phù hợp sẽ được đăng ký.

Ví dụ một cổng thanh toán giả chỉ được đăng ký trong profile test:

~~~java
@Configuration
@Profile("test")
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Cấu hình production có thể đăng ký adapter thật trong profile phù hợp:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentHttpClient client) {
        return new HttpPaymentGateway(client);
    }
}
~~~

Khi test cần dùng FakePaymentGateway, nó kích hoạt profile **test** và nạp cấu hình tương ứng. Khi chạy production, profile production cung cấp adapter thật.

Không nên xem profile là ranh giới bảo mật. Profile chỉ quyết định cấu hình và bean nào được kích hoạt; nó không tự bảo vệ credential, không ngăn một test gọi nhầm endpoint production và cũng không thay thế quyền truy cập tối thiểu của tài khoản dịch vụ.

### Dùng nhiều profile khi thật sự cần

Có thể kích hoạt nhiều profile:

~~~java
@ActiveProfiles({"test", "integration"})
@SpringJUnitConfig(IntegrationTestConfig.class)
class OrderIntegrationTest {
}
~~~

Hãy dùng nhiều profile khi chúng đại diện cho các nhóm cấu hình độc lập và có thể kết hợp hợp lý. Nếu tạo quá nhiều profile nhỏ để bật/tắt từng thuộc tính, tổ hợp profile sẽ khó hiểu và khó dự đoán.

Một profile **integration** có thể chọn bean và cấu hình tích hợp; các giá trị URL, cổng và timeout vẫn nên được cung cấp qua property source phù hợp.

## 3. Tách cấu hình theo profile bằng property file

Spring Framework cung cấp nhiều cách đưa property vào Environment. Với Spring TestContext, một cách trực tiếp là **@TestPropertySource**.

Có thể tạo file trong test resources, ví dụ **src/test/resources/test-config/order-test.properties**:

~~~properties
orders.currency=VND
orders.shipping.fee=30000
payment.mode=fake
payment.timeout=2s
~~~

Test nạp file này:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(
    locations = "classpath:test-config/order-test.properties"
)
@ActiveProfiles("test")
class OrderPropertiesTest {

    @Autowired
    private Environment environment;

    @Test
    void loadsTestProperties() {
        assertEquals("VND", environment.getProperty("orders.currency"));
        assertEquals("fake", environment.getProperty("payment.mode"));
    }
}
~~~

**@TestPropertySource** có thể nạp file property hoặc khai báo thuộc tính trực tiếp trong annotation:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(properties = {
    "orders.currency=VND",
    "payment.mode=fake",
    "payment.timeout=2s"
})
class InlineTestProperties {
}
~~~

Dùng inline properties cho một vài giá trị rất riêng của test. Nếu nhiều test cần chung cấu hình, một file test properties hoặc class cấu hình dùng chung sẽ dễ bảo trì hơn.

### Thứ tự ưu tiên property

Khi cùng một key được định nghĩa ở nhiều nguồn, giá trị cuối cùng mà bean nhận được phụ thuộc thứ tự ưu tiên của các property source. Trong Spring TestContext, các property được khai báo trực tiếp hoặc nạp bằng **@TestPropertySource** có ưu tiên cao hơn những nguồn property thông thường như **@PropertySource**, biến môi trường và system property.

**@DynamicPropertySource** có ưu tiên cao hơn **@TestPropertySource**, phù hợp với giá trị chỉ có sau khi một tài nguyên test được khởi chạy, chẳng hạn cổng database container.

Không nên khai báo cùng một key ở quá nhiều nơi. Nếu cần override, hãy giữ mục đích rõ ràng và kiểm tra giá trị hiệu lực qua **Environment** hoặc bean đã được bind.

## 4. Cấu hình theo profile trong Spring Boot

Nếu dự án dùng Spring Boot, cơ chế Config Data cho phép đặt file cấu hình theo profile, ví dụ:

~~~text
src/
  main/
    resources/
      application.yml
  test/
    resources/
      application-test.yml
~~~

Ví dụ **application-test.yml**:

~~~yaml
orders:
  currency: VND
  shipping:
    fee: 30000

payment:
  mode: fake
  base-url: http://localhost:9090
  timeout: 2s
~~~

Khi profile **test** được kích hoạt, Spring Boot có thể nạp cấu hình profile tương ứng. Trong test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {
}
~~~

Điểm cần phân biệt: **application-test.yml** là cơ chế cấu hình của Spring Boot. Một bài test chỉ dùng Spring Framework TestContext với **@SpringJUnitConfig** không tự động có toàn bộ quy tắc Config Data của Spring Boot. Với Spring Framework thuần, hãy nạp property bằng **@TestPropertySource**, **@PropertySource**, **@PropertySources**, initializer hoặc cách cấu hình Environment phù hợp.

Không đặt credential thật trong **application-test.yml** được commit vào repository. File này phù hợp với các giá trị không nhạy cảm như timeout, mode giả lập, tên schema test hoặc URL localhost.

## 5. Quản lý bí mật riêng với property thông thường

Bí mật thường xuất hiện trong cấu hình database, dịch vụ thanh toán, email, OAuth client hoặc API bên thứ ba. Dù chỉ dùng cho test, credential có thể cấp quyền đọc dữ liệu, tạo giao dịch hoặc gọi tài nguyên có chi phí.

Các nguyên tắc quan trọng:

1. Không commit password, API token, private key hoặc client secret vào Git.
2. Không đặt bí mật thật trong file YAML/Properties, test fixture, ví dụ code hoặc annotation.
3. Cấp credential qua secret manager của CI, biến môi trường hoặc cơ chế bảo mật mà nền tảng triển khai cung cấp.
4. Dùng tài khoản test có quyền tối thiểu và chỉ truy cập tài nguyên test.
5. Không ghi credential vào log, exception message, assertion failure hoặc artifact CI.
6. Thu hồi và thay mới credential khi nghi ngờ bị lộ hoặc khi vòng đời credential kết thúc.

### Dùng biến môi trường để cung cấp bí mật

Với Spring Boot, property có thể tham chiếu biến môi trường:

~~~yaml
payment:
  base-url: ${PAYMENT_SANDBOX_URL:http://localhost:9090}
  api-key: ${PAYMENT_SANDBOX_API_KEY:local-placeholder}
~~~

Giá trị mặc định **local-placeholder** chỉ là chuỗi giả để chạy test local với adapter giả hoặc server mô phỏng. Nó không phải credential có thể dùng để xác thực dịch vụ thật.

Trong CI, pipeline có thể cấp **PAYMENT_SANDBOX_API_KEY** từ secret store của nền tảng. Không lưu giá trị secret trong file workflow, log hoặc command line có thể bị ghi lại.

Với Spring Framework thuần, có thể đọc biến môi trường qua **Environment** hoặc placeholder resolver:

~~~java
@Configuration
class PaymentClientConfiguration {

    @Bean
    PaymentClient paymentClient(Environment environment) {
        String apiKey = environment.getRequiredProperty(
                "payment.api-key"
        );

        return new PaymentClient(apiKey);
    }
}
~~~

Nếu cấu hình bean thật cần credential, hãy bảo đảm test dùng fake hoặc test-specific configuration khi không cần gọi dịch vụ thật. Không yêu cầu mọi developer phải có credential sandbox chỉ để chạy unit test.

### Tách secret theo môi trường

Local, CI và môi trường tích hợp có thể cần credential khác nhau:

| Nơi chạy | Nguồn secret | Credential nên có |
|---|---|---|
| Unit test local | Không cần secret thật | Giá trị giả hoặc mock |
| Integration test local | Biến môi trường do developer tự cấu hình hoặc secret store | Tài khoản sandbox giới hạn quyền |
| CI | Secret store của CI | Credential test được cấp cho job cần dùng |
| Production | Secret manager hoặc nền tảng quản lý secret | Credential production theo quyền tối thiểu |

Không tái sử dụng credential production cho test. Một lỗi cấu hình có thể khiến test ghi hoặc xóa dữ liệu thật. Hãy dùng endpoint và tài khoản sandbox riêng, hoặc chặn truy cập mạng ra ngoài trong nhóm test không cần dịch vụ ngoài.

### Không đưa secret vào log

Tránh log toàn bộ Environment, property object hoặc HTTP header. Nếu cần chẩn đoán, chỉ ghi tên cấu hình, trạng thái đã được cấp hay chưa, hoặc một định danh không nhạy cảm. Không ghi giá trị API key, password hoặc Authorization header.

Nếu test thất bại do thiếu secret, thông báo nên nói rõ biến môi trường nào chưa được cấp mà không in giá trị của nó.

## 6. Đừng dùng profile để che giấu cấu hình production

Một cấu hình test có thể thay bean thật bằng fake, nhưng điều đó không có nghĩa mọi lỗi cấu hình production sẽ được phát hiện. Hãy chia test theo mục tiêu:

- Unit test dùng fake/stub/mock và không cần credential.
- Integration test dùng database hoặc broker test thật để xác minh adapter và cấu hình.
- Contract test có thể xác minh request/response với sandbox.
- Deployment smoke test kiểm tra cấu hình môi trường sau khi triển khai, trong phạm vi an toàn.

Nếu một test bắt buộc dùng profile **test**, nó có thể không phát hiện việc profile production thiếu bean hoặc sai endpoint. Có thể bổ sung test cấu hình hoặc smoke test riêng để xác minh những điều đó mà không cần gọi production trong unit suite.

Một profile test không nên tự động làm mọi thành phần bên ngoài biến mất nếu mục tiêu là kiểm tra tích hợp. Hãy quyết định rõ phụ thuộc nào cần thật, phụ thuộc nào có thể giả lập và test cần chứng minh điều gì.

## 7. Tách dữ liệu kiểm thử khỏi cấu hình

Dữ liệu kiểm thử mô tả trạng thái hoặc đầu vào của kịch bản. Nó có thể nằm trong code, builder, JSON, CSV hoặc SQL script.

Ví dụ một fixture JSON:

~~~json
{
  "customerId": "customer-test-18",
  "currency": "VND",
  "items": [
    {
      "sku": "SKU-RED-01",
      "quantity": 2,
      "unitPrice": 125000
    }
  ]
}
~~~

Fixture này chứa dữ liệu nghiệp vụ giả, không chứa credential. Có thể đặt trong **src/test/resources/fixtures/order-valid.json** và đọc trong test.

Dữ liệu test nên:

- Có tính tổng hợp hoặc đã được ẩn danh đúng cách.
- Chỉ chứa trường cần thiết cho kịch bản.
- Có tên dễ hiểu theo ý nghĩa nghiệp vụ.
- Có thể tái tạo và không phụ thuộc vào dữ liệu production hiện tại.
- Không chứa token, password, email hoặc thông tin cá nhân thật nếu không cần thiết.

Không nên sao chép nguyên database production để dùng làm fixture. Dữ liệu production có thể chứa thông tin cá nhân, credential, dữ liệu nhạy cảm hoặc trạng thái không ổn định. Hãy tạo dữ liệu tổng hợp theo hợp đồng nghiệp vụ.

## 8. Tạo dữ liệu bằng factory, builder và fixture

Có ba cách phổ biến để chuẩn bị dữ liệu.

### Factory hoặc builder

Dùng factory khi test cần nhiều đối tượng có cấu trúc tương tự nhưng khác một vài thuộc tính.

~~~java
final class OrderTestData {

    static Order validOrder() {
        return new Order(
                "order-test-18",
                "customer-test-7",
                List.of(new OrderLine("SKU-RED-01", 2, new BigDecimal("125000")))
        );
    }

    static Order orderForCustomer(String customerId) {
        return new Order(
                "order-test-19",
                customerId,
                List.of(new OrderLine("SKU-BLUE-02", 1, new BigDecimal("80000")))
        );
    }
}
~~~

Factory giúp giảm phần Arrange lặp lại. Tuy nhiên, không nên để factory tự gọi service production để tính expected cho chính quy tắc mà test đang kiểm tra. Dữ liệu đầu vào nên được khai báo tường minh.

Builder phù hợp khi entity có nhiều trường tùy chọn:

~~~java
Order order = Order.builder()
        .id("order-test-21")
        .customerId("customer-test-9")
        .status(OrderStatus.PENDING)
        .total(new BigDecimal("250000"))
        .build();
~~~

Builder chỉ nên tạo dữ liệu. Các quy tắc nghiệp vụ cần kiểm tra vẫn thuộc đối tượng production và cần expected độc lập.

### Fixture file

Fixture file phù hợp với payload lớn hoặc dữ liệu cần dùng chung giữa nhiều test. Có thể lưu JSON, XML, CSV hoặc YAML trong test resources.

Ưu điểm:

- Tách dữ liệu khỏi logic test.
- Dễ đọc payload nhiều trường.
- Có thể dùng cùng fixture cho unit test và integration test nếu cấu trúc phù hợp.
- Có thể review thay đổi dữ liệu trong Git.

Không nên tạo fixture quá lớn chứa nhiều dữ liệu không liên quan. Một fixture tốt thể hiện rõ kịch bản và chỉ giữ những trường cần thiết.

### SQL script

Với test persistence, Spring TestContext hỗ trợ **@Sql** để chạy script trước hoặc sau test method:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
@Sql(
    scripts = "/sql/orders-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsThePreparedOrder() {
        Optional<OrderEntity> order = repository.findById("order-test-18");

        assertTrue(order.isPresent());
        assertEquals("customer-test-7", order.get().getCustomerId());
    }
}
~~~

Ví dụ **orders-before-test.sql**:

~~~sql
INSERT INTO customers (id, name)
VALUES ('customer-test-7', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('order-test-18', 'customer-test-7', 'PENDING');
~~~

Script cần phù hợp schema và dialect database mà test sử dụng. Nếu test dùng transaction được Spring quản lý, script có thể chạy trong transaction theo cấu hình mặc định hoặc cấu hình transaction của **@Sql**. Hãy hiểu rõ transaction mode để tránh dữ liệu được commit ngoài dự kiến.

Có thể khai báo script cleanup ở phase **AFTER_TEST_METHOD** khi test không dùng rollback hoặc cần dọn side effect được commit riêng:

~~~java
@Sql(
    scripts = "/sql/cleanup-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

Nếu test đã rollback toàn bộ transaction, cleanup script có thể không cần thiết. Tránh xóa dữ liệu chung bằng điều kiện quá rộng; script cleanup phải chỉ nhắm đến dữ liệu mà test sở hữu.

## 9. Cô lập dữ liệu giữa các test

Test cần độc lập để có thể chạy riêng, chạy lại, chạy song song hoặc chạy theo thứ tự bất kỳ. Nếu một test phụ thuộc dữ liệu do test khác tạo, bộ test sẽ dễ chập chờn.

Các chiến lược thường dùng:

### Transaction rollback

Với test persistence được Spring quản lý transaction, có thể đánh dấu class hoặc method bằng **@Transactional**. Spring TestContext thường rollback transaction sau mỗi test method.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderPersistenceTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void createsOrderWithinTestTransaction() {
        repository.save(new OrderEntity("order-tx-1", "customer-tx-1"));

        assertTrue(repository.findById("order-tx-1").isPresent());
    }
}
~~~

Cách này hiệu quả khi các thao tác database tham gia cùng test-managed transaction. Nó không tự rollback:

- HTTP request gửi sang dịch vụ khác.
- Message đã được publish ra broker.
- Giao dịch chạy ở thread khác.
- Transaction độc lập đã commit.
- File đã ghi ra filesystem hoặc object storage.

Một ví dụ quan trọng là test chạy server thật với request HTTP. Request được xử lý ở thread server, không tự động tham gia transaction của test thread. Vì vậy, không thể mặc định rằng **@Transactional** trên test method sẽ rollback dữ liệu do request đó ghi.

### Dùng định danh riêng cho từng test

Khi nhiều test dùng chung database hoặc schema, tạo mã định danh riêng để tránh xung đột:

~~~java
String testRunId = UUID.randomUUID().toString();
String customerId = "customer-" + testRunId;
String orderId = "order-" + testRunId;
~~~

Dùng ID riêng giúp test song song ít va chạm hơn. Nếu cần dọn dữ liệu, hãy lưu ID hoặc namespace mà test tạo để xóa đúng phạm vi.

Không nên assert trực tiếp một UUID ngẫu nhiên đã biết trước. Hãy kiểm tra thuộc tính nghiệp vụ hoặc xác nhận kết quả dùng chính ID được tạo trong Arrange.

### Cleanup có phạm vi

Nếu dữ liệu được commit hoặc nằm ngoài transaction, test cần dọn nó sau khi hoàn tất:

- Xóa đúng các bản ghi được tạo bởi test.
- Dùng schema/database riêng cho từng suite hoặc worker.
- Dùng container riêng khi cần cô lập hạ tầng.
- Xóa message hoặc reset trạng thái broker bằng cơ chế dành cho test.
- Dừng server, container và tài nguyên được tạo trong test.

Cleanup nên an toàn khi test thất bại giữa chừng. Dùng hook teardown hoặc cơ chế lifecycle phù hợp để dọn cả khi assertion không thành công.

### Tránh dữ liệu dùng chung có thể thay đổi

Fixture tĩnh có thể được đọc lại cho từng test, nhưng không nên chia sẻ một mutable object rồi sửa nó giữa nhiều test. Nếu một test thay đổi list hoặc entity, test khác có thể nhận trạng thái đã bị biến đổi.

Hãy tạo object mới cho từng test hoặc dùng factory trả về bản sao độc lập.

## 10. Cô lập database và dịch vụ phụ trợ

Một test cần database thật nên dùng database dành riêng cho test. Có thể dùng database trong bộ nhớ cho truy vấn đơn giản, hoặc dùng container của đúng hệ quản trị nếu cần xác minh SQL và hành vi đặc thù.

Với Testcontainers, có thể khởi chạy PostgreSQL cho integration test và đăng ký thuộc tính kết nối động:

~~~java
@Testcontainers
@SpringBootTest
@ActiveProfiles("integration")
class OrderDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Testcontainers cần dependency phù hợp trong test runtime. Ví dụ này dùng Spring Boot để nạp cấu hình ứng dụng; nếu dùng Spring Framework TestContext thuần, có thể kết hợp **@ContextConfiguration** với **@DynamicPropertySource** để đăng ký các thuộc tính datasource vào Environment.

Không nên hard-code cổng container vì cổng host có thể được ánh xạ động. Dùng các phương thức JDBC URL và credential do container cung cấp.

Với broker hoặc dịch vụ phụ trợ khác, áp dụng nguyên tắc tương tự: khởi chạy instance test riêng, đăng ký endpoint động và đảm bảo lifecycle được quản lý. Nếu test chỉ cần xác minh phản ứng của service với kết quả phụ thuộc, stub/fake có thể phù hợp hơn việc khởi động toàn bộ hạ tầng.

## 11. Dữ liệu thời gian, ngẫu nhiên và locale cũng cần kiểm soát

Dữ liệu test không chỉ là bản ghi database. Thời gian hiện tại, random, timezone, locale và thứ tự collection cũng có thể làm kết quả thay đổi.

### Cố định thời gian bằng Clock

Không nên để logic nghiệp vụ gọi trực tiếp **Instant.now()** hoặc **LocalDate.now()** nếu test cần kết quả xác định. Hãy inject Clock:

~~~java
@Configuration
class TimeTestConfig {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-07-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Trong production, có thể dùng **Clock.systemUTC()**. Trong test, clock cố định giúp kiểm tra ngày hết hạn, thời điểm tạo đơn hoặc quy tắc tính kỳ hạn mà không phụ thuộc thời điểm chạy.

### Kiểm soát random

Nếu test cần số ngẫu nhiên, hãy inject một nguồn random có thể cấu hình seed hoặc dùng một implementation giả định trước kết quả. Không để test phụ thuộc vào một lần random may mắn.

Nếu mục tiêu là kiểm tra tính duy nhất của ID, có thể dùng UUID và kiểm tra định dạng hoặc tính khác nhau trong cùng kịch bản, thay vì mong đợi một giá trị cố định.

### Kiểm soát timezone và locale

Ngày giờ có thể khác khi máy local và CI dùng timezone khác nhau. Hãy dùng Instant hoặc LocalDate với Clock rõ ràng, chỉ định ZoneId khi chuyển đổi và tránh phụ thuộc timezone mặc định của máy.

Nếu test format số, tiền tệ hoặc ngày theo locale, hãy truyền locale rõ ràng thay vì dùng locale mặc định của JVM.

## 12. Tổ chức thư mục cấu hình và dữ liệu test

Một cấu trúc đơn giản có thể như sau:

~~~text
src/
  main/
    java/
    resources/
      application.yml
  test/
    java/
      .../
        config/
          TestProfileConfig.java
        support/
          OrderTestData.java
        .../
          OrderServiceTest.java
          OrderIntegrationTest.java
    resources/
      application-test.yml
      test-config/
        order-test.properties
      fixtures/
        order-valid.json
        orders.csv
      sql/
        orders-before-test.sql
        cleanup-orders.sql
~~~

Trong cấu trúc này:

- **application-test.yml** chứa cấu hình không nhạy cảm dành cho Spring Boot test.
- **test-config** chứa property file cho test dùng Spring TestContext.
- **fixtures** chứa dữ liệu JSON/CSV có thể tái sử dụng.
- **sql** chứa script tạo hoặc dọn dữ liệu database.
- **support** chứa factory, builder và helper tạo dữ liệu.
- **config** chứa cấu hình Spring dành riêng cho test.

Bí mật thật không nên nằm trong các thư mục này. Nếu local cần file secret riêng, hãy đặt ngoài repository và thêm đường dẫn file đó vào **.gitignore** khi file nằm trong workspace. Tốt hơn, dùng biến môi trường hoặc secret manager để tránh file bí mật bị thêm nhầm vào Git.

Ví dụ **.gitignore** có thể chứa các pattern dành cho file local:

~~~gitignore
.env
.env.*
!.env.example
application-local-secrets.yml
test-secrets.properties
~~~

File **.env.example** chỉ nên chứa tên biến và giá trị placeholder, không chứa credential thật.

## 13. Chạy cùng một bộ test ở local và CI

Một bộ test tốt nên cho kết quả nhất quán giữa máy developer và pipeline. Để đạt điều đó, hãy thống nhất cách kích hoạt profile, cấp property, chuẩn bị database và nạp fixture.

Ví dụ:

| Thành phần | Local | CI |
|---|---|---|
| Profile unit | test | test |
| Profile integration | integration | integration |
| Database integration | Container local | Container trên runner |
| API key sandbox | Biến môi trường nếu test cần | Secret store của CI |
| Fixture | Trong test resources | Cùng fixture trong repository |
| Dữ liệu database | Tạo mới cho test | Tạo mới cho mỗi job hoặc suite |
| Log | Không in secret | Redact credential và header nhạy cảm |

Một pipeline có thể chia thành hai nhóm:

1. **Unit và slice tests** chạy nhanh, không cần credential bên ngoài.
2. **Integration tests** khởi chạy database/broker test, nhận credential sandbox nếu thật sự cần và dọn tài nguyên sau khi chạy.

Không nên để toàn bộ suite phụ thuộc vào một API sandbox có thể gián đoạn. Nếu cần kiểm tra hợp đồng với dịch vụ ngoài, tách nhóm test đó và quản lý timeout, retry, credential và điều kiện chạy rõ ràng.

## 14. Tránh các lỗi bảo mật và tính ổn định thường gặp

### Commit credential vào repository

Một API key trong file test vẫn là secret. Xóa nó khỏi commit mới không làm credential cũ biến mất khỏi lịch sử Git. Nếu credential thật đã bị commit, hãy thu hồi hoặc rotate theo quy trình của nhà cung cấp và kiểm tra log/artifact liên quan.

### Dùng database production cho test

Một test có thể xóa hoặc cập nhật dữ liệu thật nếu endpoint hoặc JDBC URL bị cấu hình sai. Dùng database riêng, user riêng, schema riêng và quyền tối thiểu. Nếu có thể, chặn kết nối từ test suite thông thường đến production network.

### Dùng cùng một dữ liệu mutable cho mọi test

Một test thay đổi entity hoặc collection có thể ảnh hưởng test khác. Hãy tạo dữ liệu mới cho từng test và tránh static mutable fixture.

### Trông cậy vào thứ tự chạy

Test A không nên tạo dữ liệu để test B sử dụng. Mỗi test phải tự chuẩn bị trạng thái cần thiết và dọn những gì nó sở hữu.

### Chỉ dùng @DirtiesContext để dọn dữ liệu

**@DirtiesContext** quản lý ApplicationContext cache. Nó không tự xóa bản ghi đã commit, thu hồi message, xóa file hoặc reset dịch vụ bên ngoài.

### Giữ secret trong thông báo lỗi

Không nối API key hoặc password vào exception, assertion message hay debug log. Nếu cấu hình thiếu, chỉ báo tên property hoặc biến môi trường cần được cấp.

### Coi profile test là bảo đảm an toàn

Một profile có thể bị kích hoạt nhầm hoặc một property có thể bị override. Hãy dùng endpoint test riêng, credential giới hạn quyền và kiểm soát mạng. Không dựa vào tên profile để ngăn truy cập production.

### Fixture chứa dữ liệu cá nhân thật

Dùng dữ liệu tổng hợp hoặc dữ liệu đã ẩn danh phù hợp. Không đưa bản sao production vào test resources chỉ để có dữ liệu phong phú.

## 15. Quy trình thiết lập một bộ kiểm thử có thể tái tạo

Khi tạo test cho một module mới, có thể đi theo trình tự:

1. **Chọn phạm vi test**: unit, slice hay integration.
2. **Chọn profile**: xác định nhóm bean và cấu hình cần kích hoạt.
3. **Khai báo property không nhạy cảm**: URL local, timeout, tên schema, feature flag và chế độ giả lập.
4. **Xác định bí mật cần thiết**: ưu tiên không cần secret cho unit test; nếu integration cần credential, lấy từ secret store hoặc biến môi trường.
5. **Tạo dữ liệu test**: dùng builder, factory, fixture hoặc SQL script.
6. **Cô lập trạng thái**: transaction rollback, ID riêng, database/schema/container riêng hoặc cleanup có phạm vi.
7. **Kiểm soát nguồn không xác định**: Clock, random, locale, timezone và endpoint bên ngoài.
8. **Chạy lại ở CI**: bảo đảm cùng cách kích hoạt profile và property, đồng thời không ghi credential vào log.
9. **Dọn tài nguyên**: đóng context khi cần, dừng container, xóa dữ liệu đã commit và thu hồi tài nguyên tạm.

Một test cho OrderService có thể dùng profile **test**, fake repository, fake payment gateway, Clock cố định và fixture tổng hợp. Nó không cần API key thật hoặc database. Một integration test riêng có thể dùng profile **integration**, PostgreSQL container và credential sandbox được cấp riêng nếu cần xác minh adapter HTTP.

## 16. Ví dụ tổng hợp: cấu hình test tách biệt

Cấu hình test không nhạy cảm:

~~~properties
orders.currency=VND
orders.shipping.fee=30000
payment.mode=fake
payment.timeout=2s
~~~

Test configuration:

~~~java
@Configuration
@Profile("test")
class OrderTestConfiguration {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-07-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    OrderService orderService(
            OrderRepository repository,
            PaymentGateway paymentGateway,
            Clock clock) {
        return new OrderService(repository, paymentGateway, clock);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(
    locations = "classpath:test-config/order-test.properties"
)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderWithTestDependencies() {
        Order order = orderService.create(OrderTestData.validOrderCommand());

        assertEquals("customer-test-7", order.customerId());
        assertEquals(
                Instant.parse("2026-07-01T09:00:00Z"),
                order.createdAt()
        );
    }
}
~~~

Trong ví dụ, profile chọn cấu hình test, property file chứa các giá trị không nhạy cảm, fake repository và fake payment gateway thay phụ thuộc ngoài, còn Clock cố định giúp kết quả thời gian có thể dự đoán. Dữ liệu đầu vào đến từ factory trong test code.

Nếu một integration test cần kết nối sandbox, hãy dùng profile và cấu hình riêng, lấy API key từ biến môi trường được CI cấp và chỉ cấp quyền cần thiết cho test. Không đưa credential vào file fixture hoặc file property được commit.

## 17. Nguyên tắc cần giữ khi tách bí mật, môi trường và dữ liệu

- Profile quyết định nhóm cấu hình hoặc bean được kích hoạt; profile không phải secret store.
- Property source cung cấp giá trị cấu hình; không nên để nhiều nguồn cùng định nghĩa một key mà không có lý do rõ ràng.
- Secret phải được cấp từ nguồn bảo mật, giới hạn quyền, không commit và không ghi log.
- Dữ liệu test nên tổng hợp, nhỏ gọn, có ý nghĩa và được tạo riêng cho từng kịch bản.
- Fixture chỉ chứa dữ liệu, không chứa credential thật.
- Transaction rollback chỉ bảo vệ thao tác nằm trong transaction đó.
- Dữ liệu đã commit và side effect bên ngoài cần cleanup riêng.
- Test phải độc lập với thứ tự chạy, timezone, thời gian hệ thống và trạng thái còn sót.
- CI cần tái tạo được môi trường mà không phụ thuộc file bí mật trên máy developer.

Tách riêng ba nhóm này giúp mỗi bộ kiểm thử chạy đúng môi trường, có đủ dữ liệu và không cần quyền truy cập vượt quá mục đích. Khi test chỉ cần xác minh logic, dùng profile test cùng fake và fixture tổng hợp. Khi cần xác minh tích hợp, cấp tài nguyên test riêng và credential giới hạn quyền. Nhờ đó, kết quả test có thể tái tạo ở local và CI mà không làm lẫn cấu hình, bí mật hoặc dữ liệu với môi trường production.

