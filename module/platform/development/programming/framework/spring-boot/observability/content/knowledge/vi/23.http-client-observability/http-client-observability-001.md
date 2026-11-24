# http.client.requests

Trong chương **HTTP client observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, http.client.requests là tên Observation/Meter phổ biến mà Spring Framework và Micrometer dùng để ghi nhận hoạt động gọi HTTP outbound. Observation giúp ứng dụng Spring Boot đo thời gian gọi dịch vụ bên ngoài, theo dõi status/outcome và tạo client span khi tracing được bật. Nhờ đó, đội vận hành có thể nhận ra dependency nào chậm, tỷ lệ lỗi tăng ở client hay request bị timeout trước khi ảnh hưởng lan rộng.

HTTP client observability chỉ hoạt động đúng khi client được tạo và cấu hình theo cách có tích hợp Observation. Không phải mọi lệnh HTTP đều tự động được đo: client tự khởi tạo, builder không có ObservationRegistry hoặc thư viện không có instrumentation có thể bỏ qua pipeline. Bài này giải thích cách hoạt động của http.client.requests với Spring Boot, Micrometer Observation, các HTTP clients thường dùng, tags, tracing context, kiểm thử và troubleshooting.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của http.client.requests trong HTTP client observability.
2. Phân biệt client Observation, metrics timer và client span.
3. Xác định các tag thường gặp như method, uri, status, outcome và exception.
4. Cấu hình RestTemplate, RestClient và WebClient để dùng ObservationRegistry.
5. Hiểu vì sao custom client/builder có thể làm mất instrumentation mặc định.
6. Kiểm soát URI template và cardinality của outbound request metrics.
7. Liên kết client spans với server spans qua trace context propagation.
8. Phân biệt HTTP error response, exception, timeout và retry.
9. Kiểm tra metric qua Actuator và backend metrics.
10. Viết integration test để xác minh observation được tạo đúng và không rò dữ liệu nhạy cảm.

## 2. http.client.requests là gì?

http.client.requests là Observation name thường dùng cho một HTTP client exchange được instrument bởi Spring Framework. Khi client thực hiện request, instrumentation tạo Observation quanh vòng đời gửi request và nhận response. Observation có thể được xử lý bởi nhiều handler:

- Micrometer metrics handler ghi timer và tags.
- Micrometer Tracing handler tạo client span.
- Observation handlers khác có thể bổ sung logging hoặc convention.

Một HTTP client Observation giúp trả lời: gọi dependency nào và bằng HTTP method nào; request mất bao lâu; response status thuộc nhóm nào; lỗi xảy ra ở DNS/connect/TLS/read hay trong quá trình xử lý; request downstream có được nối vào trace hiện tại không?

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| HTTP client Observation | Mô tả một lần HTTP exchange ở cấp instrumentation. | http.client.requests |
| Timer metric | Tổng hợp số lần gọi và thời gian. | Count, total time, max, histogram. |
| Client span | Biểu diễn một lần gọi outbound trong distributed trace. | GET inventory-service /items/{id} |
| Log record | Ghi sự kiện hoặc lỗi cụ thể. | Timeout khi gọi inventory. |

Observation là điểm tích hợp chung. Metrics và tracing là các biểu diễn khác nhau của cùng hoạt động; chúng không nhất thiết có cùng tags hoặc retention. Tên meter có thể được backend chuyển đổi khi export, ví dụ Prometheus timer series có suffix _seconds_count, _seconds_sum và histogram buckets. Hãy xác minh naming convention của registry đang dùng.

## 3. Vòng đời của HTTP client Observation

~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Client as Instrumented HTTP client
    participant Registry as ObservationRegistry
    participant Handler as Observation handlers
    participant Remote as Downstream service

    App->>Client: Gửi HTTP request
    Client->>Registry: Start http.client.requests
    Registry->>Handler: Bắt đầu metrics/tracing
    Client->>Remote: HTTP request + trace context
    Remote-->>Client: HTTP response
    Client->>Registry: Stop Observation
    Registry->>Handler: Record duration/status/span
    Client-->>App: Trả response hoặc exception
~~~

Observation thường bắt đầu khi client thực hiện exchange và kết thúc khi nhận response hoặc gặp lỗi. Thời gian ghi nhận phụ thuộc implementation/instrumentation và bao gồm phần chờ response trong lifecycle được đo.

