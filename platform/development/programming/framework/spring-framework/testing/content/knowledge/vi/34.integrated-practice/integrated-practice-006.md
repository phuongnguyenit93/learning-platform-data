# Kiểm chứng client gọi dịch vụ ngoài bằng phản hồi có kiểm soát

**Ngữ cảnh:** Spring Framework Testing → Thực hành tổng hợp.

Một ứng dụng Spring thường gọi dịch vụ HTTP bên ngoài để lấy dữ liệu hoặc thực hiện một thao tác nghiệp vụ. Khi kiểm thử phần tích hợp này, ta cần kiểm soát được response mà dịch vụ bên ngoài trả về để có thể xác nhận ứng dụng gửi request đúng, giải mã response đúng và xử lý lỗi theo hợp đồng.

Không nên để test phụ thuộc vào Internet, dữ liệu thật hoặc trạng thái của nhà cung cấp dịch vụ. Một mock HTTP server hoặc công cụ kiểm thử HTTP của Spring có thể trả về những response được định trước: thành công, không tìm thấy dữ liệu, lỗi máy chủ, body rỗng hoặc response không đúng định dạng.

Bài thực hành này xây dựng một luồng từ service nghiệp vụ đến HTTP client:

~~~text
OrderService
    |
    v
CatalogGateway
    |
    v
RestClient
    |
    v
MockRestServiceServer
    |
    +--> response JSON 200
    +--> response 404
    +--> response 503
    +--> response body rỗng
~~~

Test sẽ kiểm tra cả request gửi đi lẫn cách ứng dụng sử dụng response nhận về. Dịch vụ Catalog thật không cần chạy trong quá trình kiểm thử.

## 1. Mục tiêu và ranh giới kiểm thử

Giả sử ứng dụng bán hàng cần kiểm tra tồn kho trước khi tạo đơn. Ứng dụng gọi Catalog API:

- GET /v1/items/{sku} để lấy thông tin sản phẩm.
- POST /v1/reservations để giữ số lượng sản phẩm.
- Catalog trả JSON khi thành công.
- Catalog trả 404 nếu SKU không tồn tại.
- Catalog có thể trả 5xx khi dịch vụ gặp sự cố.

Bài test cần chứng minh:

1. Client gọi đúng host, path và HTTP method.
2. Request có header Accept và Content-Type phù hợp.
3. Request body được serialize đúng nếu có thao tác POST.
4. Response JSON được deserialize thành DTO đúng.
5. Ứng dụng phân biệt sản phẩm không tồn tại với lỗi dịch vụ.
6. Service nghiệp vụ chỉ tạo reservation khi sản phẩm còn hàng.
7. Một kịch bản không gửi thêm request ngoài dự kiến.
8. Test có kết quả lặp lại được mà không cần dịch vụ bên ngoài.

Ranh giới này là outbound HTTP client adapter. Nó không thay thế controller test hoặc test logic nội bộ của Catalog. Test của OrderService có thể mock giao diện CatalogGateway; test của HttpCatalogGateway cần kiểm tra HTTP request thật do RestClient tạo ra.

## 2. Chọn công cụ trả response có kiểm soát

Spring có nhiều cách kiểm soát response cho HTTP client. Chọn công cụ theo tầng cần kiểm chứng.

| Công cụ | Client phù hợp | Cách hoạt động | Điều được kiểm chứng |
|---|---|---|---|
| MockRestServiceServer | RestClient, RestTemplate | Thay request factory bằng cơ chế mock của Spring | URI, method, header, body, status và response conversion |
| MockWebServer | RestClient, RestTemplate, WebClient | Mở HTTP server cục bộ, client gửi request qua socket | HTTP request qua connector/transport cục bộ và response |
| WireMock | Nhiều HTTP client | Chạy mock HTTP server với mapping và request journal | HTTP contract, scenario, delay và nhiều dạng response |
| Mockito mock gateway | Service nghiệp vụ | Thay giao diện adapter bằng mock object | Logic nghiệp vụ khi nhận kết quả/lỗi từ gateway |
| ExchangeFunction giả | WebClient | Trả ClientResponse ngay trong pipeline | Logic WebClient filter/adapter ở tầng ExchangeFunction |

Trong bài này, phần chính dùng **RestClient** và **MockRestServiceServer** vì đây là cách kiểm thử được Spring hỗ trợ trực tiếp. MockRestServiceServer không mở cổng mạng; nó kiểm tra request tại tầng request factory của Spring. Vì vậy, nó phù hợp để xác nhận HTTP contract và message conversion.

Nếu cần kiểm tra connector, socket, TLS hoặc timeout trên HTTP transport, dùng MockWebServer hoặc WireMock. Các phần sau sẽ chỉ ra cách chuyển cùng kịch bản sang các công cụ đó.

## 3. Chuẩn bị dependency

Ví dụ dưới đây giả định ứng dụng dùng Spring Framework 6.1 trở lên để có RestClient. Dự án Spring Boot có thể dùng dependency management của Boot để đồng bộ phiên bản.

