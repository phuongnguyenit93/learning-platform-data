# Không dùng cấu hình kiểm thử để che cấu hình sản xuất bị lỗi

Một bộ kiểm thử có thể chạy xanh trong khi ứng dụng vẫn không khởi động được ở production. Nguyên nhân thường gặp là môi trường test cung cấp property, profile hoặc bean thay thế khiến Spring không còn sử dụng cấu hình mà production thực sự cần.

Ví dụ, production yêu cầu URL của cổng thanh toán và khóa API từ biến môi trường. Test lại đặt sẵn một URL giả và một khóa mẫu bằng @TestPropertySource. Bài test vẫn chạy, nhưng không chứng minh rằng môi trường production có cung cấp đúng hai giá trị đó. Tương tự, profile test có thể đăng ký FakePaymentGateway trong khi profile production thiếu bean PaymentGateway thật.

Đây là một dạng **cảm giác an toàn giả do cấu hình test che khuất lỗi cấu hình production**. Bài test chỉ chứng minh ứng dụng hoạt động với tập property và bean đã được dựng cho test. Muốn kiểm tra cấu hình production, cần xác định rõ cấu hình nào đang được kiểm tra, cấu hình nào được thay thế có chủ đích và cấu hình nào phải được xác minh trong môi trường triển khai.

## 1. Vì sao test xanh vẫn có thể che lỗi production?

Spring lấy cấu hình từ nhiều nguồn: file application.yml, file theo profile, biến môi trường, system properties, tham số dòng lệnh, property source được thêm bằng code và các nguồn cấu hình của Spring Test.

Các nguồn này có thứ tự ưu tiên. Một giá trị được đặt ở nguồn ưu tiên cao hơn có thể ghi đè giá trị trong application.yml hoặc application-prod.yml.

Ví dụ:

~~~yaml
# application-prod.yml
payment:
  base-url: https://payments.example.com
  api-key: ${PAYMENT_API_KEY}
  connect-timeout: 2s
  read-timeout: 5s
~~~

Test có thể khai báo:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
@TestPropertySource(properties = {
        "payment.base-url=http://localhost:9099",
        "payment.api-key=test-key",
        "payment.connect-timeout=10s"
})
class PaymentServiceTest {
}
~~~

Test này đang chạy với profile prod, nhưng ba property quan trọng đã bị ghi đè bởi property source của test. Nếu application-prod.yml thiếu base-url, cấu hình timeout sai hoặc biến PAYMENT_API_KEY không được triển khai, test vẫn có thể xanh.

Cần phân biệt hai kết luận:

- Test xanh chứng minh service hoạt động với các giá trị test đã cung cấp.
- Test xanh không chứng minh các giá trị production được đóng gói hoặc được môi trường triển khai cung cấp là đúng.

Tên profile prod trong annotation không đủ để chứng minh test đang sử dụng đầy đủ cấu hình production. Hãy xem xét toàn bộ property sources và các bean thay thế trong context.

## 2. Những cách cấu hình test thường che khuất lỗi production

### 2.1. Dùng profile test thay cho profile production

Giả sử dự án có hai file:

~~~yaml
# application-test.yml
payment:
  enabled: false
  base-url: http://localhost:9099
~~~

~~~yaml
# application-prod.yml
payment:
  enabled: true
  base-url: ${PAYMENT_API_URL}
~~~

Test dùng:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentServiceTest {
}
~~~

Khi profile test hoạt động, Spring nạp application-test.yml. Test không kiểm tra application-prod.yml. Điều này hoàn toàn hợp lý nếu mục tiêu là kiểm tra nghiệp vụ trong môi trường test, nhưng không thể dùng kết quả đó để kết luận cấu hình production đúng.

Một số khác biệt có thể bị bỏ sót:

- Bean thanh toán production không được đăng ký trong profile test.
- Cờ payment.enabled trong production bị đặt sai.
- URL production thiếu hoặc sai định dạng.
- Timeout, retry hoặc TLS khác với yêu cầu production.
- Profile production không được kích hoạt khi triển khai.
- Một bean chỉ tồn tại trong production bị thiếu dependency.

Test theo profile riêng vẫn cần thiết. Điều quan trọng là phải có một bước kiểm tra riêng cho cấu hình production hoặc cấu hình production-like.

### 2.2. Dùng @TestPropertySource để cung cấp mọi giá trị còn thiếu

