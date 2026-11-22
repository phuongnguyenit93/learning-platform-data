# Chỉ nạp các thành phần cần cho rủi ro đang kiểm chứng

Khi kiểm thử một ứng dụng Spring, phạm vi ApplicationContext quyết định những bean, cấu hình và hạ tầng nào được khởi tạo. Nạp toàn bộ ứng dụng cho mọi test có thể làm test chậm, khó chẩn đoán và phụ thuộc vào nhiều cấu hình không liên quan. Ngược lại, cắt context quá nhỏ có thể bỏ qua đúng phần tích hợp đang có nguy cơ sai.

Nguyên tắc thiết kế là **chọn phạm vi nhỏ nhất vẫn thực sự kiểm chứng được rủi ro cần quan tâm**. Nếu rủi ro nằm ở quy tắc nghiệp vụ của một service, thường không cần Spring context. Nếu rủi ro nằm ở request mapping và chuyển đổi HTTP, dùng MVC test slice. Nếu rủi ro nằm ở JPA mapping hoặc truy vấn, dùng JPA slice. Nếu cần xác nhận nhiều thành phần được wiring và phối hợp trong cấu hình ứng dụng thật, mới cần context rộng hơn.

## 1. Bắt đầu từ rủi ro, không bắt đầu từ annotation

Trước khi chọn @SpringBootTest, @WebMvcTest hay @DataJpaTest, hãy diễn đạt điều có thể hỏng và bằng chứng cần quan sát.

Một rủi ro là khả năng hệ thống không đáp ứng một cam kết trong điều kiện cụ thể. Ví dụ:

- Controller có thể ánh xạ sai URL, bind request sai hoặc trả JSON không đúng.
- Service có thể tính sai quy tắc nghiệp vụ khi dependency trả về dữ liệu đặc biệt.
- Repository có thể tạo truy vấn sai, mapping entity sai hoặc không thực thi đúng constraint.
- Spring có thể không tạo được bean vì thiếu dependency hoặc cấu hình điều kiện không khớp.
- Transaction, cache, security filter hoặc AOP proxy có thể không hoạt động như mong đợi.
- Nhiều thành phần có thể hoạt động riêng lẻ nhưng không phối hợp đúng khi được wiring trong ApplicationContext.

Mỗi rủi ro đòi hỏi một ranh giới quan sát khác nhau. Một test chỉ tạo object Java và gọi method có thể chứng minh logic của object, nhưng không chứng minh Spring đã inject bean. Một test dùng mock repository có thể chứng minh service gửi dữ liệu đúng, nhưng không chứng minh SQL hoặc transaction thực tế hoạt động.

### Ma trận rủi ro và phạm vi test

| Rủi ro cần kiểm chứng | Phạm vi thường phù hợp | Bằng chứng |
|---|---|---|
| Quy tắc thuần Java trong service | Unit test không nạp Spring | Giá trị trả về, exception, trạng thái object |
| Controller mapping, binding, validation, response | @WebMvcTest | HTTP status, header, body, model |
| Entity mapping, repository query, persistence | @DataJpaTest | Dữ liệu lưu và truy vấn qua database test |
| JSON serialization/deserialization | @JsonTest | JSON và cấu trúc object |
| REST client request/response mapping | @RestClientTest | Request gửi đi và phản hồi được xử lý |
| Wiring của một nhóm bean cụ thể | @ContextConfiguration hoặc test slice tùy biến | Bean được tạo và phối hợp đúng |
| Cấu hình ứng dụng rộng, nhiều tầng tích hợp | @SpringBootTest | Luồng ứng dụng trong context thực |
| Proxy transaction/cache/security/AOP | Spring context test với cấu hình liên quan | Hành vi qua proxy và hạ tầng thực |

Bảng này là điểm bắt đầu, không phải quy tắc cứng. Chẳng hạn, một MVC slice có thể bao gồm security configuration nếu security filter là một phần của rủi ro; nếu mục tiêu chỉ là JSON mapping của controller, có thể cần cấu hình slice gọn hơn.

## 2. Phân biệt unit test với Spring context test

Unit test thuần khởi tạo class trực tiếp và truyền dependency qua constructor hoặc setter. Nó không cần Spring container:

~~~java
class PriceServiceTest {

    private final DiscountPolicy discountPolicy =
            Mockito.mock(DiscountPolicy.class);