Với Gradle, các dependency liên quan có thể gồm:

~~~groovy
dependencies {
    implementation("org.springframework:spring-web")
    implementation("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Trong ứng dụng Spring Boot, các starter tương ứng có thể đã cung cấp Spring Web, Jackson, JUnit và AssertJ. Cần bảo đảm spring-test có mặt trên test classpath; Spring Boot thường đưa nó vào qua spring-boot-starter-test.

Nếu dùng RestTemplate thay vì RestClient, MockRestServiceServer cũng thuộc spring-test. Nếu dùng WebClient, cần spring-webflux và thường dùng reactor-test cùng MockWebServer hoặc WireMock cho test HTTP qua socket.

## 4. Thiết kế các kiểu dữ liệu và giao diện gateway

Bắt đầu với các DTO biểu diễn response và request.

~~~java
public record CatalogItem(
        String sku,
        String name,
        boolean available
) {}

public record ReservationRequest(
        String sku,
        int quantity
) {}

public record Reservation(
        String reservationId,
        String sku,
        int quantity
) {}

public record OrderDecision(
        String sku,
        int quantity,
        String status,
        String reservationId
) {}
~~~

Định nghĩa giao diện mà service nghiệp vụ sử dụng:

~~~java
public interface CatalogGateway {

    CatalogItem findBySku(String sku);

    Reservation reserve(String sku, int quantity);
}
~~~

Service nghiệp vụ chỉ phụ thuộc CatalogGateway. Nó không cần biết ứng dụng dùng RestClient, RestTemplate hay WebClient.

~~~java
public class OrderService {

    private final CatalogGateway catalogGateway;

    public OrderService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    public OrderDecision placeOrder(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero");
        }

        CatalogItem item = catalogGateway.findBySku(sku);

        if (!item.available()) {
            return new OrderDecision(
                    sku, quantity, "REJECTED_OUT_OF_STOCK", null);
        }

        Reservation reservation =
                catalogGateway.reserve(sku, quantity);

        return new OrderDecision(
                sku,
                quantity,
                "CONFIRMED",
                reservation.reservationId()
        );
    }
}
~~~

Luồng này có hai quyết định quan trọng:

- Nếu Catalog báo sản phẩm không còn hàng, OrderService trả kết quả từ chối và không gọi POST reservation.
- Nếu sản phẩm còn hàng, OrderService gửi yêu cầu giữ hàng và trả kết quả xác nhận khi Catalog tạo reservation thành công.

Các exception nghiệp vụ được định nghĩa để tách lỗi từ dịch vụ ngoài khỏi cách Spring biểu diễn HTTP error:

~~~java
public class CatalogItemNotFoundException extends RuntimeException {

    public CatalogItemNotFoundException(String sku) {
        super("Catalog item not found: " + sku);
    }
}

public class CatalogUnavailableException extends RuntimeException {

    public CatalogUnavailableException(String message) {
        super(message);
    }
}

public class CatalogProtocolException extends RuntimeException {

    public CatalogProtocolException(String message) {
        super(message);
    }
}
~~~

Trong ứng dụng thật, exception có thể mang thêm status, mã lỗi hoặc thông tin correlation. Tránh đưa token, credential hay response body chứa dữ liệu nhạy cảm vào message của exception.

## 5. Cài đặt HTTP adapter bằng RestClient

RestClient là API HTTP đồng bộ fluent được giới thiệu trong Spring Framework 6.1. Adapter sẽ chịu trách nhiệm tạo request, xử lý status và đọc body.

~~~java
public class HttpCatalogGateway implements CatalogGateway {

    private final RestClient restClient;

    public HttpCatalogGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public CatalogItem findBySku(String sku) {
        CatalogItem item = restClient.get()
                .uri("/v1/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        status -> status.value() == 404,
                        (request, response) -> {
                            throw new CatalogItemNotFoundException(sku);
                        }
                )
                .onStatus(
                        HttpStatusCode::is5xxServerError,
                        (request, response) -> {
                            throw new CatalogUnavailableException(
                                    "Catalog returned HTTP "
                                            + response.getStatusCode().value()
                            );
                        }
                )
                .body(CatalogItem.class);

        if (item == null) {
            throw new CatalogProtocolException(
                    "Catalog returned an empty item response");
        }

        return item;
    }

    @Override
    public Reservation reserve(String sku, int quantity) {
        Reservation reservation = restClient.post()
                .uri("/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(new ReservationRequest(sku, quantity))
                .retrieve()
                .onStatus(
                        HttpStatusCode::is5xxServerError,
                        (request, response) -> {
                            throw new CatalogUnavailableException(
                                    "Catalog returned HTTP "
                                            + response.getStatusCode().value()
                            );
                        }
                )
                .body(Reservation.class);

        if (reservation == null) {
            throw new CatalogProtocolException(
                    "Catalog returned an empty reservation response");
        }

        return reservation;
    }
}
~~~

Một số điểm cần chú ý:

- URI dùng template và path variable để tránh nối chuỗi thủ công.
- GET gửi Accept JSON để thông báo kiểu response mong muốn.
- POST khai báo Content-Type JSON và dùng DTO làm request body.
- 404 được ánh xạ thành CatalogItemNotFoundException.
- 5xx được ánh xạ thành CatalogUnavailableException.
- Body rỗng ở response thành công được xem là lỗi giao thức trong ví dụ này.

Các status 4xx khác chưa được ánh xạ riêng nên vẫn đi theo error handling mặc định của RestClient. Trong ứng dụng thật, hãy xác định rõ contract cho 400, 401, 403, 409, 422 và 429 nếu service cần phân biệt các trường hợp đó.

## 6. Tạo RestClient gắn với MockRestServiceServer

Điểm quan trọng là bind MockRestServiceServer vào đúng RestClient.Builder trước khi build client.

~~~java
private static final String CATALOG_BASE_URL =
        "https://catalog.example.test";

RestClient.Builder builder = RestClient.builder()
        .baseUrl(CATALOG_BASE_URL);

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();

CatalogGateway gateway = new HttpCatalogGateway(restClient);
~~~

Mock server thay request factory trong builder để request từ RestClient được đối chiếu với các expectation mà test đăng ký. Response do test cấu hình sẽ được trả lại cho client như một response HTTP.

Nếu adapter được tạo từ một RestClient khác không dùng builder đã bind, mock server sẽ không quan sát request đó. Trong Spring context test, cần bảo đảm bean RestClient được tạo từ builder đã được gắn mock server.

Mỗi test nên có mock server riêng hoặc fixture riêng. Không dùng một server có expectation mutable chung cho nhiều test chạy đồng thời nếu chưa có cơ chế cô lập.

## 7. Viết test tích hợp cho luồng đặt hàng thành công

### 7.1. Thiết lập fixture cho từng test

~~~java
class OrderServiceHttpIntegrationTest {

    private MockRestServiceServer mockServer;
    private CatalogGateway catalogGateway;
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        mockServer = MockRestServiceServer.bindTo(builder).build();

        RestClient restClient = builder.build();

        catalogGateway = new HttpCatalogGateway(restClient);
        orderService = new OrderService(catalogGateway);
    }
}
~~~

Mock server và RestClient được tạo mới trong mỗi test. Nhờ đó, expectation của kịch bản này không rò sang kịch bản khác.

### 7.2. Định nghĩa response GET và POST

Kịch bản thành công cần hai response:

1. GET item trả về sản phẩm còn hàng.
2. POST reservation trả về mã reservation.

~~~java
@Test
void confirmsOrderWhenCatalogItemIsAvailable() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(content().json("""
                    {
                      "sku": "SKU-42",
                      "quantity": 2
                    }
                    """))
            .andRespond(withStatus(HttpStatus.CREATED)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "reservationId": "RSV-100",
                              "sku": "SKU-42",
                              "quantity": 2
                            }
                            """));

    OrderDecision decision = orderService.placeOrder("SKU-42", 2);

    assertThat(decision.status()).isEqualTo("CONFIRMED");
    assertThat(decision.sku()).isEqualTo("SKU-42");
    assertThat(decision.quantity()).isEqualTo(2);
    assertThat(decision.reservationId()).isEqualTo("RSV-100");

    mockServer.verify();
}
~~~

Test này đi qua OrderService, CatalogGateway và RestClient. Nó xác nhận:

- GET được gửi đúng URI và method.
- Header Accept là JSON.
- JSON response được giải mã thành CatalogItem.
- POST được gửi đúng endpoint.
- Request body chứa SKU và quantity đúng.
- Response 201 được giải mã thành Reservation.
- OrderService trả kết quả CONFIRMED với reservation id tương ứng.

Matcher JSON so sánh cấu trúc JSON, do đó không phụ thuộc thứ tự thuộc tính hoặc khoảng trắng trong body.

### 7.3. Vì sao gọi verify() ở cuối test?

MockRestServiceServer.verify() xác nhận các expectation đã đăng ký đều được đáp ứng. Nếu service không gửi POST như mong đợi, expectation POST còn thiếu và verify sẽ báo lỗi.

Nếu client gửi một request ngoài dự kiến, mock server cũng báo request không khớp với expectation. Điều này giúp phát hiện trường hợp service vô tình gọi endpoint thêm lần nữa.

Không nên chỉ assert object trả về mà bỏ verify. Một test có thể nhận được kết quả mong đợi từ code giả hoặc đường đi khác trong khi request HTTP thực tế đã thay đổi.

## 8. Kiểm soát response theo từng tình huống

Một ưu điểm của mock HTTP server là test quyết định chính xác response mà client nhận. Mỗi tình huống có thể được viết thành test riêng để chỉ rõ hành vi cần bảo vệ.

### 8.1. Sản phẩm không còn hàng: HTTP 200

Không phải mọi tình huống nghiệp vụ đều là HTTP error. Catalog có thể trả HTTP 200 với available=false.

~~~java
@Test
void rejectsOrderWithoutCreatingReservationWhenItemIsUnavailable() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": false
                    }
                    """, MediaType.APPLICATION_JSON));

    OrderDecision decision = orderService.placeOrder("SKU-42", 2);

    assertThat(decision.status())
            .isEqualTo("REJECTED_OUT_OF_STOCK");
    assertThat(decision.reservationId()).isNull();

    mockServer.verify();
}
~~~

