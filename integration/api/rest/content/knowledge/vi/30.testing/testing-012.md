# Mock server cho lỗi phụ thuộc, độ trễ và phản hồi bất thường

Một REST API có thể hoạt động hoàn hảo khi hệ thống bên ngoài trả `200 OK`, nhưng thất bại ngay khi dịch vụ tính phí vận chuyển trả `503 Service Unavailable`, phản hồi chậm hơn deadline, gửi JSON thiếu trường hoặc đóng kết nối giữa chừng. Nếu chỉ kiểm thử *happy path*, lỗi có thể xuất hiện lần đầu ở production: request bị treo, retry vô hạn, tạo đơn hàng trùng, trả `500` thiếu ngữ cảnh hoặc ghi log chứa token của đối tác.

Trong mô-đun **INTEGRATION_API_REST**, người học thiết kế REST API theo resource, URI, phương thức, mã trạng thái HTTP và hợp đồng dữ liệu rõ ràng. Chương **Kiểm thử** mở rộng hợp đồng đó sang chiều **API của chúng ta gọi một API khác**: client của hệ thống phải hiểu được thành công, lỗi ứng dụng, lỗi hạ tầng và dữ liệu bất thường. Bài này hướng dẫn dựng **mock HTTP server** bằng Java/WireMock để chủ động tạo các tình huống hiếm nhưng quan trọng, sau đó xác minh chính sách timeout, retry, xử lý lỗi, bảo mật và tính nhất quán nghiệp vụ của Spring Boot.

## 1. Mục tiêu và phạm vi

Sau bài học, người học có thể:

1. Phân biệt mock server với mock method, fake repository, contract test và môi trường E2E.
2. Điều khiển status, header, body, độ trễ và lỗi kết nối từ một HTTP dependency mà không phụ thuộc vào dịch vụ thật.
3. Kiểm tra một Java/Spring HTTP client nhận diện đúng `200`, `429`, `500`, `503`, JSON sai, body rỗng, media type lạ và request timeout.
4. Xây retry có giới hạn, có deadline, backoff/jitter và hiểu nguy cơ lặp tác dụng phụ khi dependency dùng `POST`.
5. Viết assertions về request gửi đi, số lần gọi, kết quả trả về, trạng thái dữ liệu và thông tin nhạy cảm không bị lộ.
6. Nhận ra những rủi ro không thể chứng minh bằng mock server đơn lẻ, từ đó bổ sung integration/contract/E2E test phù hợp.

Một mock HTTP server cho phép test điều khiển phản hồi từ **ranh giới HTTP**. Nó không có nghĩa là phải giả lập toàn bộ hệ thống đối tác. Ta chỉ mô tả các hành vi của đối tác mà hợp đồng và thiết kế resilience của ứng dụng cần xử lý.

## 2. Vì sao mock server hữu ích?

Giả sử endpoint `POST /api/v1/orders/preview` cần lấy phí vận chuyển từ một hãng vận chuyển trước khi trả bảng tổng tiền. Ứng dụng nhận request từ client, gọi:

~~~http
GET /v1/quotes?postalCode=700000 HTTP/1.1
Host: shipping-provider.example.test
Accept: application/json
Authorization: Bearer <service-token>
~~~

Dependency thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"fee":25000,"currency":"VND"}
~~~

Nhưng dependency cũng có thể quá tải, hết hạn token, không có dịch vụ cho địa chỉ, gửi HTML lỗi từ gateway hoặc giữ kết nối rất lâu. Ta **không nên** bắt test CI đợi dịch vụ thật hỏng để có dữ liệu kiểm thử. Mock server chạy trên loopback hoặc container riêng, mở một HTTP endpoint trong test, nhận request thực do HTTP client gửi và trả response do test chủ động cấu hình.

~~~mermaid
flowchart LR
    A["Test / MockMvc"] -->|"POST /orders/preview"| B["Spring API thật"]
    B -->|"RestClient: GET /v1/quotes"| C["WireMock HTTP server"]
    C -->|"200 / 429 / 503 / timeout / invalid JSON"| B
    B -->|"200 / 4xx / 5xx theo hợp đồng"| A
    D["Test assertions"] -->|"Kiểm tra HTTP output và số lần gọi"| B
    D -->|"Verify request journal"| C
~~~

Vị trí WireMock thay thế **dịch vụ bên ngoài ở ranh giới mạng**. Controller, service, serializer, interceptor, timeout, retry policy và HTTP client của hệ thống có thể chạy thật. Nhờ đó ta kiểm chứng quá trình xây URL, gửi header, đọc body và ánh xạ lỗi mà mock một phương thức Java không chứng minh được.

### 2.1. Mock server khác các loại test double khác ra sao?

| Công cụ/cách làm | Ranh giới thay thế | Đặc điểm | Thích hợp khi |
| --- | --- | --- | --- |
| Mockito mock `ShippingClient` | Một interface/method Java | Rất nhanh, không có HTTP thật | Unit test logic xử lý giá hoặc quyết định fallback |
| Fake repository in-memory | Persistence port | Có hành vi đơn giản nhưng khác database thật | Kiểm tra thuật toán, quy tắc chuyển trạng thái |
| WireMock/MockWebServer | HTTP endpoint của dependency | Nhận request HTTP, trả status/header/body, tạo delay/fault | Test RestClient/WebClient/HTTP integration và resilience |
| Contract test | Hợp đồng producer-consumer | Kiểm tra request/response có tuân hợp đồng đã thống nhất | Tránh lệch schema, URI và status giữa các đội |
| Môi trường staging/E2E thật | Đường kết nối triển khai | Gồm gateway, DNS, TLS, auth, network và dịch vụ thực/tương đương | Kiểm tra integration thực tế và deployment |

Một mock server do đội consumer tự lập có thể **sai khác** với provider. Vì vậy cần cập nhật mapping theo OpenAPI/contract đã được thống nhất, kết hợp provider verification hoặc một lượng nhỏ test với sandbox thật khi có điều kiện. Nếu test mock server luôn trả đúng điều client mong đợi, ta chỉ chứng minh rằng **client và chính mock do mình viết thống nhất với nhau**.

## 3. Chọn tình huống theo loại thất bại

