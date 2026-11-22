# Khác biệt giữa mock đối tượng API và máy chủ HTTP thật

Khi kiểm thử ứng dụng Spring, ta có thể mô phỏng request/response bằng các đối tượng do Spring Test cung cấp, hoặc khởi động một máy chủ HTTP thật rồi gửi request qua mạng. Hai cách này kiểm tra những ranh giới khác nhau của ứng dụng. Chọn đúng cách giúp test nhanh, ổn định và vẫn phát hiện được lỗi ở lớp hạ tầng cần bảo vệ.

Các mock object như `MockHttpServletRequest`, `MockHttpServletResponse`, `MockServerHttpRequest`, `MockServerHttpResponse` và `MockServerWebExchange` mô phỏng contract của Servlet hoặc WebFlux trong bộ nhớ. `MockMvc` và `WebTestClient` có thể sử dụng những mock object này để chạy một phần hoặc phần lớn pipeline web của Spring mà không mở cổng HTTP. Khi cần kiểm tra connector, socket, HTTP protocol hoặc cấu hình server thực tế, ta phải gửi request đến một máy chủ đang chạy.

## 1. Hai cách kiểm thử nằm ở những ranh giới khác nhau

**Mock đối tượng API** tạo các đối tượng đại diện cho request, response, session hoặc exchange. Test truyền chúng trực tiếp vào component đang kiểm tra. Không có client kết nối qua socket và không có server connector xử lý request.

**Máy chủ HTTP thật** khởi động một server như Tomcat, Jetty, Undertow hoặc Reactor Netty, sau đó dùng HTTP client gửi request đến port mà server đang lắng nghe. Request đi qua connector và pipeline web thực tế của ứng dụng.

| Khía cạnh | Mock object API / mock web environment | Máy chủ HTTP thật |
|---|---|---|
| Cách gọi | Gọi component bằng đối tượng mock hoặc dùng test client bind trong bộ nhớ | HTTP client gửi request đến host và port |
| Socket và network | Không có kết nối mạng thật | Có kết nối HTTP thật, thường qua loopback khi test local |
| Server connector | Không kiểm tra connector của server | Có kiểm tra connector và quá trình nhận request |
| HTTP parsing/framing | Được biểu diễn bởi đối tượng mock và framework test | Được xử lý bởi server connector |
| Spring MVC/WebFlux pipeline | Có thể kiểm tra trực tiếp hoặc qua mock server adapter | Chạy qua pipeline trong server đang hoạt động |
| Tốc độ | Thường nhanh và ít phụ thuộc môi trường | Chậm hơn do khởi động server và giao tiếp HTTP |
| Cách cô lập | Dễ dựng request và dependency theo từng test | Cần quản lý port, tài nguyên, dữ liệu và vòng đời server |
| Lỗi có thể phát hiện tốt | Logic controller/filter/handler, binding, validation và response theo phạm vi mock | Lỗi tích hợp server, connector, port, protocol và cấu hình chạy thật |

Mock object API không phải mock của nghiệp vụ theo nghĩa Mockito. Đây là các implementation test của contract web mà Spring cung cấp để component có thể được kiểm thử mà không cần container thật.

## 2. Các mức kiểm thử web với Spring

Không phải mọi test dùng mock object đều có cùng phạm vi. Có thể chia thành các mức sau:

```text
Unit test component
  Mock request/response/exchange
  Gọi trực tiếp interceptor, filter hoặc handler
          |
          v
Spring web test trong bộ nhớ
  MockMvc hoặc WebTestClient bind với controller/context
  Chạy Spring web pipeline mà không mở HTTP server
          |
          v
Integration test với server thật
  Khởi động embedded server
  Gửi HTTP request qua client và connector
```

Mỗi mức thêm một phần hạ tầng vào phạm vi kiểm tra. Khi một test thất bại, phạm vi càng nhỏ thì nguyên nhân thường càng dễ xác định. Khi cần xác minh các lớp hạ tầng cùng hoạt động, cần chọn mức kiểm thử rộng hơn.

## 3. Mock object API trong Spring MVC

Spring Test cung cấp nhiều mock object cho Servlet API trong package `org.springframework.mock.web`, chẳng hạn:

- `MockHttpServletRequest`: mô phỏng method, URI, parameter, header, body, session và attribute của request.
- `MockHttpServletResponse`: lưu status, header, cookie, redirect và nội dung response.
- `MockHttpSession`: mô phỏng session phía server.
- `MockServletContext`: mô phỏng ServletContext.
- `MockFilterChain`: hỗ trợ kiểm thử Servlet Filter.
- `MockServletConfig`: mô phỏng cấu hình của servlet.

Các đối tượng này hữu ích khi muốn gọi trực tiếp một thành phần phụ thuộc vào Servlet API, ví dụ `HandlerInterceptor`, `Filter`, một adapter hoặc một lớp tiện ích đọc request.

### 3.1. Gọi trực tiếp component với request/response mock

Ví dụ một interceptor đọc header và thêm một response header:

```java
public class RequestIdInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            return false;
        }

        response.setHeader("X-Request-Id", requestId);
        return true;
    }
}
```

Unit test có thể tạo request và response trong bộ nhớ:

```java
@Test
void copiesRequestIdToResponse() throws Exception {
    var request = new MockHttpServletRequest("GET", "/orders");
    var response = new MockHttpServletResponse();
    request.addHeader("X-Request-Id", "req-42");

    boolean proceed = new RequestIdInterceptor()
            .preHandle(request, response, new Object());

    assertTrue(proceed);
    assertEquals("req-42", response.getHeader("X-Request-Id"));
}
```

Test này kiểm tra logic của interceptor và cách nó thao tác với Servlet API. Nó không chứng minh interceptor đã được đăng ký trong `HandlerInterceptorRegistry`, được gắn vào đúng URL pattern hoặc được gọi trong request thực tế. Những điều đó thuộc phạm vi kiểm thử cấu hình MVC.

### 3.2. MockMvc: chạy Spring MVC pipeline mà không có server thật

`MockMvc` cung cấp API fluent để gửi request và kiểm tra response. Nó chạy `DispatcherServlet` cùng các thành phần MVC trong môi trường mock Servlet, không cần khởi động Tomcat, Jetty hoặc server Servlet khác.

Ví dụ:

```java
mockMvc.perform(get("/api/orders/42")
        .header("X-Request-Id", "req-42"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(42));
```

Có hai cách dựng `MockMvc` thường gặp:

```java
// Dựng nhanh với controller và MVC infrastructure tối thiểu
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController(orderService))
        .build();

// Dùng Spring WebApplicationContext của ứng dụng
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

`standaloneSetup` phù hợp với test controller tập trung, trong đó ta chủ động cung cấp controller và các thành phần cần thiết. `webAppContextSetup` sử dụng cấu hình Spring MVC trong `WebApplicationContext`, do đó phù hợp khi cần kiểm tra mapping, converter, formatter, validator, controller advice hoặc cấu hình MVC đã được đăng ký trong context. Filter có thể được thêm vào MockMvc thông qua cấu hình builder phù hợp.

Trong Spring Boot, `@WebMvcTest` thường được dùng để nạp một MVC slice và cung cấp `MockMvc`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenItExists() throws Exception {
        when(orderService.findById(42L))
                .thenReturn(new OrderResponse(42L, "PENDING"));

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
```

Ví dụ dùng các lớp `OrderController`, `OrderService` và `OrderResponse` giả định của ứng dụng. `@WebMvcTest` là annotation của Spring Boot Test; trong Spring Framework thuần, có thể dựng `MockMvc` bằng `MockMvcBuilders`.

MockMvc kiểm tra được nhiều phần của Spring MVC như handler mapping, argument resolver, data binding, validation, exception resolver, message converter và response status. Tuy nhiên, nó không kiểm tra Servlet container thật, socket, TLS, HTTP framing hoặc hành vi connector.

## 4. Mock object API trong Spring WebFlux

WebFlux có contract server reactive riêng, vì vậy không dùng mock Servlet để kiểm tra component nhận `ServerWebExchange`.

Các mock object thường dùng gồm:

- `MockServerHttpRequest`: tạo request reactive trong bộ nhớ.
- `MockServerHttpResponse`: ghi nhận status, header, cookie và body được ghi qua `DataBuffer`.
- `MockServerWebExchange`: gom request, response, session và ngữ cảnh của một lần trao đổi.

