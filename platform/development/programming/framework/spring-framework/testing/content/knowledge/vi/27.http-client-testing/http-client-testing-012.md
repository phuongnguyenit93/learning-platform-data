# Tránh giả lập chuỗi fluent của client quá sâu

Khi viết unit test cho service có gọi HTTP API bên ngoài, một cách làm dễ gặp là mock từng lời gọi trong chuỗi fluent của HTTP client: `get()`, `uri(...)`, `retrieve()` rồi `body(...)`. Với `WebClient`, chuỗi có thể dài hơn: `get()`, `uri(...)`, `retrieve()`, `bodyToMono(...)`. Cách này thường cần deep stubbing hoặc nhiều mock lồng nhau.

Các test như vậy rất dễ phụ thuộc vào chi tiết triển khai. Chỉ cần đổi cách tạo URI, thêm header, chuyển từ `retrieve()` sang `exchange()` hoặc tái cấu trúc client là test có thể hỏng dù hành vi HTTP bên ngoài vẫn đúng. Hơn nữa, khi mock toàn bộ chuỗi, test không kiểm tra được request thực sự được gửi đi như thế nào, JSON được serialize ra sao, status lỗi được xử lý thế nào hay response body có deserialize đúng không.

Một cách thiết kế bền vững hơn là phân biệt hai trách nhiệm: kiểm thử logic nghiệp vụ qua một interface mà ứng dụng sở hữu, và kiểm thử HTTP adapter bằng HTTP client thật kết nối tới mock HTTP server. Với Spring, `MockRestServiceServer` phù hợp cho `RestClient` và `RestTemplate`; `MockWebServer` hoặc WireMock thường phù hợp với `WebClient` và các client giao tiếp qua socket.

## 1. Vì sao mock sâu chuỗi fluent dễ gây vấn đề?

Giả sử service sử dụng `RestClient` để lấy thông tin kho hàng:

```java
public class InventoryService {

    private final RestClient restClient;

    public InventoryService(RestClient restClient) {
        this.restClient = restClient;
    }

    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Một test có thể cố gắng mock toàn bộ chuỗi:

```java
@Mock(answer = Answers.RETURNS_DEEP_STUBS)
RestClient restClient;

when(restClient.get()
        .uri("/api/inventory/{sku}", "SKU-1")
        .retrieve()
        .body(InventoryItem.class))
    .thenReturn(new InventoryItem("SKU-1", 12));
```

Đoạn code minh họa việc dùng deep stubs để thay thế tất cả đối tượng trung gian. Cách làm này có một số nhược điểm:

- Test phải biết chính xác chuỗi method mà implementation đang gọi. Thêm một bước `accept(...)` hoặc đổi cách dựng URI có thể làm stubbing không còn khớp.
- Các interface trung gian của `RestClient` là chi tiết của API fluent. Mock từng bước khiến test gắn chặt với cách sử dụng API thay vì hành vi mà ứng dụng cần cung cấp.
- Mock `retrieve()` và `body(...)` không thực hiện HTTP exchange. Test không xác nhận method, URL, header, request body, status code hay response body thực tế.
- Không có JSON serialization/deserialization thật trong chuỗi đã mock, nên lỗi cấu hình message converter có thể bị bỏ sót.
- Một test có thể xanh dù request thật bị sai, vì mock trả kết quả theo lời gọi đã được định nghĩa sẵn.

Deep stubs không phải lúc nào cũng sai. Chúng có thể hữu ích với API fluent đơn giản hoặc một số test tương tác rất hẹp. Tuy nhiên, với HTTP client, chúng thường thay thế chính phần hành vi cần kiểm thử: giao tiếp HTTP và chuyển đổi dữ liệu.

## 2. Tách logic nghiệp vụ khỏi HTTP client

Service nghiệp vụ thường không cần biết `RestClient` có những method nào. Nó chỉ cần một khả năng ở mức ứng dụng, ví dụ “tra cứu tồn kho theo SKU”. Ta có thể biểu diễn khả năng đó bằng một interface do ứng dụng sở hữu.

```java
public interface InventoryGateway {
    InventoryItem findBySku(String sku);
}