Trước khi viết code, hãy tạo ma trận **trigger → phản hồi dependency → hành vi mong đợi của API**. Thí dụ dưới đây giả định phí vận chuyển là dữ liệu bắt buộc để báo tổng tiền chính xác; khi không lấy được phí, ứng dụng **không tự đặt phí bằng 0**.

| Tình huống dependency | Điều khiển tại mock | Hành vi mong đợi ở client/API |
| --- | --- | --- |
| Thành công | `200` + JSON hợp lệ | Parse, validate fee/currency và trả kết quả đúng |
| Không có dịch vụ cho địa chỉ | `404` với mã lỗi đã quy ước | Ánh xạ sang lỗi domain như địa chỉ không hỗ trợ; không retry mù |
| Input gửi lên provider sai | `400`/`422` | Xem lại mapping request; không tự động retry y hệt |
| Token dịch vụ không hợp lệ/không đủ quyền | `401`/`403` | Fail an toàn, log mã lỗi đã lọc, alert; không chuyển token ra client |
| Vượt rate limit | `429` + `Retry-After` | Tôn trọng giới hạn, deadline và retry budget nếu được phép |
| Provider quá tải/bảo trì | `503`, có thể có `Retry-After` | Retry có giới hạn hoặc trả lỗi tạm thời theo contract |
| Lỗi máy chủ | `500` | Chính sách retry rõ ràng; không đổi thành “địa chỉ không hợp lệ” |
| Gateway sai | `502`/`504` | Nhận diện là lỗi upstream/gateway, áp dụng timeout/retry budget |
| Response chậm | `200` nhưng delay vượt read timeout | Client không chờ vô hạn; giải phóng tài nguyên |
| Đứt kết nối hoặc response lỗi khung | TCP reset/truncated response nếu công cụ hỗ trợ | Phân loại network/protocol failure, tránh lộ chi tiết nội bộ |
| JSON hỏng cú pháp | `200` + body không parse được | Lỗi hợp đồng upstream; không trả dữ liệu mặc định sai |
| JSON hợp lệ nhưng thiếu `fee` | `200` + body thiếu field | Reject semantic invalid response |
| Media type bất thường | `200` + `text/html` | Không cố nhận HTML là phí vận chuyển |
| Body rỗng không hợp đồng | `204` hoặc `200` body rỗng | Không coi là phí bằng 0 |
| Số tiền âm hoặc đơn vị tiền sai | `200` + `fee:-1` hoặc `currency:"USD"` | Validate domain invariant |
| Response lớn hơn giới hạn | `200` + body quá lớn | Giới hạn kích thước để tránh cạn memory |

Không phải **mọi** lỗi đều cần retry. Lỗi `400`/`401`/`403` thường không được khắc phục bằng gửi lại cùng request; `404` có thể là kết quả hợp lệ của domain. Ngược lại, `429`, `502`, `503`, `504` và lỗi mạng tạm thời có thể retry **nếu thao tác an toàn, ngân sách còn đủ và chính sách đối tác cho phép**. `500` không tự động chứng minh request chưa được xử lý.

### 3.1. Xác định hợp đồng lỗi trước khi mock

Ví dụ provider trả `503` dưới dạng Problem Details:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 2

{
  "type":"https://shipping-provider.example.test/problems/unavailable",
  "title":"Service Unavailable",
  "status":503
}
~~~

Phía API của chúng ta có thể trả `503` hoặc `502` tùy hợp đồng công khai; phải xác định ý nghĩa phù hợp với dịch vụ đang cung cấp. Có thể dùng một mã lỗi ứng dụng như `UPSTREAM_TEMPORARILY_UNAVAILABLE` ở Problem Details, nhưng không sao chép nguyên body thô của provider, endpoint nội bộ hoặc bearer token vào phản hồi cho client. Khi upstream bắt buộc để tính tổng tiền, fallback `fee=0` là sai nghiệp vụ trừ khi có quy tắc dự phòng được sản phẩm cho phép.

## 4. Thiết lập WireMock cho Java/Spring

WireMock hỗ trợ stub HTTP theo method, URL, header, body; trả status, header, JSON, delay và một số lỗi transport mô phỏng. Trong dự án dùng JUnit Jupiter, có thể sử dụng `WireMockExtension` với một cổng ngẫu nhiên để tránh trùng port khi chạy CI.

Các dependency test thường cần:

~~~text
org.wiremock:wiremock          (test)
org.junit.jupiter:junit-jupiter (test)
org.springframework.boot:spring-boot-starter-test (test)
~~~

Chọn phiên bản WireMock phù hợp với Java và build của dự án; artifact thực tế có thể dùng biến thể phù hợp môi trường runtime. Không cố định cổng 8080 trong test vì có thể đã được ứng dụng khác sử dụng. Khi dùng Maven/Gradle, đặt mock server trong scope test, không đóng gói vào production artifact.

### 4.1. HTTP client mà ta muốn kiểm tra

Ví dụ dùng **Spring Framework 6.1+/Spring Boot 3.2+** với `RestClient`. Để tập trung vào HTTP contract, định nghĩa DTO phí và wrapper gọi provider:

~~~java
public record ShippingQuote(BigDecimal fee, String currency) {}

public final class UpstreamContractException extends RuntimeException {
    public UpstreamContractException(String message) {
        super(message);
    }
}

public final class ShippingQuoteClient {
    private final RestClient restClient;

    public ShippingQuoteClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public ShippingQuote quote(String postalCode) {
        ResponseEntity<ShippingQuote> response = restClient.get()
            .uri(uri -> uri.path("/v1/quotes")
                .queryParam("postalCode", postalCode)
                .build())
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(ShippingQuote.class);

        ShippingQuote quote = response.getBody();
        if (quote == null
                || quote.fee() == null
                || quote.fee().signum() < 0
                || !"VND".equals(quote.currency())) {
            throw new UpstreamContractException(
                "Phản hồi báo phí không hợp lệ");
        }
        return quote;
    }
}
~~~