Chỉ có một expectation GET. Nếu OrderService gọi POST reservation sai logic, request không có expectation tương ứng và test thất bại. Đây là cách xác nhận một nhánh nghiệp vụ không được tạo side effect.

### 8.2. SKU không tồn tại: HTTP 404

~~~java
@Test
void mapsCatalogNotFoundToDomainException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/MISSING"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "code": "ITEM_NOT_FOUND",
                              "message": "Unknown SKU"
                            }
                            """));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("MISSING"))
            .isInstanceOf(CatalogItemNotFoundException.class)
            .hasMessageContaining("MISSING");

    mockServer.verify();
}
~~~

Test xác nhận HTTP 404 được adapter ánh xạ thành exception nghiệp vụ. Service phía trên không cần phụ thuộc vào RestClientResponseException hoặc chi tiết triển khai của HTTP client.

### 8.3. Catalog lỗi máy chủ: HTTP 503

~~~java
@Test
void mapsCatalogServerFailureToUnavailableException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "code": "TEMPORARILY_UNAVAILABLE"
                            }
                            """));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(CatalogUnavailableException.class)
            .hasMessageContaining("503");

    mockServer.verify();
}
~~~

HTTP 503 thường biểu thị dịch vụ tạm thời không thể xử lý request. Adapter ánh xạ nó thành CatalogUnavailableException để tầng nghiệp vụ có thể xử lý theo chính sách retry, fallback hoặc báo lỗi cho caller.

