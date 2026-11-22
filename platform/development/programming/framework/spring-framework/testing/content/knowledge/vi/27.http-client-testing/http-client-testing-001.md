# Ranh giới cần kiểm chứng của RestClient, RestTemplate hoặc WebClient

**Ngữ cảnh:** Spring Framework Testing → Kiểm thử HTTP client.

Một ứng dụng Spring thường gọi dịch vụ HTTP bên ngoài để lấy dữ liệu, gửi lệnh hoặc phối hợp với hệ thống khác. Những lời gọi này tạo ra một ranh giới giữa ứng dụng và hệ thống từ xa. Kiểm thử ranh giới đó cần xác nhận ứng dụng tạo request đúng, hiểu response đúng và xử lý các tình huống lỗi theo hợp đồng đã thống nhất.

Spring có ba HTTP client thường gặp:

- **RestTemplate:** API HTTP đồng bộ kiểu template, được dùng rộng rãi trong các ứng dụng Spring hiện hữu.
- **RestClient:** API HTTP đồng bộ fluent, được giới thiệu trong Spring Framework 6.1.
- **WebClient:** API HTTP reactive, hỗ trợ non-blocking I/O và stream dữ liệu.

Cả ba đều có thể gọi HTTP, nhưng cách thực thi, cấu hình và công cụ kiểm thử khác nhau. Một bài kiểm thử tốt phải xác định rõ ranh giới cần bảo vệ: adapter của ứng dụng có tạo đúng HTTP request và xử lý đúng response hay không; không cần kiểm thử lại toàn bộ hệ thống bên thứ ba mà ứng dụng đang gọi.

## 1. Ranh giới HTTP client nằm ở đâu?

Giả sử một ứng dụng bán hàng gọi dịch vụ Catalog để kiểm tra tồn kho. Controller nhận request từ người dùng, service điều phối nghiệp vụ và một adapter dùng HTTP client để gọi Catalog.

~~~text
HTTP request từ người dùng
        |
        v
OrderController
        |
        v
OrderService
        |
        v
CatalogGateway (adapter của ứng dụng)
        |
        v
RestClient / RestTemplate / WebClient
        |
        v
HTTP transport
        |
        v
Catalog service bên ngoài
~~~

Ranh giới cần kiểm chứng của HTTP client nằm tại lời gọi từ adapter sang HTTP transport. Bài test cần xác nhận adapter chuyển yêu cầu nghiệp vụ thành request HTTP đúng và chuyển response HTTP thành kết quả hoặc lỗi mà ứng dụng hiểu được.

Ví dụ, khi OrderService yêu cầu thông tin tồn kho của SKU, CatalogGateway cần:

1. Gọi đúng host và path.
2. Dùng đúng HTTP method.
3. Mã hóa path variable và query parameter đúng.
4. Gửi header cần thiết như Accept, Content-Type, Authorization hoặc correlation id.
5. Serialize request body đúng định dạng.
6. Đọc response thành DTO đúng kiểu.
7. Xử lý status 4xx, 5xx, body rỗng hoặc response không hợp lệ.
8. Áp dụng timeout, retry hoặc cancellation theo chính sách của ứng dụng.

Một bài test adapter không cần xác nhận thuật toán tồn kho nội bộ của Catalog. Đó là trách nhiệm của hệ thống Catalog. Test của ứng dụng chỉ cần xác nhận cách ứng dụng tương tác với hợp đồng HTTP mà Catalog công bố.

## 2. Phân biệt kiểm thử HTTP client với kiểm thử HTTP server

Cả hai phía đều dùng HTTP nhưng kiểm tra những trách nhiệm khác nhau.

| Loại kiểm thử | Thành phần đang kiểm tra | Câu hỏi chính |
|---|---|---|
| Controller test | Endpoint nhận request của ứng dụng | Ứng dụng phản hồi đúng khi client gọi vào không? |
| HTTP client adapter test | RestClient, RestTemplate hoặc WebClient được ứng dụng sử dụng | Ứng dụng gửi request đúng và xử lý response từ dịch vụ từ xa đúng không? |
| Application integration test | Nhiều thành phần của ứng dụng cùng hoạt động | Cấu hình, dependency injection và luồng nghiệp vụ có kết nối đúng không? |
| End-to-end test với dịch vụ thật | Tích hợp qua mạng với môi trường thật hoặc sandbox | Các hệ thống có thực sự tương tác được trong môi trường triển khai không? |

**MockMvc** và **WebTestClient** thường được dùng để kiểm thử server-side endpoint. Chúng gửi request đến ứng dụng Spring đang được test. Chúng không tự động kiểm thử outbound HTTP call mà controller hoặc service thực hiện.