Các import Java (`BigDecimal`), Spring (`RestClient`, `ResponseEntity`, `MediaType`) đã được lược bớt. `RestClient.retrieve()` mặc định ném exception cho status 4xx/5xx; mã minh họa **chưa** chứa chính sách retry/fallback và chưa kiểm tra rõ `Content-Type` trước parse. Nếu cần kiểm soát cả header, response streaming hay giới hạn body, thêm tầng xử lý response có quy tắc thay vì tin rằng kiểu DTO đủ để xác thực mọi phản hồi.

Lưu ý dữ liệu tiền trong ví dụ dùng `BigDecimal`, không dùng `double` để tính tiền. Validation trong client là lớp bảo vệ trước **response có cú pháp JSON đúng nhưng vi phạm hợp đồng nghiệp vụ**; schema OpenAPI nên định nghĩa thêm giá trị hợp lệ, trường bắt buộc và đơn vị tiền.

### 4.2. Cấu hình timeout có thật trong test

Spring `RestClient` dùng một `ClientHttpRequestFactory`. Ví dụ với JDK HTTP client:

~~~java
static RestClient newClient(String baseUrl) {
    HttpClient jdk = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .build();

    JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(jdk);
    factory.setReadTimeout(Duration.ofMillis(150));

    return RestClient.builder()
        .baseUrl(baseUrl)
        .requestFactory(factory)
        .build();
}
~~~

Đây là cấu hình minh họa cho test; thời gian timeout production phải theo SLA và deadline toàn chuỗi gọi. `connectTimeout` giới hạn giai đoạn thiết lập kết nối (theo cơ chế JDK client), còn `readTimeout` kiểm soát chờ phản hồi theo request factory. **Chúng không tự động tạo ra một deadline tổng cho cả chuỗi nhiều lần retry**, và mỗi thư viện client có semantics timeout khác nhau. Khi triển khai phải kiểm tra cách request factory xử lý deadline, cancellation và streaming body.

Test với delay tại một server localhost đã **kết nối thành công** chủ yếu kiểm tra read timeout, không chứng minh connect timeout, DNS timeout, TLS handshake timeout hay proxy ở môi trường thật.

## 5. Test cơ bản bằng WireMockExtension

Trong JUnit 5, khởi động mock server cổng ngẫu nhiên và trỏ `RestClient` tới URL được cấp. Dùng `@RegisterExtension`, stub theo đường dẫn/query và verify số request thực sự được gửi.

~~~java
class ShippingQuoteClientIT {
    @RegisterExtension
    static WireMockExtension shipping = WireMockExtension.newInstance()
        .options(wireMockConfig().dynamicPort())
        .build();

    ShippingQuoteClient client;

    @BeforeEach
    void setup() {
        shipping.resetAll();
        client = new ShippingQuoteClient(newClient(shipping.baseUrl()));
    }

