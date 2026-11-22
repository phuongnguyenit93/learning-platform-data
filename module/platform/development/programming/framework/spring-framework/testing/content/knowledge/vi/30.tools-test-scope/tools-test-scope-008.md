# Chọn công cụ bổ sung theo rủi ro thay vì dùng mọi công cụ cho mọi bài

Một dự án Spring có thể dùng rất nhiều công cụ kiểm thử: JUnit, Mockito, Spring TestContext, MockMvc, WebTestClient, RestTestClient, Testcontainers, WireMock, MockWebServer, Awaitility, StepVerifier, ArchUnit và nhiều thư viện khác. Việc có nhiều công cụ không có nghĩa mọi test đều cần tất cả chúng. Mỗi công cụ tạo ra một mức độ mô phỏng, độ tin cậy, chi phí chạy và chi phí bảo trì khác nhau.

Hãy bắt đầu từ rủi ro cần phát hiện. Nếu lỗi có thể xảy ra trong logic của một phương thức thuần Java, một unit test với JUnit và Mockito thường đủ. Nếu rủi ro nằm ở request mapping, validation hoặc JSON binding, cần test qua Spring MVC infrastructure. Nếu ứng dụng phụ thuộc vào hành vi riêng của PostgreSQL, Kafka hoặc một HTTP service, cần kiểm thử tích hợp với hạ tầng tương ứng hoặc một mô phỏng có hợp đồng rõ ràng. Nếu rủi ro nằm ở thời điểm hoàn tất của tác vụ bất đồng bộ, cần công cụ đồng bộ và xác minh publisher hoặc trạng thái cuối.

Mục tiêu là chọn bộ công cụ nhỏ nhất vẫn tạo được bằng chứng đáng tin cậy cho rủi ro quan trọng. Cách chọn này giúp test nhanh, dễ hiểu và có ý nghĩa khi thất bại.

## 1. Bắt đầu từ rủi ro, không bắt đầu từ danh sách công cụ

Trước khi chọn công cụ, hãy mô tả điều gì có thể hỏng và hậu quả của nó. Một cách phân tích thực tế là xem xét bốn yếu tố:

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| Tác động | Nếu lỗi xảy ra, người dùng, dữ liệu hoặc hệ thống bị ảnh hưởng đến mức nào? |
| Khả năng xảy ra | Logic hoặc cấu hình này có dễ sai khi thay đổi code, dependency hoặc môi trường không? |
| Độ khó phát hiện | Unit test hoặc log hiện tại có phát hiện được lỗi trước khi phát hành không? |
| Mức phụ thuộc | Hành vi có phụ thuộc vào Spring container, database, HTTP protocol, broker, thread hoặc hạ tầng thật không? |

Ví dụ:

- Một hàm tính phí đơn giản có đầu vào và đầu ra rõ ràng: rủi ro chủ yếu nằm ở logic; JUnit và AssertJ thường đủ.
- Controller nhận JSON có LocalDate, validation và exception advice: rủi ro nằm ở mapping, message converter và cấu hình MVC; cần test slice MVC.
- Repository dùng truy vấn native hoặc phụ thuộc hành vi riêng của PostgreSQL: mock repository không thể xác nhận SQL thật; cần database cùng loại hoặc tương đương.
- Client gọi dịch vụ thanh toán: rủi ro nằm ở URI, method, header, serialization, timeout và response lỗi; cần kiểm tra request outbound.
- Tác vụ nền cập nhật trạng thái sau khi xử lý: rủi ro nằm ở dispatch, đồng bộ, retry và race condition; cần xác minh hoàn tất và các trạng thái cạnh tranh.

Không phải mọi rủi ro đều cần môi trường production-like. Cần chọn đúng ranh giới nơi lỗi có thể xuất hiện.

## 2. Dùng mức kiểm thử phù hợp với ranh giới cần xác nhận

Có thể phân loại kiểm thử theo phạm vi tăng dần:

~~~text
Logic Java thuần
    |
    v
Unit test
JUnit + Mockito + AssertJ
    |
    v
Một lát cắt Spring
@WebMvcTest / @DataJpaTest / @JsonTest
    |
    v
ApplicationContext
@SpringBootTest
    |
    v
Hạ tầng tích hợp thật hoặc mô phỏng protocol
Testcontainers / WireMock / MockWebServer
    |
    v
Hệ thống chạy qua HTTP và môi trường gần triển khai
Random port / external test environment
~~~

Phạm vi rộng hơn thường có chi phí khởi động, thời gian chạy và số nguyên nhân có thể làm test thất bại lớn hơn. Vì vậy, dùng phạm vi rộng khi nó kiểm tra được rủi ro mà phạm vi hẹp không thể kiểm tra.

### 2.1. Unit test cho logic không cần Spring

Chọn JUnit Jupiter, Mockito và AssertJ khi:

- Đối tượng không cần Spring container để thực thi.
- Dependency có thể thay bằng interface hoặc collaborator giả.
- Điều cần xác minh là quy tắc, nhánh logic, phép tính hoặc cách phối hợp các dependency.
- Không cần kiểm tra serialization, dependency injection, transaction manager hoặc request mapping.

Ví dụ:

~~~java
class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void waivesFeeWhenOrderMeetsThreshold() {
        Money fee = calculator.calculate(
                Money.of(600_000, "VND"),
                DeliveryRegion.CITY);

        assertThat(fee).isEqualTo(Money.zero("VND"));
    }
}
~~~

Không cần @SpringBootTest chỉ để tạo một object có constructor đơn giản. Khởi động context cho logic thuần Java làm test chậm và có thể khiến lỗi cấu hình không liên quan che khuất lỗi nghiệp vụ.

Mockito phù hợp để cô lập collaborator và kiểm tra tương tác có ý nghĩa. Không mock mọi object chỉ để tăng số lượng assertion. Nếu test mock toàn bộ lớp bên dưới và chỉ xác nhận các lời gọi mock theo đúng thứ tự implementation, nó có thể trở nên mong manh khi code được tái cấu trúc mà hành vi bên ngoài không đổi.

### 2.2. Spring test slice cho một phần framework

Dùng test slice khi rủi ro nằm ở một phần cụ thể của Spring:

| Slice | Ranh giới được kiểm tra |
|---|---|
| @WebMvcTest | Controller, request mapping, argument binding, validation, converter và advice trong MVC slice |
| @DataJpaTest | Repository, mapping entity, query và tích hợp JPA trong test context |
| @JsonTest | Serialization/deserialization JSON và cấu hình Jackson liên quan |
| @RestClientTest | Thành phần client REST và cấu hình kiểm thử outbound HTTP theo Spring Boot |

Ví dụ @WebMvcTest phù hợp khi cần xác nhận JSON field được bind đúng và lỗi validation trả status đúng. Service thường được mock vì test không nhằm xác nhận logic service hoặc database.

Ví dụ @DataJpaTest phù hợp khi cần kiểm tra mapping, constraint, quan hệ và truy vấn repository. Nếu database test mặc định khác database production, hãy cân nhắc Testcontainers để phát hiện khác biệt dialect, kiểu dữ liệu hoặc hành vi SQL.

Slice có lợi thế khởi động nhanh hơn application context đầy đủ và giới hạn phạm vi test. Nhưng một slice chỉ kiểm tra cấu hình được nạp trong slice đó. Nếu test cần một bean hoặc cấu hình không có trong slice, hãy import nó có chủ đích hoặc chuyển sang test context phù hợp; không nên thêm nhiều cấu hình tùy tiện khiến slice mất ý nghĩa.

### 2.3. ApplicationContext đầy đủ khi tích hợp nhiều bean

@SpringBootTest phù hợp khi rủi ro nằm ở cách nhiều bean và cấu hình phối hợp:

- Dependency injection, conditional configuration hoặc bean selection.
- Transaction manager phối hợp với service và repository.
- Security filter chain hoặc cấu hình toàn ứng dụng.
- Event listener, scheduler hoặc executor được đăng ký trong context.
- Nhiều lớp ứng dụng phối hợp qua cấu hình Spring.

Ví dụ:

~~~java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void storesOrderAndPublishesApplicationEvent() {
        Order order = orderService.placeOrder(
                new PlaceOrderCommand("COFFEE-01", 2));

        assertThat(orderRepository.findById(order.getId()))
                .isPresent();
    }
}
~~~

Đây chỉ là khung minh họa. Test context đầy đủ không tự động có nghĩa database, broker hoặc HTTP service bên ngoài đều là thật. Các dependency ngoài vẫn phụ thuộc cấu hình test. Hãy ghi rõ phần nào là thật, phần nào là mock và phần nào là container.

Không dùng @SpringBootTest cho mọi test chỉ vì ứng dụng dùng Spring Boot. Một test đầy đủ context có thể chậm và khó chẩn đoán hơn nhiều test nhỏ có cùng khả năng phát hiện lỗi.

## 3. Chọn công cụ theo loại rủi ro

Bảng sau giúp ánh xạ rủi ro phổ biến với công cụ phù hợp:

| Rủi ro cần phát hiện | Công cụ thường phù hợp | Khi nào cần nâng phạm vi |
|---|---|---|
| Sai quy tắc nghiệp vụ thuần Java | JUnit, AssertJ, Mockito | Khi quy tắc phụ thuộc dữ liệu hoặc framework thật |
| Sai HTTP mapping, status, header hoặc JSON binding | MockMvc cho Spring MVC; WebTestClient cho WebFlux; RestTestClient khi phiên bản hỗ trợ | Khi cần xác nhận connector, Servlet container hoặc network |
| Sai JSON serialization/deserialization | @JsonTest, Jackson test hoặc MVC/WebFlux test | Khi cần xác nhận JSON trong toàn bộ request/response endpoint |
| Sai truy vấn hoặc mapping JPA | @DataJpaTest | Khi SQL/dialect phụ thuộc database cụ thể, dùng Testcontainers |
| Sai request outbound từ RestClient/RestTemplate | MockRestServiceServer | Khi cần xác nhận protocol qua socket, TLS hoặc behavior của HTTP client thật |
| Sai request outbound từ WebClient | MockWebServer hoặc WireMock | Khi cần kiểm tra service ngoài thật trong môi trường tích hợp |
| Sai hành vi database, broker hoặc cache | Testcontainers với công nghệ phù hợp | Khi cần xác nhận triển khai đa dịch vụ hoặc môi trường thật |
| Sai thời điểm hoàn tất của tác vụ async | CompletableFuture, CountDownLatch, Awaitility | Khi cần kiểm tra nhiều worker, queue, rejection hoặc race condition |
| Sai luồng reactive hoặc backpressure | Reactor StepVerifier | Khi cần xác nhận kết nối HTTP/reactive end-to-end |
| Vi phạm dependency giữa module | ArchUnit hoặc Spring Modulith | Khi cần xác nhận kiến trúc ở quy mô nhiều module |

Không cần đưa tất cả công cụ trong bảng vào cùng một test suite. Hãy chọn công cụ tương ứng với ranh giới nơi rủi ro phát sinh.

## 4. HTTP inbound: chọn MockMvc, WebTestClient hay RestTestClient

Các công cụ HTTP inbound kiểm tra request đi vào ứng dụng. Việc chọn công cụ phụ thuộc loại web stack và phiên bản Spring:

| Công cụ | Phù hợp với | Điểm cần nhớ |
|---|---|---|
| MockMvc | Spring MVC trên Servlet stack | Kiểm tra MVC qua mock Servlet API, không mở socket |
| WebTestClient | Spring WebFlux; cũng có thể dùng để test một số MVC endpoint qua adapter phù hợp | API reactive, hỗ trợ kiểm tra publisher và streaming |
| RestTestClient | Spring Framework 7.0+ cho kiểm thử REST endpoint đồng bộ | Có thể bind vào controller, context, router function hoặc server |
| TestRestTemplate | Spring Boot integration test với server chạy thật | Gửi HTTP qua cổng server, phù hợp kiểm tra end-to-end hơn |

Ví dụ:

- Controller MVC có mapping, validation và @ControllerAdvice: dùng @WebMvcTest với MockMvc.
- WebFlux endpoint trả Flux hoặc Server-Sent Events: dùng WebTestClient và StepVerifier.
- Dự án Spring Framework 7 dùng RestTestClient cho REST endpoint: chọn kiểu bind phù hợp với phạm vi test.
- Cần kiểm tra cổng, connector hoặc filter ở server thật: chạy server trên random port và dùng HTTP client.

Không dùng MockMvc để kết luận network, TLS hoặc proxy hoạt động đúng. Nó không mở socket. Ngược lại, không cần khởi động server thật chỉ để kiểm tra một field JSON được bind đúng trong controller.

## 5. HTTP outbound: mock request hay chạy mock server?

Service thường gọi API ngoài qua một HTTP client. Chọn công cụ theo loại client và điều cần xác nhận:

| Client trong ứng dụng | Công cụ test phù hợp |
|---|---|
| RestClient | MockRestServiceServer.bindTo(RestClient.Builder) |
| RestTemplate | MockRestServiceServer.createServer(RestTemplate) |
| WebClient | MockWebServer hoặc WireMock |

MockRestServiceServer kiểm tra request ở abstraction của Spring RestClient hoặc RestTemplate. Nó hữu ích khi cần xác nhận URI, method, header, body và response mapping mà không cần mở cổng mạng.

MockWebServer hoặc WireMock tạo một HTTP server giả mà client thực sự gửi request tới. Chúng hữu ích khi cần kiểm tra request qua connector, timeout, retry hoặc behavior phụ thuộc HTTP protocol. WireMock còn có thể mô phỏng nhiều response và tình huống lỗi theo kịch bản.

Không nên mock trực tiếp phương thức RestClient hoặc WebClient ở mọi test nếu mục tiêu là xác nhận request HTTP được tạo đúng. Mock method call có thể bỏ qua URI builder, serialization, header mặc định và cấu hình connector mà ta cần kiểm tra.

Chỉ gọi service ngoài thật trong test khi môi trường đó được kiểm soát và có mục đích rõ ràng. Test phụ thuộc API công cộng có thể thất bại do mạng, quota, dữ liệu thay đổi hoặc sự cố nhà cung cấp, làm CI không ổn định.

## 6. Database và middleware: khi nào cần Testcontainers?

Mock repository không kiểm tra SQL thật, mapping thật hoặc transaction behavior của database. Database nhúng có thể hữu ích cho một số test, nhưng nếu production dùng PostgreSQL, MySQL hoặc một engine có hành vi riêng, database khác loại có thể bỏ sót lỗi.

Testcontainers cho phép khởi chạy dependency thật trong container trong quá trình test:

~~~java
@Testcontainers
@DataJpaTest
class OrderRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersUsingProductionDatabaseDialect() {
        // Lưu dữ liệu test và kiểm tra truy vấn repository.
    }
}
~~~

Ví dụ trên cần dependency Testcontainers tương ứng với JUnit và PostgreSQL, Docker-compatible runtime trong môi trường chạy test, cùng cấu hình database phù hợp với dự án. Phiên bản image nên được pin theo chính sách dependency của dự án thay vì dùng tag thay đổi tùy thời điểm.

Testcontainers phù hợp khi:

- Truy vấn sử dụng cú pháp hoặc tính năng riêng của database.
- Mapping JSON, UUID, array, sequence hoặc kiểu dữ liệu phụ thuộc engine.
- Transaction isolation, locking hoặc constraint có ý nghĩa quan trọng.
- Migration phải chạy đúng trên database production.
- Ứng dụng tích hợp broker như Kafka hoặc Redis và hành vi thật của dependency là rủi ro chính.