Ví dụ, nếu OrderController gọi CatalogGateway, một MockMvc test có thể mock CatalogGateway để tập trung vào response của controller. Một CatalogGateway test riêng dùng mock HTTP server để kiểm tra request thực tế mà RestClient hoặc WebClient tạo ra.

Hai test có ranh giới khác nhau và bổ sung cho nhau.

## 3. Chọn công cụ theo loại HTTP client

Công cụ kiểm thử nên tương ứng với transport và abstraction mà ứng dụng sử dụng.

| HTTP client | Kiểu thực thi | Công cụ thường dùng để giả lập dịch vụ từ xa |
|---|---|---|
| RestTemplate | Đồng bộ, blocking | MockRestServiceServer |
| RestClient | Đồng bộ, blocking | MockRestServiceServer |
| WebClient | Reactive, non-blocking | MockWebServer hoặc WireMock |
| WebClient với logic rất hẹp | Reactive | Stub ExchangeFunction có kiểm soát |

**MockRestServiceServer** thuộc Spring Test và có thể gắn với RestTemplate hoặc RestClient.Builder để xác nhận request và cung cấp response giả. Nó không phải mock server mạng thật; nó chặn request ở tầng request factory của Spring.

**MockWebServer** và **WireMock** mở một HTTP server cục bộ trên loopback, cho client gửi request qua HTTP thật. Chúng phù hợp với WebClient vì có thể kiểm tra request đã đi qua WebClient connector, HTTP codec và transport.

Có thể dùng ExchangeFunction giả để kiểm tra một phần logic WebClient như filter hoặc cách xây dựng request. Tuy nhiên, cách này bỏ qua HTTP connector thực tế, vì vậy không chứng minh được cấu hình network client hoặc việc truyền nhận qua socket hoạt động đúng.

Không nên dùng MockRestServiceServer để kiểm thử WebClient. Hai công cụ nằm ở các tầng client khác nhau.

## 4. Thiết kế adapter để có ranh giới kiểm thử rõ ràng

Không nên để logic nghiệp vụ ở mọi nơi tự tạo URL, tự đặt header và tự parse response. Một adapter tập trung giúp xác định hợp đồng HTTP tại một vị trí.

Ví dụ:

~~~java
record ProductAvailability(String sku, boolean available) {}

interface CatalogGateway {
    ProductAvailability findAvailability(String sku);
}
~~~

OrderService chỉ phụ thuộc vào giao diện nghiệp vụ:

~~~java
class OrderService {

    private final CatalogGateway catalogGateway;

    OrderService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    void placeOrder(String sku) {
        ProductAvailability availability =
                catalogGateway.findAvailability(sku);

        if (!availability.available()) {
            throw new OutOfStockException(sku);
        }

        // Tiếp tục xử lý đơn hàng.
    }
}
~~~

Adapter HTTP chịu trách nhiệm gọi dịch vụ:

~~~java
class HttpCatalogGateway implements CatalogGateway {

    private final RestClient restClient;

    HttpCatalogGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public ProductAvailability findAvailability(String sku) {
        return restClient.get()
                .uri("/products/{sku}/availability", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ProductAvailability.class);
    }
}
~~~

Thiết kế này tạo ra hai ranh giới dễ kiểm tra:

- Unit test OrderService mock CatalogGateway để kiểm tra quyết định nghiệp vụ.
- HTTP adapter test dùng mock server để kiểm tra giao tiếp thật ở tầng HTTP client.

Nếu service tự xây URL, tự serialize JSON và tự xử lý status ở nhiều nơi, test sẽ khó xác định chính xác thành phần nào chịu trách nhiệm cho hợp đồng HTTP.

## 5. Kiểm thử RestClient bằng MockRestServiceServer

### 5.1. RestClient hoạt động như thế nào?

RestClient là HTTP client đồng bộ có API fluent. Request được xây dựng qua các bước như:

- get(), post(), put(), delete() hoặc method(...).
- uri(...) để chọn địa chỉ.
- header(...), contentType(...) và accept(...).
- body(...) để gửi dữ liệu.
- retrieve() để xử lý response theo kiểu đọc body hoặc ánh xạ lỗi.
- body(...), toEntity(...) hoặc các thao tác tương ứng để lấy kết quả.

RestClient được giới thiệu trong Spring Framework 6.1. Nó dùng hạ tầng request factory và message converter của Spring, đồng thời có thể cấu hình base URL, interceptor, default header và status handler.

### 5.2. Gắn mock server vào RestClient.Builder

Ví dụ cấu hình:

~~~java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://catalog.example.test");

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();

CatalogGateway gateway = new HttpCatalogGateway(restClient);
~~~

MockRestServiceServer được gắn vào builder trước khi tạo RestClient. Request mà client gửi sẽ được chuyển tới mock server để đối chiếu expectation và trả response đã cấu hình.