@TestPropertySource cho phép thêm property cố định vào Environment của test. Các giá trị này có độ ưu tiên cao và có thể che property thiếu hoặc sai trong file cấu hình.

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:postgresql://localhost/testdb",
        "spring.datasource.username=test",
        "spring.datasource.password=test",
        "payment.api-key=dummy",
        "payment.base-url=http://localhost:9099"
})
class ApplicationIntegrationTest {
}
~~~

Cách này tiện để cô lập dependency, nhưng nếu test được dùng làm bằng chứng cho cấu hình production thì nó đã thay thế chính các giá trị cần xác minh.

Trước khi thêm property vào test, hãy ghi rõ mục đích:

- Giá trị này chỉ giúp test chạy an toàn với database hoặc mock server?
- Giá trị này có phải là một phần của hợp đồng cấu hình production?
- Nếu property production bị thiếu, test có cần thất bại không?
- Việc đặt giá trị test có làm mất khả năng phát hiện lỗi cần tìm không?

Nếu property đang được kiểm tra, đừng ghi đè nó trong test đó. Nếu cần thay một dependency bên ngoài để tránh gọi hệ thống thật, hãy chỉ thay những property kết nối không thuộc phạm vi đang xác minh.

### 2.3. Dùng @DynamicPropertySource để thay cấu hình thật

@DynamicPropertySource rất hữu ích khi test dùng Testcontainers hoặc mock server và cần URL được xác định tại runtime.

~~~java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Các property động này có độ ưu tiên cao trong Spring TestContext. Điều đó giúp test dùng database container, nhưng đồng thời có nghĩa test không kiểm tra URL và thông tin đăng nhập database production.

Đây không phải lý do để tránh Testcontainers. Hãy sử dụng chúng đúng mục tiêu:

- Repository integration test xác minh ứng dụng làm việc với PostgreSQL thật trong môi trường test.
- Configuration contract test xác minh các property production được cung cấp và bind đúng.
- Deployment validation xác minh manifest, secret reference và biến môi trường được gắn vào workload.

Một test không cần chứng minh mọi điều cùng lúc. Nhưng không được lấy kết quả của test đã thay database production bằng container để kết luận cấu hình database production đã đúng.

### 2.4. Mock hoặc thay bean production bằng implementation test

Ví dụ, production dùng:

~~~java
@Component
@Profile("prod")
class HttpPaymentGateway implements PaymentGateway {
    // Gọi dịch vụ thanh toán bên ngoài.
}
~~~

Trong test, cấu hình thay bean:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Test dùng FakePaymentGateway sẽ không kiểm tra HttpPaymentGateway. Nó cũng không xác minh các dependency, HTTP client, timeout, TLS hoặc property mà adapter production cần.

Thay bean là cách cô lập hợp lệ khi kiểm tra nghiệp vụ của service. Nhưng nếu mục tiêu là kiểm tra wiring hoặc cấu hình adapter production, không nên thay chính bean đó.

Có thể chia thành các test riêng:

- Unit test cho PaymentService với mock PaymentGateway.
- Adapter test cho HttpPaymentGateway với mock HTTP server.
- Context test xác minh bean production được đăng ký và nhận đúng cấu hình.
- System test có chọn lọc để xác minh giao tiếp qua môi trường tích hợp an toàn.

### 2.5. Vô hiệu hóa tính năng để test khởi động được

Một số cấu hình test đặt các tính năng production về false:

~~~properties
payment.enabled=false
messaging.enabled=false
scheduler.enabled=false
security.enabled=false
~~~

Điều này có thể giúp context khởi động nhanh, nhưng có thể che các lỗi như:

- Bean production không được đăng ký.
- Điều kiện @ConditionalOnProperty bị cấu hình sai.
- SecurityFilterChain không tồn tại hoặc không được áp dụng.
- Message listener không được tạo.
- Scheduler không có dependency cần thiết.
- Tích hợp quan trọng bị tắt ngoài ý muốn.

Nếu test chỉ kiểm tra một service không liên quan, việc tắt các tính năng có thể phù hợp. Nhưng cần một bài test riêng xác minh những tính năng bắt buộc phải bật trong production.

## 3. Property precedence: hiểu giá trị cuối cùng Spring thực sự sử dụng

Spring Environment tổng hợp property từ nhiều PropertySource. Khi cùng một key xuất hiện ở nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ được dùng.