    private final PriceService priceService =
            new PriceService(discountPolicy);

    @Test
    void appliesVipDiscount() {
        Mockito.when(discountPolicy.rateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        BigDecimal total = priceService.calculate(
                new BigDecimal("100.00"), "VIP");

        assertEquals(new BigDecimal("90.00"), total);
    }
}
~~~

Test này tập trung vào thuật toán của PriceService. Nó chạy nhanh và không phụ thuộc vào cấu hình Spring. Tuy nhiên, nó không xác nhận:

- PriceService được component scan phát hiện.
- Bean DiscountPolicy đúng được inject.
- Profile hoặc conditional configuration tạo bean phù hợp.
- Transactional, caching hoặc AOP proxy được áp dụng.
- Các bean trong context có thể khởi tạo cùng nhau.

Khi rủi ro chỉ nằm ở logic của class, đó là phạm vi thích hợp. Khi rủi ro nằm ở container hoặc tích hợp, cần một test có Spring context.

### Không phải mọi class có @Service đều cần @SpringBootTest

Annotation @Service đánh dấu class để Spring quản lý như một bean. Nó không khiến mọi hành vi của class phụ thuộc vào container. Nếu test chỉ cần kiểm tra public method và dependency có thể thay bằng mock, tạo object trực tiếp là đủ.

Hãy dùng context khi chính hành vi của Spring là điều cần kiểm chứng: component scanning, bean conditions, dependency injection, proxy, transaction, security hoặc cấu hình tích hợp.

## 3. Test slice: nạp một phần ApplicationContext theo loại thành phần

Spring Boot cung cấp các test slice để tập trung vào một khu vực ứng dụng. Mỗi slice chọn một tập auto-configuration và component phù hợp với mục tiêu của nó.

Các annotation phổ biến:

| Annotation | Phạm vi tập trung | Ví dụ rủi ro |
|---|---|---|
| @WebMvcTest | Spring MVC và thành phần web liên quan | Controller mapping, binding, validation, response |
| @DataJpaTest | JPA, entity, repository và persistence test support | JPQL, derived query, mapping, constraint |
| @JdbcTest | JDBC và cấu hình datasource liên quan | SQL qua JdbcTemplate |
| @JsonTest | JSON mapper và JSON test support | Serialization và deserialization |
| @RestClientTest | REST client test support | Request factory, URI, headers, response conversion |
| @WebFluxTest | WebFlux controller và hạ tầng reactive web | Reactive handler và response |
| @DataMongoTest | MongoDB mapping và repository slice | Document mapping, query MongoDB |
| @DataRedisTest | Redis data support | Serialization và thao tác Redis |
| @GraphQlTest | GraphQL controller và hạ tầng GraphQL liên quan | GraphQL mapping và resolver |

Danh sách và phạm vi chính xác phụ thuộc phiên bản Spring Boot. Hãy dùng tài liệu của phiên bản dự án để biết auto-configuration và component filter nào được kích hoạt.

### @WebMvcTest cho rủi ro ở tầng MVC

Ví dụ, controller nhận request tạo khách hàng và trả response DTO. Rủi ro cần kiểm chứng là request được bind, validation được áp dụng và response có cấu trúc đúng.

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;

    @Test
    void returnsCreatedCustomer() throws Exception {
        given(customerService.create(any()))
                .willReturn(new CustomerResponse(42L, "Linh"));

        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Linh"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Linh"));
    }
}
~~~

@WebMvcTest chỉ nạp nhóm thành phần MVC cần thiết thay vì toàn bộ ứng dụng. Service được thay bằng mock vì logic service không thuộc rủi ro đang kiểm chứng trong test này.

Nếu cần kiểm tra logic service, viết unit test service riêng. Nếu cần xác nhận controller và service thật phối hợp qua bean wiring, chọn một test tích hợp rộng hơn.

### @DataJpaTest cho rủi ro ở tầng persistence

Khi cần kiểm tra derived query, mapping entity hoặc constraint database, test cần JPA infrastructure và database test:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmailIgnoringCase() {
        customerRepository.saveAndFlush(
                new Customer("linh@example.com"));

        Optional<Customer> result =
                customerRepository.findByEmailIgnoreCase(
                        "LINH@EXAMPLE.COM");

        assertTrue(result.isPresent());
        assertEquals(
                "linh@example.com",
                result.orElseThrow().getEmail());
    }
}
~~~

