# Phân biệt kiểm thử đơn vị, tích hợp và toàn hệ thống

Trong một ứng dụng Spring, cùng một hành vi có thể được kiểm tra ở nhiều phạm vi khác nhau. Với chức năng tạo đơn hàng, ta có thể kiểm tra riêng quy tắc tính tổng tiền, kiểm tra sự phối hợp giữa controller, service và repository, rồi kiểm tra hành trình khách hàng gửi yêu cầu và nhận được đơn hàng đã lưu.

Ba phạm vi đó thường được gọi là **kiểm thử đơn vị (unit testing)**, **kiểm thử tích hợp (integration testing)** và **kiểm thử toàn hệ thống (system testing)**. Chúng khác nhau chủ yếu ở ranh giới được kiểm tra, số lượng thành phần tham gia thật và môi trường mà bài kiểm thử cần dựng lên.

Không nên phân loại chỉ dựa vào tên lớp test hoặc một annotation. Một lớp dùng **@SpringBootTest** chưa chắc là kiểm thử toàn hệ thống; một lớp dùng **@WebMvcTest** thường là kiểm thử lát cắt MVC; còn một bài test khởi tạo trực tiếp service bằng constructor có thể là unit test dù dự án sử dụng Spring. Cần nhìn vào điều bài test đang chứng minh.

## 1. Ba phạm vi nhìn từ ranh giới kiểm thử

Hãy hình dung một yêu cầu tạo đơn hàng đi qua các thành phần:

~~~text
HTTP request
    |
    v
OrderController
    |
    v
OrderService ------> PaymentGateway
    |
    v
OrderRepository
    |
    v
Database
~~~

Mỗi loại kiểm thử đặt ranh giới ở một vị trí khác nhau:

- **Unit test** tập trung vào một đơn vị nhỏ, chẳng hạn **OrderService**. Các cộng tác viên bên ngoài đơn vị đó thường được thay bằng mock, stub hoặc fake.
- **Integration test** kiểm tra hai hay nhiều thành phần thật phối hợp qua một ranh giới, chẳng hạn controller gọi service, service làm việc với repository, hoặc repository truy vấn cơ sở dữ liệu.
- **System test** kiểm tra hệ thống hoàn chỉnh trong môi trường gần với cách hệ thống được vận hành, dựa trên đầu vào và kết quả quan sát được ở ranh giới của hệ thống. Với ứng dụng web, một cách triển khai phổ biến là kiểm thử end-to-end (E2E) theo hành trình người dùng.

Ba phạm vi bổ sung cho nhau. Unit test giúp tìm lỗi cục bộ nhanh; integration test phát hiện lỗi kết nối, cấu hình và hợp đồng giữa các thành phần; system test phát hiện lỗi chỉ xuất hiện khi nhiều lớp của hệ thống cùng hoạt động.

### Phân biệt system test và E2E

Trong thực tế, hai thuật ngữ này thường được dùng gần như đồng nghĩa, nhưng có thể hiểu chính xác hơn:

- **System testing** là kiểm thử hệ thống như một sản phẩm hoàn chỉnh đối chiếu với yêu cầu. Phạm vi có thể bao gồm luồng API, xử lý nền, batch job, phân quyền, khôi phục hoặc các hành vi vận hành.
- **End-to-end testing** là cách kiểm thử một luồng xuyên suốt từ điểm bắt đầu đến kết quả cuối cùng. Với sản phẩm web, luồng thường bắt đầu từ giao diện hoặc API công khai và đi qua các thành phần cần thiết để tạo ra kết quả.

E2E thường là một phần quan trọng của system testing. Một bài test gọi API trực tiếp có thể kiểm tra end-to-end ở phạm vi backend, nhưng chưa bao phủ giao diện trình duyệt hay toàn bộ hệ thống bên ngoài backend.

## 2. Kiểm thử đơn vị (Unit Testing)

### Mục tiêu và phạm vi

Unit test xác minh hành vi của một đơn vị nhỏ trong điều kiện được kiểm soát. Đơn vị có thể là một hàm, một phương thức, một lớp hoặc một nhóm rất nhỏ có trách nhiệm thống nhất. Điều quan trọng là ranh giới kiểm thử đủ hẹp để khi thất bại, ta dễ xác định phần logic có vấn đề.