Trong Spring Boot, những nguồn có độ ưu tiên cao như tham số dòng lệnh, system properties, biến môi trường và property source được bổ sung cho test có thể ghi đè giá trị trong file cấu hình. Thứ tự chính xác còn phụ thuộc loại nguồn và cách ứng dụng được khởi chạy.

Một số nguồn phổ biến:

| Nguồn | Ví dụ | Tác dụng |
|---|---|---|
| application.yml | payment.connect-timeout: 2s | Giá trị mặc định được đóng gói |
| application-prod.yml | Cấu hình riêng profile prod | Ghi đè cấu hình chung khi profile prod hoạt động |
| Biến môi trường | PAYMENT_CONNECT_TIMEOUT=3s | Cấu hình do môi trường triển khai cung cấp |
| System property | -Dpayment.connect-timeout=4s | Cấu hình ở cấp JVM |
| Tham số dòng lệnh | --payment.connect-timeout=5s | Ghi đè khi chạy ứng dụng |
| @TestPropertySource | payment.connect-timeout=10s | Property riêng của test |
| @DynamicPropertySource | URL container lấy từ supplier | Property động cho test |

Không nên chỉ nhìn file YAML để kết luận giá trị thực tế. Production có thể nhận giá trị từ biến môi trường hoặc secret/config store. Ngược lại, test có thể đang dùng một nguồn ưu tiên cao hơn khiến file YAML không được kiểm tra.

Có thể đọc giá trị đã được resolve từ Environment:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class PaymentConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void shouldResolvePaymentTimeout() {
        assertEquals(
                Duration.ofSeconds(2),
                environment.getProperty(
                        "payment.connect-timeout",
                        Duration.class
                )
        );
    }
}
~~~

Assertion trên xác minh giá trị cuối cùng mà Environment trả về trong context test. Nó vẫn chưa chứng minh giá trị đến từ đúng nguồn. Nếu một property test hoặc biến môi trường đang ghi đè file production, giá trị assertion có thể đúng vì lý do khác.

Khi cần xác minh nguồn cấu hình, có thể xem PropertySource đang chứa key hoặc dùng metadata origin của Spring Boot cho các property source hỗ trợ origin tracking. Đừng ghi giá trị secret ra log khi kiểm tra cấu hình.

## 4. Phân biệt cấu hình ứng dụng, cấu hình triển khai và secret

Không phải mọi giá trị production đều nên được lưu trong application-prod.yml.

Có thể chia cấu hình thành ba nhóm:

| Nhóm | Ví dụ | Nguồn thường gặp |
|---|---|---|
| Cấu hình ứng dụng | Timeout, retry, feature flag, tên queue | File cấu hình hoặc config store |
| Cấu hình môi trường | Host database, URL API, tên bucket | Environment, deployment config, ConfigMap |
| Secret | Password, API key, private key, token | Secret manager, Kubernetes Secret hoặc nền tảng quản lý secret |

Một test không nên yêu cầu secret production thật. Dùng secret thật trong test có thể khiến thông tin nhạy cảm xuất hiện trong log, artifact hoặc môi trường CI không phù hợp.

Tuy nhiên, dùng giá trị giả cũng không chứng minh secret production đã được cung cấp.

Nên tách trách nhiệm:

1. **Configuration contract test** kiểm tra tên property, kiểu dữ liệu, giá trị bắt buộc và quy tắc validation bằng cấu hình an toàn.
2. **Deployment configuration validation** kiểm tra manifest hoặc pipeline tham chiếu đúng secret và biến môi trường.
3. **Runtime startup validation** xác minh workload nhận được các giá trị cần thiết khi khởi động trong môi trường staging hoặc production.
4. **Secret availability check** chỉ xác minh secret tồn tại và có thể được truy cập bởi workload, không in giá trị ra log.

Không đưa secret vào source code, test report hoặc assertion message. Nếu cần kiểm tra secret có mặt, chỉ xác minh điều kiện tồn tại hoặc kết quả bind hợp lệ.

## 5. Kiểm tra cấu hình production mà không kết nối production

Một lỗi thường gặp là nghĩ rằng muốn kiểm tra profile prod thì phải khởi chạy ứng dụng với toàn bộ dịch vụ production. Điều đó không cần thiết và có thể gây tác động không mong muốn.