@DataJpaTest thường cấu hình database nhúng nếu có dependency phù hợp và chạy test trong transaction được rollback sau mỗi test. Nếu ứng dụng phụ thuộc hành vi riêng của PostgreSQL, MySQL hoặc một database cụ thể, hãy dùng database cùng loại trong test, thường qua Testcontainers. Database nhúng có thể không tái hiện dialect, constraint, collation hoặc SQL behavior của production.

### @JsonTest cho rủi ro JSON

Nếu mục tiêu là xác nhận Jackson serialize và deserialize DTO đúng, không cần nạp MVC controller hoặc toàn bộ ứng dụng:

~~~java
@JsonTest
class CustomerJsonTest {

    @Autowired
    private JacksonTester<CustomerResponse> json;

    @Test
    void serializesCustomerResponse() throws Exception {
        CustomerResponse response =
                new CustomerResponse(42L, "Linh");

        assertThat(json.write(response))
                .extractingJsonPathNumberValue("$.id")
                .isEqualTo(42);

        assertThat(json.write(response))
                .extractingJsonPathStringValue("$.name")
                .isEqualTo("Linh");
    }
}
~~~

Test slice này tập trung vào JSON support. Nó không chứng minh endpoint thực tế trả về JSON đúng qua toàn bộ MVC pipeline.

## 4. Khi nào cần @SpringBootTest?

@SpringBootTest tạo ApplicationContext theo cách gần với cấu hình ứng dụng Spring Boot thực tế hơn. Nó phù hợp khi rủi ro nằm ở tương tác giữa nhiều bean hoặc cấu hình rộng.