    @Test
    void validJsonIsParsedAndRequestIsCorrect() {
        shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
            .withQueryParam("postalCode", equalTo("700000"))
            .withHeader("Accept", containing("application/json"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"fee":25000,"currency":"VND"}
                    """)));

        ShippingQuote quote = client.quote("700000");

        assertThat(quote.fee())
            .isEqualByComparingTo(new BigDecimal("25000"));
        assertThat(quote.currency()).isEqualTo("VND");
        shipping.verify(1, getRequestedFor(
            urlPathEqualTo("/v1/quotes"))
            .withQueryParam("postalCode", equalTo("700000")));
    }
}
~~~

Các static import WireMock DSL, JUnit, AssertJ và lớp `newClient` ở mục 4.2 được giả định đã khai báo; khi viết code thật nên đặt `newClient` vào test fixture/cấu hình Spring tương ứng. Test này xác minh client gửi đúng method, đường dẫn, query và `Accept`, sau đó parse/validate response. Nếu mock method `ShippingQuoteClient.quote()` bằng Mockito thì test sẽ **không phát hiện** lỗi URL encoding, header hoặc JSON decoder.

Nên thêm assert body mà client gửi ở các request `POST`/`PUT`, ví dụ `equalToJson(...)` với các trường bắt buộc và giá trị chính xác. Với request nhạy cảm, verify cả cách xây `Authorization`/request ID ở mức thích hợp nhưng **không in secret thật** vào log khi test lỗi. Có thể dùng token giả dành riêng test nếu cần xác minh format header.

## 6. Kịch bản lỗi 4xx/5xx và ánh xạ status

### 6.1. Provider trả 503, không được coi là phí 0

~~~java
@Test
void upstream503MustNotBeInterpretedAsValidQuote() {
    shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
        .willReturn(aResponse()
            .withStatus(503)
            .withHeader("Retry-After", "2")
            .withHeader("Content-Type", "application/problem+json")
            .withBody("""
                {"title":"Service Unavailable","status":503}
                """)));

    assertThatThrownBy(() -> client.quote("700000"))
        .isInstanceOf(RestClientResponseException.class)
        .satisfies(error -> {
            RestClientResponseException http =
                (RestClientResponseException) error;
            assertThat(http.getStatusCode().value()).isEqualTo(503);
        });

    shipping.verify(1, getRequestedFor(
        urlPathEqualTo("/v1/quotes")));
}
~~~

Ở mức client **chưa có retry**, xác minh một lần gọi là đúng. Khi thêm retry ở service, cần đổi kỳ vọng theo chính sách mới và bảo đảm có giới hạn. Không hardcode 3 lần gọi trong test nếu đó chưa phải hợp đồng đã được thống nhất. Nếu outer API trả `503` cho client, cần test controller/integration riêng để xác nhận exception được ánh xạ thành Problem Details đã lọc.

Các tình huống `401` và `403` của provider cần được phân loại khác với `401`/`403` của người dùng gọi API của chúng ta. Nếu token **dịch vụ** sai, gửi nguyên `401` của upstream ra client có thể khiến client hiểu nhầm rằng họ phải đăng nhập lại. Hệ thống nên chọn mã lỗi public thích hợp, audit sự kiện cấu hình và tránh làm lộ token, issuer, URL nội bộ.

### 6.2. Ma trận trạng thái cần thử

| Upstream HTTP | Test nên kỳ vọng | Những điều cần tránh |
| --- | --- | --- |
| `200` | Schema, kiểu và giá trị hợp lệ | Mặc nhiên chấp nhận mọi JSON |
| `204` | Nếu contract yêu cầu quote body, báo contract violation | Mặc định phí = 0 |
| `400`/`422` | Xử lý input mapping hoặc domain lỗi theo contract | Retry cùng request sai |
| `401`/`403` | Báo lỗi xác thực/permission của integration | Lộ credential/chi tiết nội bộ ra public API |
| `404` | Nếu theo contract nghĩa là không phục vụ địa chỉ, ánh xạ domain | Coi mọi 404 là server down |
| `409` | Theo contract conflict với trạng thái provider | Đổi thành `500` thiếu ngữ nghĩa |
| `429` | Xử lý rate limit, `Retry-After` và budget | Retry sát nhau tạo thêm áp lực |
| `500` | Lỗi nội bộ provider, có thể transient | Kết luận request write chưa tạo side effect |
| `502`/`503`/`504` | Gateway/service tạm thời lỗi | Vòng lặp vô hạn/timeout không giới hạn |
| `3xx` | Kiểm tra redirect policy của client | Tự động follow redirect sang host không tin cậy, lộ token |

Tùy contract, status ngoài danh sách cũng cần được phân loại rõ. Một số HTTP client tự follow redirect trong vài tình huống; không nên để header `Authorization` hoặc dữ liệu nhạy cảm bị chuyển tới domain lạ. Kiểm tra cấu hình redirect của client hoặc chặn/allowlist đích khi gọi provider. Status `206 Partial Content` không có ý nghĩa cho JSON quote đầy đủ trừ khi provider định nghĩa rõ range contract.

## 7. Mô phỏng độ trễ, timeout và lỗi transport

### 7.1. Response chậm vượt read timeout

~~~java
@Test
void slowProviderMustFailWithinClientTimeout() {
    shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
        .willReturn(aResponse()
            .withStatus(200)
            .withHeader("Content-Type", "application/json")
            .withFixedDelay(800)
            .withBody("""
                {"fee":25000,"currency":"VND"}
                """)));

    assertThatThrownBy(() -> client.quote("700000"))
        .isInstanceOf(ResourceAccessException.class);
}
~~~

Giả định request factory được cấu hình `readTimeout=150 ms` như mục 4.2 và Spring bọc lỗi I/O trong `ResourceAccessException`. Loại exception cụ thể có thể khác theo JDK, request factory hoặc phiên bản framework; trong code thật hãy kiểm tra **loại lỗi mà policy bắt** thay vì phụ thuộc sâu vào tên exception thấp nhất. Delay 800 ms nên **cách biệt rõ** timeout 150 ms để giảm flakiness. Test không nên đòi chính xác một vài millisecond vì CI có jitter.

Nếu test muốn đo giới hạn thời gian tổng, có thể dùng assertion timeout có biên rộng hơn timeout client; đừng chỉ đặt `assertTimeoutPreemptively` để che việc client vẫn đang giữ thread/socket. Cần chứng minh client **thực sự cấu hình timeout ở tầng HTTP** và tài nguyên được giải phóng khi timeout.

### 7.2. Đóng kết nối, reset hoặc response bị hỏng

WireMock có một số fault mode để mô phỏng kết nối bất thường, chẳng hạn:

~~~java
shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
    .willReturn(aResponse()
        .withFault(Fault.CONNECTION_RESET_BY_PEER)));
~~~

Sau đó gọi client và xác minh có lỗi transport được phân loại, không tạo thành một `ShippingQuote` hợp lệ và không làm ứng dụng treo. Trong mạng thực, connection reset có thể xảy ra **trước** khi request tới provider, **trong** khi provider xử lý hoặc **sau** khi side effect đã xảy ra. Chỉ quan sát exception ở client **không thể kết luận provider đã hoặc chưa thực hiện thao tác**.

Các lỗi như DNS NXDOMAIN, TLS handshake sai chứng chỉ, route/firewall, proxy timeout, packet loss và kết nối half-open có thể cần hạ tầng kiểm thử riêng (toxiproxy, network namespace, container/proxy hoặc staging). WireMock ở localhost chủ yếu phù hợp với response-level faults và một số lỗi kết nối do server tạo. Khi thử TLS thật, **không tắt certificate/hostname verification** chỉ để test thành công.

### 7.3. Timeout thuộc nhiều tầng khác nhau

| Thời gian/giới hạn | Ai kiểm soát | Điều gì có thể xảy ra nếu thiếu? |
| --- | --- | --- |
| DNS/connect timeout | HTTP client/OS/network | Thread bị giữ khi chưa kết nối thành công |
| TLS handshake timeout | HTTP client/TLS stack | Bắt tay treo hoặc mất quá nhiều thời gian |
| Read/response timeout | HTTP client | Chờ response header/body vô hạn |
| Per-attempt timeout | Retry wrapper/client | Một lần gọi chiếm toàn bộ budget |
| Overall deadline | Application service/API gateway | Nhiều retry cộng lại vượt SLO của request |
| Queue/connection pool timeout | HTTP client pool | Đợi connection rảnh kéo dài |
| Gateway timeout | Ingress/reverse proxy | Client nhận `504` dù backend còn xử lý |

Hãy thiết kế **deadline xuyên suốt**: ví dụ API cần phản hồi trong 2 giây thì nhiều lần chờ provider 1,5 giây cộng delay có thể đã vượt hạn. Timeout là chính sách vận hành, không tự động hủy một tác dụng phụ đã gửi tới provider. Khi sử dụng reactive client, cơ chế cancellation và scheduler cần được kiểm thử tương ứng.

## 8. JSON hợp lệ nhưng nội dung sai còn nguy hiểm hơn JSON hỏng

Không chỉ test parser ném exception khi response là dấu `{` chưa đóng. Nhiều lỗi tương thích lặng lẽ hơn: provider trả status 200, JSON hợp lệ nhưng thiếu `fee`, đơn vị tiền thay đổi hoặc giá trị âm. Nếu DTO dùng primitive `int`/`double`, trường vắng mặt có thể thành giá trị mặc định khiến API tính sai.

### 8.1. Dựng response bất thường

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "{}",
    "{\"fee\":-1,\"currency\":\"VND\"}",
    "{\"fee\":25000,\"currency\":\"USD\"}",
    "{\"fee\":null,\"currency\":\"VND\"}"
})
void semanticallyInvalidJsonIsRejected(String body) {
    shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
        .willReturn(aResponse()
            .withStatus(200)
            .withHeader("Content-Type", "application/json")
            .withBody(body)));

    assertThatThrownBy(() -> client.quote("700000"))
        .isInstanceOf(UpstreamContractException.class);
}
~~~

Ví dụ `ShippingQuoteClient` chủ động kiểm tra `fee != null`, số tiền không âm và currency được chấp nhận. Test parser riêng nên gửi JSON hỏng cú pháp hoặc sai kiểu như `{"fee":"abc","currency":"VND"}` rồi assert lỗi chuyển đổi dữ liệu. Không bắt mọi exception rồi lặng lẽ trả phí 0.

### 8.2. Content-Type và body size

Một upstream gateway có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8

<html><body>Service maintenance</body></html>
~~~

Nếu contract yêu cầu `application/json`, client nên phân loại đây là **protocol/contract violation**, không đối xử như dữ liệu JSON hợp lệ. Kiểm tra media type có thể triển khai ở response handler/interceptor trước khi deserialize. Cẩn thận với HTTP client: một số converter chọn theo media type và ném lỗi, một số cấu hình khác có thể cố parse nội dung. Test phải kiểm tra hành vi **đang chạy thật** của client.

Với response cực lớn, đừng tạo một chuỗi JSON khổng lồ trong mỗi unit test chỉ để tốn RAM. Có thể dựng một fixture đủ vượt giới hạn và kiểm tra cơ chế dừng đọc hoặc streaming giới hạn. **Mock server chỉ phát body lớn; chính client/gateway phải có giới hạn** (ví dụ max in-memory size, streaming parser, content-length guard). Không tin `Content-Length` một cách tuyệt đối vì body có thể dùng chunked transfer hoặc header bị sai.

### 8.3. Trường mới, enum lạ và tương thích tiến hóa

Một provider có thể bổ sung trường mới mà client cũ không dùng, hoặc bổ sung giá trị enum. Hãy phân biệt **mở rộng hợp lệ** với **phá vỡ contract**:

- Trường JSON mới không ảnh hưởng business logic thường có thể được bỏ qua nếu hợp đồng cho phép mở rộng.
- Trường bắt buộc bị bỏ, đổi kiểu hoặc đổi ý nghĩa phải bị phát hiện.
- Enum mới cần chính sách rõ: fail closed, trạng thái `UNKNOWN` được xử lý, hoặc ánh xạ theo phiên bản; không tự mặc định thành `SUCCESS`.
- Nếu response được ký hoặc có checksum, cần kiểm tra chữ ký/toàn vẹn ngoài JSON syntax.

Contract test nên giúp cả provider và consumer thống nhất những kỳ vọng này, còn mock server giúp buộc client đi qua các nhánh xử lý.

## 9. Retry, backoff, rate limit và circuit breaker

**Retry** có thể giúp vượt qua lỗi tạm thời, nhưng cũng làm quá tải dependency và kéo dài response. Muốn test retry đúng, mock server cần kiểm soát **chuỗi phản hồi theo từng lần gọi**, không chỉ một response cố định.

### 9.1. Tạo chuỗi 503 rồi 200

WireMock cho phép tạo **scenario state**:

~~~java
shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
    .inScenario("quote-temporary-failure")
    .whenScenarioStateIs(Scenario.STARTED)
    .willReturn(aResponse().withStatus(503))
    .willSetStateTo("recovered"));

shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
    .inScenario("quote-temporary-failure")
    .whenScenarioStateIs("recovered")
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"fee":25000,"currency":"VND"}
            """)));