Ví dụ kiểm tra một `WebFilter` trực tiếp:

```java
var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/orders")
                .header("X-Tenant-Id", "tenant-a")
                .build());

WebFilterChain chain = nextExchange -> {
    nextExchange.getResponse().setStatusCode(HttpStatus.OK);
    return nextExchange.getResponse().setComplete();
};

filter.filter(exchange, chain).block();

assertEquals(HttpStatus.OK, exchange.getResponse().getStatusCode());
```

Đây là unit test cho filter và exchange. `block()` chỉ được dùng tại ranh giới test đồng bộ để chờ publisher hoàn tất. Trong mã production WebFlux, cần compose `Mono`/`Flux` và giữ luồng reactive.

### 4.1. WebTestClient có thể chạy trong bộ nhớ hoặc qua server thật

`WebTestClient` là HTTP client dành cho kiểm thử Spring web. Nó cung cấp cách viết request và assertion response nhất quán, nhưng phạm vi thực thi phụ thuộc cách bind:

| Cách bind | Phạm vi |
|---|---|
| `bindToController(...)` | Controller và hạ tầng mock tối thiểu |
| `bindToApplicationContext(...)` | WebFlux application context trong môi trường mock |
| `bindToRouterFunction(...)` | Router function và handler tương ứng |
| `bindToServer()` | Kết nối đến HTTP server đang chạy qua mạng |

Ví dụ bind với controller:

```java
WebTestClient client = WebTestClient
        .bindToController(new OrderController(orderService))
        .build();

client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

Ví dụ này dùng test infrastructure trong bộ nhớ. Dù API trông giống HTTP client, nó không mở socket đến một server thật.

Với Spring MVC, `MockMvcWebTestClient` cũng cho phép dùng API fluent của `WebTestClient` trên nền MockMvc. Vì vậy, cần xem cách client được bind thay vì chỉ nhìn tên lớp để xác định test có sử dụng network hay không.

## 5. Kiểm thử với máy chủ HTTP thật

Một test dùng server thật cần khởi động ứng dụng hoặc server trước, lấy địa chỉ/port đang lắng nghe rồi gửi request bằng HTTP client. Trong Spring Boot, `@SpringBootTest` có các chế độ web environment để điều khiển việc khởi động server.

| `webEnvironment` | Hành vi |
|---|---|
| `MOCK` | Tạo web application context dạng mock; không khởi động embedded server |
| `RANDOM_PORT` | Khởi động embedded server trên port ngẫu nhiên |
| `DEFINED_PORT` | Khởi động embedded server trên port được cấu hình, thường là `server.port` |
| `NONE` | Tạo ApplicationContext không phải web environment |

`MOCK` thường phù hợp với MockMvc hoặc test context. `RANDOM_PORT` phù hợp khi cần kiểm tra request qua connector thật mà không phụ thuộc một port cố định. `DEFINED_PORT` có thể dùng khi test cần một port đã biết, nhưng dễ xung đột với tiến trình khác trên máy hoặc trong CI.

### 5.1. Spring MVC với embedded server và TestRestTemplate

Với ứng dụng Spring Boot MVC, có thể dùng `RANDOM_PORT` và `TestRestTemplate`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void returnsOrderThroughRealHttpServer() {
        ResponseEntity<OrderResponse> response = http.getForEntity(
                "/api/orders/42", OrderResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(42L, response.getBody().id());
    }
}
```

`TestRestTemplate` được Spring Boot cung cấp cho kiểm thử ứng dụng web. Khi dùng `RANDOM_PORT`, Boot cấu hình client để gửi request đến embedded server đang chạy. Request đi qua server connector và pipeline ứng dụng như một HTTP request thực.

### 5.2. WebFlux với embedded server và WebTestClient