Không nên tự động retry mọi POST. Nếu thao tác có side effect như tạo reservation, retry cần idempotency key hoặc một contract bảo đảm không tạo reservation trùng lặp.

### 8.4. HTTP 200 nhưng body rỗng

Trong ví dụ, adapter yêu cầu body CatalogItem phải tồn tại. Có thể kiểm tra response 204:

~~~java
@Test
void rejectsEmptySuccessfulResponse() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(CatalogProtocolException.class);

    mockServer.verify();
}
~~~

Response rỗng có thể hợp lệ với một số endpoint, ví dụ DELETE trả 204. Nhưng endpoint GET cần CatalogItem không thể hoàn thành hợp đồng nếu không có body. Test cần phản ánh đúng contract của endpoint thay vì mặc định mọi 204 đều là lỗi.

### 8.5. Response có JSON không hợp lệ

Nếu server trả body sai định dạng hoặc thiếu kiểu dữ liệu cần thiết, message converter có thể ném exception trong quá trình deserialize.

~~~java
@Test
void failsWhenCatalogReturnsMalformedJson() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andRespond(withSuccess(
                    "{ this-is-not-valid-json",
                    MediaType.APPLICATION_JSON));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(RestClientException.class);

    mockServer.verify();
}
~~~

Loại exception cụ thể có thể phụ thuộc message converter và phiên bản Spring/Jackson. Nếu adapter cần chuẩn hóa lỗi decode thành CatalogProtocolException, hãy bắt và ánh xạ đúng loại lỗi ở adapter rồi viết test theo contract đó. Không nên khẳng định mọi lỗi deserialize đều có cùng một exception class trong mọi cấu hình.

## 9. Kiểm tra POST request body và header chi tiết

Khi client gửi lệnh thay đổi dữ liệu, request body là một phần quan trọng của contract.

Ví dụ request reservation:

~~~java
new ReservationRequest("SKU-42", 2)
~~~