Trong cấu hình Spring, có thể tạo builder từ bean được quản lý và gắn mock server vào builder đó trong test. Cần bảo đảm instance RestClient được dùng bởi adapter chính là instance được tạo từ builder đã bind.

### 5.3. Xác nhận request GET

Giả sử adapter gọi:

~~~java
ProductAvailability result =
        gateway.findAvailability("SKU-42");
~~~

Test:

~~~java
@Test
void sendsExpectedGetRequestAndReadsJsonResponse() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/SKU-42/availability"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    ProductAvailability result =
            gateway.findAvailability("SKU-42");

    assertThat(result)
            .isEqualTo(new ProductAvailability("SKU-42", true));

    mockServer.verify();
}
~~~

Test xác nhận cả hai chiều của hợp đồng:

- Request được gửi đến đúng URL, dùng GET và khai báo Accept JSON.
- Response JSON được đọc thành ProductAvailability với dữ liệu mong đợi.

Nếu adapter đổi path, method hoặc header ngoài ý muốn, expectation sẽ thất bại. Nếu response không được deserialize đúng, assertion trên DTO sẽ thất bại.

### 5.4. Xác nhận path variable và query parameter

Giả sử API tìm kiếm sản phẩm bằng mã và trạng thái:

~~~java
restClient.get()
        .uri(builder -> builder
                .path("/products/{sku}")
                .queryParam("includeInactive", false)
                .build(sku))
        .retrieve()
        .body(ProductAvailability.class);
~~~

Test có thể kiểm tra URI cuối cùng:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/products/SKU-42"
                        + "?includeInactive=false"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-42","available":true}
                """,
                MediaType.APPLICATION_JSON));
~~~

Với dữ liệu có dấu cách, dấu gạch chéo hoặc ký tự Unicode, cần xác nhận cách encode URI phù hợp với contract. Dùng URI template và builder thay vì nối chuỗi thủ công giúp tránh lỗi encoding và injection vào path/query.

### 5.5. Kiểm tra POST request body

Ví dụ adapter gửi lệnh tạo reservation:

~~~java
record ReservationRequest(String sku, int quantity) {}
record ReservationResponse(String reservationId) {}
~~~

Adapter:

~~~java
ReservationResponse reserve(String sku, int quantity) {
    return restClient.post()
            .uri("/reservations")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(new ReservationRequest(sku, quantity))
            .retrieve()
            .body(ReservationResponse.class);
}
~~~

Test:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "SKU-42",
                  "quantity": 2
                }
                """))
        .andRespond(withSuccess("""
                {
                  "reservationId": "RSV-100"
                }
                """, MediaType.APPLICATION_JSON));

ReservationResponse response = gateway.reserve("SKU-42", 2);

assertThat(response.reservationId()).isEqualTo("RSV-100");
mockServer.verify();
~~~

Nên xác nhận những trường body có ý nghĩa với hợp đồng. Không nên so sánh JSON bằng chuỗi nguyên văn nếu thứ tự thuộc tính hoặc khoảng trắng không phải điều kiện của API.

### 5.6. Kiểm tra status lỗi và ánh xạ exception

RestClient với retrieve mặc định chuyển response 4xx/5xx thành exception phù hợp, thường là các lớp con của RestClientResponseException. Adapter có thể giữ exception đó hoặc ánh xạ sang exception nghiệp vụ của ứng dụng.

Ví dụ dùng onStatus:

~~~java
ProductAvailability findAvailability(String sku) {
    return restClient.get()
            .uri("/products/{sku}/availability", sku)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    (request, response) -> {
                        if (response.getStatusCode()
                                .equals(HttpStatus.NOT_FOUND)) {
                            throw new ProductNotFoundException(sku);
                        }
                    })
            .body(ProductAvailability.class);
}
~~~

Test cho tình huống không tìm thấy:

~~~java
@Test
void mapsCatalogNotFoundToDomainException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/MISSING/availability"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {"code":"PRODUCT_NOT_FOUND"}
                            """));

    assertThatThrownBy(() ->
            gateway.findAvailability("MISSING"))
            .isInstanceOf(ProductNotFoundException.class);

    mockServer.verify();
}
~~~

Test cần xác nhận ứng dụng đưa ra loại lỗi mà service phía trên mong đợi. Không nhất thiết phải kiểm tra mọi chi tiết exception của Spring nếu chúng không phải một phần của contract nội bộ.

## 6. Kiểm thử RestTemplate bằng MockRestServiceServer

### 6.1. RestTemplate và trách nhiệm cần kiểm tra

RestTemplate là API đồng bộ kiểu template, được sử dụng rộng rãi trong ứng dụng Spring trước khi RestClient xuất hiện. Nó vẫn có thể được dùng trong các hệ thống hiện hữu.

Các phương thức phổ biến:

- getForObject(...) và getForEntity(...).
- postForObject(...) và postForEntity(...).
- exchange(...) khi cần kiểm soát method, header và kiểu response.
- execute(...) cho các tình huống callback hoặc xử lý body tùy chỉnh.

Các điểm cần kiểm tra giống RestClient: URI, method, header, body serialization, response decoding và error handling.

### 6.2. Gắn MockRestServiceServer

~~~java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

Ví dụ adapter:

~~~java
class LegacyCatalogGateway {

    private final RestTemplate restTemplate;
    private final String baseUrl;

    LegacyCatalogGateway(RestTemplate restTemplate, String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl;
    }

    ProductAvailability findAvailability(String sku) {
        return restTemplate.getForObject(
                baseUrl + "/products/{sku}/availability",
                ProductAvailability.class,
                sku
        );
    }
}
~~~

Test:

~~~java
@Test
void restTemplateReadsCatalogAvailability() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/SKU-42/availability"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    ProductAvailability result =
            gateway.findAvailability("SKU-42");

    assertThat(result.available()).isTrue();
    mockServer.verify();
}
~~~

Với code mới, URI nên được xây dựng bằng UriBuilder hoặc cấu hình base URL tập trung thay vì nối chuỗi. Ví dụ nối chuỗi trên chỉ rút gọn cho dễ đọc; cần tránh lỗi slash, query encoding và cấu hình host khác nhau giữa môi trường.

### 6.3. Kiểm tra header và body với exchange

Khi cần xác nhận nhiều thuộc tính request, dùng HttpEntity:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
headers.setBearerAuth("test-token");

HttpEntity<ReservationRequest> request =
        new HttpEntity<>(
                new ReservationRequest("SKU-42", 2),
                headers
        );

ResponseEntity<ReservationResponse> response =
        restTemplate.exchange(
                baseUrl + "/reservations",
                HttpMethod.POST,
                request,
                ReservationResponse.class
        );
~~~

Mock server có thể xác nhận header Authorization, Content-Type, Accept và body JSON. Trong test, dùng token giả. Không đưa token thật vào source code hoặc log.

### 6.4. Kiểm tra error handler

RestTemplate mặc định dùng ResponseErrorHandler để xử lý status lỗi. Có thể dùng handler mặc định và xác nhận exception, hoặc cung cấp handler tùy chỉnh nếu ứng dụng ánh xạ lỗi theo contract riêng.

Ví dụ với hành vi mặc định:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/products/MISSING"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() ->
        restTemplate.getForObject(
                "https://catalog.example.test/products/MISSING",
                ProductAvailability.class))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

mockServer.verify();
~~~

Nếu adapter có custom ResponseErrorHandler, test cần xác nhận status và error body được chuyển thành lỗi nghiệp vụ đúng. Cũng cần xác nhận response error body được đọc và đóng theo cơ chế của client; không để custom handler nuốt lỗi hoặc làm mất thông tin cần cho chẩn đoán.

## 7. Kiểm thử WebClient bằng MockWebServer

### 7.1. Vì sao WebClient cần công cụ khác?

WebClient dùng API reactive và một ClientHttpConnector để thực hiện HTTP. Trong nhiều ứng dụng, connector là Reactor Netty; cũng có thể dùng connector khác.

MockRestServiceServer không gắn vào WebClient. Để kiểm tra request qua WebClient, có thể chạy một mock HTTP server cục bộ như **MockWebServer** của OkHttp hoặc **WireMock**.

MockWebServer mở một cổng HTTP cục bộ, nhận request thật từ WebClient và cho phép test xếp hàng response giả. Nó hỗ trợ kiểm tra method, path, headers và body đã được gửi qua transport.

### 7.2. Dependency kiểm thử

Ví dụ Gradle khi dự án đã quản lý phiên bản bằng BOM:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("com.squareup.okhttp3:mockwebserver")
}
~~~

WebClient thuộc spring-webflux; MockWebServer là thư viện độc lập; StepVerifier thuộc reactor-test. Phiên bản MockWebServer nên được quản lý đồng bộ với phiên bản OkHttp mà dự án sử dụng nếu có.

Nếu dùng WireMock thay MockWebServer, chỉ cần chọn một mock server phù hợp với nhu cầu. Không nhất thiết đưa cả hai thư viện vào cùng một bộ test.

### 7.3. Khởi tạo MockWebServer

Ví dụ JUnit 5:

~~~java
class WebClientCatalogGatewayTest {

    private MockWebServer mockServer;
    private WebClient webClient;
    private WebClientCatalogGateway gateway;

    @BeforeEach
    void setUp() throws IOException {
        mockServer = new MockWebServer();
        mockServer.start();

        webClient = WebClient.builder()
                .baseUrl(mockServer.url("/").toString())
                .build();

        gateway = new WebClientCatalogGateway(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        mockServer.shutdown();
    }
}
~~~

Server được tạo riêng cho test và tắt sau khi test hoàn tất. Không dùng host hoặc port cố định vì CI có thể chạy nhiều test đồng thời.

### 7.4. Xác nhận request GET và response DTO

Adapter:

~~~java
class WebClientCatalogGateway {

    private final WebClient webClient;

    WebClientCatalogGateway(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<ProductAvailability> findAvailability(String sku) {
        return webClient.get()
                .uri("/products/{sku}/availability", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductAvailability.class);
    }
}
~~~

Test:

~~~java
@Test
void sendsGetRequestAndDecodesResponse() throws Exception {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """));

    StepVerifier.create(gateway.findAvailability("SKU-42"))
            .assertNext(result -> {
                assertThat(result.sku()).isEqualTo("SKU-42");
                assertThat(result.available()).isTrue();
            })
            .verifyComplete();

    RecordedRequest request =
            mockServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request).isNotNull();
    assertThat(request.getMethod()).isEqualTo("GET");
    assertThat(request.getPath())
            .isEqualTo("/products/SKU-42/availability");
    assertThat(request.getHeader(HttpHeaders.ACCEPT))
            .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
}
~~~