Có thể xây dựng một môi trường **production-like**: dùng cùng cấu trúc cấu hình, cùng tên property và cùng các điều kiện bean quan trọng, nhưng trỏ dependency bên ngoài tới database/container hoặc mock server an toàn.

Mục tiêu là giữ nguyên những giá trị đang cần kiểm tra và chỉ thay thế các ranh giới không thuộc phạm vi kiểm thử.

Ví dụ:

- Giữ profile prod để nạp application-prod.yml.
- Giữ payment.enabled và các timeout production.
- Giữ các bean production cần xác minh.
- Dùng PostgreSQL container thay database production.
- Dùng mock HTTP server thay cổng thanh toán thật.
- Cấp secret giả có định dạng hợp lệ nếu test chỉ cần khởi tạo bean.
- Kiểm tra secret production thật ở deployment pipeline hoặc runtime environment riêng.

Cần ghi rõ trong test rằng database URL và payment endpoint là các giá trị được thay có chủ đích. Những property này không được dùng làm bằng chứng cho cấu hình production.

### Ví dụ kiểm tra property của profile production

Giả sử application-prod.yml có:

~~~yaml
payment:
  enabled: true
  connect-timeout: 2s
  read-timeout: 5s
  retry:
    max-attempts: 3
  api-key: ${PAYMENT_API_KEY}
~~~

Ta có thể viết một test khởi tạo context với profile prod, cung cấp giá trị giả cho secret để bind bean, rồi xác minh các property không bị ghi đè:

~~~java
@SpringBootTest(properties = {
        "payment.api-key=configuration-test-placeholder"
})
@ActiveProfiles("prod")
class ProductionProfileContractTest {

    @Autowired
    private Environment environment;

    @Autowired
    private PaymentProperties paymentProperties;

    @Test
    void shouldLoadProductionPaymentSettings() {
        assertTrue(environment.acceptsProfiles(Profiles.of("prod")));
        assertTrue(paymentProperties.enabled());
        assertEquals(Duration.ofSeconds(2),
                paymentProperties.connectTimeout());
        assertEquals(Duration.ofSeconds(5),
                paymentProperties.readTimeout());
        assertEquals(3, paymentProperties.retry().maxAttempts());
    }
}
~~~

Trong ví dụ, api-key được thay bằng placeholder vì test không sử dụng secret thật. Do đó, test không chứng minh PAYMENT_API_KEY được cấu hình trong production. Nó chỉ xác minh các thiết lập khác của profile production được nạp theo context test.

Nếu context đầy đủ có thể khởi tạo datasource hoặc client thật, hãy cấu hình dependency an toàn cho test hoặc tạo một context contract nhỏ chỉ nạp phần cấu hình cần kiểm tra. Không chạy test này với endpoint production thật.

### Kiểm tra property bắt buộc bằng validation

Có thể dùng @ConfigurationProperties và Bean Validation để phát hiện cấu hình thiếu hoặc không hợp lệ khi khởi tạo:

~~~java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        boolean enabled,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Valid Retry retry,
        @NotBlank String apiKey
) {
    public record Retry(
            @Min(1) int maxAttempts
    ) {
    }
}
~~~

Khi property bắt buộc không có hoặc sai kiểu, context có thể thất bại trong quá trình bind/validation. Điều này tốt hơn việc để lỗi chỉ xuất hiện khi request đầu tiên gọi cổng thanh toán.

Nhưng validation chỉ chứng minh property có mặt và đáp ứng ràng buộc đã khai báo. Nó không chứng minh API key còn hiệu lực hoặc endpoint thực sự phục vụ đúng dịch vụ. Những điều đó cần kiểm tra ở lớp tích hợp hoặc health check phù hợp.

## 6. Tách test logic khỏi test cấu hình

Một bộ test có thể chia theo bằng chứng cần tạo:

| Loại test | Profile/bean sử dụng | Điều cần chứng minh |
|---|---|---|
| Unit test | Không cần Spring context; mock dependency | Logic nghiệp vụ |
| Service integration test | Context test và dependency giả lập có kiểm soát | Sự phối hợp của service với các thành phần liên quan |
| Production profile contract test | Nạp profile production hoặc production-like; chỉ override ranh giới an toàn | Property, profile, bean và điều kiện production |
| Adapter integration test | Adapter thật với mock server hoặc container | HTTP, SQL, serialization, timeout và retry |
| Deployment validation | Manifest, env, secret references của bản triển khai | Cấu hình thực tế được gắn vào workload |
| Staging smoke test | Cấu hình staging gần production | Ứng dụng khởi động và tích hợp được trong môi trường gần thực tế |