Client span thường là child của span hiện tại nếu context propagation hoạt động. Nếu không có span hiện tại, client instrumentation có thể tạo root span hoặc không có quan hệ parent như mong đợi tùy context.

Không tự tạo Observation cùng tên quanh client call nếu client đã tự instrument; làm vậy có thể tạo timer/span trùng. Nếu muốn đo business operation lớn hơn, tạo Observation tên riêng bao quanh thao tác và để HTTP client Observation mô tả dependency exchange bên trong.

## 4. Những HTTP client được hỗ trợ

Spring Framework cung cấp instrumentation cho một số HTTP client abstraction phổ biến. Spring Boot auto-configuration có thể cung cấp builder/bean đã tích hợp Observation khi dependencies và cấu hình phù hợp.

| Client | Cách tích hợp thường dùng | Điểm cần chú ý |
| --- | --- | --- |
| RestTemplate | RestTemplateBuilder và observation registry/interceptors phù hợp. | Tạo từ Boot builder để nhận customizers. |
| RestClient | RestClient.Builder được Boot cấu hình. | Dùng builder được inject; không tự tạo builder rời nếu cần auto-configuration. |
| WebClient | WebClient.Builder với ObservationRegistry. | Dùng reactive client builder đã được Boot cấu hình. |
| Java HttpClient/Apache/OkHttp | Tùy thư viện và instrumentation tương ứng. | Không mặc định có Micrometer Observation chỉ vì có Actuator. |

Tên API và auto-configuration phụ thuộc Spring Boot/Spring Framework version. RestClient có trong các dòng Spring Framework mới hơn; ứng dụng cũ có thể chỉ dùng RestTemplate hoặc WebClient.

## 5. Cấu hình RestTemplate

Trong Spring Boot, inject RestTemplateBuilder rồi tạo client từ builder:

~~~java
@Service
public class InventoryClient {
    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplateBuilder builder) {
        this.restTemplate = builder
                .rootUri("http://inventory-service")
                .build();
    }

    public InventoryResponse findItem(String itemId) {
        return restTemplate.getForObject(
                "/items/{itemId}",
                InventoryResponse.class,
                itemId);
    }
}
~~~

Boot builder có thể áp dụng customizers, message converters và observation customization đã được cấu hình. Nếu tự tạo new RestTemplate() hoặc thay request factory/interceptors không đúng cách, bạn có thể bỏ qua cấu hình tích hợp.

Ví dụ bean dùng builder:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {
    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://inventory-service").build();
    }
}
~~~

Không tạo nhiều RestTemplate không cần thiết trong mỗi method. Tái sử dụng client được cấu hình, connection pool và timeout phù hợp.

## 6. Cấu hình RestClient

RestClient là synchronous fluent HTTP client trong Spring Framework. Spring Boot có thể cung cấp RestClient.Builder đã được tùy chỉnh:

~~~java
@Service
public class PricingClient {
    private final RestClient restClient;

    public PricingClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://pricing-service")
                .build();
    }

    public PriceResponse getPrice(String sku) {
        return restClient.get()
                .uri("/prices/{sku}", sku)
                .retrieve()
                .body(PriceResponse.class);
    }
}
~~~

Dùng builder được inject để giữ customizers và ObservationRegistry do Boot cấu hình. Nếu tự gọi factory/builder độc lập, cần tự gắn ObservationRegistry theo API của Spring Framework đang dùng.

## 7. Cấu hình WebClient

WebClient là reactive HTTP client. Spring Boot có thể cung cấp WebClient.Builder đã được cấu hình với ObservationRegistry:

~~~java
@Service
public class CatalogClient {
    private final WebClient webClient;

    public CatalogClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    public Mono<ProductResponse> getProduct(String productId) {
        return webClient.get()
                .uri("/products/{productId}", productId)
                .retrieve()
                .bodyToMono(ProductResponse.class);
    }
}
~~~

Dùng builder được inject giúp giữ customizers, connector và Observation configuration do Boot quản lý. Reactive pipeline có thể chạy qua nhiều thread; trace context phải được propagate qua Reactor context và instrumentation tương ứng. Không tự đọc MDC trên một thread rồi giả định mọi callback đều nhìn thấy giá trị đó.