Test xác nhận cả request trên HTTP transport lẫn response được WebClient decode thành DTO. StepVerifier subscribe vào Mono và xác nhận nó phát đúng một phần tử rồi hoàn tất.

### 7.5. Xác nhận POST request body

~~~java
@Test
void sendsReservationAsJson() throws Exception {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(201)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {"reservationId":"RSV-100"}
                    """));

    StepVerifier.create(gateway.reserve("SKU-42", 2))
            .assertNext(response ->
                    assertThat(response.reservationId())
                            .isEqualTo("RSV-100"))
            .verifyComplete();

    RecordedRequest request =
            mockServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request.getMethod()).isEqualTo("POST");
    assertThat(request.getPath()).isEqualTo("/reservations");
    assertThat(request.getHeader(HttpHeaders.CONTENT_TYPE))
            .contains(MediaType.APPLICATION_JSON_VALUE);
    String body = request.getBody().readUtf8();
    assertThat(body).contains("\"sku\":\"SKU-42\"");
    assertThat(body).contains("\"quantity\":2");
}
~~~

Cũng có thể parse body thành JSON để xác nhận cấu trúc và giá trị mà không phụ thuộc thứ tự thuộc tính. Điều quan trọng là kiểm tra request mà WebClient thực sự gửi, không chỉ kiểm tra object đầu vào trước khi serialize.

### 7.6. Kiểm tra lỗi HTTP

WebClient retrieve mặc định chuyển status 4xx/5xx thành WebClientResponseException. Có thể ánh xạ bằng onStatus:

~~~java
Mono<ProductAvailability> findAvailability(String sku) {
    return webClient.get()
            .uri("/products/{sku}/availability", sku)
            .retrieve()
            .onStatus(HttpStatusCode::is4xxClientError,
                    response -> response.bodyToMono(String.class)
                            .defaultIfEmpty("")
                            .map(body ->
                                    new ProductNotFoundException(sku)))
            .bodyToMono(ProductAvailability.class);
}
~~~

Test:

~~~java
@Test
void mapsNotFoundResponseToDomainException() {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(404)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {"code":"PRODUCT_NOT_FOUND"}
                    """));

    StepVerifier.create(gateway.findAvailability("MISSING"))
            .expectError(ProductNotFoundException.class)
            .verify(Duration.ofSeconds(3));
}
~~~

Với WebClient, assertion lỗi cần subscribe vào publisher. Nếu chỉ tạo Mono mà không subscribe hoặc verify, HTTP request có thể chưa được thực thi và test không thực sự kiểm tra gì.

### 7.7. Kiểm tra request đã được gửi và không bị lặp

MockWebServer giữ các request nhận được dưới dạng RecordedRequest. Có thể dùng nó để xác nhận retry hoặc số lần gọi:

~~~java
RecordedRequest first = mockServer.takeRequest();
RecordedRequest second = mockServer.takeRequest();

assertThat(first.getPath()).isEqualTo("/products/SKU-42");
assertThat(second.getPath()).isEqualTo("/products/SKU-42");
~~~

Chỉ kỳ vọng nhiều request khi ứng dụng có chính sách retry hoặc thực hiện nhiều lần gọi theo thiết kế. Nếu không, một request ngoài dự kiến có thể là dấu hiệu subscribe lặp, retry không chủ ý hoặc code gửi request hai lần.

## 8. Khi nào nên dùng ExchangeFunction giả?

WebClient có thể nhận một **ExchangeFunction** tùy chỉnh:

~~~java
ExchangeFunction exchangeFunction = request ->
        Mono.just(ClientResponse.create(HttpStatus.OK)
                .header(
                        HttpHeaders.CONTENT_TYPE,
                        MediaType.APPLICATION_JSON_VALUE)
                .body("""
                        {
                          "sku": "SKU-42",
                          "available": true
                        }
                        """)
                .build());

WebClient webClient = WebClient.builder()
        .exchangeFunction(exchangeFunction)
        .build();
~~~

Cách này tạo response ngay trong test mà không mở cổng HTTP. Nó hữu ích khi cần kiểm tra logic rất hẹp, ví dụ:

- Filter thêm header xác thực.
- Logic chọn URI dựa trên input.
- Adapter ánh xạ response thành domain object.
- Cách xử lý một status cụ thể ở tầng ExchangeFunction.

Tuy nhiên, ExchangeFunction giả bỏ qua connector thực tế. Test không xác nhận DNS, socket, TLS, connection pool, network timeout hoặc cách connector truyền body. Tùy cách tạo ClientResponse, nó cũng không đại diện đầy đủ cho hành vi của HTTP server và codec trên wire.

Nếu mục tiêu là kiểm tra HTTP contract của WebClient, ưu tiên MockWebServer hoặc WireMock. Dùng ExchangeFunction giả cho unit test tập trung vào logic filter hoặc adapter khi phần transport đã được kiểm chứng ở một test khác.

## 9. Xác định các điều kiện cần kiểm tra ở ranh giới

Không phải endpoint nào cũng cần kiểm tra mọi thuộc tính. Chọn các điều kiện có ý nghĩa với hợp đồng dịch vụ.

### 9.1. URI và HTTP method

Kiểm tra:

- Scheme và host có đúng theo cấu hình môi trường không?
- Base URL có bị ghép path sai hoặc thiếu slash không?
- HTTP method có đúng không?
- Path variable có được encode đúng không?
- Query parameter có tên, giá trị và encoding đúng không?
- Request có gửi nhầm sang endpoint khác không?

Với base URL thay đổi theo môi trường, test có thể dùng host giả nhưng vẫn xác nhận path và query. Không hard-code host production vào test.

### 9.2. Request headers

Các header thường quan trọng:

- Accept và Content-Type.
- Authorization.
- X-Request-Id hoặc trace/correlation id.
- Header phiên bản API.
- Locale hoặc tenant id.
- Idempotency-Key cho thao tác có thể retry.

Chỉ xác nhận header thuộc contract. Không cần khóa chặt các header transport tự sinh như User-Agent hoặc Connection nếu ứng dụng không cam kết chúng.

### 9.3. Request body

Kiểm tra:

- Field bắt buộc và kiểu dữ liệu.
- Tên property JSON.
- Null, field bị bỏ qua và default value.
- Ngày giờ, timezone và định dạng số.
- Generic collection hoặc nested object.
- Nội dung nhạy cảm có bị gửi nhầm không.

Nên dùng dữ liệu đại diện cho các trường hợp thực tế, bao gồm Unicode, chuỗi đặc biệt và giá trị biên khi chúng ảnh hưởng đến serialization.

### 9.4. Response body

Kiểm tra:

- DTO được deserialize đúng.
- Field bị thiếu hoặc null được xử lý đúng.
- Enum không nhận diện được.
- Generic type và collection.
- Response rỗng hoặc 204 No Content.
- Content-Type không đúng hoặc body lỗi định dạng.
- Error body của dịch vụ từ xa.

Không nên chỉ xác nhận body không null. Kiểm tra các trường mà logic nghiệp vụ thực sự phụ thuộc.

### 9.5. HTTP status và lỗi nghiệp vụ

Xác định rõ cách adapter phản ứng với:

- 2xx: thành công.
- 3xx: redirect có được theo hoặc từ chối theo chính sách client.
- 400/401/403/404/409/422: lỗi request hoặc nghiệp vụ.
- 429: giới hạn tốc độ.
- 5xx: lỗi dịch vụ từ xa.
- Status không mong đợi hoặc body không hợp lệ.

Một adapter có thể ánh xạ các status khác nhau thành exception domain riêng. Test cần bảo đảm tầng nghiệp vụ nhận được loại lỗi ổn định thay vì phụ thuộc quá sâu vào exception cụ thể của thư viện HTTP.

### 9.6. Timeout, retry và cancellation

Timeout và retry là một phần của hợp đồng vận hành khi chúng ảnh hưởng đến kết quả nghiệp vụ.

Cần xác nhận:

- Request không chờ vô hạn khi dịch vụ không phản hồi.
- Retry chỉ diễn ra với status hoặc lỗi được cho phép.
- Số lần retry bị giới hạn.
- Backoff không làm test kéo dài quá mức.
- Request có tính idempotent nếu được retry.
- Khi subscriber hủy Mono/Flux, client ngừng công việc phù hợp và giải phóng tài nguyên.