Không nên cố biến một bài unit test thành test cấu hình chỉ bằng cách thêm @SpringBootTest. Cũng không nên gọi một test là production configuration test nếu nó đã thay tất cả bean và property quan trọng bằng giá trị test.

Mỗi test cần nêu rõ điều gì được giữ thật, điều gì được mô phỏng và giới hạn của kết luận.

## 7. Kiểm tra profile production được kích hoạt đúng

Một vấn đề riêng là ứng dụng có thể được đóng gói với application-prod.yml nhưng khi triển khai lại không kích hoạt profile prod.

Có thể xác minh profile đang hoạt động trong một context test:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ActiveProductionProfileTest {

    @Autowired
    private Environment environment;

    @Test
    void shouldActivateProductionProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("prod")));
    }
}
~~~

Bài test chứng minh context của test đã kích hoạt profile prod theo annotation. Nó không chứng minh manifest triển khai thực tế có đặt SPRING_PROFILES_ACTIVE=prod.

Cần thêm bước kiểm tra deployment configuration:

- Kiểm tra environment variable hoặc tham số khởi chạy được khai báo trong manifest.
- Kiểm tra profile được truyền vào đúng container hoặc process.
- Kiểm tra profile mặc định có thể vô tình ghi đè hoặc bổ sung profile ngoài ý muốn.
- Kiểm tra startup log chỉ hiển thị profile đang hoạt động, không in secret.
- Xác minh runtime environment ở staging sau khi deploy.

Nếu profile được cấu hình bằng nhiều nguồn, cần xác định thứ tự ưu tiên và kết quả cuối cùng trong workload thực tế.

## 8. Kiểm tra điều kiện đăng ký bean mà không vô tình thay bean production

Spring Boot thường đăng ký bean theo điều kiện:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "payment",
        name = "enabled",
        havingValue = "true"
)
PaymentGateway paymentGateway(PaymentClient client) {
    return new HttpPaymentGateway(client);
}
~~~

Nếu test đặt payment.enabled=false, bean PaymentGateway sẽ không được tạo. Nếu test sau đó dùng @MockBean để cung cấp PaymentGateway, bài test có thể chạy xanh dù cấu hình production không đăng ký adapter thật.

Một configuration contract test nên xác minh điều kiện quan trọng:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionPaymentBeanTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldRegisterProductionPaymentGateway() {
        assertThat(context)
                .hasSingleBean(PaymentGateway.class);

        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(HttpPaymentGateway.class);
    }
}
~~~

Ví dụ này chỉ phù hợp khi context test được cấu hình để không gọi dịch vụ production lúc khởi tạo. Nếu bean tạo kết nối ngay khi được tạo, hãy thay transport bằng mock server hoặc dùng context test giới hạn chỉ xác minh bean wiring.

Không nên thêm @MockBean PaymentGateway vào chính test này vì như vậy test không còn kiểm tra adapter production được đăng ký.

Có thể dùng ApplicationContextRunner cho các cấu hình điều kiện độc lập. Khi cần xác minh profile, property và bean của ứng dụng hoàn chỉnh, dùng context test phù hợp với cấu hình thực tế.

## 9. Không để test property ghi đè cấu hình đang cần xác minh

Một cách tổ chức hữu ích là chia property theo mục tiêu:

~~~text
Cấu hình production cần xác minh
    |
    +-- payment.enabled
    +-- payment.connect-timeout
    +-- payment.read-timeout
    +-- payment.retry.max-attempts
    +-- payment.tls.enabled

Dependency được thay để test an toàn
    |
    +-- spring.datasource.url
    +-- spring.datasource.username
    +-- spring.datasource.password
    +-- payment.base-url (nếu đang kiểm tra business settings,
         nhưng không kiểm tra endpoint production)
    +-- payment.api-key (placeholder nếu không kiểm tra secret)
~~~

Hãy tạo một bảng phạm vi cho từng test suite:

| Property | Có được override trong test không? | Lý do |
|---|---|---|
| payment.connect-timeout | Không trong test kiểm tra profile production | Giá trị production là đối tượng cần xác minh |
| payment.retry.max-attempts | Không trong test kiểm tra retry policy production | Cần phát hiện sai cấu hình |
| spring.datasource.url | Có thể | Dùng database container thay production |
| spring.datasource.password | Có thể | Dùng credential của database test |
| payment.base-url | Có thể trong adapter test | Trỏ tới mock server để không gọi dịch vụ thật |
| payment.api-key | Chỉ khi test không kiểm tra secret | Placeholder không chứng minh secret production tồn tại |
| payment.enabled | Không trong test kiểm tra conditional bean | Cần xác minh bean production được đăng ký |

Nếu property vừa là dependency endpoint vừa là đối tượng cần kiểm tra, hãy tách test. Ví dụ, một test xác minh endpoint production được bind đúng từ cấu hình đã đóng gói; một adapter test khác dùng mock server để kiểm tra HTTP client. Đừng ghi đè endpoint rồi dùng kết quả để kết luận endpoint production đúng.

## 10. Dùng nguồn cấu hình giống môi trường triển khai

Một nguyên nhân khác khiến test không phản ánh production là test chỉ đọc file cấu hình trong source code, trong khi production nhận cấu hình từ hệ thống bên ngoài.

Ví dụ, workload production có thể nhận:

~~~text
SPRING_PROFILES_ACTIVE=prod
PAYMENT_API_URL=https://payments.example.com
PAYMENT_API_KEY=<secret được inject từ secret manager>
SPRING_DATASOURCE_URL=<endpoint database production>
~~~

Nếu CI chỉ chạy test với application-prod.yml trong repository, nó không chứng minh rằng deployment manifest đã gắn đúng biến môi trường hoặc secret reference.

Nên kiểm tra theo từng lớp:

**Lớp source/configuration artifact**

- File application.yml và application-prod.yml có được đóng gói không?
- Các key bắt buộc có đúng tên và kiểu dữ liệu không?
- Placeholder có trỏ đến tên biến môi trường đúng không?
- Profile-specific configuration có được đặt đúng vị trí không?

**Lớp deployment manifest**

- Workload có kích hoạt đúng profile không?
- Biến môi trường có được truyền vào container không?
- Secret reference có đúng tên, namespace và key không?
- ConfigMap hoặc config store có được mount/import đúng không?
- Giá trị có bị ghi đè bởi chart, manifest hoặc tham số dòng lệnh không?

**Lớp runtime**

- ApplicationContext có khởi động thành công không?
- Các bean bắt buộc có tồn tại không?
- Các giá trị được bind có nằm trong miền hợp lệ không?
- Kết nối staging có thành công không?
- Health indicator có phản ánh đúng tình trạng tích hợp không?

Test source code và kiểm tra deployment bổ sung cho nhau. Không có một annotation JUnit nào có thể thay thế việc xác minh manifest và môi trường thực tế.

## 11. Cẩn thận với @SpringBootTest và @ActiveProfiles("prod")

Một test như sau có thể khởi động nhiều thành phần của ứng dụng:

~~~java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionProfileContextTest {
}
~~~

Nếu application-prod.yml cấu hình database, message broker, scheduler hoặc API production, context có thể khởi tạo các bean tương ứng. Một số bean có thể mở kết nối ngay khi khởi tạo hoặc chạy tác vụ startup.

Vì vậy:

- Không chạy test với thông tin kết nối production thật trên máy developer hoặc CI thông thường.
- Không giả định chỉ nạp profile prod thì ứng dụng sẽ không tạo side effect.
- Không dùng profile production để chạy integration test nếu chưa cô lập dependency bên ngoài.
- Tắt hoặc thay thế đúng các tác vụ startup có side effect, đồng thời giữ nguyên phần cấu hình đang cần xác minh.
- Nếu chỉ cần kiểm tra property, dùng context tối giản hoặc công cụ đọc/validate cấu hình thay vì khởi động toàn bộ ứng dụng.
- Nếu cần kiểm tra full context, dùng môi trường staging hoặc production-like với dependency an toàn.

Có thể tạo một profile production-like riêng, nhưng phải hiểu rõ cấu hình chung và phần ghi đè. Nếu profile production-like ghi đè tất cả property quan trọng của production, nó cũng có thể tạo cảm giác an toàn giả giống profile test.

Một quy ước tốt là dùng cùng các cấu hình nghiệp vụ và bean conditions, còn endpoint/credential bên ngoài được thay bằng tài nguyên test. Ghi rõ danh sách property bị thay và không dùng test đó để xác nhận các giá trị đã thay.

