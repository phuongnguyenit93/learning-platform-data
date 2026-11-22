# So sánh kết quả mô phỏng với HTTP qua máy chủ thật

## 1. Vì sao cần kiểm thử ở cả hai cấp?

Trong Spring, một endpoint có thể được kiểm thử bằng MockMvc hoặc WebTestClient bind vào mock infrastructure. Cách này cho phép gửi request qua các thành phần Spring web và kiểm tra status, header, body mà không cần khởi chạy server lắng nghe trên cổng mạng.

Một HTTP integration test lại khởi động server thật, thường bằng Spring Boot với cổng ngẫu nhiên, rồi gửi request qua HTTP. Request đi qua connector, socket và servlet/reactive server trước khi tới ứng dụng.

Hai cấp kiểm thử trả lời những câu hỏi khác nhau:

- **Kiểm thử mô phỏng** xác nhận routing, binding, validation, controller, exception handling và response contract trong web infrastructure mà test đã cấu hình.
- **Kiểm thử HTTP qua server thật** xác nhận các thành phần đó hoạt động khi có request HTTP thực đi vào server, đồng thời kiểm tra connector, port, filter chain và cách client nhận response.

Một test mô phỏng thành công không chứng minh ứng dụng đã bind port hoặc HTTP connector hoạt động. Một test HTTP thành công cũng không thay thế mọi test mô phỏng: khởi động server thường chậm hơn và làm việc cô lập một nhánh nhỏ trở nên khó hơn.

Bộ test tốt dùng mỗi cấp cho mục tiêu phù hợp, sau đó so sánh cùng một hợp đồng API để phát hiện khác biệt có ý nghĩa.

## 2. Phân biệt MockMvc, WebTestClient và HTTP client thật

### MockMvc

**MockMvc** thuộc Spring Test và kiểm thử Spring MVC bằng mock servlet request/response. Request được dispatch qua các thành phần MVC như DispatcherServlet, handler mapping, controller, argument resolver, message converter và exception resolver.

MockMvc không mở TCP socket và không cần Tomcat, Jetty hoặc servlet container đang lắng nghe trên port. Nó vẫn có thể kiểm tra nhiều thành phần Spring MVC, bao gồm filter nếu filter được đăng ký trong cấu hình test.

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42));
~~~

### WebTestClient

**WebTestClient** có thể chạy theo nhiều chế độ:

- Bind trực tiếp tới controller hoặc RouterFunction.
- Bind tới ApplicationContext mock.
- Bind tới server đang chạy bằng HTTP thật.

Vì vậy, chỉ nhìn thấy WebTestClient trong source code chưa đủ để kết luận test có sử dụng socket. Cần xem cách tạo client:

~~~java
WebTestClient.bindToApplicationContext(context)
        .build();
~~~

Đây là mock web infrastructure.

~~~java
WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Đây là HTTP client kết nối tới server đang chạy.

### HTTP client qua máy chủ thật

Với Spring Boot, test có thể khởi động embedded server trên cổng ngẫu nhiên:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {
}
~~~

Sau đó dùng TestRestTemplate, RestTestClient (khi phiên bản Spring hỗ trợ) hoặc WebTestClient bind tới server để gửi request.

| Cách kiểm thử | Có server lắng nghe trên port? | Có HTTP socket thật? | Phần chính được kiểm tra |
|---|---:|---:|---|
| MockMvc | Không | Không | Spring MVC request processing |
| WebTestClient bind controller/context | Không | Không | WebFlux/MVC mock infrastructure |
| WebTestClient bind server | Có | Có | HTTP qua server đang chạy |
| TestRestTemplate / RestTestClient bind server | Có | Có | HTTP qua server đang chạy |
| Client gọi staging qua proxy | Có | Có | Ứng dụng cùng các tầng hạ tầng nằm trên đường request |

## 3. Cùng một endpoint để so sánh công bằng

Giả sử ứng dụng cung cấp API đọc đơn hàng:

~~~java
public record OrderResponse(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable Long id) {
        return orderService.findById(id);
    }
}
~~~

Service trả về đơn hàng hoặc ném exception nếu không tìm thấy:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderResponse findById(Long id) {
        Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus()
        );
    }
}
~~~