Ví dụ, một quy trình đăng ký khách hàng cần controller, service, repository, transaction manager và event publisher phối hợp. Nếu mục tiêu là xác nhận toàn bộ luồng đó hoạt động với wiring thật, một context rộng có thể cần thiết.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerRegistrationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void registersCustomerThroughApplicationFlow() throws Exception {
        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Linh",
                                  "email": "linh@example.com"
                                }
                                """))
                .andExpect(status().isCreated());

        assertTrue(customerRepository
                .findByEmail("linh@example.com")
                .isPresent());
    }
}
~~~

Ví dụ này dùng context rộng và MockMvc để đi qua controller, service và repository thật. Test kiểm tra cả phản hồi lẫn dữ liệu được lưu.

Không cần dùng @SpringBootTest nếu mục tiêu chỉ là kiểm tra một controller trả HTTP 201 hoặc một repository query. Context rộng làm tăng chi phí khởi tạo và số cấu hình có thể ảnh hưởng đến test. Hãy dành nó cho rủi ro cần nhiều thành phần phối hợp.

### Chọn web environment phù hợp

@SpringBootTest hỗ trợ nhiều chế độ web environment:

| Chế độ | Ý nghĩa | Khi phù hợp |
|---|---|---|
| MOCK (mặc định) | Tạo web ApplicationContext mô phỏng, không mở server thật | Dùng MockMvc hoặc WebTestClient với mock server setup phù hợp |
| RANDOM_PORT | Khởi động server trên cổng ngẫu nhiên | Kiểm tra HTTP qua server thật trong test |
| DEFINED_PORT | Khởi động server trên cổng cấu hình | Chỉ khi test cần cổng xác định và môi trường được kiểm soát |
| NONE | Không tạo web environment | Kiểm thử cấu hình ứng dụng không cần web |

Ví dụ dùng server thật:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void servesHealthEndpoint() {
        // Gửi HTTP client request tới localhost và port được cấp.
    }
}
~~~

Dùng RANDOM_PORT khi cần kiểm tra server thực sự khởi động, socket, servlet container hoặc giao tiếp HTTP end-to-end. Nếu chỉ cần test handler mapping và response qua MVC, MockMvc thường đủ và không cần mở cổng.

## 5. Nạp đúng cấu hình với @ContextConfiguration

Không phải mọi bài test có Spring context đều cần Spring Boot. Spring TestContext Framework cho phép chỉ định rõ cấu hình cần nạp bằng @ContextConfiguration.

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        ServiceTestConfiguration.class,
        PricingService.class
})
class PricingServiceContextTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void calculatesPriceUsingConfiguredPolicy() {
        // Kiểm tra hành vi qua bean trong context nhỏ.
    }
}
~~~

Cách này phù hợp khi cần kiểm tra một tập bean Spring cụ thể, ví dụ constructor injection hoặc một configuration class. Nó tránh component scanning toàn ứng dụng và tránh kéo theo auto-configuration không liên quan.

Một cấu hình test có thể khai báo dependency test:

~~~java
@Configuration
class ServiceTestConfiguration {

    @Bean
    DiscountPolicy discountPolicy() {
        return new FixedDiscountPolicy();
    }
}
~~~

Có thể dùng @Import để đưa cấu hình hoặc component cần thiết vào context:

~~~java
@Configuration
@Import({PricingService.class, ServiceTestConfiguration.class})
class TestRootConfiguration {
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestRootConfiguration.class)
class PricingServiceContextTest {
    // ...
}
~~~

Đặt @Import trên configuration class được nạp bởi @ContextConfiguration để Spring đăng ký đúng các component và cấu hình được chỉ định. Điều quan trọng là chỉ đưa vào những bean phục vụ mục tiêu. Tránh import cả package cấu hình lớn nếu test chỉ cần một bean.

## 6. Bổ sung dependency còn thiếu một cách có chủ đích

Một test slice có thể không tự động nạp service, mapper hoặc component tùy chỉnh mà controller cần. Nếu dependency đó không phải rủi ro đang kiểm chứng, thay bằng mock thường hợp lý. Nếu dependency thật là một phần của rủi ro, import hoặc cấu hình nó rõ ràng.

Ví dụ, MVC slice cần một formatter tùy chỉnh để parse request parameter:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceWebConfiguration.class)
class InvoiceControllerTest {
    // ...
}
~~~

Nếu chỉ cần thay service:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    private InvoiceService invoiceService;
}
~~~

Hãy quyết định dựa trên câu hỏi:

- Service có logic đang được test không? Nếu không, mock nó.
- Converter/formatter có hành vi cần xác nhận không? Nếu có, nạp implementation thật.
- Security filter có nằm trong rủi ro không? Nếu có, giữ security configuration liên quan.
- Một bean chỉ là hạ tầng phụ trợ không liên quan? Có thể loại khỏi context hoặc thay bằng test double.

### @Import và @TestConfiguration

@TestConfiguration cho phép khai báo bean dành riêng cho test. Ví dụ:

~~~java
@TestConfiguration
class FakeClockConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

Sau đó import vào test:

~~~java
@SpringBootTest
@Import(FakeClockConfiguration.class)
class BillingServiceTest {

    @Autowired
    private BillingService billingService;
}
~~~

Một nested @TestConfiguration thường không được component scan thông thường tự động thêm vào ứng dụng như một cấu hình chính, vì vậy có thể import có chủ đích. Cách sử dụng cụ thể nên theo Spring Boot version và cấu trúc test của dự án.

Nếu cần thay một bean thật bằng mock trong context, dùng cơ chế override bean phù hợp phiên bản. Với Spring Framework 6.2 trở lên, có thể dùng @MockitoBean. Một số dự án Spring Boot cũ dùng @MockBean. Tránh trộn nhiều cơ chế override mà không có lý do.

## 7. Tạo custom test slice khi slice có sẵn chưa phù hợp

Các slice tiêu chuẩn không bao phủ mọi kiến trúc. Nếu một nhóm test thường xuyên cần cùng một tập cấu hình chuyên biệt, có thể tạo meta-annotation hoặc test configuration dùng chung.

Một custom slice thường kết hợp:

- @BootstrapWith hoặc cơ chế bootstrap tương ứng của Spring Boot test.
- @TypeExcludeFilters để giới hạn loại component được nạp.
- @ImportAutoConfiguration để nạp đúng nhóm auto-configuration.
- Các annotation cấu hình bổ sung phù hợp với mục tiêu.

Đây là kỹ thuật nâng cao. Không nên tạo custom slice cho một test đơn lẻ nếu một @Import hoặc @ContextConfiguration đơn giản đã đủ. Custom slice hữu ích khi nhiều test cùng một ranh giới cần một cấu hình nhất quán, có thể tái sử dụng và dễ bảo trì.

Khi tạo custom slice, hãy ghi rõ component nào được phép nạp và lý do. Nếu filter vô tình loại bỏ bean cần thiết, test có thể chỉ chạy được nhờ mock hoặc cấu hình thủ công mà không phản ánh ranh giới mong muốn.

## 8. Chọn thành phần theo từng rủi ro cụ thể

### Rủi ro: controller có mapping và validation đúng

Dùng @WebMvcTest cho controller, giữ MVC infrastructure và validation liên quan, mock service nếu logic service nằm ngoài mục tiêu.

~~~java
@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    RegistrationService registrationService;

    @Test
    void rejectsInvalidEmail() throws Exception {
        mockMvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "not-an-email"
                                }
                                """))
                .andExpect(status().isBadRequest());
    }
}
~~~