~~~

Sau đó test gọi **component thật có áp dụng retry**, kiểm tra kết quả cuối là quote hợp lệ và WireMock nhận **đúng hai request**. `ShippingQuoteClient` minh họa ở mục 4.1 chưa có retry, nên nếu gọi nó nguyên trạng, test đúng sẽ dừng ở lần `503` đầu tiên. Khi đã thêm retry policy, mới viết:

~~~java
ShippingQuote quote = retryingQuoteService.quote("700000");

assertThat(quote.fee())
    .isEqualByComparingTo("25000");
shipping.verify(2, getRequestedFor(
    urlPathEqualTo("/v1/quotes")));
~~~

`retryingQuoteService` ở đây đại diện cho thành phần cần xây dựng bằng Spring Retry, Resilience4j hoặc logic ứng dụng tương đương; không phải bean có sẵn trong code mẫu. Test phải chỉ rõ **số lần tối đa** và điều kiện retry, tránh vô tình viết test để xác nhận “mọi lỗi đều retry”.

### 9.2. Thiết kế retry policy trước khi kiểm thử

| Thành phần chính sách | Câu hỏi cần trả lời | Kịch bản mock |
| --- | --- | --- |
| Loại lỗi có thể retry | Chỉ `429`/`502`/`503`/`504`, I/O transient hay cả `500`? | Gửi lần lượt các status; verify call count |
| Số lần tối đa | 2 hay 3 lần gọi tổng cộng, tính cả lần đầu? | Upstream luôn `503`; bảo đảm dừng |
| Backoff | Fixed, exponential, capped, jitter? | Ghi timestamp/clock để kiểm tra khoảng chờ, tránh sleep chính xác |
| Retry-After | Hỗ trợ số giây, HTTP-date và giới hạn tối đa? | `429`/`503` với từng dạng header |
| Overall deadline | Tổng thời gian request cho phép bao lâu? | Response liên tiếp chậm; không vượt budget |
| Idempotency | Method an toàn? Có khóa idempotency cho `POST` không? | Verify key giữ nguyên qua retry |
| Circuit breaker | Khi nào mở, half-open, hồi phục? | Nhiều lỗi liên tiếp, rồi upstream hồi phục |
| Bulkhead/rate limit | Có giới hạn concurrent call/retry storm không? | Nhiều request song song, tính số request upstream |

`Retry-After` có thể chứa **delta-seconds** hoặc ngày HTTP; client phải parse theo chuẩn và giới hạn bởi deadline. Jitter giúp tránh hàng loạt client retry đồng thời khi provider hồi phục. Với test backoff, tốt nhất tách scheduler/clock để kiểm tra logic có tính quyết định; test một số ít trường hợp integration với thời gian thực để xác minh việc wiring.