public record InventoryItem(String sku, int availableQuantity) {
}
```

Service nghiệp vụ phụ thuộc vào interface:

```java
public class OrderService {

    private final InventoryGateway inventoryGateway;

    public OrderService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    public boolean canFulfill(String sku, int requestedQuantity) {
        InventoryItem item = inventoryGateway.findBySku(sku);
        return item.availableQuantity() >= requestedQuantity;
    }
}
```

Unit test của `OrderService` chỉ cần mock `InventoryGateway`:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    InventoryGateway inventoryGateway;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldAllowOrderWhenStockIsEnough() {
        when(inventoryGateway.findBySku("SKU-1"))
                .thenReturn(new InventoryItem("SKU-1", 12));

        assertThat(orderService.canFulfill("SKU-1", 5)).isTrue();

        verify(inventoryGateway).findBySku("SKU-1");
    }

    @Test
    void shouldRejectOrderWhenStockIsInsufficient() {
        when(inventoryGateway.findBySku("SKU-1"))
                .thenReturn(new InventoryItem("SKU-1", 3));

        assertThat(orderService.canFulfill("SKU-1", 5)).isFalse();
    }
}
```

Test này tập trung vào quy tắc nghiệp vụ: số lượng yêu cầu có được đáp ứng bởi tồn kho hay không. Nó không cần biết dữ liệu tồn kho đến từ HTTP, database, cache hay một nguồn khác. Interface đóng vai trò ranh giới giữa logic nghiệp vụ và phần tích hợp bên ngoài.

Lớp triển khai interface sẽ sử dụng HTTP client:

```java
public class InventoryHttpAdapter implements InventoryGateway {

    private final RestClient restClient;

    public InventoryHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Adapter này là nơi cần kiểm tra cách HTTP request được tạo và response được chuyển thành `InventoryItem`. Thay vì mock từng method của `RestClient`, ta có thể chạy adapter với một `RestClient` thật được nối tới mock HTTP server.

## 3. Dùng `MockRestServiceServer` với `RestClient`

Spring Test cung cấp `MockRestServiceServer` để kiểm thử code sử dụng `RestClient` hoặc `RestTemplate` mà không cần gọi dịch vụ bên ngoài. Mock server nhận request do HTTP client phát ra, cho phép đặt expectation về URL, method, header và body, rồi trả về response giả lập.

Với `RestClient`, Spring Framework hỗ trợ bind mock server vào `RestClient.Builder` từ Spring Framework 6.1. Cần bind trước khi gọi `build()` để builder sử dụng request factory do mock server cấu hình.

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.GET;

@Test
void shouldReadInventoryItemFromHttpResponse() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example");

    MockRestServiceServer server = MockRestServiceServer
            .bindTo(builder)
            .build();

    RestClient restClient = builder.build();
    InventoryHttpAdapter adapter = new InventoryHttpAdapter(restClient);

    server.expect(requestTo("https://inventory.example/api/inventory/SKU-1"))
            .andExpect(method(GET))
            .andExpect(header("Accept", MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess(
                    """
                    {"sku":"SKU-1","availableQuantity":12}
                    """,
                    MediaType.APPLICATION_JSON
            ));

    InventoryItem item = adapter.findBySku("SKU-1");

    assertThat(item).isEqualTo(new InventoryItem("SKU-1", 12));
    server.verify();
}
```

Test này sử dụng HTTP client thật của Spring. `MockRestServiceServer` chặn request ở request factory và trả response đã khai báo. Do đó test thực sự đi qua chuỗi `RestClient` mà ứng dụng dùng, bao gồm việc dựng URI, gắn header, thực hiện exchange và deserialize JSON.

