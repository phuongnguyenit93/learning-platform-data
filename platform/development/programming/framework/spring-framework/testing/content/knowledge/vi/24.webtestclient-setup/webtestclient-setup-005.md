# bindToServer để kiểm thử HTTP qua mạng thật

## 1. `bindToServer()` dùng để làm gì?

`WebTestClient` là HTTP client có API kiểm thử theo chuỗi lệnh. Nó cho phép gửi request, chờ response và xác nhận status, header, cookie, body hoặc dữ liệu streaming. Khi dùng `bindToServer()`, client kết nối đến một HTTP server đang chạy qua địa chỉ mạng và cổng TCP.

Đây là cách kiểm thử ở ranh giới HTTP thực tế của ứng dụng. Request đi qua HTTP stack của server, servlet filter hoặc WebFlux filter, quá trình routing, message conversion và response serialization trước khi quay lại client. Vì vậy, cách này có thể kiểm tra ứng dụng Spring MVC hoặc Spring WebFlux đang chạy trên một cổng thật.

Điều quan trọng là `bindToServer()` **không tự khởi động server**. Nó tạo một client hướng đến server đã có địa chỉ. Test phải khởi động ứng dụng hoặc một server riêng trước khi gửi request.

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Đoạn code trên tạo client gửi HTTP request đến `localhost:8080`. Nếu không có server lắng nghe tại địa chỉ đó, request sẽ thất bại ở bước kết nối.

## 2. Phân biệt `bindToServer()` với các cách bind khác

`WebTestClient` có thể kiểm thử ở nhiều ranh giới khác nhau. Chọn cách bind sẽ quyết định test gọi trực tiếp thành phần nào và có cần một server đang chạy hay không.

| Cách bind | Thành phần được kiểm thử | Có HTTP server đang chạy không? |
|---|---|---|
| `bindToController(...)` | WebFlux controller được đăng ký trực tiếp | Không |
| `bindToRouterFunction(...)` | WebFlux `RouterFunction` | Không |
| `bindToApplicationContext(...)` | Cấu hình web và các bean trong application context qua mock server infrastructure | Không cần server mạng thật |
| `bindToServer()` | Ứng dụng HTTP đang lắng nghe tại địa chỉ được cấu hình | Có |

Các cách bind in-process phù hợp với test tập trung vào handler, routing hoặc cấu hình web. `bindToServer()` phù hợp khi cần xác nhận hành vi ở ranh giới HTTP mà client bên ngoài thực sự sử dụng.

Một ứng dụng Spring MVC không cần chuyển sang WebFlux để dùng `WebTestClient` làm HTTP client. `WebTestClient` gửi HTTP request đến server; server có thể là Spring MVC, Spring WebFlux hoặc một HTTP server tương thích khác. Tuy nhiên, phía test cần có các thư viện client cần thiết của Spring WebFlux và một `ClientHttpConnector` khả dụng trên classpath.

## 3. Khởi động ứng dụng trên cổng ngẫu nhiên