Với ứng dụng reactive, có thể bind `WebTestClient` vào server đang chạy:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveOrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void returnsOrderThroughRealHttpServer() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42);
    }
}
```

Ví dụ dùng `@LocalServerPort` của Spring Boot Test và `WebTestClient.bindToServer()`. Với một phiên bản hoặc cấu hình ứng dụng cụ thể, có thể dùng cách auto-configure WebTestClient của Spring Boot; điều cần xác nhận là client được bind đến địa chỉ server thật. Nếu dùng `bindToApplicationContext`, test sẽ chạy trong bộ nhớ và không kiểm tra connector.

### 5.3. Những thành phần được kiểm tra khi đi qua server thật

Request gửi qua server thật có thể kiểm tra các phần mà mock environment không bao phủ đầy đủ:

- Server connector nhận kết nối, quản lý port và xử lý request line/header/body.
- HTTP protocol, giới hạn header/body và một số hành vi framing.
- TLS/HTTPS khi test được cấu hình certificate và connector tương ứng.
- Compression, connection handling, timeout và cấu hình server.
- Context path, forwarded header hoặc cấu hình proxy khi được thiết lập.
- Sự phối hợp giữa server, Spring application context, filter chain, controller/handler và serialization.

Mức độ bao phủ phụ thuộc server và cấu hình được khởi động trong test. Ví dụ test local HTTP không tự xác minh TLS nếu connector không bật HTTPS; test với embedded server cũng không chứng minh reverse proxy hoặc load balancer production hoạt động đúng.

## 6. Khác biệt về độ tin cậy và chi phí

Mock test thường chạy nhanh vì không cần khởi động server và không có giao tiếp socket. Dữ liệu đầu vào được dựng trực tiếp, nên test dễ lặp lại và dễ cô lập một nhánh logic. Đây là lựa chọn phù hợp cho nhiều test controller, filter, interceptor, converter và handler.

Server integration test có chi phí cao hơn vì phải khởi động hạ tầng và chờ HTTP client. Đổi lại, test có thể phát hiện lỗi chỉ xuất hiện khi request đi qua connector, chẳng hạn cấu hình port, protocol, header parsing, body size, codec hoặc server-specific behavior. Nó cũng xác minh ứng dụng có thể khởi động với cấu hình triển khai đã chọn.

Không nên đánh giá chất lượng test chỉ bằng việc test có dùng server thật hay không. Một test server thật nhưng chỉ gọi một endpoint đơn giản có thể không bảo vệ được nhiều quy tắc nghiệp vụ; một unit test mock được thiết kế tốt có thể kiểm tra hàng chục nhánh logic với tốc độ cao. Cần xác định mục tiêu của mỗi test và chọn ranh giới nhỏ nhất có thể chứng minh hành vi đó.

## 7. Giao dịch và dữ liệu khi test server thật

Một khác biệt dễ gây nhầm lẫn là transaction trong test.

Với test dùng Spring TestContext và `@Transactional`, transaction thường được mở quanh test method và rollback khi test kết thúc. Điều này hữu ích cho các test persistence chạy trong cùng thread và transaction context.

Khi test gửi HTTP đến embedded server, request được xử lý trên thread của server và transaction nghiệp vụ được mở ở phía xử lý request. Transaction đó độc lập với transaction của test method. Vì vậy, đánh dấu test method `@Transactional` không tự động rollback những thay đổi database do server request tạo ra.

Ví dụ, nếu test gọi `POST /orders` qua `TestRestTemplate`, request có thể commit đơn hàng ở server. Khi test kết thúc, transaction của test method không bao trùm transaction server. Test cần dọn dữ liệu bằng API, repository hoặc fixture cleanup phù hợp, hoặc dùng database/schema cô lập theo chiến lược của dự án.

Với cả mock và server test, nên chuẩn bị dữ liệu có định danh riêng, tránh phụ thuộc vào thứ tự chạy và đảm bảo cleanup không xóa dữ liệu của test khác.

## 8. Những gì mock test có thể và không thể chứng minh

| Câu hỏi | Mock object / MockMvc / WebTestClient bind trong bộ nhớ | HTTP server thật |
|---|---|---|
| Controller trả status và body đúng? | Có, theo pipeline mock được dựng | Có |
| Validation và exception handling của Spring MVC đúng? | Có, nếu dùng cấu hình MVC tương ứng | Có |
| WebFilter hoặc WebHandler xử lý exchange đúng? | Có, khi gọi trực tiếp hoặc bind WebFlux context | Có |
| Converter/formatter được đăng ký trong context? | Có, nếu test dùng application context tương ứng | Có |
| Filter/interceptor đã được đăng ký trong ứng dụng? | Có thể, nếu test nạp cấu hình ứng dụng đầy đủ | Có |
| Port và connector thực sự lắng nghe? | Không | Có |
| TLS handshake và HTTP framing của server? | Không | Có, nếu cấu hình test tương ứng |
| Client và server giao tiếp qua socket? | Không | Có |
| Hành vi của proxy/load balancer production? | Không | Chỉ khi test đi qua hạ tầng đó |

Mock test vẫn có thể dùng application context thật của Spring. Từ “mock” ở đây nói đến request/response hoặc môi trường web được mô phỏng, không có nghĩa mọi bean trong ứng dụng đều là mock. Ngược lại, server integration test vẫn có thể mock một dependency nghiệp vụ nếu mục tiêu chỉ là kiểm tra server và HTTP pipeline.

## 9. Chọn đúng công cụ cho từng mục tiêu

| Mục tiêu kiểm thử | Công cụ nên cân nhắc | Lý do |
|---|---|---|
| Logic interceptor/filter độc lập | `MockHttpServletRequest`/`MockHttpServletResponse` hoặc `MockServerWebExchange` | Gọi trực tiếp component với request/response mock |
| Spring MVC mapping, binding, validation và response | `MockMvc` | Chạy `DispatcherServlet` và MVC infrastructure trong bộ nhớ |
| Spring WebFlux controller, router hoặc filter chain | `WebTestClient` bind với controller/application context; mock exchange cho component thấp hơn | Kiểm tra reactive web pipeline theo phạm vi cần thiết |
| Ứng dụng khởi động và lắng nghe port đúng | `@SpringBootTest(RANDOM_PORT)` cùng HTTP client | Cần embedded server thực sự hoạt động |
| Server connector, HTTPS, giới hạn HTTP hoặc cấu hình server | HTTP client gửi đến server thật | Những hành vi này nằm ngoài mock API |
| Luồng tích hợp giữa nhiều service và hạ tầng bên ngoài | Integration test có server và dependency test phù hợp | Kiểm tra các ranh giới tích hợp liên quan |

Một bộ test cân bằng thường có nhiều unit test và mock web test, một số integration test với context hoặc database, và một số ít test khởi động server thật cho những hành vi phụ thuộc connector hoặc cấu hình triển khai. Tỷ lệ cụ thể tùy ứng dụng; không có con số cố định áp dụng cho mọi module.

## 10. Quy trình quyết định phạm vi kiểm thử

Trước khi viết test, hãy trả lời các câu hỏi sau:

1. Thành phần cần kiểm tra nhận Servlet API, WebFlux API hay chỉ là dữ liệu Java thuần?
2. Mục tiêu là logic của một component, Spring web pipeline, hay kết nối HTTP qua server?
3. Có cần xác minh `DispatcherServlet`, WebFlux handler chain, converter, validator hoặc filter registration không?
4. Có cần kiểm tra connector, port, TLS, HTTP framing, timeout hoặc server-specific configuration không?
5. Test có phụ thuộc database, session, security context, locale hoặc trạng thái bên ngoài không?
6. Nếu gửi request qua server thật, dữ liệu được commit ở thread/transaction nào và sẽ cleanup ra sao?
7. Test cần chạy trong local/CI với port, JDK và dependency nào?

Nếu chỉ kiểm tra một quy tắc xử lý request, mock object hoặc MockMvc/WebTestClient bind trong bộ nhớ thường đủ. Nếu cần bảo vệ việc Spring cấu hình và nối các thành phần, dùng application context test. Nếu hành vi cần xác minh nằm ở server connector hoặc giao tiếp HTTP thực, khởi động server và gửi request bằng client thật.

Khi phân biệt rõ các ranh giới này, test sẽ cho biết chính xác phần nào đang được bảo vệ. Mock object API giúp kiểm tra logic web nhanh và có kiểm soát; máy chủ HTTP thật xác minh ứng dụng hoạt động qua connector và giao thức thực tế. Kết hợp chúng theo mục tiêu sẽ tạo ra bộ kiểm thử Spring vừa nhanh trong phát triển hằng ngày vừa đủ tin cậy cho quá trình tích hợp và triển khai.