### Ý nghĩa của các bước

1. Tạo `RestClient.Builder` với base URL của dịch vụ.
2. Bind `MockRestServiceServer` vào builder.
3. Build `RestClient` sau khi đã bind mock server.
4. Tạo adapter bằng client thật.
5. Đặt expectation cho URL, HTTP method và header.
6. Khai báo response JSON giả lập.
7. Gọi adapter như code production.
8. Kiểm tra DTO nhận được và gọi `server.verify()` để xác nhận request dự kiến đã xảy ra.

Không cần dựng các mock `RequestHeadersUriSpec`, `RequestHeadersSpec`, `ResponseSpec` hoặc các interface trung gian khác. Test quan sát request ở ranh giới HTTP.

## 4. Kiểm tra request body, header và response của POST

Đối với client gửi dữ liệu, mock server có thể kiểm tra JSON request body và trả response phù hợp.

Giả sử adapter tạo đơn hàng:

```java
public record CreateOrderRequest(String sku, int quantity) {
}

public record OrderResponse(long id, String status) {
}

public class OrderHttpAdapter {

    private final RestClient restClient;

    public OrderHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    public OrderResponse create(CreateOrderRequest request) {
        return restClient.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(OrderResponse.class);
    }
}
```

Test kiểm tra method, URL, content type và JSON body:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.POST;

@Test
void shouldSendOrderAsJsonAndReadCreatedOrder() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://orders.example");
    MockRestServiceServer server = MockRestServiceServer
            .bindTo(builder)
            .build();

    OrderHttpAdapter adapter = new OrderHttpAdapter(builder.build());

    server.expect(requestTo("https://orders.example/api/orders"))
            .andExpect(method(POST))
            .andExpect(header("Content-Type", MediaType.APPLICATION_JSON_VALUE))
            .andExpect(content().json("""
                    {"sku":"SKU-1","quantity":2}
                    """))
            .andRespond(withSuccess(
                    """
                    {"id":101,"status":"CREATED"}
                    """,
                    MediaType.APPLICATION_JSON
            ));

    OrderResponse response = adapter.create(new CreateOrderRequest("SKU-1", 2));

    assertThat(response).isEqualTo(new OrderResponse(101L, "CREATED"));
    server.verify();
}
```

Expectation `content().json(...)` so sánh cấu trúc JSON. Nó không buộc test phụ thuộc vào khoảng trắng hoặc thứ tự property trong chuỗi JSON. Nếu thứ tự hoặc định dạng byte thực sự là hợp đồng cần xác nhận, có thể dùng matcher body phù hợp hơn.

## 5. Kiểm tra status lỗi và cách adapter xử lý exception

HTTP adapter không chỉ cần đọc response thành công. Nó còn phải có hành vi rõ ràng khi dịch vụ bên ngoài trả về `4xx` hoặc `5xx`, khi timeout hoặc khi body lỗi không đúng schema.

`RestClient.retrieve()` mặc định chuyển response status thuộc nhóm lỗi thành exception như `HttpClientErrorException` hoặc `HttpServerErrorException`. Adapter có thể để exception đi lên, hoặc đăng ký `onStatus(...)` để ánh xạ sang exception miền nghiệp vụ.

Ví dụ adapter ánh xạ 404 thành exception riêng:

```java
public class InventoryItemNotFoundException extends RuntimeException {
    public InventoryItemNotFoundException(String sku) {
        super("Inventory item not found: " + sku);
    }
}

public class InventoryHttpAdapter implements InventoryGateway {

    private final RestClient restClient;