Nếu test không kích hoạt Bean Validation vì validator configuration bị loại khỏi slice hoặc không có dependency cần thiết, hãy kiểm tra test dependencies và cấu hình validation. Đừng chuyển ngay sang full context nếu chỉ cần thêm một cấu hình MVC/validation phù hợp.

### Rủi ro: repository query đúng với database thật

Dùng @DataJpaTest và database phù hợp. Nếu query phụ thuộc vào dialect hoặc extension riêng của database production, cấu hình Testcontainers hoặc datasource test tương ứng. Không mock repository vì như vậy bỏ qua truy vấn cần kiểm tra.

### Rủi ro: @Transactional thực sự mở và rollback transaction

Cần một Spring context có transaction manager và resource phù hợp. Test có thể gọi bean qua Spring proxy rồi kiểm tra kết quả transaction. Unit test tạo object trực tiếp không chạy proxy. Nếu cần xác nhận commit/rollback qua nhiều transaction hoặc thread, phải thiết kế test phù hợp với ranh giới transaction thực tế.

### Rủi ro: profile và conditional bean tạo đúng implementation

Nạp configuration cần thiết với profile cụ thể, hoặc dùng Spring Boot context test nếu điều kiện phụ thuộc cấu hình ứng dụng. Xác nhận bean thực tế được inject hoặc hành vi của implementation được chọn. Mock bean có thể che mất lỗi điều kiện tạo bean, vì vậy không override chính bean đang cần kiểm chứng.

### Rủi ro: controller và service phối hợp qua dependency injection

Nếu chỉ cần xác nhận mapping HTTP, dùng MVC slice và mock service. Nếu cần xác nhận controller nhận đúng service bean thật cùng cấu hình ứng dụng, nạp context rộng hơn hoặc một context test tùy chỉnh có cả hai thành phần. Không cần database thật nếu repository không thuộc rủi ro.

### Rủi ro: toàn bộ luồng từ HTTP đến database

Dùng @SpringBootTest hoặc một integration test có phạm vi tương đương, database test thật và request đi qua HTTP hoặc MockMvc tùy yêu cầu. Đây là nơi context rộng mang lại bằng chứng có giá trị.

## 9. Tránh nạp quá nhiều và quá ít

Hai lỗi đối lập thường gặp:

**Nạp quá nhiều:** dùng @SpringBootTest cho một phép tính service hoặc một controller response đơn giản. Test khởi động nhiều bean, cần nhiều cấu hình và có thể thất bại vì một hệ thống phụ không liên quan. Thời gian chạy tăng và nguyên nhân lỗi khó xác định.

**Nạp quá ít:** dùng unit test với mock cho một rủi ro liên quan đến Spring proxy, SQL, validation infrastructure hoặc security filter. Test xanh nhưng hành vi thực tế vẫn có thể sai vì phần đang rủi ro chưa được chạy.

Một cách chọn tốt là tăng phạm vi đúng đến điểm cần thiết:

~~~text
Logic thuần Java
      |
      v
Unit test không có Spring
      |
      | cần kiểm tra một hạ tầng cụ thể?
      v
Test slice / context cấu hình hẹp
      |
      | cần nhiều tầng phối hợp?
      v
@SpringBootTest hoặc end-to-end test
~~~

Không cần mọi loại test đều xuất hiện trong mọi dự án. Mục tiêu là có bằng chứng ở đúng nơi rủi ro tồn tại.

## 10. Tốc độ và context caching

Khởi tạo ApplicationContext tốn thời gian. Spring TestContext Framework có cơ chế cache context để các test có cấu hình tương đương có thể dùng lại context đã khởi tạo.

Các yếu tố có thể làm context khác nhau và giảm khả năng tái sử dụng gồm:

- Các lớp cấu hình khác nhau.
- Danh sách active profiles khác nhau.
- Property source khác nhau.
- Context initializer khác nhau.
- Bean override khác nhau.
- Context hierarchy khác nhau.

Dùng một cấu hình test nhất quán cho các test cùng mục tiêu giúp tận dụng cache. Tuy nhiên, không nên ép mọi test dùng chung một context lớn chỉ để tăng cache hit. Context phải đúng với rủi ro cần kiểm chứng trước.

Một test slice nhỏ thường khởi động nhanh hơn full context. Một unit test thuần thường còn nhanh hơn vì không có container. Nếu suite có hàng trăm test, phân biệt phạm vi giúp giảm đáng kể tổng thời gian chạy.

## 11. Profile, property và cấu hình điều kiện

Rủi ro cấu hình có thể được kiểm tra bằng cách nạp context với profile hoặc property cụ thể.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Test
    void usesTestPaymentGateway() {
        assertInstanceOf(
                StubPaymentGateway.class,
                paymentGateway);
    }
}
~~~

Nếu bean được chọn theo property:

~~~java
@SpringBootTest(properties = {
        "payment.mode=stub"
})
class PaymentModeConfigurationTest {
    // Kiểm tra bean được tạo theo property.
}
~~~

Hãy xác định rõ cấu hình nào đang được kiểm tra. Nếu test dùng @MockitoBean để thay PaymentGateway, nó không còn chứng minh được conditional configuration đã chọn đúng implementation. Đối với rủi ro wiring, hãy để bean thật được tạo và xác nhận implementation hoặc hành vi của nó.

## 12. Security và filter: giữ lại khi đó là rủi ro

@WebMvcTest có thể nạp security configuration và filter liên quan tùy ứng dụng và cấu hình test. Nếu test nhằm xác nhận endpoint từ chối user không có quyền, security infrastructure phải tham gia test.