Nếu tạo WebClient bằng builder độc lập, hãy gắn ObservationRegistry đúng cách và kiểm tra context propagation. Tránh tạo Observation thủ công quanh từng operator khi instrumentation client đã bao phủ exchange.

## 8. Tags của http.client.requests

Các low-cardinality tags thường dùng trong HTTP client metrics:

| Tag | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| method | HTTP method. | GET, POST |
| uri | URI template/route pattern nếu xác định được. | /items/{itemId} |
| client.name | Host/service đích đã chuẩn hóa. | inventory-service |
| status | HTTP response status. | 200, 404, 503 |
| outcome | Nhóm kết quả. | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| exception | Loại exception nếu exchange kết thúc bằng exception. | ResourceAccessException |

Tag cụ thể phụ thuộc convention, client và version. Hãy inspect meter trong Actuator thay vì copy nguyên danh sách từ version khác.

### URI template quan trọng với client metrics

Không tạo metric tag từ full URL hoặc raw path có identifier:

~~~text
/items/1001
/items/1002
/items/1003
~~~

Dùng template ổn định:

~~~text
/items/{itemId}
~~~

Khi gọi URI bằng template API như uri("/items/{itemId}", itemId), framework thường có cơ hội giữ template. Nếu tự nối chuỗi "/items/" + itemId, instrumentation có thể chỉ thấy raw path và tạo cardinality cao.

Đối với query parameters, không đưa giá trị nhạy cảm hoặc thay đổi liên tục vào tag. Access token, email và search terms không bao giờ nên trở thành metric dimensions.

### client.name và destination

Host đích cũng cần được kiểm soát. Nếu client gọi URL được xây dựng từ input bên ngoài, tag client.name có thể biến thành hàng nghìn hostname khác nhau. Chuẩn hóa destination thành service name hoặc nhóm host được kiểm soát, tránh ghi raw user-provided host.

## 9. Low-cardinality và high-cardinality values

Micrometer Observation phân biệt low-cardinality và high-cardinality key-values. Low-cardinality values có thể trở thành metric tags; high-cardinality values phù hợp hơn cho tracing/logs khi cần và được cho phép.

| Giá trị | Low-cardinality metric tag? | Ghi chú |
| --- | --- | --- |
| method=GET | Có | Tập giá trị nhỏ. |
| status=503 | Có | Status code hữu hạn. |
| client.name=inventory-service | Có nếu destination ổn định | Service name có tập giá trị kiểm soát. |
| uri=/items/{itemId} | Có | Template ổn định. |
| itemId=1001 | Không | Giá trị thay đổi theo request. |
| full URL có query | Không | Có thể chứa PII/secrets và cardinality cao. |
| request ID | Không | Dùng log/trace correlation theo policy. |

Không đưa high-cardinality values vào metric tags để debug. Điều đó có thể tạo quá nhiều time series và tăng memory/index cost. Nếu cần điều tra một request cụ thể, dùng trace ID hoặc request ID được quản lý trong logs/traces.

## 10. Status, outcome, exception và timeout

HTTP client exchange có thể kết thúc theo nhiều cách:
- Response 2xx: thường là thành công.
- Response 4xx: lỗi phía client hoặc business rejection tùy semantics.
- Response 5xx: lỗi server downstream.
- Connect timeout: không thiết lập được kết nối trong thời hạn.
- Read/response timeout: chờ phản hồi quá thời gian.
- DNS/TLS/connect failure: lỗi trước khi nhận HTTP response.
- Cancellation: request bị hủy bởi caller hoặc reactive subscription.

Response 4xx/5xx không nhất thiết ném exception với mọi API. WebClient retrieve() có thể chuyển status error thành exception; API exchange khác có thể trả response cho caller tự xử lý. Metrics convention có thể ghi status nếu response có mặt, hoặc exception khi request kết thúc bằng lỗi transport.

Đừng gộp mọi 4xx vào lỗi hạ tầng. Định nghĩa outcome theo semantics ứng dụng và SLO. Một 404 khi tìm tài nguyên không tồn tại có thể là kết quả nghiệp vụ bình thường; 503 từ dependency có thể là lỗi cần alert.

