# Xử lý lỗi, thời gian chờ và giới hạn do client nền quyết định

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, HTTP interface là cách mô tả hợp đồng gọi API bằng Java interface cùng các annotation **@HttpExchange**, **@GetExchange**, **@PostExchange**. Spring tạo proxy để biến lời gọi phương thức Java thành HTTP request. Proxy **không phải một HTTP transport độc lập**: việc thiết lập kết nối, gửi/nhận dữ liệu, xử lý HTTP status, timeout, redirect và nhiều giới hạn tài nguyên được quyết định bởi **client nền** mà proxy sử dụng.

Ví dụ, cùng một interface gọi dịch vụ tồn kho có thể chạy trên:

- **RestClientAdapter** → **RestClient** → một **ClientHttpRequestFactory** như JDK HttpClient hoặc Apache HttpComponents.
- **WebClientAdapter** → **WebClient** → một **ClientHttpConnector** như Reactor Netty, JDK HttpClient hoặc Jetty.
- **RestTemplateAdapter** → **RestTemplate** → request factory tương ứng, chủ yếu khi bảo trì hệ thống cũ.

Bài học tập trung vào việc đưa ra chính sách lỗi, thời gian chờ và giới hạn tài nguyên ở đúng tầng khi tích hợp qua HTTP trong Spring Boot. Sau khi học, bạn cần:

1. Giải thích vì sao annotation HTTP interface không tự sinh retry, timeout hoặc cơ chế chuyển lỗi nghiệp vụ.
2. Phân biệt lỗi HTTP, lỗi vận chuyển, lỗi timeout và lỗi giải mã response.
3. Cấu hình client nền cho HTTP interface đồng bộ hoặc reactive.
4. Nhận diện giới hạn connection pool, codec, streaming, blocking và ngân sách thời gian.
5. Kiểm thử các tình huống thất bại tác động trực tiếp đến tính đúng đắn của tích hợp.

## 2. HTTP interface đứng ở đâu trong đường đi request?

Giả sử ứng dụng bán hàng cần hỏi số lượng tồn kho trước khi xác nhận đơn. Khai báo hợp đồng:

~~~java
@HttpExchange(accept = MediaType.APPLICATION_JSON_VALUE)
public interface WarehouseApi {

    @GetExchange("/inventory/{sku}")
    StockResponse getStock(@PathVariable String sku);
}

public record StockResponse(String sku, int available) {}
~~~

Lời gọi **getStock("SKU-01")** mô tả **đường dẫn, phương thức và kiểu dữ liệu**; nó không diễn tả DNS/TCP/TLS được phép mất bao lâu, bao nhiêu connection sử dụng đồng thời, cách phản ứng với 404/503, bao lâu chưa có response thì hủy, hoặc có retry hay không.

Đường đi điển hình:

~~~mermaid
flowchart TD
    A["Application service"] --> B["@HttpExchange interface proxy"]
    B --> C["HttpServiceProxyFactory / adapter"]
    C --> D{"Client nền"}
    D --> E["RestClient"]
    D --> F["WebClient"]
    E --> G["ClientHttpRequestFactory"]
    F --> H["ClientHttpConnector"]
    G --> I["HTTP server bên ngoài"]
    H --> I
    I --> J["Status / headers / body hoặc lỗi I/O"]
    J --> D
    D --> K["Exception hoặc dữ liệu giải mã"]
    K --> A
~~~

**Nguyên tắc cốt lõi:** interface mô tả *gọi gì*; client nền quyết định phần lớn cách *gọi như thế nào*. Khi request thất bại, cần truy ngược từ adapter xuống client/transport trước khi thay đổi annotation.

## 3. Phân loại lỗi trước khi chọn cách xử lý

Không nên xem mọi exception là lỗi HTTP 500. Có ít nhất bốn nhóm sự cố:

| Nhóm | Ví dụ | Tín hiệu điển hình | Xử lý |
| --- | --- | --- | --- |
| **HTTP response lỗi** | 400, 404, 409, 429, 503 | Có HTTP status, có thể có body | Diễn giải theo hợp đồng API; chỉ retry status phù hợp |
| **Vận chuyển** | DNS lỗi, TLS handshake thất bại, connection reset | Không nhận HTTP response hợp lệ | Ghi nhận downstream không sẵn sàng; cân nhắc retry giới hạn |
| **Timeout** | Connect timeout, chờ response quá lâu, hết deadline | Lời gọi không hoàn tất kịp thời | Xác định pha bị chờ; đánh giá nguy cơ upstream đã xử lý |
| **Hợp đồng dữ liệu** | JSON sai định dạng, kiểu trường không tương thích | Có thể nhận 2xx nhưng giải mã DTO thất bại | Coi là lỗi hợp đồng tích hợp, kiểm tra schema |