Không cần khởi chạy container cho mọi repository test nếu test chỉ kiểm tra một phép tính hoặc một mapper thuần Java. Cũng không cần container cho mọi test chỉ vì dự án có Docker; chi phí khởi động và yêu cầu môi trường phải tương xứng với rủi ro cần phát hiện.

## 7. Tác vụ bất đồng bộ và reactive: chọn công cụ theo hành vi

Một tác vụ nền có thể hoàn tất sau khi phương thức gọi đã trả về. Test cần đồng bộ với tín hiệu thật:

- CompletableFuture.get(timeout, unit) khi API trả future.
- CountDownLatch khi cần chờ một tác vụ void.
- Awaitility khi trạng thái cuối được cập nhật qua nhiều bean hoặc repository.
- StepVerifier khi cần kiểm tra Mono hoặc Flux.

Ví dụ chờ một trạng thái được cập nhật:

~~~java
worker.startProcessing(jobId);

await()
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(jobRepository.findStatus(jobId))
                        .isEqualTo(JobStatus.COMPLETED));
~~~

Awaitility phù hợp khi test cần chờ một điều kiện cuối cùng và không có future/latch trực tiếp. Nếu test cần xác nhận chính xác một publisher phát ra tín hiệu nào, StepVerifier thường rõ hơn.

Không dùng Thread.sleep(...) làm cơ chế đồng bộ. Sleep không xác nhận task đã chạy, không truyền lỗi từ worker về test và dễ chập chờn trên CI. Cũng không gom toàn bộ Flux vào list nếu API được thiết kế streaming và test chỉ cần xác minh một số phần tử.

## 8. Kiến trúc module: công cụ chỉ cần khi có rủi ro kiến trúc

Một unit test có thể chứng minh một phương thức trả kết quả đúng nhưng không phát hiện module A bắt đầu phụ thuộc trực tiếp vào implementation nội bộ của module B. Nếu dự án có quy tắc kiến trúc rõ, có thể bổ sung:

- ArchUnit để kiểm tra package, layer, naming rule và dependency direction.
- Spring Modulith để kiểm tra ranh giới module, dependency giữa module và một số hành vi tích hợp module trong ứng dụng Spring.

Ví dụ quy tắc ArchUnit:

~~~java
@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule controllersShouldNotAccessRepositories =
            noClasses()
                    .that().resideInAPackage("..web..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..repository..");
}
~~~

Kiểm tra kiến trúc hữu ích khi nhiều nhóm cùng phát triển hoặc codebase có module boundary cần giữ ổn định. Với ứng dụng nhỏ, chưa có quy tắc module cụ thể, thêm hàng loạt architecture test chung chung chỉ tạo thêm chi phí bảo trì.

## 9. Xác định mức rủi ro để chọn phạm vi test

Có thể dùng ma trận định tính sau để quyết định mức đầu tư:

| Tác động khi lỗi | Độ không chắc chắn thấp | Độ không chắc chắn cao |
|---|---|---|
| Thấp | Unit test hoặc test hiện có; không cần thêm hạ tầng | Unit test bổ sung case biên; có thể thêm test slice nhỏ |
| Trung bình | Unit test và một test slice ở ranh giới chính | Test slice cộng một integration test tập trung |
| Cao | Integration test cho dependency có tác động trực tiếp | Integration test với dependency tương ứng, kiểm tra lỗi và đường phục hồi; thêm test end-to-end có mục tiêu |

Ví dụ các tiêu chí rủi ro cao:

- Giao dịch tiền, thanh toán, hoàn tiền hoặc thay đổi số dư.
- Xóa hoặc cập nhật dữ liệu hàng loạt.
- Bảo mật, xác thực, phân quyền và rò rỉ dữ liệu.
- Tác vụ bất đồng bộ có thể chạy trùng, mất hoặc sai thứ tự.
- Tích hợp với hệ thống bên ngoài có hợp đồng hoặc quota quan trọng.
- Migration hoặc truy vấn có thể làm hỏng dữ liệu production.