## 12. Kiểm tra giá trị và nguồn gốc property

Khi test thất bại hoặc giá trị không như mong đợi, cần tìm property source nào đang cung cấp key.

Có thể in tên property source và chỉ kiểm tra sự hiện diện của key:

~~~java
@Autowired
private ConfigurableEnvironment environment;

@Test
void shouldInspectPaymentPropertySource() {
    String key = "payment.connect-timeout";

    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(key)) {
            System.out.println(
                    source.getName() + " provides " + key
            );
        }
    }
}
~~~

Ví dụ chỉ in tên nguồn và tên key, không in giá trị. Điều này hữu ích khi chẩn đoán property bị ghi đè.

Trong Spring Boot, một số property source hỗ trợ origin metadata để truy ra file và vị trí cung cấp property. Có thể dùng OriginLookup hoặc các công cụ Actuator phù hợp trong môi trường được bảo vệ. Không bật endpoint env/configprops công khai trong production nếu chưa kiểm soát quyền truy cập và việc che secret.

Khi báo lỗi cấu hình, chỉ hiển thị key, nguồn và trạng thái hợp lệ. Không in password, API key, token hoặc nội dung secret.

## 13. Fail fast khi cấu hình production không hợp lệ

Cấu hình quan trọng nên được xác thực ngay khi context khởi tạo thay vì để lỗi xuất hiện khi người dùng thực hiện một hành động hiếm gặp.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) int maxAttempts,
        @NotBlank String apiKey
) {
}
~~~

Đăng ký properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
class PaymentConfiguration {
}
~~~

Có thể thêm ràng buộc nghiệp vụ bằng custom validator, ví dụ:

- Timeout phải lớn hơn zero.
- maxAttempts nằm trong khoảng cho phép.
- baseUrl phải dùng HTTPS trong profile production.
- Retry không được bật cho các thao tác không idempotent nếu hệ thống không có idempotency key.
- Một feature flag bắt buộc phải bật trong profile production.
- Tên queue hoặc topic phải tuân theo quy ước đã triển khai.

Validation phải phản ánh hợp đồng thực tế, tránh kiểm tra cứng các giá trị chỉ tình cờ đúng trong một môi trường.

Đối với secret, chỉ kiểm tra có mặt và không rỗng nếu đó là điều kiện bắt buộc. Không log nội dung. Kiểm tra secret có hiệu lực với nhà cung cấp cần được thực hiện bằng một integration hoặc smoke test có kiểm soát, không phải bằng cách in giá trị ra để debug.

## 14. Quy trình thực tế để tránh cấu hình test che lỗi production

Có thể tổ chức quy trình theo các bước sau:

1. **Xác định cấu hình quan trọng.** Liệt kê property, profile, bean condition và secret reference mà production cần.
2. **Phân loại property.** Đánh dấu giá trị nào là đối tượng cần kiểm tra và giá trị nào chỉ là dependency bên ngoài cần thay cho test.
3. **Giữ property cần kiểm tra nguyên vẹn.** Không đặt lại chúng trong @TestPropertySource, @SpringBootTest(properties) hoặc @DynamicPropertySource.
4. **Tách test theo mục tiêu.** Unit test kiểm tra logic; adapter test kiểm tra giao tiếp; configuration contract test kiểm tra profile/property/bean; deployment validation kiểm tra manifest và secret references.
5. **Dùng dependency an toàn.** Database container, mock HTTP server và fake service giúp test không gọi production.
6. **Kiểm tra cả trường hợp cấu hình sai.** Thiếu property bắt buộc, sai kiểu, profile không bật, feature flag sai hoặc bean không được đăng ký phải tạo lỗi dễ nhận biết.
7. **Xác minh deployment artifact.** Kiểm tra cấu hình được đóng gói và các biến môi trường/secret references được gắn vào workload.
8. **Chạy smoke test ở staging.** Xác minh context, kết nối và health indicator trong môi trường gần production.
9. **Giữ log an toàn.** Chỉ ghi key, nguồn và lỗi bind; không in secret.
10. **Ghi rõ giới hạn test.** Nêu property nào đã được thay và kết luận nào không thể rút ra từ test đó.

Quy trình này giúp test tạo ra bằng chứng đúng phạm vi. Test không cần dùng thông tin production thật để phát hiện phần lớn lỗi cấu trúc và binding, nhưng deployment vẫn phải xác minh các giá trị do môi trường thật cung cấp.