Với lời gọi HTTP interface theo hành vi mặc định:

- **RestClient** thường ném **RestClientResponseException** hoặc lớp con đối với response 4xx/5xx. Lỗi I/O thường được bọc bằng **ResourceAccessException**.
- **WebClient** thường ném **WebClientResponseException** cho response lỗi và **WebClientRequestException** cho lỗi thực hiện request. Lỗi giải mã có thể xuất hiện riêng.
- **RestTemplate** dùng **ResponseErrorHandler** để xác định status lỗi và exception tương ứng.

**Không có HTTP status** là khác biệt quan trọng: một ConnectException hoặc connect timeout không thể xử lý bằng nhánh kiểm tra status 503, vì server chưa trả status nào.

### Diễn giải HTTP status theo hợp đồng

| Status | Ý nghĩa thường gặp | Retry? |
| --- | --- | --- |
| 400, 422 | Payload hoặc tham số không thỏa hợp đồng | Không; cần sửa request |
| 401, 403 | Xác thực hoặc phân quyền | Không retry mù; xử lý token/quyền đúng cơ chế |
| 404 | Tài nguyên không tồn tại hoặc sai đường dẫn API | Chỉ chuyển thành “không có dữ liệu” nếu hợp đồng cho phép |
| 409 | Xung đột trạng thái/phiên bản | Giải quyết theo nghiệp vụ |
| 429 | Bị giới hạn tần suất | Có thể thử lại theo Retry-After và deadline |
| 500, 502, 503, 504 | Upstream hoặc phụ thuộc gặp sự cố | Có thể retry có chọn lọc với thao tác an toàn/idempotent |

Một 404 của API tra cứu tồn kho có thể mang nghĩa SKU không tồn tại, nhưng 404 khác có thể là sai base URL sau triển khai. Không nên “nuốt 404” trên mọi dịch vụ.

## 4. Cấu hình lỗi tập trung trên RestClient

Ví dụ dùng Spring Boot với **RestClient.Builder**, **JdkClientHttpRequestFactory** và HTTP interface, phù hợp với Spring Framework 6.1+ (có RestClient). Import Java/Spring được lược bỏ để tập trung vào luồng cấu hình.

~~~java
@Configuration
public class WarehouseClientConfiguration {

    @Bean
    WarehouseApi warehouseApi(RestClient.Builder restClientBuilder) {
        java.net.http.HttpClient jdkHttpClient =
                java.net.http.HttpClient.newBuilder()
                        .connectTimeout(Duration.ofMillis(800))
                        .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(jdkHttpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(2));

        RestClient restClient = restClientBuilder
                .baseUrl("https://warehouse.example.internal")
                .requestFactory(requestFactory)
                .defaultStatusHandler(HttpStatusCode::isError,
                        (request, response) -> {
                            throw new WarehouseHttpException(
                                    response.getStatusCode().value());
                        })
                .build();

        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(WarehouseApi.class);
    }
}

public final class WarehouseHttpException extends RuntimeException {
    private final int statusCode;

    public WarehouseHttpException(int statusCode) {
        super("Warehouse HTTP error: " + statusCode);
        this.statusCode = statusCode;
    }

    public int statusCode() {
        return statusCode;
    }
}
~~~

Các bước diễn ra:

1. Proxy tạo request theo **WarehouseApi**.
2. **RestClient** dùng **JdkClientHttpRequestFactory**, nơi timeout kết nối và timeout request JDK được cấu hình.
3. Khi nhận status lỗi, **defaultStatusHandler** ném **WarehouseHttpException** chứa status có thể kiểm tra.
4. Nếu lỗi thuộc DNS, TLS, kết nối hoặc giải mã, status handler **không** chuyển chúng thành WarehouseHttpException; tầng service phải xét loại lỗi tương ứng.

Trong ứng dụng thật, nên giữ error code từ upstream, correlation ID và metadata an toàn; không phân tích chuỗi thông báo chứa “503” để quyết định retry, cũng không ghi token hay toàn bộ payload nhạy cảm vào log.