Rủi ro cao không có nghĩa mọi test phải chạy end-to-end. Ví dụ thanh toán có thể cần unit test cho tính phí, contract test cho request outbound, integration test với database và một số test workflow. Mỗi test kiểm tra một lớp rủi ro cụ thể.

## 10. Ví dụ chọn công cụ cho một luồng đặt hàng

Giả sử luồng đặt hàng gồm:

~~~text
HTTP request
    |
    v
OrderController
    |
    v
OrderService
    |--------------------|
    v                    v
OrderRepository      PaymentClient
    |                    |
    v                    v
PostgreSQL           Payment API
    |
    v
OrderPlaced event
    |
    v
Background worker
~~~

Không cần một test duy nhất khởi động tất cả thành phần. Có thể phân bổ công cụ theo rủi ro:

| Thành phần | Rủi ro | Công cụ phù hợp |
|---|---|---|
| Tính tổng đơn và phí giao hàng | Sai quy tắc tính toán | JUnit + AssertJ |
| Controller tạo đơn | Sai JSON binding, validation hoặc status | @WebMvcTest + MockMvc |
| Repository | Sai truy vấn, mapping hoặc transaction | @DataJpaTest; Testcontainers PostgreSQL nếu phụ thuộc dialect |
| PaymentClient | Sai URI, method, token, body hoặc mapping lỗi | MockRestServiceServer nếu dùng RestClient; WireMock/MockWebServer nếu cần HTTP server giả |
| Event worker | Tác vụ không hoàn tất, lỗi hoặc chạy trùng | CompletableFuture, latch, Awaitility; kiểm tra retry/idempotency theo thiết kế |
| Toàn bộ workflow | Cấu hình bean hoặc tích hợp nhiều lớp sai | Một số @SpringBootTest có dependency được kiểm soát |

Test controller không cần database thật nếu mục tiêu là request mapping. Test repository không cần payment API. Test client không cần khởi động toàn bộ ứng dụng nếu chỉ kiểm tra request outbound. Một số integration test workflow sẽ xác nhận các phần phối hợp, nhưng không thay thế các test nhỏ có thông tin lỗi rõ ràng.

## 11. Chọn số lượng test và tránh kiểm tra trùng lặp

Một hành vi có thể được kiểm tra ở nhiều lớp, nhưng mỗi lớp nên bổ sung bằng chứng khác nhau:

- Unit test kiểm tra nhiều trường hợp logic và điều kiện biên với tốc độ cao.
- Slice test xác nhận tích hợp với một phần framework.
- Integration test xác nhận dependency và cấu hình thật trong phạm vi được kiểm soát.
- End-to-end test xác nhận một luồng quan trọng qua nhiều ranh giới.

Ví dụ, nếu unit test đã kiểm tra hàng chục trường hợp tính phí, không cần lặp toàn bộ các trường hợp đó trong @SpringBootTest. Một integration test có thể kiểm tra một vài kịch bản đại diện để xác nhận cấu hình và luồng tích hợp.

Không nên tạo nhiều test chỉ khác nhau ở cách khởi tạo context nhưng cùng xác minh một assertion không có giá trị bổ sung. Test trùng lặp làm thay đổi nhỏ cũng phải cập nhật ở nhiều nơi và tăng thời gian CI mà không tăng tương ứng khả năng phát hiện lỗi.

Tuy nhiên, cùng một kết quả cuối có thể cần được xác nhận ở nhiều ranh giới nếu các ranh giới có cơ chế lỗi khác nhau. Ví dụ, unit test chứng minh service xử lý 404 đúng; test client chứng minh HTTP response 404 được chuyển thành exception; integration test có thể xác nhận cấu hình endpoint và client phối hợp đúng.