### 9.3. Retry không tự động an toàn cho POST

Giả sử đặt thanh toán:

~~~http
POST /v1/charges HTTP/1.1
Authorization: Bearer <service-token>
Idempotency-Key: "order-123-charge"
Content-Type: application/json

{"orderId":"order-123","amount":250000,"currency":"VND"}
~~~

Provider đã thu tiền nhưng kết nối bị reset **trước khi client nhận `201`**. Nếu hệ thống tự retry với **Idempotency-Key khác**, nó có thể thu tiền lần hai. Khi giao tiếp với API có side effect, cần hợp đồng provider bảo đảm idempotency/reconciliation và giữ nguyên key cho cùng nghiệp vụ, hoặc dừng và truy vấn trạng thái bằng định danh ổn định. Một lỗi `500` cũng không chứng minh tác dụng phụ đã rollback ở provider.

Mock server có thể verify key không thay đổi giữa hai lần gửi. Tuy nhiên, **mock không chứng minh provider xử lý key đúng**; điều này cần contract/provider test hoặc xác minh với sandbox/SDK chính thức. Khi thử tình huống response mất sau commit, mô hình hóa **trạng thái phía provider** rồi kiểm tra ứng dụng không tạo giao dịch trùng.

### 9.4. Circuit breaker và bulkhead

Circuit breaker không đồng nghĩa retry. Sau một ngưỡng thất bại, circuit mở và từ chối gọi upstream trong một thời gian; khi hồi phục, chỉ cho phép lượng request thử được kiểm soát. Test cần xác nhận những request khi circuit mở **không chạm mock server**, sau đó trạng thái half-open được xử lý theo policy. Dùng clock/scheduler kiểm soát nếu thư viện hỗ trợ để test ổn định.

Bulkhead và connection pool hạn chế số request đồng thời, ngăn một provider chậm dùng hết thread/connection của API. Mock server có thể trả chậm để tạo áp lực, nhưng load test thực tế cần môi trường kiểm soát tài nguyên và giám sát; không diễn giải một bài test đơn luồng là bằng chứng chống quá tải.

## 10. Tích hợp mock server vào Spring Boot integration test

Khi muốn test **controller thật → service thật → RestClient thật → mock upstream**, giữ URL của dependency trong cấu hình, thay thế URL bằng WireMock ở môi trường test, không sửa production code để “biết đang test”.

Ví dụ cấu hình ứng dụng:

~~~yaml
shipping:
  base-url: https://shipping-provider.example.test
  read-timeout: 500ms
~~~