**Chú ý timeout:** phương thức **JdkClientHttpRequestFactory.setReadTimeout(...)** chuyển cấu hình xuống timeout request của JDK HTTP client (tham chiếu **HttpRequest.Builder.timeout**). Tên API không có nghĩa là mọi thao tác đọc từng byte hoặc toàn bộ xử lý nghiệp vụ đều được bảo vệ bằng một deadline chung. Ngữ nghĩa timeout khác nhau giữa JDK HttpClient, Apache HttpComponents và Reactor Netty.

### Chuyển lỗi thành kết quả nghiệp vụ tại service

Giả sử hợp đồng warehouse quy định 404 nghĩa là SKU chưa tồn tại:

~~~java
public Optional<StockResponse> findStock(String sku) {
    try {
        return Optional.ofNullable(warehouseApi.getStock(sku));
    } catch (WarehouseHttpException ex) {
        if (ex.statusCode() == 404) {
            return Optional.empty();
        }
        throw ex;
    }
}
~~~

Đoạn mã đúng khi **chính WarehouseHttpException** là lỗi do client được cấu hình ném ra và 404 thật sự biểu diễn “không có SKU”. Nếu giữ status handler mặc định, cần bắt kiểu exception tương ứng, chẳng hạn **HttpClientErrorException.NotFound**. Không biến 401, 503, timeout hay lỗi JSON thành **Optional.empty()**.

## 5. Cấu hình lỗi và timeout trên WebClient

HTTP interface có thể dựa trên **WebClient** khi cần luồng reactive, nhiều I/O đồng thời hoặc streaming. Hợp đồng lúc này có thể trả về Reactor type:

~~~java
@HttpExchange(accept = MediaType.APPLICATION_JSON_VALUE)
public interface ReactiveWarehouseApi {

    @GetExchange("/inventory/{sku}")
    Mono<StockResponse> getStock(@PathVariable String sku);
}
~~~

Khi dùng Reactor Netty làm connector, các timeout cơ bản đặt trên **HttpClient**:

~~~java
@Bean
ReactiveWarehouseApi reactiveWarehouseApi() {
    reactor.netty.http.client.HttpClient nettyClient =
            reactor.netty.http.client.HttpClient.create()
                    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                    .responseTimeout(Duration.ofSeconds(2));

    WebClient webClient = WebClient.builder()
            .baseUrl("https://warehouse.example.internal")
            .clientConnector(new ReactorClientHttpConnector(nettyClient))
            .defaultStatusHandler(HttpStatusCode::isError,
                    response -> Mono.just(
                            new WarehouseHttpException(
                                    response.statusCode().value())))
            .build();

    return HttpServiceProxyFactory
            .builderFor(WebClientAdapter.create(webClient))
            .build()
            .createClient(ReactiveWarehouseApi.class);
}
~~~

**CONNECT_TIMEOUT_MILLIS** giới hạn pha thiết lập TCP; **responseTimeout** do Reactor Netty thi hành với phản hồi; **defaultStatusHandler** chuyển status lỗi thành exception. Chúng là các cơ chế khác nhau. Service có thể thêm deadline cho luồng reactive:

~~~java
Mono<StockResponse> stock =
        reactiveWarehouseApi.getStock("SKU-01")
                .timeout(Duration.ofSeconds(3));
~~~

**Mono.timeout** giới hạn thời gian chờ tín hiệu của pipeline được subscribe và thường dẫn tới cancellation khi quá hạn. Nó không thay thế giới hạn pool, cấu hình kết nối hoặc đảm bảo server chưa thực hiện request. Đối với phương thức trả về kiểu đồng bộ đi qua **WebClientAdapter**, Spring còn hỗ trợ **blockTimeout** ở adapter; nên ưu tiên timeout tại HTTP client nền để có nhiều quyền kiểm soát các pha I/O hơn.

**Cẩn thận với event loop:** phương thức trả Mono chỉ thực hiện request khi có subscription. Không tùy tiện gọi **.block()** trong luồng WebFlux/Reactor Netty event loop, vì nó có thể chặn các luồng I/O và làm giảm khả năng phục vụ dưới tải.

## 6. Các loại thời gian chờ không thay thế được nhau

Một cuộc gọi HTTP có thể đi qua nhiều pha:

~~~text
Chờ tài nguyên/pool
    → DNS → thiết lập TCP → bắt tay TLS
    → gửi request → chờ response headers
    → nhận response body → giải mã JSON
    → áp dụng logic nghiệp vụ
~~~

