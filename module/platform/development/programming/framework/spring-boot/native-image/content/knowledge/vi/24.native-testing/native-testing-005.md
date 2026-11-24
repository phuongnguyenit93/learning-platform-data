# @SpringBootTest, test slice và lựa chọn phạm vi kiểm thử

## 1. Chọn đúng phạm vi kiểm thử

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT rồi biên dịch thành GraalVM Native Image. Để kiểm tra ứng dụng đáng tin cậy, cần nhiều mức kiểm thử: test logic đơn vị, test một lát cắt Spring, test toàn bộ ApplicationContext và test executable native trong môi trường gần production.

`@SpringBootTest` và các test slice đều tạo Spring test context, nhưng chúng có mục đích và chi phí khác nhau:

- `@SpringBootTest` tải ApplicationContext của ứng dụng theo cấu hình gần với lúc chạy thật. Dùng khi cần kiểm tra nhiều bean phối hợp, auto-configuration, transaction, security hoặc tích hợp giữa các layer.
- Test slice như `@WebMvcTest`, `@DataJpaTest` và `@JsonTest` chỉ tải nhóm cấu hình liên quan đến một phần của ứng dụng. Dùng khi muốn kiểm tra một layer nhanh, cô lập và chỉ rõ dependency bên ngoài.
- Native executable test kiểm tra ứng dụng sau khi đã được AOT và GraalVM biên dịch. Đây là bước cần thiết để phát hiện khác biệt do reachability, reflection, resource, proxy, JNI hoặc service loading.

Không có một annotation nào phù hợp cho mọi test. Chọn phạm vi nhỏ nhất vẫn kiểm tra được hành vi cần xác nhận, sau đó bổ sung một số integration/native tests cho các đường đi xuyên suốt.

## 2. Nhìn vào test pyramid

~~~mermaid
flowchart TB
    N["Native executable / deployment tests"]
    I["@SpringBootTest integration tests"]
    S["Spring test slices"]
    U["Unit tests"]
    U --> S
    S --> I
    I --> N
~~~

| Mức kiểm thử | Spring context | Phạm vi | Chi phí tương đối |
| --- | --- | --- | --- |
| Unit test | Không | Một class hoặc logic thuần | Thấp |
| Test slice | Một phần context | MVC, JSON, persistence, client hoặc layer cụ thể | Thấp đến trung bình |
| `@SpringBootTest` | Gần như toàn bộ context | Tương tác giữa bean và cấu hình ứng dụng | Trung bình đến cao |
| Native/deployment test | Ứng dụng đã biên dịch native | Executable, OS, container, library và runtime behavior | Cao |

Pyramid không phải quy tắc cứng về số lượng. Một adapter gọi SDK có thể cần contract test riêng; một luồng thanh toán quan trọng có thể cần nhiều integration tests. Điều cần tránh là dùng full context cho mọi trường hợp chỉ vì cách viết test tiện lợi.

## 3. Unit test khi không cần Spring

Nếu class nhận dependency qua constructor và logic không phụ thuộc container, test trực tiếp bằng JUnit:

~~~java
class InvoiceCalculatorTests {

    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    @Test
    void calculatesTotalWithoutLosingDecimalPrecision() {
        Money net = new Money(new BigDecimal("100.25"), "USD");
        Money tax = new Money(new BigDecimal("8.02"), "USD");

        Money total = calculator.add(net, tax);

        assertThat(total.amount())
            .isEqualByComparingTo("108.27");
    }
}
~~~

Test này không cần `@SpringBootTest`, không khởi tạo ApplicationContext và không cần GraalVM. Đây là cách nhanh nhất để kiểm tra quy tắc tính toán, validation thuần, mapping đơn giản hoặc thuật toán.

Nếu một service phụ thuộc repository/gateway, có thể truyền fake/mock qua constructor để kiểm tra cách service phối hợp. Khi cần xác nhận Spring thực sự tạo và inject bean, chuyển sang test slice hoặc integration test.

## 4. Dùng @SpringBootTest cho toàn bộ ApplicationContext

`@SpringBootTest` tạo test ApplicationContext bằng cơ chế bootstrap của Spring Boot. Mặc định, Spring tìm cấu hình ứng dụng chính (thường là class có `@SpringBootApplication`) từ package của test hoặc package cha.

Ví dụ:

~~~java
@SpringBootTest
class BillingApplicationTests {