Trong integration test có thể inject cổng động:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderPreviewHttpIT {
    @RegisterExtension
    static WireMockExtension shipping = WireMockExtension.newInstance()
        .options(wireMockConfig().dynamicPort())
        .build();

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("shipping.base-url", shipping::baseUrl);
    }

    @Autowired MockMvc mvc;

    @Test
    void providerUnavailableMapsToStableApiError() throws Exception {
        shipping.stubFor(get(urlPathEqualTo("/v1/quotes"))
            .willReturn(aResponse().withStatus(503)));

        mvc.perform(post("/api/v1/orders/preview")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.preview")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"skuId":"11111111-1111-4111-8111-111111111111",
                     "quantity":1,"postalCode":"700000"}
                    """))
            .andExpect(status().isServiceUnavailable())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.valueOf("application/problem+json")));
    }
}
~~~

Đoạn mã là **khung bài test**: giả định ứng dụng có endpoint `/api/v1/orders/preview`, Spring Security Test, xử lý `503` thành Problem Details và bean `ShippingQuoteClient` đọc cấu hình `shipping.base-url`. Các import Spring Test, MockMvc, WireMock DSL và JUnit được lược bớt. Với cấu hình client có retry, mock server phải được reset giữa các test và assert số lần gọi theo chính sách. Một số bản tích hợp extension có lifecycle khác với `@DynamicPropertySource`; nếu property được đọc trước khi server khởi động, nên dùng setup theo lifecycle chắc chắn (ví dụ static WireMockServer start/stop, hoặc tích hợp Spring đã được dự án chọn).

`with(jwt())` của Spring Security Test **giả lập authentication**, không kiểm tra chữ ký JWT, issuer, audience hoặc TLS thật. Nếu API dùng cookie/CSRF, bài test phải dùng authentication và CSRF request post-processors phù hợp. Chỉ mock **upstream dependency**, còn controller/service/error handler cần chạy thật khi ta muốn kiểm tra contract API ngoài.

### 10.1. Nếu ứng dụng dùng WebClient

WireMock vẫn hoạt động vì nó là HTTP server; ta chỉ thay HTTP client ở phía ứng dụng bằng `WebClient`. Cần kiểm tra mapping status với `onStatus`, `responseTimeout`/`timeout`, cancellation, pool timeout và cách tiêu thụ body để tránh memory leak. Reactive client không nên gọi `block()` trong event loop của WebFlux. Test bằng `StepVerifier`/WebTestClient khi cần, nhưng vẫn dựng các HTTP fault ở mock server và verify request bên ngoài thật sự được gửi.

### 10.2. Tránh lẫn test mức controller và integration

Một `@WebMvcTest` với `ShippingService` mock chủ yếu chứng minh mapping HTTP, validation và error handler. Một `@SpringBootTest` dùng HTTP client thật nối WireMock mới kiểm tra cách client xử lý `Retry-After`, JSON bất thường hoặc timeout. Dùng Mockito cho logic domain tại unit test vẫn hữu ích; chỉ đừng tuyên bố đã kiểm thử HTTP resilience nếu chưa có HTTP request thực.

## 11. Assertions phải kiểm tra hành vi, không chỉ status

Với upstream trả `503` và API trả `503`, chỉ kiểm tra status dễ bỏ sót những lỗi nguy hiểm: tạo đơn trước khi gọi quote, retry 100 lần hoặc ghi token vào log. Bài test nên quan sát nhiều lớp:

1. **Request gửi đi:** method, path, query, `Accept`/`Content-Type`, auth header, idempotency key, correlation/request ID; query được encode đúng.
2. **Số lần gọi:** đúng với policy retry, không lặp đối với lỗi không retry; kịch bản circuit mở không gọi upstream.
3. **Kết quả API:** đúng mã HTTP và Problem Details, response không lộ host/token/stack trace upstream.
4. **Tác dụng phụ:** không tạo order, charge, inventory reservation hay outbox event nếu báo phí thất bại trước quyết định nghiệp vụ; hoặc ghi trạng thái PENDING rõ ràng nếu workflow cho phép.
5. **Tài nguyên:** timeout có giới hạn, connection và thread không bị giữ vô thời hạn.
6. **Khả năng truy vết:** có request ID/trạng thái upstream trong metric/log được lọc, không chứa secret, PII không cần thiết hoặc body nhạy cảm.

Khi test gửi request có header `Authorization`, nên dùng giá trị test giả và log-masking trong test harness; không cài test để in toàn bộ request journal ra CI artifact. Một failure assertion có thể vô tình dump header/token. Chỉ log dữ liệu tối thiểu để debug và scrub theo chính sách.

### 11.1. Assertion về lỗi sau partial side effect

Ví dụ API tạo đơn rồi mới gọi provider, provider timeout, transaction của đơn có thể đã commit. Vì vậy test cần phân biệt:

- Nếu quote **bắt buộc trước khi tạo đơn**, lỗi quote phải khiến không có đơn/tác dụng phụ.
- Nếu hệ thống có **quy trình bất đồng bộ**, API có thể commit đơn ở trạng thái `PENDING_QUOTE` và outbox event, rồi trả `202 Accepted`; worker xử lý lỗi provider/retry riêng.
- Nếu đã gọi một provider có side effect, transaction local không rollback được tác dụng phụ đó; cần idempotency và trạng thái reconciliation.

Mock server không tự cung cấp đảm bảo nhất quán nghiệp vụ. Chính assertions trên database/job queue và điều kiện commit mới xác nhận hành vi của hệ thống khi dependency lỗi.

## 12. Kỹ thuật quản lý stub và tránh flaky test

Mock server giúp test có tính quyết định hơn mạng thật, nhưng vẫn có thể flake nếu viết thiếu kiểm soát:

- Dùng **cổng ngẫu nhiên** và truyền base URL qua cấu hình thay vì cố định `localhost:8080`.
- **Reset stubs, scenario state và request journal** giữa các test; không để mapping của test trước ảnh hưởng test sau.
- Không cho nhiều bài test song song dùng chung scenario state khi chúng phụ thuộc thứ tự gọi. Nếu cần chạy song song, tạo mock server riêng per test hoặc namespace hóa request/mapping.
- Tránh stub quá rộng như `anyRequestedFor(anyUrl())`/một mapping `200` cho mọi request: nó che lỗi URL, method và header.
- Phát hiện **unmatched requests** thay vì để WireMock trả mặc định `404` rồi client hiểu nhầm rằng provider không có dữ liệu.
- Với delay, chọn biên đủ xa timeout để tránh flake do CPU/GC scheduling; dùng fake clock cho test logic backoff.
- Tránh dùng `Thread.sleep` cố định trong assertions async; chờ điều kiện có deadline và giới hạn số lần kiểm tra.
- Không chia sẻ ID, idempotency key, database row hoặc user test giữa các test chạy song song nếu chúng có thể ảnh hưởng trạng thái.
- Không thử nghiệm lỗi nguy hiểm bằng cách nhắm vào sandbox/production của đối tác; dùng mock/server test riêng theo thỏa thuận.

### 12.1. Contract từ OpenAPI và fixture

Lưu các mẫu response thành công và lỗi dựa vào schema của provider. Với những response như `application/problem+json`, schema có thể khác JSON thành công; đừng cố deserialize mọi response thành một DTO. Test consumer nên verify chính xác các field bắt buộc, enum, header, status và compatibility policy; một test contract phía provider là bằng chứng mạnh hơn giả định từ stub do consumer tự tạo.

Mỗi fixture nên có tên mô tả hành vi (ví dụ `quote-503-retry-after`, `quote-200-missing-fee`, `quote-slow-800ms`), nhưng chỉ dùng đúng những biến thể có ý nghĩa. Đừng duy trì hàng trăm body giống nhau để tạo vẻ phủ rộng; ưu tiên ma trận theo lớp lỗi và bảo đảm một case chỉ ra rõ nguyên nhân khi thất bại.

### 12.2. Chọn chế độ record/replay cẩn thận

WireMock có chức năng ghi lại traffic và replay, thuận tiện tạo fixture ban đầu. Tuy nhiên, response thực có thể chứa access token, cookie, địa chỉ, thông tin khách hàng hoặc ID nhạy cảm. Nếu ghi traffic, phải dùng môi trường/dữ liệu test được phép và **loại bỏ/ẩn thông tin nhạy cảm trước khi lưu fixture**. Fixture cũ cũng có thể không đại diện cho version mới của provider; record/replay không thay thế contract review.

## 13. Kết hợp test theo các tầng

Một cách phân bổ hợp lý cho tính năng báo phí vận chuyển:

| Rủi ro | Unit test | Mock HTTP integration | Provider sandbox / E2E |
| --- | --- | --- | --- |
| Tính tổng đơn và quy tắc phí | Test domain thuần Java | Xác minh DTO từ provider đúng | Vài luồng đặt hàng thực |
| URL, query, encoding, auth headers | Không đủ bằng chứng nếu chỉ mock interface | Verify WireMock request journal | Kiểm tra cấu hình thật khi triển khai |
| `429`/`503` và Retry-After | Test retry decision bằng fake clock | Test chuỗi 503→200 và call count | Theo dõi rate limit thực |
| Read timeout/connection reset | Test classification ở logic | Delay/fault injection qua WireMock | Kiểm thử network/proxy chọn lọc |
| Malformed/semantic-invalid JSON | Test validator/mapper | Trả body/status thật qua HTTP | Contract test với provider |
| SSL/DNS/certificate/hostname | Không chứng minh được | Local TLS mock có giới hạn | E2E/infra test tại ingress/provider thực |
| Retry POST gây side effect trùng | Unit test policy key | Verify key được giữ qua retry | Contract/sandbox xác nhận provider idempotency |
| Transaction rollback hoặc outbox | Unit test domain decision | Kết hợp database thật và WireMock | Workflow E2E theo trạng thái cuối |
| CORS/auth của API public | Controller/security slice | Mock upstream + Spring filter chain | Browser/ingress thật theo nhu cầu |

Ở PR, nên chạy unit và mock HTTP integration ổn định để có phản hồi nhanh; test với sandbox/provider thật có thể chạy theo lịch hoặc trước release, tùy SLA và quyền sử dụng. Trong cả hai trường hợp, test cần giữ tính độc lập, không dựa vào outage thật của provider và không làm phát sinh chi phí/giao dịch thật ngoài chủ đích.

## 14. Bài tập thực hành

**Bài tập 1 — Dựng mock server có hợp đồng.** Với `GET /v1/quotes?postalCode=700000`, cấu hình WireMock trả `200` JSON phí 25.000 VND. Viết `ShippingQuoteClient` bằng `RestClient`, kiểm tra client gửi đúng method/query/`Accept`, parse `BigDecimal` và từ chối currency ngoài danh sách. Sau đó thêm `200` có field mới không ảnh hưởng kết quả để kiểm thử khả năng mở rộng hợp đồng.

**Bài tập 2 — Lỗi HTTP và phân loại retry.** Mock lần lượt `400`, `401`, `404`, `429` và `503`. Định nghĩa lỗi domain/transport nào được retry, response public API nên có status nào và không được rò thông tin gì. Viết test khẳng định 400/401 không retry, 429/503 chỉ retry trong budget được phép.

**Bài tập 3 — Delay, timeout và lỗi JSON.** Cấu hình `withFixedDelay(800)` trong khi read timeout là 150 ms. Kiểm tra request thất bại có giới hạn thời gian và không giữ trạng thái “đang xử lý” vô hạn. Thử thêm JSON sai cú pháp, thiếu `fee`, `fee=-1`, `currency="USD"`, response `text/html` và `204` rỗng. Mỗi case phải có kỳ vọng riêng, không trả phí mặc định 0.

**Bài tập 4 — Retry có trạng thái.** Dùng WireMock scenario trả `503` lần đầu rồi `200` lần hai. Tạo retry policy cho GET với tối đa hai lần gọi, backoff có giới hạn và deadline. Xác minh đúng hai request. Thay mock thành “luôn 503” và chứng minh request kết thúc đúng hạn, không chạy retry vô hạn; thử thêm `Retry-After` quá dài so với deadline.

**Bài tập 5 — Giao dịch thanh toán có response bị mất.** Tạo mock `POST /v1/charges` nhận `Idempotency-Key`. Mô phỏng provider đã tạo charge nhưng kết nối bị reset trước khi trả kết quả. Thiết kế cách ứng dụng xác định trạng thái cuối bằng cùng key hoặc API truy vấn, tránh charge thứ hai. Viết test chứng minh các lần gọi giữ nguyên key và không tạo hai giao dịch nghiệp vụ ở phía ứng dụng.

**Bài tập 6 — Kiểm thử API hoàn chỉnh.** Tạo `POST /api/v1/orders/preview` với controller/service thật và WireMock thay dependency báo phí. Khi provider trả `503`, API cần trả Problem Details có status phù hợp và không tạo order; khi provider trả `200`, API trả tổng tiền đã bao gồm phí. Dùng MockMvc và database test để quan sát không có side effect trong nhánh lỗi; phân biệt test này với `@WebMvcTest` chỉ mock service.

### Tiêu chí đánh giá

Lời giải đạt yêu cầu khi (1) mock server nhận **HTTP request thật** từ client; (2) test phân loại lỗi theo HTTP status, transport và contract; (3) có thử delay/timeout và response hỏng; (4) retry bị chặn bởi max attempts/deadline, tôn trọng idempotency; (5) assertions bao gồm request journal, kết quả và side effect; (6) fixture/test độc lập, không chứa bí mật; và (7) nêu rõ những hành vi phải kiểm tra với provider hoặc hạ tầng thật.

## 15. Checklist khi review kiểm thử dependency

- [ ] Mỗi dependency có contract HTTP và bảng xử lý status/exception/timeout rõ ràng; không gộp mọi lỗi thành “không có dữ liệu”.
- [ ] Mock server chạy trên cổng ngẫu nhiên, URL được cấu hình từ test, stub và request journal được reset.
- [ ] Có happy path, 4xx/5xx quan trọng, `429 Retry-After`, delay, connection reset, JSON hỏng, JSON hợp lệ nhưng sai nghiệp vụ và media type lạ.
- [ ] Test xác minh method, path, query, body, header và **số lần gọi**; stub quá rộng không che lỗi contract.
- [ ] Timeout tại HTTP client và overall deadline được kiểm tra; test không dùng wait vô hạn hoặc sleep cố định.
- [ ] Retry có max attempts, backoff/jitter/deadline; chỉ áp dụng khi thao tác an toàn hoặc có idempotency rõ ràng.
- [ ] Không nhầm response mất với rollback của provider; POST có side effect cần key/tra cứu trạng thái/reconciliation.
- [ ] Lỗi upstream được ánh xạ thành HTTP/Problem Details ổn định; response/log không lộ token, cookie, private URL hay thông tin nhạy cảm.
- [ ] Test lỗi có assertions về trạng thái DB/outbox/job để chứng minh không tạo side effect sai.
- [ ] Contract/provider verification và E2E bổ sung phần mock không chứng minh được như TLS, DNS, mạng thật và cách provider thực thi idempotency.

**Điểm cốt lõi:** mock HTTP server giúp tạo ra **những phản hồi bất lợi nhưng có thể tái hiện** của dependency để kiểm tra chính sách lỗi, timeout và retry của API. Giá trị của bài test nằm ở việc xác minh cả request gửi đi, phản hồi trả về và bất biến nghiệp vụ sau lỗi; mock server là công cụ mô phỏng ranh giới HTTP, còn hợp đồng provider và hạ tầng thật vẫn phải được kiểm chứng ở các tầng phù hợp.