| Giới hạn | Mục đích | Nơi cấu hình |
| --- | --- | --- |
| **Pool acquire/lease timeout** | Giới hạn việc chờ connection rảnh | Transport có pool, chẳng hạn connection manager |
| **Connect timeout** | Giới hạn thời gian mở kết nối mạng | JDK HttpClient, Reactor Netty, Apache HttpClient... |
| **TLS/handshake timeout** | Giới hạn bắt tay bảo mật nếu transport hỗ trợ | HTTP transport |
| **Response/read timeout** | Giới hạn chờ dữ liệu phản hồi theo ngữ nghĩa của client cụ thể | Request factory hoặc HTTP connector/client |
| **Deadline toàn lời gọi** | Giới hạn thời gian service chấp nhận chờ | Tầng application, operator reactive hoặc deadline thống nhất |
| **Retry budget** | Giới hạn tổng thời gian thử lại và backoff | Tầng resilience/orchestration |

Ví dụ bước xác minh tồn kho chỉ có ngân sách 3 giây. Nếu thử ba lần với **responseTimeout = 2s** cộng backoff 200 ms, tổng thời gian có thể vượt 3 giây. Do đó cần:

- Phân bổ ngân sách từ deadline nghiệp vụ xuống từng cuộc gọi và retry.
- Đặt connect timeout ngắn hơn ngân sách tổng nhưng đủ cho điều kiện mạng thực tế.
- Tính cả thời gian chờ pool và backoff, không chỉ thời gian chờ response.
- Dựa vào latency p95/p99 và SLO downstream để lựa chọn giá trị, sau đó đo trong môi trường chạy thật.

Timeout transport là một biện pháp giới hạn I/O; nó không tự tạo cam kết thời gian của toàn chuỗi nghiệp vụ.

## 7. Retry, giới hạn tần suất và hậu quả của timeout

HTTP interface **không tự retry** vì có **@GetExchange**. Retry phải được thiết kế ở tầng điều phối hoặc resilience (ví dụ Resilience4j, Spring Retry, Reactor **retryWhen**) và thống nhất với circuit breaker, rate limiter.

Các nguyên tắc:

1. **Chỉ retry lỗi có thể tạm thời**, như lỗi kết nối nhất thời, một số 5xx hoặc 429. Không retry payload sai 400/422.
2. **Giới hạn số lần, backoff và jitter** để tránh nhiều client đồng thời gửi lại và làm downstream quá tải.
3. **Xem xét idempotency**: GET thường an toàn để thử lại; POST tạo giao dịch có thể đã thành công tại server dù client nhận timeout. Dùng idempotency key hoặc cơ chế chống trùng nếu nghiệp vụ yêu cầu.
4. **Tôn trọng Retry-After** khi upstream cung cấp, đồng thời giới hạn bởi deadline gốc.
5. **Tránh retry chồng lớp**: nếu gateway retry ba lần và application cũng retry ba lần, một thao tác có thể tạo tới chín cuộc gọi.

Với thao tác ghi dữ liệu, timeout chỉ có nghĩa là **client chưa nhận kết quả kịp thời**, không chứng minh server chưa xử lý. Cần cơ chế đối soát hoặc tra cứu trạng thái trước khi quyết định gửi lại.

Ví dụ retry có giới hạn cho GET reactive:

~~~java
Mono<StockResponse> result = reactiveWarehouseApi.getStock("SKU-01")
        .retryWhen(Retry.backoff(1, Duration.ofMillis(150))
                .filter(error -> error instanceof WarehouseHttpException ex
                        && (ex.statusCode() == 429
                            || ex.statusCode() == 503)))
        .timeout(Duration.ofSeconds(3));
~~~

Đoạn này cho phép **một lần thử lại** sau request đầu tiên và chỉ cho hai status đã chọn; không retry DNS/timeout vì các lỗi đó chưa nằm trong bộ lọc. Khi triển khai thật, cần xử lý Retry-After, jitter và thống kê retry. Việc đặt **timeout** ngoài **retryWhen** ràng buộc thời gian của cả chuỗi retry theo giới hạn pipeline Reactor, nhưng vẫn cần timeout tầng HTTP.

## 8. Giới hạn và hành vi khác do client nền quyết định

Hai HTTP interface giống hệt nhau chưa chắc có cùng đặc tính vận hành:

| Vấn đề | Tác động |
| --- | --- |
| **Connection pool** | Số connection mở, chờ mượn connection, idle timeout và năng lực chịu tải; pool nhỏ có thể gây hàng đợi dài ngay cả khi server nhanh |
| **Blocking vs non-blocking** | RestClient dùng API đồng bộ; WebClient hỗ trợ reactive; chọn mô hình phù hợp với thread model |
| **HTTP/2, redirect, proxy, TLS** | Tùy transport và cấu hình; không suy ra từ annotation interface |
| **Body buffering và codec** | Response lớn có thể tiêu tốn bộ nhớ hoặc vượt giới hạn giải mã |
| **Streaming** | Kiểu trả về, codec và adapter quyết định cách đọc dữ liệu; WebClient hỗ trợ Flux |
| **Header, filter/interceptor** | Cách gắn auth, tracing, logging khác nhau giữa các client |
| **Vòng đời tài nguyên** | Event loop và pool có thể cần dùng chung hoặc được đóng đúng cách |

Ví dụ giới hạn bộ đệm giải mã của **WebClient**:

~~~java
WebClient webClient = WebClient.builder()
        .codecs(config -> config.defaultCodecs()
                .maxInMemorySize(512 * 1024))
        .build();
~~~

Giá trị 512 KiB ở trên là giới hạn bộ đệm giải mã được cấu hình, **không đồng nghĩa** với giới hạn tổng kích thước mọi response hoặc số byte truyền trên mạng. Với payload lớn, cân nhắc phân trang, stream hoặc xử lý theo từng phần thay vì chỉ tăng vô hạn bộ đệm.

Đối với **RestClient**, lựa chọn **ClientHttpRequestFactory** quyết định nhiều khả năng của HTTP transport. JDK HttpClient hỗ trợ cấu hình gọn; Apache HttpComponents cung cấp nhiều tùy chọn connection pool hơn. Chọn dựa trên yêu cầu thực tế và xác minh default của phiên bản thư viện đang chạy.

## 9. Xử lý lỗi đúng lớp và có khả năng quan sát

Một thiết kế dễ vận hành thường phân chia trách nhiệm:

| Lớp | Trách nhiệm |
| --- | --- |
| HTTP interface | Endpoint, tham số, DTO yêu cầu/phản hồi |
| Client builder / transport | Base URL, TLS, auth, timeout, pool, codec, status handler |
| Adapter | Kết nối proxy với client đã cấu hình |
| Application service | Ánh xạ lỗi sang nghiệp vụ, quyết định fallback và retry |
| Observability | Latency, status, timeout, số retry, pool và trace liên dịch vụ |

Nếu warehouse trả 503, application service có thể trả trạng thái *không thể xác minh tồn kho* và từ chối xác nhận đơn. Không được tự động coi lỗi đó là **available = 0**: “hết hàng” khác hoàn toàn “không biết tồn kho”.

Nên đo các tín hiệu với nhãn metric có số lượng giá trị thấp:

- Số lần gọi theo downstream, operation, nhóm HTTP status và kết quả.
- Latency p95/p99; lỗi connect/response timeout, lỗi mạng, lỗi giải mã.
- Số retry và tỷ lệ thành công sau retry; số lượt hết ngân sách.
- Thời gian chờ pool, số connection sử dụng, độ bão hòa nếu transport cung cấp metric.
- Trace ID/correlation ID xuyên caller và downstream.

Không ghi nguyên URL chứa dữ liệu nhạy cảm, token hoặc toàn bộ response body vào metric/log. Nếu sử dụng builder do Spring Boot quản lý, hãy xác nhận cấu hình observation/metrics đã được áp dụng. Tự dựng builder và connector có thể cần gắn thêm các tùy biến mà Boot thường cung cấp.

## 10. Kiểm thử tình huống mà annotation không bảo đảm

Chỉ test response 200 là chưa đủ. Dùng **MockWebServer**, **WireMock** hoặc HTTP server giả có thể chủ động trì hoãn, đóng kết nối và trả body sai. Với trường hợp kiểm thử status đơn giản, có thể dùng **MockRestServiceServer** cho RestClient.

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| 200, JSON hợp lệ | DTO và tham số đường dẫn được ánh xạ đúng |
| 404 | Chỉ trả kết quả rỗng khi hợp đồng quy định |
| 429 có Retry-After | Retry có giới hạn, tôn trọng thời gian được chỉ định |
| 503 rồi 200 | Retry đúng số lần, không vượt deadline |
| DNS lỗi/kết nối từ chối | Đi vào nhánh vận chuyển, không nhầm HTTP status |
| Upstream trì hoãn response | Timeout thật sự phát sinh, caller không chờ vô hạn |
| 200 nhưng JSON sai | Lỗi giải mã không bị biến thành “không có hàng” |
| Response quá lớn | Có hành vi rõ ràng: phân trang, streaming hoặc lỗi giới hạn codec |
| POST thành công tại server rồi mất response | Không tạo giao dịch trùng sau khi retry |