Ví dụ, với **OrderService**, unit test có thể xác minh:

- Đơn hàng bị từ chối khi giỏ hàng rỗng.
- Tổng tiền được tính đúng khi có giảm giá.
- Không lưu đơn hàng nếu thanh toán bị từ chối.
- Trạng thái đơn hàng chuyển sang **PAID** khi cổng thanh toán xác nhận thành công.

Trong bài test này, **OrderService** là đối tượng thật. Repository và cổng thanh toán thường được thay bằng các đối tượng giả lập để kiểm soát kết quả trả về và quan sát lời gọi.

### Ví dụ với JUnit 5 và Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void shouldNotSaveOrderWhenPaymentIsRejected() {
        var command = new CreateOrderCommand("customer-1", 250_000);

        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.rejected());

        var result = orderService.create(command);

        assertEquals(OrderStatus.PAYMENT_REJECTED, result.status());
        verify(orderRepository, never()).save(any());
    }
}
~~~

Các kiểu dữ liệu trong ví dụ là mô hình minh họa; tên constructor và phương thức cần điều chỉnh theo ứng dụng thực tế.

Ở đây:

- **OrderService** được tạo và kiểm tra trực tiếp.
- **@Mock** tạo cộng tác viên giả lập.
- **@InjectMocks** đưa các mock vào service.
- **when(...).thenReturn(...)** quy định phản hồi của cổng thanh toán.
- **verify(..., never())** xác minh repository không được gọi khi thanh toán thất bại.

Bài test không cần khởi động Spring ApplicationContext. Nó kiểm tra logic của service trong môi trường nhẹ, vì vậy thường chạy nhanh và cho lỗi khá tập trung.

### Khi nào nên dùng unit test?

Dùng unit test khi muốn kiểm tra quy tắc nghiệp vụ, các nhánh điều kiện, tính toán, chuyển đổi dữ liệu, chuẩn hóa đầu vào, xử lý trạng thái và các trường hợp biên. Unit test cũng hữu ích để xác minh quyết định gọi hoặc không gọi cộng tác viên, và hành vi khi cộng tác viên trả về dữ liệu lỗi, rỗng hoặc ném exception.

Ta có thể chủ động tạo từng tình huống mà không cần dựng database, web server hay dịch vụ bên ngoài.

### Ưu điểm và giới hạn

**Ưu điểm**

- Thời gian chạy thường rất ngắn.
- Dễ tạo dữ liệu đầu vào cho từng trường hợp.
- Ít phụ thuộc môi trường, dễ chạy lặp lại.
- Khi thất bại, phạm vi nguyên nhân thường hẹp.
- Phù hợp để kiểm tra nhiều trường hợp biên.

**Giới hạn**

- Mock không chứng minh rằng các thành phần thật tương thích với nhau.
- Bài test có thể vẫn xanh dù câu lệnh SQL, mapping JPA hoặc cấu hình Spring bị sai.
- Nếu mock quá sâu, bài test có thể phản ánh cách triển khai hiện tại thay vì hành vi mà người dùng cần.
- Unit test không chứng minh ứng dụng có thể khởi động hoặc nhận HTTP request thành công.

Không nên cố biến mọi lớp thành một bài unit test bằng cách mock toàn bộ phụ thuộc. Hãy mock ranh giới bên ngoài đơn vị đang kiểm tra, còn phần cộng tác cần được xác minh thì giữ ở dạng thật.

## 3. Kiểm thử tích hợp (Integration Testing)

### Mục tiêu và phạm vi

Integration test xác minh các thành phần phối hợp đúng với nhau. Nó tập trung vào các ranh giới nơi dữ liệu, lời gọi hoặc cấu hình được chuyển từ thành phần này sang thành phần khác.

Ví dụ:

- Controller nhận JSON, chuyển dữ liệu vào service và trả đúng HTTP status.
- Service gọi repository thật và dữ liệu được ghi, đọc đúng trong database.
- JPA entity được ánh xạ đúng thành bảng và quan hệ.
- Cấu hình Spring tạo đúng bean và inject đúng dependency.
- Một adapter gửi thông điệp đúng định dạng đến message broker thử nghiệm.