MockRestServiceServer có thể xác nhận:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "SKU-42",
                  "quantity": 2
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "reservationId": "RSV-100",
                          "sku": "SKU-42",
                          "quantity": 2
                        }
                        """));
~~~

Nếu API yêu cầu idempotency key, correlation id hoặc authorization header, thêm expectation tương ứng:

~~~java
.andExpect(header("Idempotency-Key", "order-test-100"))
.andExpect(header("X-Correlation-Id", "trace-test-100"))
~~~

Không dùng token thật trong test fixture. Nếu cần kiểm tra Authorization, dùng credential giả và chỉ xác nhận header có đúng format hoặc giá trị test mong đợi.

Không nên kiểm tra mọi header do HTTP stack tự sinh như Connection, User-Agent hoặc Content-Length nếu chúng không phải contract của adapter. Những header này có thể thay đổi theo request factory, JDK hoặc connector.

## 10. Phân biệt lỗi HTTP với lỗi kết nối

MockRestServiceServer kiểm soát response ở tầng request factory. Nó rất phù hợp để mô phỏng status và body, nhưng không mô phỏng đầy đủ một kết nối mạng bị timeout hoặc TLS handshake thất bại.

Hai nhóm lỗi cần được phân biệt:

| Nhóm lỗi | Ví dụ | Cách kiểm thử phù hợp |
|---|---|---|
| HTTP response error | 404, 429, 500, 503 | MockRestServiceServer hoặc mock HTTP server |
| Transport error | Connection refused, socket disconnect, DNS failure, timeout, TLS handshake failure | MockWebServer/WireMock với socket policy hoặc test môi trường transport phù hợp |

Nếu ứng dụng có chính sách timeout hoặc retry, nên có test riêng cho transport. Không dùng một response HTTP 503 để kết luận client xử lý connection timeout đúng; đó là hai tình huống khác nhau.

Với RestClient/RestTemplate, MockWebServer có thể mở cổng cục bộ, cho phép client thực hiện HTTP qua connector thật. Khi đó có thể cấu hình response delay hoặc ngắt kết nối. Hãy chọn request factory rõ ràng nếu cần kiểm tra một hành vi transport cụ thể.

## 11. Khi cần kiểm tra HTTP transport bằng MockWebServer

### 11.1. Khởi động server cục bộ

MockWebServer thuộc thư viện OkHttp. Nó chạy một HTTP server trên loopback với port động.

~~~java
class CatalogTransportTest {

    private MockWebServer mockWebServer;
    private RestClient restClient;

    @BeforeEach
    void setUp() throws IOException {
        mockWebServer = new MockWebServer();
        mockWebServer.start();

        restClient = RestClient.builder()
                .baseUrl(mockWebServer.url("/").toString())
                .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        mockWebServer.shutdown();
    }
}
~~~

Test xếp hàng response:

~~~java
@Test
void sendsRequestThroughLocalHttpServer() throws Exception {
    mockWebServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": true
                    }
                    """));

    CatalogItem item = restClient.get()
            .uri("/v1/items/{sku}", "SKU-42")
            .retrieve()
            .body(CatalogItem.class);

    assertThat(item.available()).isTrue();

    RecordedRequest request =
            mockWebServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request).isNotNull();
    assertThat(request.getMethod()).isEqualTo("GET");
    assertThat(request.getPath()).isEqualTo("/v1/items/SKU-42");
}
~~~

MockWebServer nhận request qua HTTP cục bộ. Test có thể kiểm tra RecordedRequest, response delay, socket policy và các chi tiết transport mà MockRestServiceServer không mô phỏng.

### 11.2. Kiểm tra delay và timeout

Có thể xếp hàng response có độ trễ:

~~~java
mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBodyDelay(2, TimeUnit.SECONDS)
        .setBody("""
                {"sku":"SKU-42","name":"Keyboard","available":true}
                """));
~~~

Sau đó cấu hình HTTP client timeout ngắn hơn độ trễ và xác nhận adapter xử lý lỗi timeout theo contract.

Cách cấu hình timeout phụ thuộc request factory/connector mà RestClient đang dùng. Vì vậy, test cần khởi tạo client bằng đúng factory sẽ triển khai hoặc factory có hành vi tương ứng. Không nên chỉ thay một timeout tùy ý trong test rồi suy luận cấu hình production đã đúng.

### 11.3. Kiểm tra disconnect

MockWebServer có các socket policy để mô phỏng một số tình huống kết nối, ví dụ ngắt kết nối trước khi response hoàn tất. Dùng chúng khi cần xác nhận cách adapter hoặc retry policy xử lý transport failure.

Các chính sách socket cụ thể và hành vi exception phụ thuộc phiên bản MockWebServer/HTTP client. Hãy assert vào contract ổn định của ứng dụng, ví dụ CatalogUnavailableException hoặc một retry count xác định, thay vì khóa test vào message exception của JDK.

## 12. Chuyển cùng kịch bản sang RestTemplate

RestTemplate cũng có thể được kiểm thử bằng MockRestServiceServer. Điểm khác biệt chủ yếu là cách gọi API của client.

Khởi tạo:

~~~java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

Adapter:

~~~java
CatalogItem item = restTemplate.getForObject(
        "https://catalog.example.test/v1/items/{sku}",
        CatalogItem.class,
        sku
);
~~~

Expectation:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("""
                {
                  "sku": "SKU-42",
                  "name": "Mechanical Keyboard",
                  "available": true
                }
                """, MediaType.APPLICATION_JSON));

CatalogItem item = gateway.findBySku("SKU-42");

assertThat(item.available()).isTrue();
mockServer.verify();
~~~

MockRestServiceServer xác nhận request và response ở tầng Spring request factory. Không cần tạo một mock cho CatalogGateway trong bài test adapter vì mục tiêu là kiểm tra chính RestTemplate được cấu hình và sử dụng đúng.