## 15. Một ví dụ chiến lược test cho payment configuration

Giả sử ứng dụng có ba nhóm cấu hình:

~~~yaml
# application.yml
payment:
  enabled: false
  connect-timeout: 2s
  read-timeout: 5s
  retry:
    max-attempts: 1
~~~

~~~yaml
# application-prod.yml
payment:
  enabled: true
  base-url: ${PAYMENT_API_URL}
  api-key: ${PAYMENT_API_KEY}
  retry:
    max-attempts: 3
~~~

Có thể thiết kế nhiều test:

**Unit test cho nghiệp vụ**

- Mock PaymentGateway.
- Kiểm tra đơn hàng thành công hoặc bị từ chối.
- Không kiểm tra URL production.

**Adapter test**

- Tạo HttpPaymentGateway thật.
- Dùng mock HTTP server.
- Kiểm tra request path, header, timeout, response mapping.
- URL trỏ tới mock server là override có chủ đích.

**Production profile contract test**

- Nạp application-prod.yml.
- Không ghi đè payment.enabled, timeout hoặc retry.max-attempts.
- Cấp placeholder cho API key nếu cần bind nhưng không kiểm tra secret.
- Kiểm tra profile prod, bean condition và giá trị cấu hình nghiệp vụ.
- Không mở kết nối tới payment production.

**Deployment validation**

- Xác minh manifest kích hoạt prod.
- Xác minh PAYMENT_API_URL được cung cấp.
- Xác minh PAYMENT_API_KEY tham chiếu đúng secret.
- Không đọc hoặc in giá trị secret trong test report.

**Staging smoke test**

- Khởi động ứng dụng bằng cấu hình staging.
- Kiểm tra health và kết nối với sandbox payment provider.
- Xác minh các request thử nghiệm có phản hồi hợp lệ.

Khi một test trong nhóm unit hoặc adapter xanh, không nên kết luận production profile đã đúng. Khi configuration contract test xanh, cũng không nên kết luận secret production có hiệu lực hoặc nhà cung cấp thanh toán đang hoạt động. Mỗi test chỉ trả lời câu hỏi trong phạm vi được thiết kế.

## 16. Những câu hỏi cần đặt ra khi đọc một test đang có

Khi review test Spring, hãy xem xét:

- Test đang kích hoạt profile nào?
- File application-{profile}.yml nào được nạp?
- Có @TestPropertySource hoặc properties trong @SpringBootTest không?
- Có @DynamicPropertySource ghi đè URL hoặc credential không?
- Có @MockBean, @Primary hoặc @TestConfiguration thay bean production không?
- Các @ConditionalOnProperty quan trọng đang được kiểm tra với giá trị nào?
- Property nào là đối tượng cần xác minh, property nào chỉ là dependency test?
- Test có vô tình tắt security, messaging, payment hoặc scheduler cần thiết không?
- Có kiểm tra deployment manifest và secret reference ở bước khác không?
- Nếu một property production bị thiếu, test nào sẽ thất bại?

Nếu không trả lời được những câu hỏi này, kết quả xanh chưa đủ để khẳng định cấu hình production được bảo vệ.

## 17. Kết luận

Cấu hình kiểm thử giúp tạo môi trường ổn định, nhanh và an toàn. Nhưng mỗi property, profile hoặc bean thay thế đều có thể làm thay đổi điều mà test thực sự đang kiểm tra.

Hãy phân biệt rõ:

- Test profile chứng minh ứng dụng chạy với cấu hình test.
- Integration test chứng minh các thành phần được giữ thật phối hợp trong ranh giới đã chọn.
- Production profile contract test chứng minh các property và bean production được nạp trong context kiểm tra, với những override được công khai rõ ràng.
- Deployment validation chứng minh manifest, biến môi trường và secret references được gắn vào workload đúng cách.
- Staging smoke test chứng minh ứng dụng khởi động và tích hợp trong môi trường gần production.

Không dùng giá trị test để thay thế property đang cần xác minh. Chỉ thay dependency bên ngoài khi cần cô lập, ghi rõ giới hạn của test và kiểm tra riêng cấu hình do môi trường triển khai cung cấp. Khi làm rõ được nguồn property và ranh giới của từng bài test, kết quả xanh mới phản ánh đúng mức độ tin cậy mà nhóm cần.