Observation ghi nhận duration nhưng không tự quyết định timeout. Cấu hình connect/read/response timeout ở request factory, HTTP connector hoặc client implementation. Timeout quá dài có thể giữ thread/connection; timeout quá ngắn có thể tạo false failures.

## 11. Tracing và propagation từ client sang server

Khi Micrometer Tracing/OpenTelemetry hoặc Brave được cấu hình, HTTP client instrumentation có thể tạo client span và inject trace context vào outbound request. Service nhận request extract context và tạo server span làm child của client span.

~~~mermaid
sequenceDiagram
    participant A as order-api
    participant C as Instrumented HTTP client
    participant B as inventory-api
    participant T as Trace backend

    A->>C: Gọi GET /items/{itemId}
    Note over C: Client span bắt đầu
    C->>B: HTTP + traceparent/baggage
    Note over B: Extract context, tạo server span
    B-->>C: HTTP response
    Note over C: Client span kết thúc
    C->>T: Export client span
    B->>T: Export server span
~~~

Nếu trace ID thay đổi giữa hai service, kiểm tra client instrumentation, W3C/B3 propagation, header có bị proxy/gateway xóa hoặc ghi đè, context có bị mất trong async/reactive boundary và client có dùng builder/registry đúng không. Không gửi token, email hoặc dữ liệu cá nhân trong baggage.

## 12. Tùy chỉnh Observation convention

Có thể tùy chỉnh HTTP client Observation convention để thêm tags hoặc chuẩn hóa destination. Ưu tiên low-cardinality fields có số giá trị hữu hạn. Dùng convention/handler phù hợp với Spring Framework version; không áp convention của server cho client.

Ví dụ ý tưởng chuẩn hóa destination:

~~~java
String serviceGroup = switch (host) {
    case "inventory.internal" -> "inventory-service";
    case "pricing.internal" -> "pricing-service";
    default -> "external";
};
~~~

Không dùng raw host do user cung cấp làm metric tag. Với custom convention, giữ tags mặc định như method, uri, status/outcome nếu dashboard dựa vào chúng. Test request thành công, HTTP error và transport exception.

## 13. Kiểm tra qua Actuator

Nếu Actuator và metrics endpoint được expose trong môi trường kiểm soát, truy vấn:

~~~http
GET /actuator/metrics/http.client.requests
~~~

Ví dụ payload minh họa:

~~~json
{
  "name": "http.client.requests",
  "measurements": [
    { "statistic": "COUNT", "value": 12.0 },
    { "statistic": "TOTAL_TIME", "value": 1.48 }
  ],
  "availableTags": [
    { "tag": "method", "values": ["GET", "POST"] },
    { "tag": "uri", "values": ["/items/{itemId}"] },
    { "tag": "client.name", "values": ["inventory-service"] },
    { "tag": "status", "values": ["200", "503"] }
  ]
}
~~~

Payload thực tế thay đổi theo client/version. Có thể lọc meter theo tag đã có:

~~~http
GET /actuator/metrics/http.client.requests?tag=client.name:inventory-service
~~~

Không expose endpoint metrics công khai chỉ để debug. Bảo vệ Actuator bằng authentication/network policy và chỉ expose endpoints cần thiết.

Tên Prometheus series có thể là http_client_requests_seconds_count, _sum, _bucket tùy registry/version. Ví dụ query rate theo client:

~~~promql
sum by (client_name, uri, method) (
  rate(http_client_requests_seconds_count[5m])
)
~~~

Tên metric/label có thể được chuẩn hóa theo exporter. Inspect labels thực tế trước khi tạo dashboard.

## 14. Kiểm thử HTTP client Observation

Một integration test nên dùng HTTP server giả hoặc mock server để kiểm soát response, delay và exception.

~~~java
@SpringBootTest
class InventoryClientObservationTest {