    public InventoryHttpAdapter(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .onStatus(status -> status.value() == 404, (request, response) -> {
                    throw new InventoryItemNotFoundException(sku);
                })
                .body(InventoryItem.class);
    }
}
```

Mock server có thể trả 404 và test xác nhận exception:

```java
server.expect(requestTo("https://inventory.example/api/inventory/MISSING"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> adapter.findBySku("MISSING"))
        .isInstanceOf(InventoryItemNotFoundException.class)
        .hasMessage("Inventory item not found: MISSING");

server.verify();
```

Test này kiểm tra adapter phản ứng đúng với HTTP status thực tế được mock server trả về. Nếu adapter không có logic ánh xạ lỗi riêng, có thể xác nhận exception mặc định của `RestClient`.

## 6. Kiểm thử `RestTemplate` với cùng cách tiếp cận

`RestTemplate` là HTTP client đồng bộ lâu đời của Spring. `MockRestServiceServer` hỗ trợ bind trực tiếp vào instance `RestTemplate`:

```java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();

server.expect(requestTo("https://catalog.example/api/products/42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"id":42,"name":"Keyboard"}
                """,
                MediaType.APPLICATION_JSON
        ));

Product product = restTemplate.getForObject(
        "https://catalog.example/api/products/{id}",
        Product.class,
        42
);

assertThat(product).isEqualTo(new Product(42L, "Keyboard"));
server.verify();
```

Điểm quan trọng vẫn giống `RestClient`: test dùng `RestTemplate` thật và mock server ở tầng HTTP. Không cần mock các thành phần nội bộ của client.

## 7. Kiểm thử `WebClient` bằng mock HTTP server

`WebClient` có API fluent và reactive. Nó trả về `Mono` hoặc `Flux`, do đó deep stubbing thường còn phức tạp hơn. Đối với adapter sử dụng `WebClient`, một mock HTTP server như OkHttp `MockWebServer` hoặc WireMock cho phép gửi request qua HTTP stack thật của `WebClient`.

Ví dụ adapter:

```java
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return webClient.get()
                .uri("/api/inventory/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
```

Test với `MockWebServer`:

```java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import reactor.test.StepVerifier;

class ReactiveInventoryClientTest {

    private MockWebServer server;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void shouldCallInventoryEndpointAndDecodeResponse() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"sku":"SKU-1","availableQuantity":12}
                        """));

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();
        ReactiveInventoryClient client = new ReactiveInventoryClient(webClient);

        StepVerifier.create(client.findBySku("SKU-1"))
                .expectNext(new InventoryItem("SKU-1", 12))
                .verifyComplete();

        RecordedRequest request = server.takeRequest();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/api/inventory/SKU-1");
        assertThat(request.getHeader("Accept")).contains("application/json");
    }
}
```

`MockWebServer` mở một cổng loopback tạm thời và trả các response đã enqueue. `WebClient` gửi request qua HTTP connector bình thường; `StepVerifier` subscribe vào `Mono`, chờ kết quả và xác nhận item được phát ra. Sau đó test đọc `RecordedRequest` để kiểm tra method, path và header đã gửi.

Test cần các dependency test phù hợp, thường gồm OkHttp MockWebServer và `reactor-test`. Hãy dùng phiên bản tương thích với Java và dependency management của project.

### Kiểm tra response lỗi trong WebClient

`retrieve()` của `WebClient` mặc định tạo `WebClientResponseException` cho status lỗi. Có thể enqueue response 404 và xác nhận lỗi bằng Reactor Test:

```java
server.enqueue(new MockResponse().setResponseCode(404));