## 12. Chi phí của công cụ cũng là một phần quyết định

Trước khi thêm công cụ, hãy cân nhắc:

| Chi phí | Điều cần xem xét |
|---|---|
| Thời gian chạy | Công cụ làm test nhanh hơn hay thêm nhiều giây/phút khởi động? |
| Môi trường | CI có Docker, port, filesystem hoặc service cần thiết không? |
| Độ ổn định | Test có phụ thuộc timing, mạng, dữ liệu ngoài hoặc thứ tự chạy không? |
| Bảo trì | Ai cập nhật image, stub, fixture, version và cấu hình? |
| Độ trung thực | Mô phỏng có phản ánh hành vi cần kiểm tra hay đang bỏ qua ranh giới quan trọng? |
| Chẩn đoán | Khi test thất bại, log có chỉ rõ request, SQL, task hoặc dependency gây lỗi không? |

Một công cụ có thể rất phù hợp cho integration test nhưng không phù hợp với hàng trăm unit test chạy mỗi lần lưu file. Ngược lại, mock quá mức có thể làm test nhanh nhưng bỏ qua lỗi cấu hình hoặc protocol. Chọn theo cả giá trị phát hiện lỗi và chi phí vận hành.

## 13. Tổ chức test suite theo tốc độ phản hồi

Có thể chia test thành các nhóm chạy ở thời điểm khác nhau:

| Nhóm | Nội dung | Thời điểm chạy |
|---|---|---|
| Fast tests | Unit test, mock-based test, một số slice nhỏ | Mỗi lần commit hoặc pull request |
| Integration tests | Database/container, HTTP mock server, application context rộng | Pull request hoặc pipeline tích hợp |
| Extended tests | Nhiều dependency, migration, concurrency hoặc workflow phức tạp | Trước release hoặc lịch chạy định kỳ |
| Environment tests | Kiểm tra với hệ thống test/staging bên ngoài | Theo quy trình triển khai và hợp đồng môi trường |

Đây là cách tổ chức tham khảo, không phải quy tắc cứng. Một integration test nhanh và ổn định vẫn có thể chạy ở mọi pull request. Một test end-to-end quan trọng có thể cần chạy trước mỗi release. Hãy dựa vào thời gian, mức rủi ro và khả năng tái lập.

Tách nhóm test bằng JUnit tags hoặc Gradle source set/task theo cấu trúc dự án. Đừng tạo nhiều tầng build phức tạp nếu chỉ có vài test. Điều quan trọng là developer biết nhóm nào chạy mặc định, nhóm nào cần Docker hoặc service ngoài và cách chạy chúng tại local.

## 14. Các dấu hiệu đang dùng quá nhiều công cụ

- Mọi test đều khởi động @SpringBootTest, kể cả test tính toán thuần Java.
- Mọi repository test đều dùng container dù không kiểm tra hành vi phụ thuộc database.
- Mọi HTTP client test đều gọi service thật trên mạng.
- Test dùng nhiều mock đến mức không còn xác nhận request, serialization hoặc SQL.
- Test async dùng sleep và timeout dài để chờ một cách đoán mò.
- Test end-to-end lặp lại toàn bộ trường hợp đã được kiểm tra rõ ở unit và slice test.
- Một test khởi tạo database, broker, web server, mock HTTP server và nhiều executor dù chỉ xác minh một hành vi.
- Khi test thất bại, không xác định được lỗi đến từ code, cấu hình, môi trường hay service ngoài.

Nếu thấy các dấu hiệu này, hãy quay lại câu hỏi: rủi ro nào đang được kiểm tra, và công cụ nào là cần thiết để phát hiện nó?

## 15. Các dấu hiệu đang dùng công cụ chưa đủ

Ngược lại, một bộ test có thể quá nhẹ nếu:

- Repository chỉ được kiểm tra bằng mock trong khi SQL có logic quan trọng.
- Controller chỉ được gọi trực tiếp như method Java, không kiểm tra mapping hoặc serialization.
- Client outbound chỉ mock method call, không kiểm tra URI/header/body.
- Transaction hoặc locking quan trọng nhưng chưa có test với database tương ứng.
- Security chỉ được kiểm tra ở service method, bỏ qua filter chain hoặc request authentication.
- Tác vụ async chỉ được gọi mà không chờ hoàn tất hoặc quan sát exception.
- Migration không được chạy trong test với database tương thích.
- Cấu hình bean có nhiều profile/condition nhưng chưa có test context xác nhận profile quan trọng.

Trong các trường hợp này, thêm một test ở đúng ranh giới có thể tạo giá trị lớn hơn nhiều test unit bổ sung.

## 16. Quy trình chọn công cụ trước khi viết test

Với mỗi tính năng hoặc thay đổi, thực hiện các bước:

1. Mô tả hành vi người dùng hoặc hợp đồng hệ thống cần bảo vệ.
2. Liệt kê các cách hành vi có thể hỏng và hậu quả.
3. Xác định ranh giới nơi lỗi có thể xuất hiện: logic, Spring MVC/WebFlux, database, HTTP client, broker, executor hay cấu hình ứng dụng.
4. Chọn công cụ gần ranh giới đó nhất nhưng vẫn kiểm tra được hành vi cần thiết.
5. Xác định dependency nào là thật, dependency nào là mock và vì sao.
6. Kiểm tra chi phí chạy, môi trường CI và khả năng tái lập.
7. Chỉ thêm test ở phạm vi rộng hơn khi test hẹp không thể phát hiện rủi ro quan trọng.
8. Đặt tên test theo hành vi cần bảo vệ, không theo tên thư viện hoặc cách triển khai.
9. Khi test thất bại, bảo đảm thông tin đủ để tìm ra request, dữ liệu, task hoặc dependency liên quan.

Ví dụ quyết định:

| Câu hỏi | Nếu câu trả lời là có | Lựa chọn nên cân nhắc |
|---|---|---|
| Logic có thể chạy mà không cần Spring không? | Có | Unit test |
| Cần xác nhận request/response MVC? | Có | MockMvc hoặc công cụ MVC tương ứng |
| Cần xác nhận một bean/cấu hình toàn ứng dụng? | Có | ApplicationContext test hoặc @SpringBootTest |
| SQL phụ thuộc database cụ thể? | Có | Testcontainers với database cùng loại |
| Cần xác nhận HTTP request outbound? | Có | MockRestServiceServer, WireMock hoặc MockWebServer theo client |
| Cần chờ trạng thái bất đồng bộ? | Có | Future, latch hoặc Awaitility |
| Cần kiểm tra publisher reactive? | Có | StepVerifier |
| Cần giữ quy tắc dependency giữa module? | Có | ArchUnit hoặc Spring Modulith |
| Cần kiểm tra connector/network thật? | Có | Server chạy thật và HTTP client |

## 17. Nguyên tắc kết luận

Không có một công cụ kiểm thử Spring nào phù hợp cho mọi rủi ro. Unit test cho phản hồi nhanh và kiểm tra logic; slice test xác nhận tích hợp với một phần framework; application context test kiểm tra nhiều bean và cấu hình phối hợp; Testcontainers và mock HTTP server xác nhận ranh giới với dependency; Awaitility và StepVerifier xác nhận hành vi bất đồng bộ hoặc reactive.

Chọn công cụ dựa trên hậu quả của lỗi, xác suất xảy ra, độ khó phát hiện và ranh giới thực sự cần kiểm tra. Giữ test nhỏ ở nơi có thể, thêm kiểm thử tích hợp khi nó tạo ra bằng chứng mới, và chỉ dùng môi trường gần production cho những hành vi mà mock hoặc slice không thể đại diện đáng tin cậy. Như vậy, bộ test sẽ tập trung vào rủi ro quan trọng và vẫn đủ nhanh để được chạy thường xuyên.