## 13. Chuyển cùng kịch bản sang WebClient

WebClient là reactive client. Request thường chỉ thực thi khi Mono hoặc Flux được subscribe. Để kiểm tra HTTP qua connector, dùng MockWebServer hoặc WireMock.

Ví dụ adapter:

~~~java
public Mono<CatalogItem> findBySku(String sku) {
    return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new CatalogItemNotFoundException(sku))
            )
            .onStatus(
                    HttpStatusCode::is5xxServerError,
                    response -> Mono.error(
                            new CatalogUnavailableException(
                                    "Catalog server failure"))
            )
            .bodyToMono(CatalogItem.class);
}
~~~

Test dùng response được xếp hàng:

~~~java
mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader(
                "Content-Type",
                MediaType.APPLICATION_JSON_VALUE)
        .setBody("""
                {
                  "sku": "SKU-42",
                  "name": "Mechanical Keyboard",
                  "available": true
                }
                """));

StepVerifier.create(webClientCatalogGateway.findBySku("SKU-42"))
        .assertNext(item -> {
            assertThat(item.sku()).isEqualTo("SKU-42");
            assertThat(item.available()).isTrue();
        })
        .verifyComplete();
~~~

Không chỉ gọi findBySku rồi kết thúc test. Nếu publisher chưa được subscribe, request có thể chưa được gửi. StepVerifier thực hiện subscription và xác nhận tín hiệu.

Với stream dài hạn, kiểm tra một số event cần thiết rồi hủy subscription có chủ đích. Với Mono hoặc Flux hữu hạn, xác nhận complete hoặc error như contract yêu cầu.

## 14. Khi nào dùng Mockito thay vì mock HTTP server?

Hai kiểu test trả lời hai câu hỏi khác nhau.

### 14.1. Unit test service với mock gateway

~~~java
@Test
void rejectsOrderWhenCatalogSaysUnavailable() {
    CatalogGateway gateway = mock(CatalogGateway.class);

    given(gateway.findBySku("SKU-42"))
            .willReturn(new CatalogItem(
                    "SKU-42", "Mechanical Keyboard", false));

    OrderService service = new OrderService(gateway);

    OrderDecision decision = service.placeOrder("SKU-42", 2);

    assertThat(decision.status())
            .isEqualTo("REJECTED_OUT_OF_STOCK");

    then(gateway).should().findBySku("SKU-42");
    then(gateway).shouldHaveNoMoreInteractions();
}
~~~

Test này tập trung vào logic OrderService. Nó không xác nhận URL, HTTP method, header, JSON serialization hoặc response conversion.

### 14.2. Adapter test với MockRestServiceServer