Trong integration test, nên để Spring Boot khởi động web server thật trên một cổng ngẫu nhiên. `RANDOM_PORT` tránh xung đột khi nhiều test hoặc nhiều tiến trình chạy đồng thời.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

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
    void returnsOrderList() {
        client.get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Spring Boot khởi động ứng dụng trước khi test chạy. `@LocalServerPort` nhận cổng thực tế mà embedded server đã chọn. Trong `@BeforeEach`, test tạo client với base URL tương ứng. Mỗi request dùng URI tương đối như `/api/orders`; WebTestClient ghép URI đó với base URL.

`RANDOM_PORT` phù hợp hơn việc ghi cứng `8080`, vì cổng này có thể đã được một ứng dụng khác sử dụng. Nếu cần kiểm thử một cổng được cấu hình cụ thể, có thể dùng `DEFINED_PORT`, nhưng test khi đó phải bảo đảm cổng đã sẵn sàng và không bị tiến trình khác chiếm.

## 4. Gửi request và xác nhận response

Một request cơ bản gồm method, URI, header hoặc body, sau đó gọi `exchange()` để gửi request qua HTTP:

```java
client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .value(order -> {
            assertThat(order.id()).isEqualTo(42L);
            assertThat(order.status()).isEqualTo("CONFIRMED");
        });
```

Các bước có ý nghĩa như sau:

1. `get()` chọn HTTP GET.
2. `uri(...)` chọn endpoint trên server.
3. `accept(...)` khai báo media type mà client chấp nhận.
4. `exchange()` gửi request và nhận response.
5. `expectStatus()` xác nhận status code.
6. `expectHeader()` xác nhận header response.
7. `expectBody(...)` giải mã body thành kiểu Java mong muốn.
8. `value(...)` thực hiện assertion trên object đã giải mã.

Để kiểm tra JSON theo cấu trúc mà không cần khai báo DTO, có thể dùng JSONPath:

```java
client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("CONFIRMED");
```

Nếu endpoint trả JSON và cần so sánh toàn bộ representation, có thể dùng:

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "status": "CONFIRMED"
                }
                """);
```

## 5. Gửi request body

Đối với request JSON, dùng `contentType(...)` để mô tả định dạng body và `bodyValue(...)` để gửi object. WebTestClient dùng message writer tương ứng để chuyển object thành byte HTTP.

```java
@Test
void createsOrder() {
    CreateOrderRequest request = new CreateOrderRequest("BOOK-01", 2);

    client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(OrderResponse.class)
            .value(response -> {
                assertThat(response.productCode()).isEqualTo("BOOK-01");
                assertThat(response.status()).isEqualTo("CREATED");
            });
}
```

`bodyValue(...)` phù hợp với một object đơn lẻ. Nếu cần gửi publisher, có thể dùng `body(...)`:

```java
client.post()
        .uri("/api/orders/batch")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(Flux.just(order1, order2), OrderRequest.class)
        .exchange()
        .expectStatus().isAccepted();
```

Ví dụ publisher minh họa cách gửi dữ liệu theo luồng. `APPLICATION_NDJSON` chỉ phù hợp nếu endpoint thực sự công bố và đọc NDJSON; media type và kiểu dữ liệu phải tương thích với message writer ở client và cách endpoint đọc request. Hãy dùng đúng media type mà API công bố.

Đối với body văn bản hoặc byte, có thể gửi trực tiếp:

```java
client.post()
        .uri("/api/messages")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("Xin chào Spring")
        .exchange()
        .expectStatus().isCreated();
```

## 6. Kiểm tra status, header, cookie và body

WebTestClient có các nhóm expectation riêng để thể hiện rõ phần response đang được kiểm tra.

```java
client.get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-API-Version", "v1")
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ProfileResponse.class)
        .value(profile -> assertThat(profile.username()).isNotBlank());
```

Một số dạng assertion thường dùng:

| Mục tiêu | Ví dụ |
|---|---|
| Status thành công | `expectStatus().isOk()` |
| Status tạo mới | `expectStatus().isCreated()` |
| Status không tìm thấy | `expectStatus().isNotFound()` |
| Header bằng giá trị cụ thể | `expectHeader().valueEquals("X-Trace-Id", expected)` |
| Content type tương thích | `expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` |
| Body dạng DTO | `expectBody(OrderResponse.class)` |
| Body JSONPath | `expectBody().jsonPath("$.status").isEqualTo("READY")` |
| Body văn bản | `expectBody(String.class).isEqualTo("OK")` |
| Response không có body | `expectBody().isEmpty()` |

Có thể kiểm tra cookie trong response bằng `expectCookie()`:

```java
client.post()
        .uri("/api/session")
        .bodyValue(new LoginRequest("alice", "test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectCookie().exists("SESSION");
```

Tên cookie và cách xác thực trong ví dụ phụ thuộc cấu hình server. Không nên đưa mật khẩu thật vào test; hãy dùng tài khoản và dữ liệu dành riêng cho môi trường kiểm thử.

## 7. Cấu hình client dùng chung

Builder cho phép đặt các giá trị mặc định để nhiều test dùng chung một cấu hình:

```java
client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .responseTimeout(Duration.ofSeconds(5))
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

- `baseUrl(...)` đặt địa chỉ gốc của server.
- `defaultHeader(...)` thêm header mặc định cho request.
- `responseTimeout(...)` giới hạn thời gian chờ response.
- `codecs(...)` cấu hình các codec phía client, chẳng hạn giới hạn bộ nhớ khi đọc body.

Giới hạn bộ nhớ cần được chọn theo kích thước response hợp lý của API. Nếu body lớn hơn giới hạn, việc đọc body có thể thất bại với lỗi vượt giới hạn bộ nhớ; không nên tăng giới hạn vô hạn chỉ để che một response bất thường.

Nếu cần cấu hình HTTP connector cụ thể, truyền `ClientHttpConnector` vào `bindToServer(...)`:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

client = WebTestClient.bindToServer(
                new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:" + port)
        .build();
```

Ví dụ này dùng Reactor Netty connector; cần có dependency tương ứng trên test runtime. `bindToServer()` không có đối số sử dụng connector mặc định được Spring chọn theo các thư viện có trên classpath. Chỉ chỉ định connector riêng khi test cần kiểm soát cấu hình kết nối hoặc hành vi transport.

## 8. Tái sử dụng và biến đổi client

Sau khi có một client cơ sở, có thể tạo client biến thể với cấu hình bổ sung:

```java
WebTestClient authenticatedClient = client.mutate()
        .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .build();
```

Client mới kế thừa cấu hình cơ sở và thêm header Authorization. Cách này hữu ích khi nhiều test cần cùng một endpoint nhưng dùng danh tính hoặc header mặc định khác nhau.

Đối với kiểm thử authentication qua server thật, hãy gửi credential hoặc token theo giao thức mà ứng dụng thực sự hỗ trợ. Ví dụ, gửi Basic Authorization header, bearer token đã ký cho môi trường test, hoặc cookie/session được server cấp. Các helper tạo principal giả dành cho kiểm thử in-process không thay thế việc gửi credential qua HTTP và xác minh chúng ở server.

Khi cần xác nhận server từ chối request thiếu token, hãy tạo request không có Authorization header. Khi cần xác nhận quyền, gửi token test có authority tương ứng và kiểm tra status cùng response. Điều này giúp kiểm tra cả bộ lọc xác thực và quy tắc phân quyền trên đường đi HTTP.

## 9. Kiểm thử lỗi HTTP và content negotiation

Kiểm tra trường hợp thành công là chưa đủ. Client thật cũng cần nhận được response đúng khi request sai định dạng, thiếu dữ liệu hoặc không có quyền.

Ví dụ endpoint chỉ nhận JSON có thể từ chối request gửi text/plain:

```java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("productCode=BOOK-01")
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
```

Nếu client yêu cầu định dạng response mà endpoint không hỗ trợ, có thể kiểm tra `406 Not Acceptable`:

```java
client.get()
        .uri("/api/orders")
        .accept(MediaType.APPLICATION_XML)
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
```

Kết quả cụ thể phụ thuộc mapping, message converter và exception handling của ứng dụng. Test cần phản ánh hợp đồng thực tế của endpoint. Không nên khẳng định mọi request không tương thích đều trả một status cố định nếu ứng dụng có error handler hoặc negotiation strategy tùy chỉnh.

## 10. Kiểm thử endpoint bất đồng bộ và streaming

WebTestClient có API reactive nên phù hợp với endpoint trả dữ liệu theo luồng, ví dụ Server-Sent Events (SSE). Với stream không kết thúc, không nên chờ toàn bộ body hoàn tất. Có thể nhận response body dạng `Flux` và dùng Reactor Test để kiểm tra một số phần tử rồi hủy subscription.

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event -> "READY".equals(event.data()))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Test cần đặt timeout hữu hạn để không bị treo nếu server không phát event. `thenCancel()` dừng việc đọc stream sau khi đã nhận phần tử cần xác nhận. Với endpoint trả một publisher hữu hạn, có thể dùng `expectBodyList(...)` hoặc `returnResult(...)` tùy mục tiêu kiểm thử.

Với endpoint bất đồng bộ kiểu HTTP `202 Accepted`, cần phân biệt response xác nhận đã nhận yêu cầu với kết quả công việc đã hoàn tất. Nếu API trả job id và xử lý nền, test nên kiểm tra response nhận job trước, sau đó chờ trạng thái hoàn thành qua endpoint trạng thái hoặc một cơ chế đồng bộ dành cho test. Không nên dùng `Thread.sleep(...)` dài để đoán thời điểm công việc hoàn tất.

## 11. Kiểm thử server HTTPS và các chi tiết transport

Vì `bindToServer()` là HTTP client, base URL có thể dùng `https://` nếu server bật TLS:

```java
client = WebTestClient.bindToServer()
        .baseUrl("https://localhost:" + httpsPort)
        .build();
```

Để kết nối thành công, client phải tin cậy certificate mà server trình bày và hostname phải khớp với certificate. Với certificate test tự ký, cấu hình trust store hoặc SSL context dành riêng cho test. Không tắt kiểm tra certificate trong test rồi xem đó là bằng chứng TLS được cấu hình đúng.

Kiểm thử HTTPS ở localhost xác nhận ứng dụng hoặc embedded server xử lý TLS theo cấu hình test. Nó không tự kiểm tra cấu hình TLS của reverse proxy, ingress, load balancer hoặc chứng chỉ trên môi trường production nếu các thành phần đó không nằm trên đường đi request.

Tương tự, gửi request tới `localhost` xác nhận HTTP stack của server cục bộ. Nó không tự kiểm tra DNS công khai, firewall, routing giữa các mạng, gateway production hay chính sách của CDN. Muốn kiểm tra các ranh giới đó, cần một test triển khai tới đúng môi trường hoặc một hệ thống kiểm thử mạng tương ứng.

## 12. Vòng đời server và tính cô lập của test

Với `RANDOM_PORT`, Spring Boot khởi động server trong một thread xử lý request riêng. Test gửi request qua socket tới server đó. Điều này có một hệ quả quan trọng đối với transaction:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Test thread có transaction riêng.
}
```

Transaction được tạo bởi `@Transactional` trên test không tự truyền sang thread server xử lý request. Nếu endpoint ghi dữ liệu, transaction của server có thể commit độc lập. Việc test kết thúc và rollback transaction của chính test không tự rollback dữ liệu được ghi bởi HTTP request.

Vì vậy, với real-server test:

- Tạo dữ liệu test có định danh riêng để tránh phụ thuộc thứ tự chạy.
- Dọn dữ liệu qua repository hoặc API quản trị phù hợp sau test.
- Không giả định `@Transactional` trên test sẽ tự hoàn tác mọi thao tác được gửi qua HTTP.
- Dùng database hoặc schema dành cho test, tránh ghi vào dữ liệu dùng chung.
- Tránh test phụ thuộc một request trước đã chạy hoặc một cổng cố định.
- Đặt timeout cho response, stream và tác vụ nền.

Nếu test khởi động ứng dụng trên cổng ngẫu nhiên, server thường được quản lý theo vòng đời của Spring test context. Khi nhiều test dùng chung context, server có thể được tái sử dụng; do đó trạng thái dữ liệu và cookie cần được cô lập chủ động.

## 13. So sánh WebTestClient qua server thật với MockMvc

| Tiêu chí | `WebTestClient.bindToServer()` | `MockMvc` |
|---|---|---|
| Cách gọi | HTTP request qua connector và socket | Mô phỏng servlet request/response trong tiến trình test |
| Cần server đang chạy | Có | Không |
| Có thể kiểm tra cổng và HTTP transport của server | Có | Không |
| Kiểm tra servlet filters đang đăng ký trên server | Có, nếu request đi qua server thật | Có thể, nếu filters được thêm vào MockMvc |
| Tốc độ và chi phí khởi tạo | Thường cao hơn do khởi động server và giao tiếp HTTP | Thường thấp hơn |
| Phù hợp với | HTTP integration, serialization, filter chain và hành vi server thực tế | MVC slice, controller và servlet behavior trong tiến trình |

Hai công cụ bổ sung cho nhau. Dùng MockMvc để kiểm tra nhanh các nhánh MVC và dùng `bindToServer()` cho các hợp đồng cần được xác nhận qua HTTP thật. Không cần chuyển toàn bộ test controller sang real server nếu test không cần ranh giới mạng.

## 14. Lỗi thường gặp khi dùng `bindToServer()`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Connection refused | Server chưa khởi động, sai port hoặc sai host | Dùng `RANDOM_PORT`, inject `@LocalServerPort` và kiểm tra server lifecycle |
| Test luôn gọi port 8080 | Base URL bị ghi cứng | Ghép base URL với port thực tế được inject |
| Request timeout | Endpoint bị treo, stream không kết thúc hoặc tác vụ nền chưa sẵn sàng | Đặt timeout phù hợp và kiểm tra điều kiện hoàn tất thay vì chờ vô hạn |
| Body không giải mã được | Client thiếu codec hoặc media type không tương thích | Kiểm tra dependency, `Content-Type`, kiểu body và cấu hình codec |
| Test bảo mật không giống test MockMvc | Request thật đi qua filter chain và thread server riêng | Gửi credential/token/cookie theo giao thức HTTP thật và kiểm tra policy server |
| Dữ liệu còn lại sau test | Transaction test không bao trùm transaction ở server thread | Dọn dữ liệu rõ ràng và dùng dữ liệu riêng cho từng test |
| HTTPS handshake thất bại | Certificate không được tin cậy hoặc hostname không khớp | Cấu hình trust store và certificate phù hợp với test |
| Test stream bị treo | Test chờ một response stream không kết thúc | Dùng `FluxExchangeResult`, `StepVerifier`, cancellation và timeout |

Khi điều tra lỗi, hãy xác nhận lần lượt server đã khởi động, base URL có đúng cổng, connector có thể kết nối, endpoint có phản hồi, rồi mới kiểm tra codec và assertion body. Cách phân tầng này giúp phân biệt lỗi kết nối với lỗi nghiệp vụ hoặc lỗi serialization.

## 15. Khi nào nên chọn `bindToServer()`?

Chọn `bindToServer()` khi mục tiêu kiểm thử cần đi qua HTTP server đang chạy, ví dụ:

- Xác nhận endpoint hoạt động trên cổng thật và trả status/header/body đúng.
- Kiểm tra message conversion và content negotiation ở cả client-server boundary.
- Kiểm tra servlet filter, WebFlux filter, authentication và authorization trong cấu hình server thực tế.
- Kiểm tra cookie, redirect, compression, streaming hoặc timeout.
- Xác nhận HTTPS và cấu hình connector trong môi trường kiểm thử.
- Kiểm tra hợp đồng HTTP của ứng dụng mà không gọi trực tiếp controller.

Không chọn real-server test chỉ vì API có thể được gọi bằng WebTestClient. Nếu mục tiêu chỉ là kiểm tra một controller hoặc handler, test in-process thường nhanh và dễ cô lập hơn.

`bindToServer()` biến WebTestClient thành một HTTP client kiểm thử hướng đến server đang chạy. Khi kết hợp với server trên cổng ngẫu nhiên, request thực, assertion status/header/body và dữ liệu test được cô lập, nó cung cấp bằng chứng sát hơn về hành vi mà client bên ngoài thực sự quan sát được.