Integration test không nhất thiết phải khởi động toàn bộ ứng dụng. Ta có thể chỉ dựng một lát cắt (slice) của Spring để kiểm tra một nhóm thành phần liên quan.

### Các mức kiểm thử thường gặp trong Spring

#### Kiểm thử lớp MVC bằng @WebMvcTest

**@WebMvcTest** tải phần hạ tầng MVC và các thành phần web thuộc phạm vi được chọn, thường là controller. Nó phù hợp để kiểm tra routing, binding, validation, serialization, HTTP status và xử lý exception ở lớp web.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void shouldReturnCreatedWhenOrderIsAccepted() throws Exception {
        when(orderService.create(any()))
                .thenReturn(OrderResponse.accepted("order-42"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 250000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("order-42"));
    }
}
~~~

**OrderController** và hạ tầng MVC là thành phần Spring thật trong test; **OrderService** được mock để bài test tập trung vào hợp đồng HTTP của controller.

Đây thường được gọi là **MVC slice test**. Nó có tính chất kiểm thử tích hợp ở phạm vi lát cắt web, nhưng không chứng minh service, repository hay database hoạt động đúng.

Trong Spring Boot 3.3, **@MockBean** là cách phổ biến để thay bean trong ApplicationContext bằng mock. Khi dùng phiên bản Spring Boot khác, hãy kiểm tra API test tương ứng với phiên bản đang chạy.

#### Kiểm thử repository bằng @DataJpaTest

**@DataJpaTest** tải cấu hình và các thành phần cần cho JPA, chẳng hạn entity, repository và hạ tầng persistence. Nó thích hợp để kiểm tra câu truy vấn, mapping, quan hệ, ràng buộc và thao tác lưu/đọc.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrderByCustomerId() {
        var order = new Order("customer-1", 250_000);
        orderRepository.save(order);

        var results = orderRepository.findByCustomerId("customer-1");

        assertEquals(1, results.size());
        assertEquals("customer-1", results.get(0).getCustomerId());
    }
}
~~~

Theo cấu hình mặc định, **@DataJpaTest** thường dùng database nhúng nếu có trên classpath và chạy test trong transaction được rollback sau mỗi bài test. Điều này giúp cô lập dữ liệu, nhưng cũng có nghĩa môi trường mặc định có thể khác database production.

Nếu ứng dụng chạy PostgreSQL hoặc MySQL, nên cân nhắc kiểm thử với đúng loại database bằng Testcontainers. Khi đó test có thể phát hiện khác biệt về kiểu dữ liệu, SQL dialect, constraint và hành vi transaction mà database nhúng không thể hiện.

#### Kiểm thử tích hợp với Spring TestContext

Spring Framework cung cấp TestContext Framework để nạp ApplicationContext cho test. Với JUnit Jupiter, có thể dùng **@SpringJUnitConfig** để kết hợp hỗ trợ Spring Test và cấu hình context:

~~~java
@SpringJUnitConfig(TestApplicationConfig.class)
class PricingConfigurationTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void shouldUseConfiguredPricingPolicy() {
        var result = pricingService.calculate(100_000);

        assertEquals(100_000, result.total());
    }
}
~~~

**@SpringJUnitConfig** phù hợp khi muốn kiểm tra cấu hình Spring được chọn mà không cần nạp toàn bộ ứng dụng Spring Boot. Cấu hình context có thể được khai báo bằng Java configuration hoặc các nguồn cấu hình Spring phù hợp.

#### Kiểm thử nhiều lớp bằng @SpringBootTest