Adapter test tạo RestClient thật và điều khiển response HTTP:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-42","name":"Keyboard","available":true}
                """,
                MediaType.APPLICATION_JSON));

CatalogItem item = catalogGateway.findBySku("SKU-42");

assertThat(item.available()).isTrue();
mockServer.verify();
~~~

Test này bảo vệ hợp đồng giữa adapter và dịch vụ Catalog.

Một bộ test tốt có thể có cả hai lớp: unit test service nhanh và adapter test xác nhận HTTP contract. Không cần dựng mock HTTP server trong mọi unit test nghiệp vụ.

## 15. Tổ chức expectation và fixture ổn định

### 15.1. Mỗi test tự khai báo response của nó

Không dùng response queue static hoặc một MockRestServiceServer được chia sẻ giữa các test độc lập. Mỗi test cần biết response nào được trả cho request nào.

Cách tổ chức:

- Tạo builder và mock server trong setup của test.
- Đăng ký expectation ngay trong test case.
- Gửi request qua service/adapter.
- Assert kết quả nghiệp vụ và request.
- Gọi verify để xác nhận expectation đã được dùng.
- Giải phóng tài nguyên sau test nếu có server thật.

### 15.2. Expectation theo thứ tự

MockRestServiceServer mặc định có thể kiểm tra request theo thứ tự expectation được đăng ký. Với một luồng có GET rồi POST, thứ tự này phản ánh trình tự nghiệp vụ.

Nếu thứ tự request không phải contract và test thật sự cho phép nhiều request độc lập, có thể cấu hình cơ chế bỏ qua thứ tự theo API của phiên bản Spring Test. Chỉ làm vậy khi thứ tự không có ý nghĩa; nếu thứ tự là một phần của quy trình, giữ expectation tuần tự để phát hiện lỗi.

### 15.3. Dùng response fixture có ý nghĩa

Nội dung JSON nên đại diện cho contract thực tế:

- Giá trị bắt buộc có mặt.
- Kiểu dữ liệu đúng.
- Trạng thái nghiệp vụ rõ ràng.
- Error code ổn định.
- Trường optional được kiểm tra khi ứng dụng phụ thuộc vào chúng.

Không cần sao chép response thật có hàng trăm field nếu adapter chỉ sử dụng một phần nhỏ. Nhưng không được lược bỏ field bắt buộc khiến test không còn kiểm tra được việc deserialize và mapping.

### 15.4. Tránh kiểm tra quá nhiều chi tiết không thuộc contract

Kiểm tra method, URI, header và body có ý nghĩa. Không nên buộc test phải phụ thuộc vào:

- Thứ tự key JSON.
- Khoảng trắng hoặc xuống dòng.
- Header do HTTP stack tự sinh.
- Message exception nội bộ của một phiên bản thư viện.
- Thứ tự field trong DTO nếu không phải contract.

Test nên thất bại khi hành vi của ứng dụng thay đổi theo cách có ảnh hưởng, không phải khi chi tiết triển khai không quan trọng thay đổi.

## 16. Kiểm thử retry và idempotency

Nếu adapter có retry, response có kiểm soát giúp mô phỏng lần đầu thất bại và lần sau thành công.

Ví dụ về chuỗi response:

1. Lần gọi đầu nhận HTTP 503.
2. Lần gọi tiếp theo nhận HTTP 200.
3. Client chỉ retry số lần đã cấu hình.
4. Request lặp lại giữ đúng idempotency key nếu thao tác có side effect.

Với MockRestServiceServer, đăng ký hai expectation cùng URI theo thứ tự:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andRespond(withSuccess("""
                {
                  "sku": "SKU-42",
                  "name": "Keyboard",
                  "available": true
                }
                """, MediaType.APPLICATION_JSON));
~~~

Test cần dùng chính sách retry đã cấu hình trong adapter. Nếu retry có backoff, dùng scheduler hoặc thời gian test được kiểm soát khi framework hỗ trợ; không thêm Thread.sleep tùy tiện.

Đối với POST tạo reservation, retry có thể tạo reservation trùng. Chỉ retry khi API có idempotency key hoặc cơ chế bảo đảm lệnh lặp không tạo side effect thứ hai. Test nên xác nhận key được gửi giống nhau qua các lần retry và số request không vượt giới hạn.

## 17. Kiểm thử timeout và giới hạn thời gian

Timeout có thể xuất hiện ở nhiều lớp:

- Connection timeout: không thiết lập được kết nối.
- Response/read timeout: server không trả dữ liệu đúng hạn.
- Overall request deadline: tổng thời gian xử lý vượt ngưỡng.
- Reactive timeout: publisher không phát tín hiệu trong thời gian cho phép.

MockRestServiceServer không mô phỏng đầy đủ độ trễ socket. Dùng MockWebServer/WireMock để tạo response delay hoặc ngắt kết nối khi cần xác nhận transport.

Test nên có timeout cho chính test để tránh build treo. Ví dụ với Reactor:

~~~java
StepVerifier.create(webClientGateway.findBySku("SKU-42"))
        .expectError()
        .verify(Duration.ofSeconds(5));
~~~

Timeout của StepVerifier giới hạn thời gian chờ tín hiệu trong test; nó không tự cấu hình timeout cho HTTP client. Client vẫn cần được cấu hình timeout riêng.

Nếu cần xác nhận loại exception cụ thể, ánh xạ transport error trong adapter rồi assert exception nghiệp vụ. Tránh phụ thuộc vào một exception class có thể thay đổi theo request factory hoặc connector.

## 18. Bảng test case cho adapter Catalog

Một bộ test thực hành có thể bao gồm:

| Kịch bản | Response có kiểm soát | Điều cần xác nhận |
|---|---|---|
| Sản phẩm còn hàng | 200 + available=true | DTO đúng, service tiếp tục POST reservation |
| Sản phẩm hết hàng | 200 + available=false | Service từ chối và không gửi POST |
| SKU không tồn tại | 404 | Adapter ném CatalogItemNotFoundException |
| Catalog tạm ngừng | 503 | Adapter ném CatalogUnavailableException |
| Response rỗng | 204 | Adapter xử lý theo contract, ví dụ CatalogProtocolException |
| JSON sai định dạng | 200 + malformed JSON | Decode thất bại hoặc được ánh xạ thành lỗi protocol |
| Request POST | 201 + reservation JSON | Method, URI, headers và request body đúng |
| Timeout | Server delay vượt ngưỡng | Client timeout và adapter xử lý đúng |
| Disconnect | Socket đóng trước response | Transport error được ánh xạ đúng |
| Retry | 503 rồi 200 | Số lần gọi, backoff và idempotency đúng |

Không phải dự án nào cũng cần tất cả kịch bản. Chọn những trường hợp tương ứng với contract và chính sách lỗi của adapter.

## 19. Những lỗi thường gặp khi kiểm thử với response có kiểm soát

### Test chỉ mock giao diện gateway

Khi mock CatalogGateway, test service không xác nhận request HTTP. Thêm adapter test dùng RestClient/RestTemplate/WebClient thật và mock HTTP response ở đúng tầng.

### Mock server không nhận request

Kiểm tra client có được tạo từ builder đã bind MockRestServiceServer không. Nếu adapter dùng một RestClient khác, expectation sẽ không quan sát request đó.

### WebClient không thực thi request

Mono/Flux là lazy. Phải subscribe, ví dụ bằng StepVerifier, trước khi đọc RecordedRequest hoặc kết thúc test.

### Request body không khớp

Kiểm tra Content-Type, DTO, Jackson configuration và JSON contract. Dùng JSON matcher thay vì so sánh chuỗi nếu thứ tự thuộc tính không quan trọng.

### verify() báo còn expectation

Service có thể chưa đi đến bước dự kiến, đã thoát sớm vì exception hoặc không gọi client. Xem assertion trước đó và thứ tự expectation để xác định nhánh nào không chạy.

### Có request ngoài dự kiến

Một request có thể được gửi do retry, subscribe nhiều lần, gọi lặp trong service hoặc một callback chạy nền. Dùng request count/journal của mock server để xác định số lần gọi.

### Test pass nhưng timeout production vẫn sai

MockRestServiceServer không mô phỏng socket delay. Dùng MockWebServer/WireMock và cấu hình client tương ứng để kiểm tra transport timeout.

### Test phụ thuộc dịch vụ thật

Nếu test gọi host production hoặc sandbox thật, kết quả có thể thay đổi theo mạng, dữ liệu và trạng thái dịch vụ. Thay base URL bằng mock server và giữ một nhóm smoke test riêng cho môi trường tích hợp thật.

### Test chia sẻ mock server giữa nhiều test

Expectation và response queue có trạng thái. Tạo server riêng cho test hoặc dùng lock/cô lập rõ ràng nếu buộc phải chia sẻ. Không reset queue trong lúc test khác đang sử dụng.

## 20. Quy trình thực hành từ đầu đến cuối

Có thể triển khai bài thực hành theo trình tự:

1. Xác định outbound contract: URI, method, headers, body, status và response schema.
2. Tạo DTO cho request và response.
3. Định nghĩa gateway interface để service nghiệp vụ không phụ thuộc HTTP client cụ thể.
4. Cài đặt adapter bằng RestClient, RestTemplate hoặc WebClient.
5. Chọn MockRestServiceServer cho RestClient/RestTemplate ở tầng Spring request factory.
6. Chọn MockWebServer/WireMock khi cần kiểm tra connector và HTTP transport.
7. Tạo mock server riêng cho test và đăng ký response có kiểm soát.
8. Gọi service/adapter thật trong test.
9. Assert kết quả nghiệp vụ, exception và request thực tế.
10. Verify expectation để phát hiện request thiếu hoặc ngoài dự kiến.
11. Bổ sung test cho lỗi HTTP, body sai, timeout hoặc retry khi đó là contract cần bảo vệ.
12. Giữ smoke test với dịch vụ thật ở một nhóm riêng, có cấu hình và dữ liệu được kiểm soát.

## 21. Nguyên tắc thực hành

1. Kiểm thử outbound HTTP ở ranh giới adapter, không chỉ mock giao diện gateway.
2. Dùng response có kiểm soát để test có thể lặp lại và không phụ thuộc dịch vụ bên ngoài.
3. Dùng MockRestServiceServer cho RestClient và RestTemplate khi cần kiểm tra Spring request/response handling.
4. Dùng MockWebServer hoặc WireMock khi cần request đi qua HTTP connector và socket.
5. Dùng StepVerifier để thực thi và xác nhận Mono/Flux của WebClient.
6. Kiểm tra URI, method, headers, request body và response decoding.
7. Phân biệt HTTP error response với transport failure.
8. Ánh xạ lỗi từ xa thành exception nghiệp vụ ổn định khi service cần một contract rõ ràng.
9. Xác nhận nhánh nghiệp vụ không gửi request tiếp theo ngoài dự kiến.
10. Gọi verify hoặc kiểm tra request journal để xác nhận đúng số lần gọi.
11. Chỉ retry thao tác có chính sách rõ ràng; dùng idempotency key cho side effect có thể lặp.
12. Không dùng Thread.sleep để đồng bộ; đặt timeout hữu hạn cho test và publisher.
13. Tạo mock server và fixture riêng cho từng test khi có thể.
14. Không đưa secret, token hoặc dữ liệu nhạy cảm vào response fixture và log.
15. Tách adapter test ổn định khỏi smoke test phụ thuộc dịch vụ thật.

Một response có kiểm soát cho phép test tái hiện chính xác những gì HTTP client nhận được. Khi kết hợp request expectation với assertion nghiệp vụ, bài test chứng minh được cả hai chiều của tích hợp: ứng dụng gửi đúng yêu cầu và phản ứng đúng với kết quả từ dịch vụ ngoài. MockRestServiceServer phù hợp để kiểm tra RestClient/RestTemplate ở tầng Spring; MockWebServer hoặc WireMock mở rộng kiểm chứng sang HTTP transport; còn Mockito phù hợp với unit test của service khi không cần kiểm tra giao thức.