Để so sánh kết quả hai cấp, cần kiểm soát đầu vào. Ví dụ, cả hai test đều tạo một đơn hàng có số đơn ORD-42 và trạng thái PAID, sau đó gọi GET /api/orders/{id}.

Không nên so sánh một MockMvc test mock OrderService với một HTTP test truy cập database thật rồi kết luận mọi khác biệt là do transport. Hai test đó đang dùng cấu hình và dependency khác nhau. Nếu muốn đo riêng ảnh hưởng của transport, hãy giữ controller, service, repository, cấu hình và fixture giống nhau; chỉ thay cách gửi request.

## 4. Cách tổ chức hai test cùng dùng application logic

Có thể dùng hai kiểu Spring Boot test:

- **webEnvironment = MOCK** kết hợp **@AutoConfigureMockMvc** để kiểm tra qua MockMvc.
- **webEnvironment = RANDOM_PORT** để khởi động embedded server và gửi HTTP thật.

Cả hai đều nạp ứng dụng Spring Boot. Khác biệt quan trọng nằm ở web environment và client dùng để gửi request.

### Test mô phỏng với MockMvc

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderMockMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orderRepository;

    private Long orderId;

    @Test
    void shouldReturnTheStoredOrder() throws Exception {
        Order saved = orderRepository.save(
                new Order("ORD-42", "PAID")
        );
        orderId = saved.getId();

        mockMvc.perform(get("/api/orders/{id}", orderId)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(saved.getId()))
                .andExpect(jsonPath("$.orderNumber").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }
}
~~~

Test này nạp ứng dụng và gọi qua Spring MVC infrastructure. Nó kiểm tra việc route request tới controller, truy vấn service/repository, chuyển DTO thành JSON và tạo response.

Nó chưa kiểm tra embedded server bind port, TCP connection hoặc HTTP connector.

### Test qua HTTP thật

Với Spring Boot, có thể dùng TestRestTemplate:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orderRepository;

    private Long orderId;

    @Test
    void shouldReturnTheStoredOrderOverHttp() {
        Order saved = orderRepository.save(
                new Order("ORD-42", "PAID")
        );
        orderId = saved.getId();

        ResponseEntity<OrderResponse> response = http.getForEntity(
                "/api/orders/{id}",
                OrderResponse.class,
                orderId
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType())
                .isCompatibleWith(MediaType.APPLICATION_JSON);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().id()).isEqualTo(saved.getId());
        assertThat(response.getBody().orderNumber()).isEqualTo("ORD-42");
        assertThat(response.getBody().status()).isEqualTo("PAID");
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }
}
~~~

Ở đây, Spring Boot khởi chạy embedded server trên port ngẫu nhiên và cấu hình TestRestTemplate để gọi server đó. Request đi qua HTTP connector trước khi tới DispatcherServlet.