    @Autowired
    InvoiceService invoiceService;

    @Test
    void applicationContextProvidesInvoiceService() {
        assertThat(invoiceService).isNotNull();
    }
}
~~~

Test này hữu ích khi cần xác nhận bean graph, component scanning, auto-configuration và dependency injection hoạt động cùng nhau.

### 4.1. Chỉ định class cấu hình

Nếu test nằm ngoài package có thể tìm thấy application class, chỉ định cấu hình:

~~~java
@SpringBootTest(classes = BillingApplication.class)
class BillingApplicationTests {
}
~~~

Thuộc tính `classes` cũng hữu ích cho ứng dụng có nhiều cấu hình bootstrap hoặc test một module Spring Boot cụ thể.

### 4.2. Truyền property cho test

Có thể khai báo property ngay trên annotation:

~~~java
@SpringBootTest(properties = {
    "app.invoice.currency=USD",
    "app.invoice.tax-rate=0.08"
})
class InvoiceConfigurationTests {
}
~~~

Hoặc dùng `@ActiveProfiles` và `@TestPropertySource` khi muốn chia sẻ cấu hình test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "app.storage.bucket=contract-test")
class StorageIntegrationTests {
}
~~~

Các property này tham gia cấu hình test context. Với AOT processing, cần phân biệt property được dùng để quyết định cấu trúc bean ở build time và property chỉ được bind vào bean khi context chạy. Nếu thay đổi property làm thay đổi bean graph, không thể giả định một AOT output được sinh với cấu hình này sẽ đại diện cho mọi profile/condition khác.

## 5. Chọn web environment của @SpringBootTest

Thuộc tính `webEnvironment` quyết định Spring Boot tạo loại web context nào:

| Giá trị | Hành vi | Khi nên dùng |
| --- | --- | --- |
| `MOCK` | Tạo web ApplicationContext mô phỏng; không khởi động embedded server | Test MVC với MockMvc hoặc kiểm tra context web mà không mở cổng |
| `RANDOM_PORT` | Khởi động server thật trên cổng ngẫu nhiên | Test HTTP qua network stack thật |
| `DEFINED_PORT` | Khởi động server trên cổng cấu hình | Chỉ dùng khi cần cổng cố định và kiểm soát xung đột |
| `NONE` | Tạo non-web ApplicationContext | Ứng dụng batch, service không có web server hoặc test không cần web |