Ví dụ kiểm thử status bằng **MockRestServiceServer**:

~~~java
@Test
void warehouse503IsPropagatedAsHttpError() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://warehouse.test")
            .defaultStatusHandler(HttpStatusCode::isError,
                    (request, response) -> {
                        throw new WarehouseHttpException(
                                response.getStatusCode().value());
                    });

    MockRestServiceServer mockServer =
            MockRestServiceServer.bindTo(builder).build();
    WarehouseApi api = HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(builder.build()))
            .build()
            .createClient(WarehouseApi.class);

    mockServer.expect(requestTo(
                    "https://warehouse.test/inventory/SKU-01"))
            .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

    WarehouseHttpException error = assertThrows(
            WarehouseHttpException.class,
            () -> api.getStock("SKU-01"));

    assertEquals(503, error.statusCode());
    mockServer.verify();
}
~~~

Các static import của JUnit và **MockRestServiceServer** được lược bỏ. Để xác minh timeout kết nối/response, phải chạy kiểm thử với **chính request factory hoặc connector** mà ứng dụng sử dụng; mock một status không mô phỏng được pha mạng. Việc mock phương thức interface rồi ép ném TimeoutException cũng chỉ kiểm tra nhánh application service, không chứng minh transport đã cấu hình đúng.

## 11. Các sai lầm thường gặp

**“Thêm @HttpExchange là có timeout phù hợp.”** Sai: timeout mặc định phụ thuộc client, transport, phiên bản và cấu hình hệ thống. Khai báo theo SLO và kiểm thử thực tế.

**“Bắt mọi Exception rồi trả Optional.empty().”** Cách này khiến lỗi xác thực, mạng hoặc sai JSON trông giống SKU không tồn tại. Chỉ chuyển đổi lỗi được hợp đồng quy định.

**“Timeout có nghĩa request chưa tới server.”** Timeout có thể xảy ra sau khi upstream đã thay đổi dữ liệu. Các thao tác ghi cần chống trùng và đối soát.

**“Retry càng nhiều càng ổn định.”** Retry thiếu giới hạn làm dịch vụ đang quá tải trầm trọng hơn. Luôn áp dụng deadline, backoff và giới hạn concurrency.

**“Tăng timeout sẽ giải quyết pool cạn.”** Pool cạn là vấn đề tài nguyên hoặc năng lực phục vụ; tăng thời gian chờ thường chỉ kéo dài hàng đợi.

**“Chuyển interface từ RestClient sang WebClient là tương đương tuyệt đối.”** Return type, blocking/reactive behavior, streaming, codec, exception và cấu hình connector khác nhau. Cần kiểm tra hợp đồng và test tích hợp.

## 12. Checklist thiết kế HTTP interface đáng tin cậy

Trước khi triển khai, trả lời được:

1. Interface dùng **RestClient**, **WebClient** hay client cũ? Request factory/connector thực tế là gì?
2. 404, 409, 429, 5xx có ý nghĩa nghiệp vụ ra sao? Lỗi nào phải giữ nguyên để caller phân biệt?
3. Connect timeout, response timeout, pool timeout và deadline toàn thao tác được đặt ở đâu?
4. Có retry không? Lời gọi có idempotent không? Với ghi dữ liệu, có idempotency key hoặc đối soát không?
5. Khi upstream chậm, pool đầy hoặc payload lớn, giới hạn concurrency và memory có phù hợp không?
6. Log/metric/trace có giúp phân biệt response lỗi, network error, timeout và lỗi giải mã không?
7. Test có tái hiện response lỗi, lỗi mạng, timeout và lỗi dữ liệu không?

Nếu chưa trả lời được, annotation mới chỉ hoàn thành phần **hợp đồng gọi API**, chưa hoàn thành thiết kế tích hợp chịu lỗi.

## Tài liệu tham khảo

- [Spring Framework — REST Clients / HTTP Service Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): adapter, kiểu trả về, error handling và proxy.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): connector, connect/read/write timeout và Reactor Netty response timeout.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): mô hình reactive và streaming.