~~~java
@WebMvcTest(AdminController.class)
class AdminControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void deniesAnonymousRequest() throws Exception {
        mockMvc.perform(get("/admin/users"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Kết quả thực tế có thể là 401, 302 redirect hoặc một status khác tùy cơ chế authentication và entry point của ứng dụng. Test phải dùng đúng hợp đồng bảo mật đã cấu hình.

Nếu một MVC test chỉ tập trung vào JSON mapping và security không thuộc mục tiêu, có thể cấu hình test để bỏ qua filter hoặc thay security collaborator phù hợp. Nhưng không được tắt filter trong test đang tuyên bố kiểm tra authorization.

## 13. Dùng @DirtiesContext có chọn lọc

@DirtiesContext đánh dấu ApplicationContext là không còn phù hợp để cache và yêu cầu Spring loại context đó khỏi cache sau test hoặc class theo chế độ khai báo.

Nó có thể cần thiết khi test làm thay đổi singleton bean hoặc trạng thái context theo cách không thể khôi phục an toàn. Tuy nhiên, dùng annotation này quá rộng sẽ khiến Spring phải khởi động lại context nhiều lần và làm suite chậm.

Trước khi dùng, hãy hỏi:

- Test có thực sự thay đổi cấu trúc hoặc trạng thái dùng chung của ApplicationContext không?
- Có thể reset bean state trong @AfterEach không?
- Có thể dùng một context riêng với cấu hình riêng không?
- Test đang sửa external resource hay chỉ thay đổi dữ liệu database? Nếu chỉ là dữ liệu, transaction rollback hoặc cleanup phù hợp có thể đủ.

@DirtiesContext không thay thế cleanup database, file hoặc dịch vụ ngoài. Nó chỉ quản lý vòng đời ApplicationContext trong Spring TestContext.

## 14. Những lỗi thường gặp khi chọn phạm vi context

### Dùng @SpringBootTest cho mọi test

Việc khởi động toàn bộ ứng dụng làm test chậm và tạo nhiều điểm lỗi không liên quan. Hãy chọn unit test hoặc slice nếu chúng đủ để quan sát hành vi cần kiểm chứng.

### Mock bean đang là đối tượng rủi ro

Nếu mục tiêu là xác nhận Spring tạo đúng implementation của một interface theo profile, thay bean đó bằng mock sẽ bỏ qua rủi ro. Giữ implementation thật trong context test.

### Import cả cấu hình production không cần thiết

Một configuration class có thể kéo theo datasource, broker, client hoặc service khác. Hãy chọn cấu hình nhỏ hơn hoặc cung cấp test configuration dành riêng cho test.

### Cắt context quá sâu

Nếu mục tiêu là transaction proxy, unit test gọi trực tiếp object sẽ bỏ qua proxy. Nếu mục tiêu là repository query, mock repository sẽ bỏ qua database. Tăng phạm vi đúng đến infrastructure đang được kiểm tra.

### Tắt filter trong test bảo mật

Tắt filter có thể làm test dễ chạy nhưng cũng loại bỏ chính cơ chế cần xác nhận. Chỉ bỏ filter khi security không thuộc rủi ro của test.

### Dùng database nhúng cho mọi repository test

Database nhúng không nhất thiết tương thích với database production. Dùng cùng hệ quản trị hoặc Testcontainers khi khác biệt dialect có thể ảnh hưởng kết quả.

### Dùng @DirtiesContext để sửa mọi lỗi test

Context dirty không giải quyết được dữ liệu bẩn trong database, file tạm chưa xóa hoặc dịch vụ ngoài còn trạng thái. Xác định đúng loại state cần reset.

### Cho rằng context đã khởi động thành công là đủ

Context start thành công chỉ chứng minh bean có thể được tạo theo cấu hình test. Nó chưa chứng minh request, transaction, query hoặc business flow đúng. Test vẫn cần kích hoạt hành vi và xác nhận kết quả.

## 15. Quy trình chọn ApplicationContext cho một test mới

1. **Mô tả rủi ro:** điều gì có thể sai và hậu quả quan sát được là gì?
2. **Xác định ranh giới:** logic class, MVC, persistence, JSON, REST client, proxy hay toàn bộ flow?
3. **Liệt kê thành phần bắt buộc:** chỉ giữ bean, filter, converter, transaction manager hoặc database cần thiết để thực thi ranh giới đó.
4. **Chọn phạm vi nhỏ nhất:** unit test, test slice, @ContextConfiguration hoặc @SpringBootTest.
5. **Thay collaborator ngoài mục tiêu:** dùng mock hoặc fake khi cần cô lập, nhưng không thay thành phần đang được kiểm chứng.
6. **Bổ sung cấu hình có chủ đích:** dùng @Import, @TestConfiguration, profile và property phù hợp.
7. **Kiểm tra bằng chứng:** test phải kích hoạt hành vi thật ở ranh giới đã chọn và assertion đúng với rủi ro.
8. **Đánh giá chi phí:** nếu context nạp nhiều thành phần không liên quan, xem lại phạm vi; nếu test bỏ qua proxy, database hoặc filter đang rủi ro, mở rộng phạm vi.

### Ví dụ quyết định phạm vi

Giả sử cần kiểm tra endpoint tạo hóa đơn:

- Nếu rủi ro là controller trả đúng HTTP 201 và JSON, dùng @WebMvcTest và mock InvoiceService.
- Nếu rủi ro là InvoiceService tính thuế đúng, unit test service và stub tax policy.
- Nếu rủi ro là InvoiceRepository lưu tổng tiền và truy vấn đúng, dùng @DataJpaTest với database phù hợp.
- Nếu rủi ro là @Transactional bảo đảm nhiều thao tác ghi cùng thành công hoặc cùng rollback, dùng Spring context với transaction manager và database.
- Nếu rủi ro là cả request tạo hóa đơn đi qua controller, service, repository và database, dùng integration test rộng hơn.

Cùng một chức năng có thể cần nhiều test ở các ranh giới khác nhau. Mỗi test nên chứng minh một nhóm rủi ro rõ ràng, để khi lỗi xảy ra có thể xác định tầng cần điều tra.

## Kết luận

Chọn phạm vi ApplicationContext theo rủi ro đang kiểm chứng giúp test chạy nhanh và tạo bằng chứng đúng. Unit test phù hợp với logic thuần Java; test slice phù hợp với MVC, JPA, JSON hoặc client; @ContextConfiguration và @Import phù hợp khi cần một nhóm bean cụ thể; @SpringBootTest dành cho rủi ro cần nhiều thành phần hoặc cấu hình ứng dụng phối hợp. Giữ lại đúng infrastructure cần thiết, thay collaborator ngoài mục tiêu và không mock thành phần đang cần xác nhận.