`MOCK` là mặc định. Ví dụ kiểm tra HTTP controller qua MockMvc:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class InvoiceHttpIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsInvoiceThroughMvcPipeline() throws Exception {
        mockMvc.perform(post("/api/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "customer-01",
                      "currency": "USD"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").isNotEmpty());
    }
}
~~~

`@AutoConfigureMockMvc` đăng ký MockMvc và các thành phần MVC liên quan trong context. Request đi qua Spring MVC filters, argument resolvers, validation, message converters và controller advice, nhưng không đi qua socket của embedded server.

### 5.1. Khi cần HTTP server thật

Dùng `RANDOM_PORT` khi muốn kiểm tra server startup, HTTP connector, network stack hoặc tương tác với client thực:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InvoiceServerTests {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void respondsThroughRunningServer() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/api/status", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }
}
~~~

Spring Boot cung cấp test client được cấu hình để gọi server đang chạy. Có thể dùng `WebTestClient` khi phù hợp với stack và cấu hình test.

Một lưu ý quan trọng: khi test dùng `RANDOM_PORT` hoặc `DEFINED_PORT`, request được xử lý trên thread của server, tách khỏi transaction của test thread. `@Transactional` trên method test không tự động rollback các thay đổi database do HTTP request thực hiện. Hãy dọn dữ liệu bằng API/fixture rõ ràng hoặc dùng database/schema riêng cho test.

## 6. Test slice là gì?

Test slice chỉ cấu hình một phần ApplicationContext liên quan đến mục tiêu kiểm thử. Spring Boot cung cấp annotation cho các nhóm phổ biến:

| Annotation | Thành phần chính | Mục đích |
| --- | --- | --- |
| `@WebMvcTest` | Spring MVC, controller, converter, filter và MVC advice phù hợp | Test controller trên servlet stack |
| `@WebFluxTest` | WebFlux controller và reactive web infrastructure | Test controller reactive |
| `@JsonTest` | JSON mapper và JSON test support | Test serialize/deserialize |
| `@DataJpaTest` | JPA repositories, entities và persistence configuration | Test mapping/query/repository |
| `@JdbcTest` | JDBC infrastructure và embedded database support | Test JDBC components |
| `@DataJdbcTest` | Spring Data JDBC repositories | Test repository theo JDBC aggregate |
| `@RestClientTest` | REST client components và mock server support | Test HTTP client adapter |
| `@DataMongoTest` | MongoDB mapping/repository infrastructure | Test MongoDB data layer |

Slice không có nghĩa là chỉ tạo đúng một bean. Nó nạp các auto-configuration và component liên quan đến slice đó. Các service, integration adapter hoặc cấu hình ứng dụng khác có thể không được scan tự động.

Nếu test cần thêm cấu hình, dùng `@Import` hoặc một nested `@TestConfiguration`. Chỉ thêm đúng dependency cần thiết để test vẫn thể hiện ranh giới của slice.

## 7. @WebMvcTest cho controller

`@WebMvcTest` phù hợp khi muốn test routing, binding, validation, serialization, status code và exception mapping của controller mà không khởi động toàn bộ service/repository/database.

Ví dụ:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    InvoiceService invoiceService;

    @Test
    void returnsCreatedWhenInvoiceIsAccepted() throws Exception {
        given(invoiceService.create(any()))
            .willReturn(new InvoiceResponse("inv-100", "USD"));

        mockMvc.perform(post("/api/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-01","currency":"USD"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("inv-100"));
    }
}
~~~

`@MockitoBean` thuộc Spring Framework mới hơn (Spring Framework 6.2, thường đi cùng Spring Boot 3.4+). Với phiên bản Spring Boot cũ hơn, dự án có thể đang dùng `@MockBean`; kiểm tra version trước khi chọn annotation.

Nếu controller dùng `@ControllerAdvice`, converter hoặc security configuration tùy biến, xác nhận chúng được slice nạp. Dùng `@Import` để đưa cấu hình cần thiết vào test. Không import toàn bộ application configuration chỉ để làm test pass, vì điều đó có thể biến slice thành gần-full-context test.

### 7.1. Validation và lỗi HTTP

Nên có test cho:

- request thiếu field bắt buộc;
- kiểu dữ liệu JSON sai;
- bean validation thất bại;
- service ném lỗi domain;
- người dùng chưa xác thực hoặc không đủ quyền;
- response có đúng status, error code và JSON structure.

Slice test kiểm tra hợp đồng HTTP của controller nhanh hơn full context. Một số vấn đề liên quan đến filter/security vẫn cần test với cấu hình security thật được import vào slice.

## 8. @JsonTest cho JSON contract

Nếu mục tiêu chỉ là kiểm tra Jackson mapping, dùng `@JsonTest`:

~~~java
@JsonTest
class MoneyJsonTests {

    @Autowired
    JacksonTester<Money> json;

    @Test
    void serializesMoneyUsingPublicContract() throws Exception {
        Money money = new Money(new BigDecimal("10.25"), "USD");

        assertThat(json.write(money))
            .isEqualToJson("""
                {
                  "amount": 10.25,
                  "currency": "USD"
                }
                """);
    }
}
~~~

`@JsonTest` tạo slice JSON và cung cấp các helper như `JacksonTester` hoặc `JsonbTester` tùy JSON technology. Nó hữu ích để test custom serializer, deserializer, naming strategy, mix-in và module registration liên quan.

Nếu module được đăng ký bằng Spring bean hoặc `@JsonComponent`, xác nhận slice nhận được component đó. Test thêm trường hợp input không hợp lệ, null, field thiếu và độ chính xác số.

Một test JSON slice trên JVM không chứng minh Jackson reflection hoạt động trong Native Image. Cần có native test cho endpoint hoặc serialization path quan trọng.

## 9. @DataJpaTest cho persistence layer

`@DataJpaTest` tập trung vào entity, repository và JPA infrastructure:

~~~java
@DataJpaTest
class InvoiceRepositoryTests {

    @Autowired
    InvoiceRepository invoiceRepository;

    @Test
    void persistsAndFindsInvoiceByReference() {
        Invoice invoice = new Invoice("INV-100", "USD");
        invoiceRepository.save(invoice);

        assertThat(invoiceRepository.findByReference("INV-100"))
            .isPresent();
    }
}
~~~

Slice thường chạy trong transaction và rollback sau mỗi test. Mặc định, Spring Boot có thể cấu hình embedded database nếu dependency phù hợp có mặt; nếu cần kiểm tra hành vi của database thật, dùng Testcontainers hoặc cấu hình datasource test rõ ràng.

Ví dụ với Testcontainers, Spring Boot phiên bản hỗ trợ `@ServiceConnection` có thể tự tạo connection details từ container:

~~~java
@DataJpaTest
@Testcontainers
class InvoiceRepositoryPostgresTests {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Kiểm tra version Spring Boot/Testcontainers của dự án. Nếu không dùng `@ServiceConnection`, có thể truyền URL/user/password bằng `@DynamicPropertySource`. Không để credential thật trong test source.

## 10. @RestClientTest cho HTTP client adapter

Khi test class gọi API bên ngoài qua `RestClient`, `RestTemplate` hoặc client được Spring Boot hỗ trợ, `@RestClientTest` giúp tạo slice cho client và cấu hình mock server:

~~~java
@RestClientTest(ExchangeRateClient.class)
class ExchangeRateClientTests {

    @Autowired
    ExchangeRateClient exchangeRateClient;

    @Autowired
    MockRestServiceServer server;

    @Test
    void mapsExchangeRateResponse() {
        server.expect(requestTo("/rates/USD"))
            .andRespond(withSuccess(
                """
                {"base":"USD","rate":1.0}
                """,
                MediaType.APPLICATION_JSON
            ));

        assertThat(exchangeRateClient.rateFor("USD"))
            .isEqualByComparingTo("1.0");
    }
}
~~~

Mock server kiểm tra URL, HTTP method, header, body và cách client chuyển response thành object. Nó không xác nhận network, TLS, DNS hoặc behavior của dịch vụ thật. Với các cam kết đó, cần contract test/deployment test riêng tới sandbox hoặc test server.

## 11. Thêm cấu hình vào test slice mà không mở rộng quá mức

Một slice có thể cần một bean cấu hình hoặc converter riêng. Có hai cách phổ biến:

~~~java
@TestConfiguration(proxyBeanMethods = false)
static class TestBeans {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Đưa cấu hình vào test:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceControllerTests.TestBeans.class)
class InvoiceControllerTests {
}
~~~

Hoặc import cấu hình production nhỏ, có phạm vi rõ:

~~~java
@JsonTest
@Import(MoneyJacksonConfiguration.class)
class MoneyJsonTests {
}
~~~

Không dùng component scan rộng hoặc import application class tùy tiện. Nếu phải import quá nhiều bean để slice hoạt động, có thể test đang kiểm tra nhiều hơn một layer; hãy cân nhắc `@SpringBootTest` cho trường hợp đó.

## 12. Quản lý context cache và thời gian chạy test

Spring TestContext cache ApplicationContext giữa các test có cùng cấu hình. Cache key có thể khác khi test thay đổi:

- configuration classes và initializers;
- active profiles;
- property sources;
- context customizers, mock/bean overrides;
- parent context và web resource base path.

Nếu mỗi test dùng một tổ hợp profile/property/mock khác nhau, số context được tạo tăng và suite chậm hơn.

Một số cách kiểm soát:

- dùng chung test configuration cho nhóm test có cùng nhu cầu;
- tránh khai báo property trùng lặp khác thứ tự/giá trị nếu không cần;
- chỉ dùng `@DirtiesContext` khi test thực sự làm thay đổi trạng thái context;
- dọn dữ liệu database/external resource thay vì liên tục hủy context;
- đặt mock ở đúng slice cần mock.

`@DirtiesContext` đánh dấu context không còn dùng được và yêu cầu Spring loại khỏi cache. Dùng quá nhiều sẽ làm tăng thời gian khởi động context và có thể che giấu test phụ thuộc trạng thái.

## 13. Lựa chọn phạm vi trong ứng dụng Native Image

Có ba câu hỏi khác nhau:

1. **Test có cần Spring không?** Nếu không, dùng unit test.
2. **Test cần phần nào của Spring?** Dùng slice nếu chỉ kiểm tra MVC, JSON, persistence hoặc HTTP client.
3. **Test cần chứng minh điều gì sau khi biên dịch native?** Chạy native executable và kiểm tra hành vi thật.

`@SpringBootTest` và slice annotations chủ yếu giúp tạo Spring test context trên JVM. Chúng không tự biến mọi test thành native test. Khi chạy native executable, cần xác nhận chính artifact native được build từ AOT output hoạt động đúng.

### 13.1. Những gì nên test bằng full context

Dùng `@SpringBootTest` cho các luồng cần nhiều thành phần phối hợp:

- application startup và bean graph;
- security + controller + service + repository;
- transaction boundary qua nhiều bean;
- event listener và application lifecycle;
- configuration properties cùng nhiều integration adapter;
- auto-configuration tùy biến và điều kiện bean.

Nếu test cần HTTP stack thật, chọn `RANDOM_PORT`. Nếu chỉ cần gọi MVC pipeline trong context đầy đủ, dùng `MOCK` và `@AutoConfigureMockMvc`.

### 13.2. Những gì nên test bằng slice

| Nhu cầu | Lựa chọn |
| --- | --- |
| Controller mapping, validation, exception handling | `@WebMvcTest` |
| Reactive controller | `@WebFluxTest` |
| JSON contract và custom module | `@JsonTest` |
| Entity, query và repository | `@DataJpaTest` |
| JDBC query/mapper | `@JdbcTest` |
| HTTP client mapping | `@RestClientTest` |

Slice test thường chạy nhanh hơn và làm rõ layer nào đang được xác nhận. Tuy nhiên, nó không chứng minh các layer được wiring đúng trong full application context; giữ một số integration test để kiểm tra kết nối đó.

### 13.3. Những gì phải xác nhận bằng native executable

Native testing nên tập trung vào đường chạy có nguy cơ khác JVM:

- application startup bằng executable đã build;
- controller request/response qua HTTP;
- Jackson serialization/deserialization cho DTO quan trọng;
- reflection, proxy, service loading và resource lookup;
- driver/database/client library có reachability metadata;
- JNI và shared library nếu ứng dụng sử dụng;
- cấu hình runtime, file mount, permission và container environment.

Một mô hình phổ biến là dùng test runner JVM để khởi chạy native process/container, gửi HTTP request hoặc gọi protocol thật, rồi kiểm tra response/log/exit code. Test runner không cần được nhúng vào native image của ứng dụng.

Nếu Native Build Tools của dự án có task native test, kiểm tra chính xác task đó chạy test code trong môi trường nào và test target là gì. Đừng mặc định `nativeTest` tương đương với chạy toàn bộ `@SpringBootTest`/slice context bên trong native executable; cách tích hợp phụ thuộc plugin và cấu hình dự án.

## 14. Một ma trận test thực tế

Ví dụ cho dịch vụ billing:

| Hành vi | Unit | Slice | Full context | Native executable |
| --- | --- | --- | --- | --- |
| Tính tổng hóa đơn | Có | Không cần | Không cần | Chỉ nếu có rủi ro đặc thù |
| JSON `Money` | Có thể | `@JsonTest` | Không bắt buộc | Test qua endpoint/serialization path |
| Validation của controller | Không đủ | `@WebMvcTest` | Có thể | Smoke/HTTP test |
| Query repository | Không đủ | `@DataJpaTest` | Có thể | Test khi driver/metadata có rủi ro |
| Security + service + database | Không đủ | Không đủ | `@SpringBootTest` | Native HTTP test cho luồng quan trọng |
| HTTP client mapping | Có thể | `@RestClientTest` | Có thể | Native test nếu client dùng reflection/resource |
| Startup và bean conditions | Không | Không đủ | `@SpringBootTest` | Khởi chạy executable native |
| JNI codec | Adapter fake | Không phù hợp | Có thể wiring | Native test trên OS/CPU đích |

Không cần nhân đôi mọi test JVM thành native test. Chọn các đường có rủi ro closed-world, reflection, resource, JNI, service loading hoặc khác biệt runtime để chạy native.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@SpringBootTest` không tìm thấy application configuration | Test nằm ngoài package scan hoặc có nhiều cấu hình | Chỉ định `classes = ...` |
| `@WebMvcTest` thiếu service bean | Slice không tạo service layer | Dùng `@MockitoBean`/`@MockBean` hoặc import bean cần thiết |
| Slice trả 401/403 ngoài dự kiến | Security filter/chain vẫn được áp dụng | Cấu hình user/authority hoặc import security test config phù hợp |
| `@DataJpaTest` chạy embedded DB thay vì DB thật | Auto-config chọn embedded database | Dùng Testcontainers hoặc cấu hình datasource test |
| Test dùng RANDOM_PORT không rollback database | Request chạy ở server thread riêng | Dọn dữ liệu rõ ràng hoặc dùng database/schema riêng |
| Suite tạo quá nhiều ApplicationContext | Profiles/properties/mocks làm cache key khác nhau | Chuẩn hóa context configuration |
| JVM tests pass nhưng native endpoint lỗi | Thiếu reflection/resource/proxy/JNI metadata | Chạy native path, đọc stack trace và bổ sung hints chính xác |
| Native test không thấy service provider | Service descriptor hoặc provider metadata thiếu | Kiểm tra dependency JAR và native reachability metadata |
| Test slice pass nhưng production context lỗi | Slice không load toàn bộ application wiring | Bổ sung một số `@SpringBootTest` integration tests |

Khi báo lỗi, ghi rõ annotation, web environment, active profile, Spring Boot/JDK/GraalVM version và stack trace đã loại bỏ secret.

## 16. Quy trình chọn test cho một tính năng mới

Giả sử thêm endpoint tạo hóa đơn với validation, `Money` JSON mapping và repository:

**Bước 1 — kiểm tra logic độc lập**

Test `InvoiceCalculator` và quy tắc miền bằng unit test, không khởi động Spring.

**Bước 2 — kiểm tra JSON**

Dùng `@JsonTest` để xác nhận `MoneySerializer` và `MoneyDeserializer`, bao gồm input thiếu field/sai kiểu.

**Bước 3 — kiểm tra controller**

Dùng `@WebMvcTest(InvoiceController.class)` để xác nhận route, validation, status và response JSON. Mock `InvoiceService`.

**Bước 4 — kiểm tra persistence**

Dùng `@DataJpaTest` để xác nhận mapping và query repository. Dùng database tương thích nếu query phụ thuộc hành vi riêng của vendor.

**Bước 5 — kiểm tra wiring xuyên suốt**

Dùng một số `@SpringBootTest` để xác nhận controller, service, repository, security và configuration phối hợp. Chọn `MOCK` hay `RANDOM_PORT` theo yêu cầu HTTP.

**Bước 6 — kiểm tra native**

Build native executable, khởi chạy nó trong môi trường target/container, gửi request tạo hóa đơn và xác nhận response, database write/read, JSON mapping và log. Nếu dùng JNI hoặc provider, gọi trực tiếp đường tích hợp đó.

## 17. Checklist trước khi phát hành

- [ ] Unit tests không khởi động Spring khi không cần container.
- [ ] Mỗi test slice chỉ tải layer cần xác nhận.
- [ ] `@SpringBootTest` được dành cho các hành vi cần full context.
- [ ] Web environment (`MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`) phù hợp với mục tiêu.
- [ ] Test HTTP thật xử lý dữ liệu/transaction cleanup rõ ràng.
- [ ] Bean phụ thuộc được mock hoặc import có chủ đích.
- [ ] Profiles và properties của test không vô tình thay đổi bean graph AOT.
- [ ] Context cache không bị phá bởi `@DirtiesContext` dùng quá rộng.
- [ ] Có integration tests kiểm tra wiring mà slice không bao phủ.
- [ ] Native tests khởi chạy đúng executable được build từ AOT output.
- [ ] Native test bao phủ reflection, JSON, resource, provider, JNI hoặc driver có rủi ro.
- [ ] Test chạy trên OS/CPU/container tương thích với môi trường triển khai.
- [ ] Đã ghi lại version Spring Boot, JDK, GraalVM và Native Build Tools.

**Ghi nhớ:** dùng unit test cho logic thuần, test slice cho một layer Spring, `@SpringBootTest` cho tương tác cần full context và native executable tests cho hành vi sau khi biên dịch. Test slice và full-context test trên JVM cung cấp bằng chứng về wiring và framework behavior; chúng không thay thế kiểm thử executable native trong môi trường mục tiêu.

## Tài liệu tham khảo

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test slices, test utilities và cấu hình kiểm thử.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): cách bootstrap context, web environment và test properties.
- [Spring Boot Reference — Testing Auto-configurations](https://docs.spring.io/spring-boot/reference/testing/test-auto-configuration.html): test slices và auto-configuration.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context caching, test execution và Spring test support.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): tích hợp Maven/Gradle và native test execution.