Không kiểm tra thời gian bằng một khoảng quá chặt khiến test chập chờn trên CI. Dùng timeout đủ rộng và mock server có khả năng điều khiển response delay khi cần kiểm tra hành vi timeout.

## 10. Ranh giới của các loại test trong một ứng dụng

Có thể chia test HTTP client thành nhiều tầng để không lặp lại cùng một trách nhiệm.

~~~text
                 Unit test
        Domain service + fake gateway
                  |
                  v
           HTTP adapter test
     MockRestServiceServer / MockWebServer
                  |
                  v
       Application integration test
    Spring context + adapter + cấu hình thật
                  |
                  v
       External contract / smoke test
       Sandbox hoặc dịch vụ tích hợp thật
~~~

### 10.1. Unit test service

Mock interface như CatalogGateway. Xác nhận service gọi gateway đúng lúc, xử lý kết quả và ném lỗi nghiệp vụ phù hợp.

Unit test không cần mở HTTP server và không nên kiểm tra URL, header hay JSON serialization. Những chi tiết đó thuộc adapter test.

### 10.2. HTTP adapter test

Dùng MockRestServiceServer hoặc MockWebServer. Kiểm tra request/response contract và cách adapter ánh xạ dữ liệu.

Đây thường là lớp test quan trọng nhất cho outbound client vì nó phát hiện lỗi URI, method, header, body, codec và status handling mà unit test mock gateway không thể thấy.

### 10.3. Application integration test

Khởi tạo Spring context với cấu hình thật hoặc cấu hình gần production để xác nhận:

- Adapter được inject đúng.
- Base URL được lấy từ property đúng.
- Interceptor/filter được đăng ký.
- Timeout và codec được cấu hình.
- Authentication hoặc token provider được nối vào client.
- Service dùng đúng adapter.

Có thể dùng mock HTTP server làm đích đến để không phụ thuộc dịch vụ bên ngoài. Điều này kiểm tra cấu hình Spring và adapter trong cùng một luồng mà vẫn có kết quả xác định.

### 10.4. Contract test và smoke test với dịch vụ thật

Khi có OpenAPI, schema hoặc contract được chia sẻ, có thể xác nhận adapter tuân theo contract đó. Nếu cần kiểm tra khả năng kết nối thực tế, có thể chạy một số smoke test với sandbox của nhà cung cấp.

Không nên để toàn bộ bộ test CI phụ thuộc Internet hoặc một dịch vụ bên ngoài có dữ liệu thay đổi. Test với dịch vụ thật có thể thất bại do mạng, quota, bảo trì hoặc dữ liệu môi trường; nên giới hạn phạm vi và tách khỏi test nhanh thường chạy.

## 11. Những giới hạn mà mock HTTP server không chứng minh

Mock server tạo một ranh giới có thể kiểm soát, nhưng không mô phỏng mọi đặc tính của môi trường mạng.

| Đặc tính | MockRestServiceServer | MockWebServer/WireMock |
|---|---|---|
| URI, method, header, body | Có | Có |
| Response status và body | Có | Có |
| Spring message conversion | Có thể kiểm tra qua client thực | Có thể kiểm tra qua client thực |
| HTTP connector qua socket | Không | Có |
| DNS và routing mạng thực | Không | Không đại diện môi trường production |
| TLS certificate và handshake | Không | Có thể cấu hình TLS cục bộ, nhưng không xác nhận PKI production |
| Proxy production | Không | Chỉ khi cấu hình và dựng môi trường tương ứng |
| Connection pool dưới tải thật | Không | Không đại diện đầy đủ tải production |
| Latency và packet loss thực | Không | Có thể giả lập một phần delay, không mô phỏng mạng thật đầy đủ |

Với RestClient và RestTemplate, MockRestServiceServer thay thế request factory ở tầng client. Nó rất phù hợp để xác nhận HTTP contract nhưng không kiểm tra connector hoặc network stack thật.

Với WebClient, MockWebServer cho request đi qua connector và socket cục bộ. Nó kiểm tra được nhiều thứ hơn về HTTP transport, nhưng vẫn không chứng minh cấu hình DNS, proxy, firewall, TLS trust store hoặc độ ổn định của dịch vụ thật trên môi trường triển khai.

Nếu các đặc tính này có rủi ro cao, cần một nhóm integration/smoke test riêng với môi trường được kiểm soát.

## 12. Lựa chọn theo nhu cầu thực tế

| Nhu cầu | Lựa chọn |
|---|---|
| Ứng dụng hiện hữu dùng RestTemplate | MockRestServiceServer |
| Ứng dụng mới dùng RestClient | MockRestServiceServer bind vào RestClient.Builder |
| Ứng dụng dùng WebClient và cần xác nhận HTTP thật qua local socket | MockWebServer hoặc WireMock |
| Chỉ kiểm tra logic filter của WebClient | ExchangeFunction giả |
| Kiểm tra logic nghiệp vụ không phụ thuộc HTTP | Mock interface gateway |
| Kiểm tra wiring, property và interceptor trong Spring context | Application integration test với mock HTTP server |
| Xác nhận TLS, proxy hoặc dịch vụ sandbox | Integration/smoke test trong môi trường phù hợp |