StepVerifier.create(client.findBySku("MISSING"))
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
```

Nếu adapter có `onStatus(...)` để ánh xạ exception, test có thể kiểm tra exception miền nghiệp vụ tương ứng. Cách này thực sự đi qua status handling của `WebClient`, thay vì chỉ stub một `Mono.error(...)` ở giữa chuỗi fluent.

## 8. Khi nào nên mock interface, khi nào nên mock HTTP?

Hai loại test cần trả lời hai câu hỏi khác nhau:

| Mục tiêu test | Cách thay thế dependency | Điều test xác nhận |
| --- | --- | --- |
| Unit test service nghiệp vụ | Mock interface như `InventoryGateway`. | Quy tắc nghiệp vụ và cách service phản ứng với dữ liệu/kết quả từ gateway. |
| Test HTTP adapter dùng `RestClient` | `MockRestServiceServer` bind vào `RestClient.Builder`. | Method, URL, header, request body, response status và deserialize. |
| Test HTTP adapter dùng `RestTemplate` | `MockRestServiceServer` bind vào `RestTemplate`. | Request/response qua HTTP client đồng bộ. |
| Test HTTP adapter dùng `WebClient` | `MockWebServer` hoặc WireMock. | Request thực tế qua HTTP connector, reactive body và status handling. |
| Test tích hợp với dịch vụ thật | Test environment hoặc service container. | Khả năng tương tác với server thật và hợp đồng liên dịch vụ trong môi trường gần thực tế. |

Một nguyên tắc dễ áp dụng: mock ở ranh giới do ứng dụng sở hữu; dùng mock server ở ranh giới HTTP. Tránh mock sâu vào các đối tượng fluent trung gian của framework.

## 9. Dùng Spring Boot `@RestClientTest` khi phù hợp

Nếu dự án dùng Spring Boot, `@RestClientTest` cung cấp test slice dành cho thành phần gọi REST. Nó có thể cấu hình các thành phần client cần thiết và `MockRestServiceServer` để kiểm tra adapter mà không nạp toàn bộ ứng dụng.

Ví dụ dạng tổng quát:

```java
@RestClientTest(InventoryHttpAdapter.class)
class InventoryHttpAdapterBootTest {