Nếu project dùng Spring Framework 7 và phiên bản Spring Boot tương ứng, có thể dùng RestTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderRestTestClientIntegrationTest {

    @Autowired
    RestTestClient client;

    @Test
    void shouldReturnAnOrderOverHttp() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

RestTestClient phải được kết nối với server thật. Nếu tạo client bằng một kiểu bind mock khác, test sẽ không còn kiểm tra HTTP socket.

## 5. So sánh cùng hợp đồng response

Cần so sánh những phần mà API cam kết với client:

| Phần response | Điều cần xác nhận |
|---|---|
| Status | Mã HTTP đúng với kết quả nghiệp vụ |
| Content-Type | Media type phù hợp, ví dụ application/json |
| Header nghiệp vụ | Location, ETag, Cache-Control hoặc header do API công bố |
| Body | Các field, kiểu dữ liệu và giá trị đúng |
| Error response | Status và schema lỗi thống nhất |
| Cookie/session | Hành vi đúng nếu API sử dụng cookie hoặc session |
| Security | Request không xác thực hoặc thiếu quyền bị xử lý đúng |
| Encoding | Nội dung được giải mã đúng theo contract |

Không nhất thiết mọi header phải giống hệt giữa hai môi trường. Ví dụ, header liên quan tới framing, độ dài body, connection hoặc server implementation có thể khác do cách response được ghi trên transport.

Các header như Transfer-Encoding, Content-Length, Connection, Date hoặc header đặc thù của container không nên được so sánh như một phần của API contract trừ khi sản phẩm có yêu cầu rõ ràng.

Tương tự, không nên so sánh raw JSON string nếu thứ tự property hoặc khoảng trắng không thuộc contract. Dùng JSONPath hoặc JSON structural assertion để kiểm tra nội dung.

## 6. Tạo bộ assertion dùng chung cho cùng một response contract

Nếu nhiều test client cần xác nhận cùng một schema, có thể gom assertion vào helper. Ví dụ với AssertJ:

~~~java
static void assertOrderResponse(
        OrderResponse actual,
        Long expectedId,
        String expectedNumber,
        String expectedStatus
) {
    assertThat(actual).isNotNull();
    assertThat(actual.id()).isEqualTo(expectedId);
    assertThat(actual.orderNumber()).isEqualTo(expectedNumber);
    assertThat(actual.status()).isEqualTo(expectedStatus);
}
~~~

Test HTTP có thể gọi helper sau khi nhận DTO. MockMvc lại có thể kiểm tra JSONPath trực tiếp. Nếu muốn dùng cùng helper cho cả hai, hãy parse JSON response thành DTO trước khi so sánh, nhưng không cần làm vậy nếu việc parse thêm không đem lại giá trị.

Một lựa chọn khác là tạo một helper nhận ResultActions hoặc ResponseEntity, nhưng tránh trừu tượng hóa quá sớm. Hai client có API assertion khác nhau; giữ phần request rõ ràng thường giúp test dễ đọc hơn.

Điều quan trọng là expected values phải đến từ fixture hoặc hợp đồng chung, không lấy expected bằng cách gọi lại chính method production mà test đang kiểm tra.

## 7. So sánh status và lỗi nghiệp vụ

Ví dụ endpoint không tìm thấy đơn hàng. Ứng dụng có thể dùng @ControllerAdvice để chuyển OrderNotFoundException thành HTTP 404:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }
}

public record ApiError(String code, String message) {
}
~~~

MockMvc test:

~~~java
mockMvc.perform(get("/api/orders/999999"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
~~~

HTTP test:

~~~java
ResponseEntity<ApiError> response = http.getForEntity(
        "/api/orders/999999",
        ApiError.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
assertThat(response.getBody()).isNotNull();
assertThat(response.getBody().code()).isEqualTo("ORDER_NOT_FOUND");
~~~

Hai test nên xác nhận cùng status và error code. Nếu MockMvc trả 404 nhưng HTTP thật trả 500, hãy kiểm tra khác biệt trong cấu hình exception resolver, filter, servlet container hoặc cấu hình ứng dụng được nạp ở mỗi test.

Với TestRestTemplate, 4xx/5xx thường được trả về trong ResponseEntity theo cách phù hợp để test kiểm tra status và body. Với RestClient/RestTestClient, API xử lý status có thể khác; cấu hình error handler hoặc dùng expectation API tương ứng.

## 8. Validation và request body

Một test mô phỏng có thể xác nhận Spring bind JSON vào DTO và chạy Bean Validation:

~~~java
public record CreateOrderRequest(
        @NotBlank String orderNumber,
        @NotBlank String status
) {
}
~~~

Controller:

~~~java
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

MockMvc test:

~~~java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "orderNumber": "",
                          "status": "PAID"
                        }
                        """))
        .andExpect(status().isBadRequest());
~~~

HTTP test gửi JSON qua connector:

~~~java
ResponseEntity<ApiError> response = http.postForEntity(
        "/api/orders",
        new CreateOrderRequest("", "PAID"),
        ApiError.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
~~~

MockMvc xác nhận quá trình binding/validation trong Spring MVC. HTTP test còn xác nhận request body đi qua HTTP client, connector và server trước khi được Spring xử lý. Nếu request có encoding, content length hoặc chunked transfer đặc biệt, HTTP test có thể phát hiện khác biệt mà mock request không mô phỏng.

## 9. Filter, Security và cấu hình web

MockMvc có thể chạy filter và Spring Security filter chain nếu chúng được cấu hình trong test context. Nhưng cấu hình test có thể khác cấu hình chạy server nếu slice test không nạp đủ filter hoặc security auto-configuration.

Vì vậy, khi so sánh:

- Kiểm tra MockMvc có đăng ký filter cần thiết không.
- Xác nhận security configuration được nạp trong cả hai test.
- Dùng cùng user, role, token hoặc cookie trong hai request.
- Xác nhận status 401/403 và error body theo API contract.
- Kiểm tra CORS, CSRF hoặc forwarded headers khi chúng thuộc yêu cầu của endpoint.

Ví dụ MockMvc với Spring Security có thể thêm user vào request bằng post-processor:

~~~java
mockMvc.perform(get("/api/profile").with(user("alice").roles("USER")))
        .andExpect(status().isOk());
~~~

HTTP test cần gửi thông tin xác thực mà client thật sẽ sử dụng, ví dụ bearer token:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

HttpEntity<Void> request = new HttpEntity<>(headers);

ResponseEntity<ProfileResponse> response = http.exchange(
        "/api/profile",
        HttpMethod.GET,
        request,
        ProfileResponse.class
);

assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
~~~

MockMvc post-processor user(...) mô phỏng principal trong security context của test. Nó không kiểm tra token parsing hoặc chữ ký JWT. HTTP test có bearer token đi qua authentication filter và có thể kiểm tra nhiều phần hơn của security pipeline.

Nếu muốn kiểm tra JWT decoder hoặc identity provider thật, cần cấu hình test tương ứng hoặc môi trường kiểm thử có issuer phù hợp. Một request localhost với token giả không chứng minh tích hợp identity provider production.

## 10. Khác biệt do server và connector

Khi HTTP request tới server thật, một số hành vi xuất hiện mà mock infrastructure không thể xác nhận đầy đủ:

- Server thực sự bind port và chấp nhận kết nối.
- HTTP connector đọc request line, headers và body từ socket.
- Server áp dụng giới hạn header/body của connector.
- Connection được đóng hoặc tái sử dụng theo chính sách server.
- Client nhận response qua HTTP stack và giải mã body.
- Compression, chunked transfer hoặc HTTP version được xử lý bởi connector nếu được cấu hình.

Một vài ví dụ lỗi chỉ xuất hiện ở cấp HTTP:

- Ứng dụng chạy tốt trong MockMvc nhưng server không khởi động vì port hoặc cấu hình connector sai.
- Header quá lớn bị connector từ chối trước khi request tới controller.
- Multipart request có hành vi khác do giới hạn upload.
- Response streaming bị buffer ở connector hoặc proxy.
- Connection bị đóng khi client ngắt giữa body.
- HTTP/2 hoặc TLS không được bật như cấu hình triển khai mong muốn.

HTTP integration test với embedded server có thể phát hiện lỗi ở connector của server test. Nó chưa kiểm tra reverse proxy, ingress, TLS termination hoặc network policy nếu request đi thẳng vào localhost.

## 11. Transaction và dữ liệu test có thể làm kết quả khác nhau

Một khác biệt lớn giữa MockMvc và HTTP thật là ranh giới thực thi request.

MockMvc dispatch request trong cùng tiến trình test. Với request đồng bộ, một số context thread-bound có thể tồn tại trong cùng thread; tuy nhiên, không nên giả định mọi async dispatch đều chia sẻ transaction của test.

Với RANDOM_PORT, request được xử lý bởi server trên thread hoặc reactive pipeline riêng. Transaction của test method không tự truyền qua ranh giới HTTP. Vì vậy, @Transactional trên test không tự rollback dữ liệu do endpoint ghi vào database.

Để so sánh hai kết quả, hãy dùng fixture có vòng đời rõ:

1. Tạo bản ghi test với ID hoặc namespace riêng.
2. Gửi request.
3. Xác nhận status và response.
4. Kiểm tra persistence nếu đó là một phần contract.
5. Xóa đúng bản ghi đã tạo trong cleanup.

Không dùng deleteAll() trong cleanup khi test khác có thể chạy song song trên cùng database. Nếu hai test cần dữ liệu giống nhau, hãy tạo cùng fixture ở đầu mỗi test thay vì phụ thuộc test trước.

## 12. So sánh response không có nghĩa raw bytes phải giống nhau

Mock response và response từ server thật có thể khác nhau ở những chi tiết không thuộc contract:

| Khác biệt có thể thấy | Vì sao có thể khác | Cách so sánh |
|---|---|---|
| JSON có khoảng trắng hoặc thứ tự property khác | Serializer hoặc cách render | Parse JSON và so sánh cấu trúc |
| Content-Length khác hoặc không có | Framing và cách ghi response | Chỉ assert nếu API có yêu cầu rõ |
| Transfer-Encoding xuất hiện | HTTP/1.1 streaming/chunked response | Không assert như business contract chung |
| Date hoặc server header khác | Container và thời điểm chạy | Bỏ qua nếu không thuộc yêu cầu |
| Cookie có attribute khác | Session/security configuration hoặc domain/path | Assert thuộc tính bảo mật cần thiết |
| URL trong Location khác | Base URL, context path hoặc proxy headers | Kiểm tra URI đích theo contract |
| Error message khác | Exception mapping hoặc môi trường | Ưu tiên kiểm tra error code/schema ổn định |
| Charset/encoding khác | Message converter hoặc HTTP headers | Assert media type và nội dung được giải mã |

Nếu API cam kết một header cụ thể, hãy kiểm tra nó ở cả hai cấp. Nếu header chỉ là chi tiết do container tự sinh, việc ép hai test phải giống nhau có thể làm test giòn và không phản ánh hợp đồng thực.

## 13. Kiểm thử multipart, cookie và session

MockMvc có API tạo multipart request trong bộ nhớ:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "report.txt",
        "text/plain",
        "hello".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/files").file(file))
        .andExpect(status().isCreated());
~~~

HTTP test gửi multipart qua client thật, nên kiểm tra được quá trình đóng gói multipart và giới hạn upload ở server. Nếu ứng dụng nhận file lớn hoặc dùng streaming upload, test qua server thật có giá trị hơn.

Với cookie/session, MockMvc có thể tạo session và đặt attribute trực tiếp. HTTP client cần gửi cookie từ response trước để mô phỏng client duy trì session. Hai cách không hoàn toàn tương đương: MockMvc có thể đặt trạng thái session nội bộ, còn HTTP test kiểm tra cookie được phát và gửi qua giao thức.

## 14. Async request và streaming

MockMvc hỗ trợ async request và có thể dùng asyncDispatch để kiểm tra response sau khi xử lý hoàn tất. Nó hữu ích để xác nhận async lifecycle và body cuối cùng.

Tuy nhiên, MockMvc không chứng minh client nhận được từng phần dữ liệu trong khi stream còn mở, cũng không xác nhận thời điểm flush qua socket.

Với SSE hoặc StreamingResponseBody, HTTP test cần đọc response khi server đang chạy và xác nhận event/chunk theo hợp đồng. Không nên so sánh ranh giới HTTP chunk vì chunk framing phụ thuộc giao thức; hãy kiểm tra ranh giới event theo định dạng SSE hoặc nội dung byte mà API công bố.

Nếu endpoint stream dài, test cần điều khiển server gửi event đầu tiên, giữ kết nối mở, rồi mới gửi event tiếp theo hoặc hoàn tất. Tránh dùng Thread.sleep() để đoán thời điểm event đến.

## 15. Một ma trận test giúp phát hiện khác biệt

Có thể tổ chức các test theo ma trận sau:

| Tình huống | MockMvc / mock-bound client | HTTP qua server thật |
|---|---|---|
| GET thành công và JSON response | Nên có | Nên có cho các luồng quan trọng |
| POST tạo tài nguyên | Nên có | Nên có để xác nhận connector và serialization |
| Validation lỗi | Nên có | Có cho một số contract quan trọng |
| Error mapping 404/409/500 | Nên có | Nên có cho error path quan trọng |
| Security principal/role | Nên có | Nên có để kiểm tra authentication qua HTTP |
| Multipart upload | Có thể kiểm tra mapping | Cần khi upload/connector limits quan trọng |
| Cookie/session | Kiểm tra logic MVC/security | Cần khi cần xác nhận cookie qua HTTP |
| Async completion | Có với asyncDispatch | Cần khi phụ thuộc timing/transport |
| Streaming/SSE từng phần | Chỉ kiểm tra một phần | Cần |
| TLS, HTTP/2, proxy, network | Không | Cần môi trường tương ứng |

Không cần nhân đôi mọi test. Chọn một tập HTTP integration test đại diện cho những luồng mà transport hoặc full application configuration có thể ảnh hưởng. Các trường hợp logic chi tiết vẫn có thể được kiểm tra nhanh bằng MockMvc hoặc WebTestClient mock binding.

## 16. Chẩn đoán khi hai cấp test cho kết quả khác nhau

Nếu MockMvc pass nhưng HTTP test fail, hãy xác định request đã tới tầng nào:

1. **Server không khởi động hoặc connection refused:** kiểm tra port, server lifecycle, profile và cấu hình connector.
2. **HTTP status khác trước khi vào controller:** kiểm tra filter, security, context path, CORS và giới hạn connector.
3. **Controller được gọi nhưng body khác:** kiểm tra message converter, content negotiation, serialization và request headers.
4. **Chỉ dữ liệu persistence khác:** kiểm tra transaction boundary, fixture setup, cleanup và database dùng chung.
5. **Chỉ async/streaming khác:** kiểm tra timeout, flush, buffering, client disconnect và cách test đọc response.

Nếu HTTP test pass nhưng MockMvc fail, kiểm tra xem MockMvc test có nạp cùng controller advice, filter, security configuration, message converter và bean configuration hay không. Slice test thường cố ý chỉ nạp một phần context; khác biệt đó có thể là nguyên nhân.

Nếu cả hai test dùng cùng application context và cùng fixture mà vẫn khác nhau, tập trung vào phần request/response và transport. Ghi lại method, URI, headers, status, content type và body đã nhận để đối chiếu.

## 17. Tránh so sánh sai hoặc tạo test trùng lặp

Một số cách làm dễ dẫn tới kết luận sai:

- **Mock service ở một phía, database thật ở phía kia:** khác biệt có thể đến từ service/fixture chứ không phải HTTP.
- **Dùng ID tự sinh khác nhau rồi so sánh toàn bộ JSON:** kết quả khác là bình thường; so sánh field nghiệp vụ hoặc dùng cùng fixture.
- **So sánh raw JSON string:** thứ tự field, khoảng trắng hoặc format có thể khác dù JSON tương đương.
- **Assert mọi header:** header do container/connector sinh ra có thể thay đổi giữa môi trường.
- **Chỉ kiểm tra status:** status 200 không chứng minh body đầy đủ hoặc schema đúng.
- **Chạy toàn bộ suite với database dùng chung và cleanup quá rộng:** test có thể ảnh hưởng lẫn nhau.
- **Nhân đôi mọi test cho cả hai cấp:** làm suite chậm nhưng không tăng tương xứng giá trị.

Nên dùng một bộ test mock rộng cho các nhánh logic và response contract. Sau đó chọn một số luồng HTTP thật đại diện cho các tính năng có rủi ro ở connector, filter, security, serialization, persistence hoặc async transport.

## 18. Cách chọn cấp kiểm thử

| Câu hỏi cần trả lời | Cấp kiểm thử phù hợp |
|---|---|
| Controller có map URI và method đúng không? | MockMvc hoặc WebTestClient mock binding |
| DTO có được validate và serialize đúng không? | MockMvc/WebTestClient; bổ sung HTTP test cho contract quan trọng |
| Controller advice trả đúng error schema không? | MockMvc và một số HTTP integration test |
| Security filter chain thực tế có nhận bearer token không? | HTTP test qua server thật; MockMvc bổ sung cho nhánh role |
| Server có bind port và nhận request không? | RANDOM_PORT và HTTP client |
| Connector xử lý multipart/header/body limit thế nào? | HTTP test qua server thật |
| SSE/streaming có gửi dữ liệu khi kết nối còn mở không? | HTTP client đọc stream qua server thật |
| TLS, ingress, reverse proxy hoặc DNS hoạt động không? | Test qua môi trường có các tầng hạ tầng đó |

MockMvc và mock-bound WebTestClient giúp xác nhận hành vi của Spring web layer trong môi trường kiểm soát. HTTP test qua server thật bổ sung bằng chứng rằng request và response đi qua connector như client thực tế. Khi so sánh, hãy giữ cùng API contract và fixture, chỉ thay cấp transport cần kiểm tra. Nhờ vậy, một khác biệt trong test sẽ chỉ ra phần hệ thống cần điều tra thay vì phản ánh sự khác nhau ngẫu nhiên giữa hai bộ cấu hình.