Không nên chọn công cụ chỉ vì một công cụ tạo mock response nhanh hơn. Chọn theo tầng mà test cần bảo vệ. Nếu cần kiểm tra codec, URI, headers và connector của WebClient, một stub ExchangeFunction có thể quá thấp. Nếu chỉ kiểm tra service gọi gateway và xử lý kết quả, dựng MockWebServer là quá nhiều.

## 13. Những lỗi thường gặp khi kiểm thử HTTP client

### Test xanh nhưng request thực tế sai

Nếu unit test chỉ mock gateway, nó không kiểm tra URL, method, header hoặc body. Thêm adapter test dùng mock server để xác nhận request thực tế được tạo.

### Mock server không nhận được request

Kiểm tra adapter đang sử dụng đúng client instance đã được bind với mock server chưa. Với RestClient, bind vào builder trước khi build client. Với RestTemplate, bind vào đúng instance được inject. Với WebClient, xác nhận base URL trỏ tới MockWebServer đang chạy.

### Test WebClient không chạy request

WebClient trả Mono hoặc Flux lazy. Request thường chỉ thực thi khi publisher được subscribe. Dùng StepVerifier, block có giới hạn trong test đồng bộ phù hợp, hoặc một subscriber rõ ràng. Không chỉ tạo publisher rồi kết thúc test.

### Response JSON không decode được

Kiểm tra Content-Type, codec/message converter, kiểu DTO, generic type và cấu hình ObjectMapper. Mock server cần trả đúng media type mà client mong đợi.

### Test dùng dữ liệu thật hoặc token thật

Dùng host giả, dữ liệu giả và token test. Không commit secret hoặc ghi Authorization/cookie vào log. Cấu hình base URL và credential nên được inject qua property hoặc test fixture.

### Retry làm test nhận nhiều request ngoài dự kiến

Kiểm tra retry policy và số lần subscription. Xác nhận mỗi lần retry có lý do hợp lệ, giới hạn số lần thử và chỉ áp dụng với thao tác có thể retry an toàn.

### Test phụ thuộc thứ tự hoặc port cố định

Tạo mock server riêng cho mỗi test hoặc quản lý vòng đời rõ ràng. Dùng port động và đóng server trong teardown. Không chia sẻ queue response giữa test chạy song song nếu không có cơ chế cô lập.

### Nhầm lỗi HTTP với lỗi kết nối

HTTP 404/500 là response từ server. Connection refused, DNS failure, TLS handshake failure và timeout là lỗi trước hoặc trong quá trình truyền nhận. Test nên phân biệt các nhóm này vì cách retry và ánh xạ exception có thể khác nhau.

## 14. Nguyên tắc thực hành

1. Đặt ranh giới HTTP client trong một adapter có trách nhiệm rõ ràng.
2. Dùng MockRestServiceServer cho RestClient và RestTemplate.
3. Dùng MockWebServer hoặc WireMock cho WebClient khi cần kiểm tra HTTP qua connector.
4. Dùng ExchangeFunction giả cho unit test hẹp, không coi nó là bằng chứng cho network transport.
5. Kiểm tra URI, method, header và body theo contract của dịch vụ.
6. Kiểm tra response decoding, status lỗi và exception domain mà ứng dụng công bố.
7. Với WebClient, subscribe và xác nhận publisher bằng StepVerifier.
8. Kiểm tra timeout, retry và cancellation khi chúng là một phần của hành vi cần bảo vệ.
9. Dùng mock HTTP server để kiểm tra wiring và cấu hình Spring mà không phụ thuộc dịch vụ bên ngoài.
10. Tách smoke test với dịch vụ thật khỏi bộ test nhanh, ổn định thường chạy.
11. Không kiểm tra lại logic nội bộ của hệ thống từ xa trong adapter test.
12. Không ghi secret, token, cookie hoặc dữ liệu nhạy cảm vào fixture và log.

Ranh giới cần kiểm chứng của RestClient, RestTemplate và WebClient là hợp đồng giữa ứng dụng với HTTP service mà nó gọi. MockRestServiceServer phù hợp với hai client đồng bộ của Spring; MockWebServer hoặc WireMock phù hợp với WebClient khi cần kiểm tra request qua HTTP transport. Chọn đúng tầng giúp test chứng minh được request, response và cách xử lý lỗi của ứng dụng, đồng thời giữ cho kết quả kiểm thử ổn định và độc lập với trạng thái của dịch vụ bên ngoài.