    @Autowired
    private InventoryHttpAdapter inventoryHttpAdapter;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void shouldReadInventoryItem() {
        server.expect(requestTo("https://inventory.example/api/inventory/SKU-1"))
                .andRespond(withSuccess(
                        """
                        {"sku":"SKU-1","availableQuantity":12}
                        """,
                        MediaType.APPLICATION_JSON
                ));

        assertThat(inventoryHttpAdapter.findBySku("SKU-1"))
                .isEqualTo(new InventoryItem("SKU-1", 12));

        server.verify();
    }
}
```

`@RestClientTest` là tính năng của Spring Boot, không phải annotation lõi của Spring Framework. Khả năng auto-configure và bind server phụ thuộc phiên bản Boot và loại client được sử dụng. Với Boot hỗ trợ `RestClient`, có thể dùng test slice này để cấu hình builder và mock server; nếu project dùng phiên bản khác, hãy kiểm tra tài liệu của đúng phiên bản hoặc cấu hình builder/server tường minh như ví dụ trước.

## 10. Những điều mock HTTP server kiểm tra được và giới hạn của nó

Mock HTTP server kiểm tra được nhiều hành vi quan trọng ở ranh giới client:

- HTTP method và URL mà adapter gửi.
- Path variable, query parameter và encoding.
- Header request như `Accept`, `Content-Type`, authorization hoặc correlation ID.
- Request body JSON hoặc dữ liệu khác được serialize.
- Response status, response header và body.
- JSON mapping, error handling và cách adapter chuyển dữ liệu thành kiểu miền.

Tuy nhiên, mock server không chứng minh dịch vụ bên ngoài đang hoạt động hoặc hợp đồng của nó chưa thay đổi. Nó cũng không thay thế test mạng, TLS, DNS, load balancer, timeout ở hạ tầng thật hoặc tương tác với một hệ thống có trạng thái thực.

Khi các hành vi đó quan trọng, có thể bổ sung test tích hợp dùng container hoặc môi trường kiểm thử của dịch vụ. Không cần biến mọi unit test thành end-to-end test; chọn cấp test theo rủi ro và hợp đồng cần xác nhận.

## 11. Các lỗi thiết kế test thường gặp

**Mock toàn bộ chuỗi fluent của `RestClient` hoặc `WebClient`.**

Test bị gắn với thứ tự method và không kiểm tra request thực tế. Dùng mock interface nghiệp vụ cho service, hoặc mock HTTP server cho adapter.

**Dùng `RETURNS_DEEP_STUBS` để né việc tạo các mock trung gian.**

Deep stubs làm test ngắn hơn nhưng không làm test có ý nghĩa hơn nếu toàn bộ HTTP exchange bị giả lập. Nó che giấu lỗi URL, header, serialization và status handling.

**Mock `RestClient` trong unit test rồi kết luận adapter đã gửi đúng request.**

Mock một object client chỉ xác nhận interaction đã được stub. Muốn xác nhận HTTP request, hãy dùng `MockRestServiceServer` hoặc mock server tương đương.

**Không gọi `server.verify()`.**

Nếu không verify, expectation chưa được đáp ứng có thể không được báo theo cách test mong muốn. Gọi `verify()` để xác nhận các request dự kiến đã được thực hiện.

**Bind mock server sau khi đã build client.**

Với `RestClient`, bind `MockRestServiceServer` vào builder trước khi gọi `builder.build()`. Nếu client đã được tạo từ request factory khác, mock server có thể không nằm trên đường request của client.

**Không kiểm tra header hoặc body request.**

Một response giả lập đúng không chứng minh request đúng. Đặt expectation cho các header, method, URL và body thuộc hợp đồng outbound.

**Dùng `MockRestServiceServer` cho mọi loại client.**

MockRestServiceServer phù hợp với `RestClient` và `RestTemplate`. Với `WebClient`, thường dùng MockWebServer hoặc WireMock để kiểm tra request qua HTTP connector.

**Chỉ kiểm tra response thành công.**

Client cần xử lý 404, 4xx, 5xx, body lỗi và các lỗi mạng theo hợp đồng. Hãy thêm test cho các tình huống lỗi quan trọng.

## 12. Quy trình lựa chọn chiến lược kiểm thử

Khi một service sử dụng HTTP client, hãy phân loại phần cần kiểm tra trước:

1. Nếu đang kiểm tra quyết định nghiệp vụ, tạo interface ở ranh giới ứng dụng và mock interface đó.
2. Nếu đang kiểm tra adapter gọi HTTP, giữ HTTP client thật và nối nó tới mock HTTP server.
3. Với `RestClient` hoặc `RestTemplate`, cân nhắc `MockRestServiceServer`.
4. Với `WebClient`, dùng MockWebServer hoặc WireMock và kiểm tra kết quả reactive bằng `StepVerifier` khi cần.
5. Đặt expectation cho method, URL, query, header và body request.
6. Trả response giả lập đại diện cho tình huống thành công và lỗi.
7. Kiểm tra DTO, exception hoặc kết quả miền mà adapter trả về.
8. Gọi `verify()` hoặc xác nhận recorded request để bảo đảm request đã được gửi đúng.
9. Chỉ dùng server thật hoặc service container khi cần kiểm tra hành vi không thể được mock server xác nhận.

## Kết luận

Mock sâu chuỗi fluent của HTTP client thường khiến test phụ thuộc vào chi tiết triển khai và bỏ qua chính hành vi HTTP cần xác nhận. Với logic nghiệp vụ, mock một interface hẹp do ứng dụng sở hữu. Với HTTP adapter, dùng client thật kết nối tới mock HTTP server để kiểm tra method, URL, header, body, status và chuyển đổi dữ liệu.

`MockRestServiceServer` là lựa chọn phù hợp cho `RestClient` và `RestTemplate`; `MockWebServer` hoặc WireMock phù hợp với `WebClient`. Cách chia ranh giới này giúp test tập trung vào hợp đồng mà mỗi lớp chịu trách nhiệm và ít bị ảnh hưởng khi chuỗi fluent nội bộ được thay đổi.