    @Autowired
    InventoryClient inventoryClient;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsHttpClientRequest() {
        inventoryClient.findItem("1001");

        Timer timer = meterRegistry.find("http.client.requests")
                .tag("method", "GET")
                .tag("uri", "/items/{itemId}")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Đoạn test cần cấu hình mock server gắn đúng RestTemplate được inject; đây là skeleton minh họa, không tự chạy với mọi client setup. Với RestClient/WebClient, dùng MockRestServiceServer/WebTestClient hoặc mock HTTP server phù hợp.

Các ca kiểm thử nên có:
- Response 200: timer count và status/outcome đúng.
- Response 404/503: status/outcome phản ánh response theo convention.
- Connect/read timeout: Observation dừng và exception tag phù hợp.
- DNS/TLS failure: không tạo timer treo; exception được ghi nhận.
- URI template có ID khác nhau: tag uri vẫn giữ template.
- Retry: xác định mỗi attempt tạo observation/span hay có parent operation bao ngoài.
- Async/reactive: context và span được giữ đúng.
- Không có tracing: metrics vẫn hoạt động nếu metrics handler được cấu hình.
- Không có metrics registry: tracing vẫn có thể hoạt động nếu tracing handler/exporter được cấu hình.

## 15. Retry, redirect và fan-out

Một business operation có thể tạo nhiều HTTP exchanges do retry hoặc gọi song song nhiều dependency:
- Một business Observation có thể bao quanh nhiều client observations.
- Mỗi retry attempt có thể tạo client span/metric record riêng tùy vị trí instrumentation.
- Redirect có thể được xử lý bên trong HTTP client hoặc tạo exchange khác tùy implementation.
- Fan-out tới nhiều service tạo nhiều client observations, không phải một timer duy nhất.

Không nhầm số lượng http.client.requests với số business requests. Khi điều tra retry storm, so sánh số client exchanges với inbound server request count và theo dõi retry metrics riêng.

## 16. Bảo mật và privacy cho HTTP client telemetry

Outbound URL/headers có thể chứa thông tin nhạy cảm. Không đưa vào metric tags hoặc trace attributes:
- Authorization, cookies, API keys.
- Query parameters chứa token, email hoặc dữ liệu cá nhân.
- Raw path variables như user ID/account ID nếu policy không cho phép.
- Request/response body.
- Exception message chứa credential hoặc payload.

Dùng URI template và destination group đã chuẩn hóa. Logs có thể chứa correlation ID hoặc safe error category nhưng phải tuân theo masking policy. Không log toàn bộ outbound request headers để debug.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không có http.client.requests | Client không được instrument, thiếu ObservationRegistry hoặc metrics handler/registry. | Kiểm tra builder/bean, dependencies và ObservationRegistry. |
| RestTemplate có meter, RestClient không | Dùng builder độc lập hoặc version chưa auto-configure RestClient. | Dùng Boot-injected builder và kiểm tra version. |
| WebClient không có client span | Observation/tracing registry không gắn hoặc reactive context propagation bị mất. | Kiểm tra WebClient.Builder và tracing integration. |
| uri tag chứa ID thực tế | URI được nối chuỗi thay vì dùng template hoặc convention không nhận pattern. | Dùng URI template API và kiểm tra tag values. |
| client.name thay đổi liên tục | Host động hoặc user-controlled. | Chuẩn hóa destination thành service group hữu hạn. |
| 503 không hiện là error | Convention/outcome semantics hoặc client API xử lý response như giá trị bình thường. | Kiểm tra status/outcome và SLO policy. |
| Timeout không có status | Không nhận HTTP response; exchange kết thúc bằng exception. | Kiểm tra exception tag và timeout configuration. |
| Client/server trace IDs khác nhau | Propagation bị tắt, header bị xóa hoặc context bị mất. | Kiểm tra W3C/B3, interceptors và proxy. |
| Metric count lớn hơn inbound request count | Retry, fan-out hoặc nhiều dependency calls trên một request. | Phân tích spans/exchange per business request. |
| Duplicate client spans | Instrumentation thủ công trùng với auto instrumentation/agent. | Kiểm tra instrumentation layers và exporter. |

## 18. Runbook: HTTP client call không được quan sát

1. Xác định client implementation: RestTemplate, RestClient, WebClient hay thư viện khác.
2. Kiểm tra cách tạo client: builder được inject từ Spring hay builder/client tự tạo.
3. Kiểm tra ObservationRegistry: xác nhận registry được gắn vào client.
4. Kiểm tra handlers: metrics registry và tracing handler có hoạt động riêng không.
5. Tạo request thử: gọi endpoint local/mock với response 200 và 503.
6. Kiểm tra Actuator: tìm http.client.requests và tags method/uri/client.name/status.
7. Kiểm tra trace: xem client span, trace ID, parent span và propagation headers.
8. Kiểm tra cardinality: gửi nhiều path IDs và xác nhận uri tag vẫn là template.
9. Kiểm tra lỗi: thử timeout/connect failure và xác minh observation kết thúc.
10. Kiểm tra duplicate: so sánh auto instrumentation, OTel agent và custom interceptors.
11. Kiểm tra privacy: bảo đảm URL/header/body không đưa secrets/PII vào telemetry.
12. Ghi lại version: Spring Boot, Spring Framework, Micrometer và HTTP client library.

## 19. Bài tập tự kiểm tra

### Bài 1 — Observation name

Một service dùng WebClient gọi inventory service. Meter HTTP client mặc định cần tìm là gì?

**Đáp án:** http.client.requests. Đây là Observation/Meter name thường dùng cho HTTP client exchange được instrument bởi Spring Framework/Micrometer.

### Bài 2 — URI template

Hai request gọi /items/1001 và /items/1002 bằng cùng endpoint. Metric tag uri nên có giá trị nào?

**Đáp án:** /items/{itemId} nếu client instrumentation nhận được template. Dùng raw path có thể tạo cardinality theo từng ID.

### Bài 3 — Không có metrics nhưng có traces

Trace backend có client spans nhưng Actuator không có http.client.requests. Có thể kết luận client instrumentation không hoạt động không?

**Đáp án:** Không. Tracing và metrics là handlers/pipelines riêng. Kiểm tra MeterRegistry, metrics observation handler và meter filters; client span có thể vẫn được tạo.

### Bài 4 — 503 response

Downstream trả 503 nhưng client API trả response để caller tự xử lý, không ném exception. Observation có thể ghi nhận điều gì?

**Đáp án:** Có thể ghi status 503 và outcome tương ứng nếu instrumentation nhận được response. Không cần exception mới có status error; kiểm tra convention/version.

### Bài 5 — Retry storm

Một inbound request tạo 4 outbound attempts tới cùng dependency. Vì sao client metric count có thể tăng 4?

**Đáp án:** Mỗi HTTP exchange/attempt có thể được instrument riêng. Business request count vẫn là một; cần xem retry policy và phân tích attempts per operation.

### Bài 6 — Client span không nối server span

Client span có trace ID khác server span. Cần kiểm tra những gì?

**Đáp án:** Client instrumentation, W3C/B3 propagation, outbound headers, proxy/gateway behavior và async context propagation; không chỉ tăng sampling ratio.

## 20. Checklist triển khai

- [ ] HTTP client được tạo bằng builder/client có Observation support.
- [ ] ObservationRegistry được gắn và handlers cần thiết đã hoạt động.
- [ ] Meter http.client.requests xuất hiện trong registry khi có outbound request.
- [ ] Tags method, uri, client.name, status/outcome được xác minh theo version.
- [ ] URI template được dùng thay raw path có identifiers.
- [ ] Host/destination được chuẩn hóa; không dùng URL do caller kiểm soát làm metric tag.
- [ ] Connect/read/response timeout được cấu hình ở HTTP client.
- [ ] HTTP response errors và transport exceptions được phân biệt.
- [ ] Retry/fan-out được tính đến khi phân tích request count.
- [ ] Client spans nối với server spans qua trace context propagation.
- [ ] Async/reactive context được kiểm thử.
- [ ] Không có secrets, credentials, query PII hoặc raw payload trong tags/logs/spans.
- [ ] Actuator metrics endpoint được bảo vệ.
- [ ] Integration tests kiểm tra success, HTTP error, timeout, URI template và context.
- [ ] Không có duplicate instrumentation từ custom code, starter và agent.
- [ ] Dashboard theo dõi latency, error outcome và volume theo dependency.

**Ghi nhớ:** http.client.requests cho biết các HTTP exchanges outbound đang mất bao lâu và kết thúc ra sao. Hãy dùng builder có Observation support, kiểm tra tags và URI templates, cấu hình timeout/retry hợp lý, rồi xác minh client spans nối đúng trace context. Metrics cho xu hướng tổng thể; logs và traces cung cấp chi tiết để tìm nguyên nhân dependency chậm hoặc lỗi mà vẫn kiểm soát cardinality và dữ liệu nhạy cảm.