**@SpringBootTest** tạo ApplicationContext theo cấu hình ứng dụng Spring Boot. Nó phù hợp khi cần xác minh nhiều bean thật phối hợp với nhau, ví dụ controller, service, repository và cấu hình persistence.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderRepository orderRepository;

    @MockBean
    private PaymentGateway paymentGateway;

    @Test
    void shouldPersistOrderAfterSuccessfulPayment() throws Exception {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved("payment-7"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 250000
                                }
                                """))
                .andExpect(status().isCreated());

        assertEquals(1, orderRepository
                .findByCustomerId("customer-1").size());
    }
}
~~~

Bài test trên giữ controller, service, repository và database theo cấu hình test ở dạng thật, nhưng thay cổng thanh toán bằng mock. Nó kiểm tra sự phối hợp giữa nhiều lớp bên trong ứng dụng, nên phù hợp với integration test.

**@SpringBootTest** mặc định không đồng nghĩa với việc khởi động một HTTP server thật. Khi kết hợp với **@AutoConfigureMockMvc**, request được gửi qua **MockMvc** trong môi trường kiểm thử MVC. Điều này vẫn hữu ích để kiểm tra routing và chuỗi xử lý Spring MVC, nhưng không kiểm tra kết nối mạng HTTP thực tế.

### Dùng database hoặc dịch vụ thật trong integration test

Một integration test có thể cần database thật để xác minh hành vi persistence. Testcontainers giúp khởi chạy database hoặc dịch vụ phụ thuộc trong container dành cho test, sau đó cung cấp thông tin kết nối cho Spring.

Ví dụ minh họa với PostgreSQL:

~~~java
@Testcontainers
@DataJpaTest
class OrderRepositoryPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldPersistAndReadOrder() {
        var saved = orderRepository.save(
                new Order("customer-1", 250_000));

        var loaded = orderRepository.findById(saved.getId());

        assertTrue(loaded.isPresent());
    }
}
~~~

Đoạn code cần dependency Testcontainers phù hợp và cấu hình entity/repository của dự án. Nó minh họa cách thay database nhúng bằng PostgreSQL thật trong phạm vi test.

Một bài test dùng database thật vẫn có thể là integration test. Loại test được xác định bởi ranh giới đang kiểm tra, không phải bởi việc có dùng container hay không.

### Ưu điểm và giới hạn

**Ưu điểm**

- Phát hiện lỗi wiring, cấu hình và giao tiếp giữa các bean.
- Xác minh mapping, transaction, truy vấn và serialization trong môi trường thực tế hơn unit test.
- Có thể kiểm tra hợp đồng giữa các module hoặc adapter.
- Giúp tìm lỗi mà mock không thể phát hiện.

**Giới hạn**

- Chạy chậm hơn unit test vì phải tạo context, database hoặc container.
- Có thể phụ thuộc cổng mạng, Docker, tài nguyên máy hoặc dịch vụ thử nghiệm.
- Nếu dữ liệu không được cô lập và dọn dẹp đúng cách, test dễ phụ thuộc thứ tự chạy.
- Khi nhiều lớp cùng tham gia, việc tìm nguyên nhân thất bại có thể mất thời gian hơn.

Integration test nên giữ số lượng và phạm vi vừa đủ. Hãy chọn chính xác ranh giới có rủi ro tích hợp cao, thay vì khởi động toàn bộ hệ thống cho mọi trường hợp nghiệp vụ nhỏ.

## 4. Kiểm thử toàn hệ thống (System Testing)

### Mục tiêu và phạm vi

System test xác minh hệ thống hoàn chỉnh đáp ứng yêu cầu khi các thành phần cần thiết hoạt động cùng nhau. Bài test quan sát hành vi từ ranh giới bên ngoài của hệ thống, chẳng hạn HTTP API công khai, giao diện người dùng hoặc một điểm vào của quy trình xử lý.

Với chức năng tạo đơn hàng, một luồng system/E2E có thể là:

~~~text
Khách hàng mở trang đặt hàng
        |
        v
Nhập thông tin và xác nhận
        |
        v
Frontend gửi HTTP request
        |
        v
Backend xác thực và xử lý
        |
        v
Database lưu đơn hàng
        |
        v
Hệ thống xử lý thanh toán
        |
        v
Khách hàng nhìn thấy mã đơn hàng
~~~

Bài test tập trung vào kết quả mà hệ thống cung cấp: yêu cầu hợp lệ tạo được đơn hàng, dữ liệu được lưu đúng, trạng thái trả về phù hợp và người dùng có thể quan sát kết quả mong đợi.

System test thường cố gắng giữ các thành phần trong phạm vi kiểm thử ở dạng thật. Nếu phải thay một dịch vụ bên ngoài, cần ghi rõ ranh giới nào đang được mô phỏng. Việc thay thế một dịch vụ bên thứ ba có thể hợp lý vì chi phí, tính ổn định hoặc giới hạn môi trường, nhưng bài test khi đó không chứng minh được tích hợp thực tế với dịch vụ đó.

### Kiểm thử API với server thật

Spring Boot có thể khởi động server nhúng trên cổng ngẫu nhiên bằng **webEnvironment = RANDOM_PORT**. Khi đó test gửi HTTP request qua client, thay vì gọi **MockMvc**.

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiSystemTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void shouldCreateOrderThroughHttpEndpoint() {
        var request = new CreateOrderRequest("customer-1", 250_000);

        var response = http.postForEntity(
                "/api/orders",
                request,
                OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("customer-1", response.getBody().customerId());
    }
}
~~~

Bài test này đi qua HTTP server thật của ứng dụng Spring Boot. Nếu database và các thành phần cần thiết cũng được cấu hình bằng dịch vụ thật trong môi trường test, phạm vi kiểm tra sẽ rộng hơn.

Tuy nhiên, chỉ dùng **RANDOM_PORT** chưa tự động biến bài test thành kiểm thử toàn hệ thống. Nếu một số dependency quan trọng vẫn bị mock, hoặc test chỉ xác minh một endpoint nội bộ, phạm vi thực tế vẫn có thể là kiểm thử tích hợp qua HTTP. Tên test không quyết định phạm vi; các thành phần thật và hành trình được kiểm tra mới quyết định.

### Kiểm thử hành trình người dùng bằng trình duyệt

Với sản phẩm có frontend, một bài E2E thường dùng công cụ tự động hóa trình duyệt như Playwright hoặc Selenium:

1. Mở trang đăng nhập.
2. Đăng nhập bằng tài khoản kiểm thử.
3. Mở trang tạo đơn hàng.
4. Nhập dữ liệu và gửi biểu mẫu.
5. Kiểm tra thông báo thành công và mã đơn hàng.
6. Mở lịch sử đơn hàng để xác nhận đơn vừa tạo xuất hiện.

Bài test này đi qua nhiều lớp: giao diện, HTTP API, xác thực, nghiệp vụ và persistence. Nó có giá trị cao vì mô phỏng cách người dùng thực sự sử dụng sản phẩm, nhưng cũng có nhiều điểm có thể gây lỗi: trình duyệt, mạng, dữ liệu test, thời gian chờ, dịch vụ phụ thuộc và môi trường triển khai.

### Ưu điểm và giới hạn

**Ưu điểm**

- Xác minh luồng nghiệp vụ ở góc nhìn bên ngoài.
- Phát hiện lỗi phối hợp chỉ xuất hiện khi nhiều phần của hệ thống cùng chạy.
- Kiểm tra được cấu hình triển khai, xác thực, routing và hành vi thực tế qua giao diện hoặc API.
- Cung cấp bằng chứng gần với trải nghiệm người dùng.

**Giới hạn**

- Thường chậm và tốn tài nguyên nhất trong ba phạm vi.
- Khó xác định chính xác lớp gây lỗi khi một luồng dài thất bại.
- Dễ không ổn định nếu phụ thuộc thời gian, mạng, dữ liệu dùng chung hoặc dịch vụ bên ngoài.
- Khó bao phủ mọi nhánh và mọi trường hợp biên.
- Chi phí bảo trì cao khi giao diện hoặc quy trình thay đổi.

System/E2E test nên tập trung vào các hành trình quan trọng và rủi ro cao: đăng ký, đăng nhập, thanh toán, tạo đơn hàng, phân quyền hoặc các luồng có ảnh hưởng lớn đến dữ liệu. Những quy tắc nhỏ và nhiều trường hợp biên vẫn nên được kiểm tra ở unit hoặc integration test.

## 5. Bảng so sánh

| Tiêu chí | Unit test | Integration test | System test / E2E |
|---|---|---|---|
| Câu hỏi chính | Một đơn vị có xử lý đúng logic không? | Các thành phần liên quan có phối hợp đúng không? | Hệ thống hoàn chỉnh có đáp ứng yêu cầu không? |
| Phạm vi | Hàm, lớp hoặc đơn vị nhỏ | Nhiều bean, module hoặc adapter qua một ranh giới | Một hệ thống hoặc hành trình xuyên suốt |
| Thành phần thật | Đơn vị đang kiểm tra | Các thành phần nằm trong ranh giới tích hợp | Các thành phần cần thiết cho luồng hệ thống |
| Dependency bên ngoài | Thường mock, stub hoặc fake | Có thể thật hoặc mô phỏng có chủ đích | Ưu tiên môi trường thật hoặc môi trường tương đương |
| Spring thường dùng | JUnit 5, Mockito; không cần context | @WebMvcTest, @DataJpaTest, @SpringJUnitConfig, @SpringBootTest | @SpringBootTest(RANDOM_PORT), HTTP client, công cụ trình duyệt |
| Tốc độ | Nhanh nhất | Trung bình | Thường chậm nhất |
| Khả năng khoanh vùng lỗi | Cao | Trung bình | Thấp hơn |
| Rủi ro môi trường | Thấp | Trung bình | Cao hơn |
| Ví dụ | Tính phí vận chuyển | Service lưu dữ liệu qua repository thật | Người dùng tạo đơn hàng từ giao diện đến kết quả cuối |

Các ô trong bảng mô tả xu hướng phổ biến, không phải quy tắc tuyệt đối. Một integration test dùng nhiều container có thể chạy lâu hơn một system test nhỏ; một unit test phụ thuộc quá nhiều vào môi trường cũng có thể không còn nhẹ.

## 6. Những nhầm lẫn thường gặp

### Có @SpringBootTest thì đó là system test?

Không. Annotation này nói rằng Spring Boot sẽ tạo ApplicationContext theo cấu hình ứng dụng. Nó không nói bài test đang kiểm tra bao nhiêu thành phần hoặc hành trình nào.

Ví dụ:

- **@SpringBootTest** + mock repository + kiểm tra một quy tắc service: phạm vi có thể vẫn gần với unit test có context, dù cách tổ chức này thường nặng hơn cần thiết.
- **@SpringBootTest** + controller, service, repository và database thật: thường là integration test ở phạm vi rộng.
- **@SpringBootTest(webEnvironment = RANDOM_PORT)** + HTTP client + các dependency cần thiết ở dạng thật: có thể là system/API E2E test cho backend.

Hãy phân loại dựa trên mục tiêu và ranh giới thực tế.

### Dùng MockMvc có phải là HTTP E2E?

**MockMvc** thực thi chuỗi xử lý Spring MVC trong môi trường mock, không gửi request qua một server mạng đang lắng nghe trên cổng thật. Nó rất phù hợp để kiểm tra routing, filter, argument binding, validation, controller advice và response.

Khi cần xác minh server nhúng, cổng mạng và HTTP client, hãy dùng **RANDOM_PORT** cùng **TestRestTemplate**, **WebTestClient** hoặc một HTTP client phù hợp. Nếu cần xác minh cả giao diện người dùng, hãy kiểm tra bằng trình duyệt tự động.

### Integration test có được dùng mock không?

Có. Một bài integration test có thể giữ database và repository thật nhưng mock cổng thanh toán bên ngoài. Khi đó nó kiểm tra tích hợp giữa các thành phần nội bộ và cô lập dịch vụ thanh toán.

Điều cần làm rõ là bài test đang xác minh ranh giới nào. Nếu mục tiêu là kiểm tra adapter thanh toán, mock chính adapter đó sẽ làm mất giá trị của bài test. Nếu mục tiêu là kiểm tra luồng tạo đơn hàng nội bộ và không muốn phụ thuộc nhà cung cấp thanh toán, mock cổng thanh toán có thể hợp lý.

### Dùng Testcontainers có làm bài test thành system test?

Không. Testcontainers chỉ cung cấp dịch vụ phụ thuộc thật trong container để test có môi trường gần thực tế hơn. Một bài **@DataJpaTest** dùng PostgreSQL container vẫn là repository integration test. Phạm vi được quyết định bởi hành vi và ranh giới đang kiểm tra.

### Unit test có cần Spring Context không?

Thông thường không. Nếu mục tiêu là kiểm tra logic của một lớp, tạo đối tượng trực tiếp qua constructor thường đơn giản, nhanh và rõ ràng hơn. Chỉ nạp Spring Context khi chính cấu hình hoặc cơ chế wiring của Spring nằm trong phạm vi cần xác minh.

## 7. Chọn phạm vi kiểm thử cho một thay đổi

Có thể chọn phạm vi theo rủi ro và câu hỏi cần trả lời.

| Thay đổi | Kiểm thử nên ưu tiên | Lý do |
|---|---|---|
| Thêm quy tắc tính giá | Unit test | Nhiều nhánh logic, cần kiểm tra nhanh từng trường hợp |
| Sửa cách service xử lý lỗi từ repository | Unit test và integration test | Unit kiểm tra quyết định; integration xác minh hành vi repository/transaction |
| Thêm endpoint REST | MVC slice test | Xác minh routing, binding, validation và HTTP response |
| Thay đổi mapping JPA hoặc câu query | Repository integration test | Cần database để xác minh SQL và mapping thực tế |
| Thay đổi transaction giữa nhiều repository | Integration test | Cần xác minh commit, rollback và tính nhất quán |
| Thay đổi cấu hình bảo mật | Integration test và một số system test | Cần kiểm tra filter, authentication, authorization và luồng truy cập |
| Thay đổi luồng thanh toán | Unit, integration và E2E có chọn lọc | Mỗi phạm vi xác minh một phần rủi ro khác nhau |
| Thay đổi giao diện của hành trình mua hàng | System/E2E test | Cần xác minh người dùng hoàn tất được hành trình |

Một quy trình thực tế có thể là:

1. Viết unit test cho logic mới và các trường hợp biên.
2. Viết integration test cho ranh giới bị thay đổi, chẳng hạn MVC, persistence hoặc messaging.
3. Chạy một số system/E2E test cho hành trình quan trọng bị ảnh hưởng.
4. Khi test thất bại, dùng phạm vi hẹp nhất có thể để khoanh vùng lỗi; sau đó xác minh lại luồng rộng hơn.

Không phải mọi thay đổi đều cần cả ba loại test. Một thay đổi thuần tính toán có thể chỉ cần unit test. Một thay đổi migration hoặc truy vấn cần integration test. Một thay đổi luồng đăng nhập có thể cần thêm system test để kiểm tra hành vi xuyên suốt.

## 8. Cách tự xác định một bài test thuộc phạm vi nào

Khi xem một lớp test có sẵn, hãy lần lượt trả lời các câu hỏi sau:

**1. Đối tượng chính đang được xác minh là gì?**

Nếu đó là một lớp hoặc một đơn vị logic nhỏ, bài test có xu hướng là unit test. Nếu là sự phối hợp giữa nhiều bean, repository hoặc adapter, nó có xu hướng là integration test. Nếu là hệ thống nhìn từ bên ngoài, nó có xu hướng là system test.

**2. Những thành phần nào là thật?**

Ghi rõ controller, service, repository, database, message broker, HTTP server và dịch vụ bên ngoài nào đang thật hoặc được mô phỏng. Điều này cho biết bài test có thể chứng minh điều gì.

**3. Bài test đi qua ranh giới nào?**

Gọi trực tiếp phương thức Java khác với gửi HTTP request. Gọi repository với database nhúng khác với kiểm tra hệ thống qua trình duyệt. Ranh giới càng gần cách vận hành thật thì phạm vi kiểm tra càng rộng.

**4. Nếu test xanh, ta có thể kết luận điều gì?**

Ví dụ, một unit test của service xanh chỉ chứng minh logic service đúng với các phản hồi mock đã thiết lập. Nó không chứng minh database lưu được dữ liệu. Một repository integration test xanh chứng minh truy vấn hoạt động trong database test, nhưng không chứng minh frontend gọi đúng API. Một E2E test xanh cung cấp bằng chứng cho hành trình đã chạy, nhưng không chứng minh mọi nhánh nghiệp vụ đều đúng.

**5. Nếu test đỏ, có thể khoanh vùng nguyên nhân ở đâu?**

Nếu một unit test đỏ, hãy xem logic và dữ liệu đầu vào của đơn vị. Nếu integration test đỏ, xem hợp đồng giữa các thành phần, cấu hình, transaction hoặc môi trường phụ thuộc. Nếu E2E test đỏ, kiểm tra log và trace qua từng lớp trước khi kết luận lỗi nằm ở giao diện hay backend.

Cách đặt câu hỏi này giúp tránh việc gắn nhãn theo cảm tính. Một test có thể nằm ở vùng giao nhau giữa hai phạm vi; hãy mô tả chính xác điều nó kiểm tra thay vì cố ép vào một nhãn duy nhất.

## 9. Một chiến lược kiểm thử cân bằng trong ứng dụng Spring

Một bộ kiểm thử tốt thường có nhiều unit test, một lượng integration test đủ để bảo vệ các ranh giới quan trọng và một tập system/E2E test nhỏ hơn dành cho hành trình có giá trị cao. Cách bố trí này thường được minh họa bằng **test pyramid**:

~~~text
          [E2E]             Ít hơn, chậm hơn
      [Integration]         Vừa đủ cho ranh giới
       [Unit tests]         Nhiều hơn, phản hồi nhanh
~~~

Đây là định hướng về chi phí và tốc độ phản hồi, không phải tỷ lệ phần trăm bắt buộc. Một hệ thống có nhiều tích hợp phức tạp có thể cần tỷ trọng integration test cao hơn. Điều quan trọng là mỗi bài test phải bảo vệ một rủi ro cụ thể và không lặp lại quá nhiều cùng một bằng chứng.

Khi thiết kế bộ test cho ứng dụng Spring:

- Giữ logic nghiệp vụ độc lập với framework khi có thể, để unit test không cần khởi động context.
- Dùng Spring slice test khi muốn xác minh một lớp framework cụ thể như MVC hoặc JPA.
- Dùng **@SpringBootTest** khi cần xác minh cấu hình và sự phối hợp của nhiều bean trong ứng dụng.
- Dùng database hoặc container tương thích khi rủi ro liên quan đến SQL, transaction hoặc dịch vụ hạ tầng.
- Dùng server thật và HTTP client khi cần xác minh giao tiếp qua HTTP.
- Dùng trình duyệt tự động cho một số hành trình người dùng quan trọng.
- Cô lập dữ liệu test, quản lý vòng đời container và dọn trạng thái bên ngoài để test có thể chạy lặp lại.
- Tránh phụ thuộc vào thời gian chờ cố định; ưu tiên chờ điều kiện hoặc trạng thái có thể quan sát.
- Giữ thông tin lỗi đủ rõ để biết bước nào trong luồng thất bại.

## 10. Kết luận về phạm vi và bằng chứng

Ba loại kiểm thử trả lời ba câu hỏi khác nhau:

- Unit test: **logic của đơn vị đang kiểm tra có đúng không?**
- Integration test: **các thành phần qua ranh giới được chọn có phối hợp đúng không?**
- System test: **hệ thống hoàn chỉnh có tạo ra kết quả mà yêu cầu mong đợi không?**

Trong Spring, JUnit và Mockito thường hỗ trợ unit test; Spring TestContext, **@WebMvcTest**, **@DataJpaTest** và **@SpringBootTest** hỗ trợ nhiều phạm vi integration; còn **RANDOM_PORT**, HTTP client, Testcontainers và công cụ trình duyệt giúp mở rộng kiểm tra đến môi trường vận hành gần thực tế.

Hãy chọn phạm vi từ rủi ro cần xác minh, xác định rõ thành phần thật và thành phần mô phỏng, rồi dùng annotation hoặc công cụ phù hợp. Khi hiểu được bài test đang tạo ra bằng chứng gì, ta sẽ biết test nào cần viết, test nào đang thiếu và kết quả test xanh thực sự cho phép kết luận đến đâu.

