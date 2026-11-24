# RestTemplate observation

Một ứng dụng Spring Boot gọi dịch vụ Inventory bằng RestTemplate để kiểm tra tồn kho. Khi Inventory phản hồi chậm hoặc trả 503, chỉ nhìn log của Order Service thường không đủ để biết request outbound nào gặp vấn đề, mất bao lâu, gọi host nào và lỗi có lan truyền từ dependency hay không. HTTP client Observation ghi nhận mỗi lần gọi HTTP outbound như một operation có thời gian, kết quả và context; metrics cho biết xu hướng, còn trace cho thấy dependency call nằm ở đâu trong request tổng thể.

Bài **RestTemplate observation** thuộc chương **HTTP client observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Điểm cốt lõi:** RestTemplate chỉ được instrument khi nó được cấu hình với ObservationRegistry phù hợp. Trong Spring Boot, hãy ưu tiên dùng RestTemplateBuilder do Boot cung cấp để nhận cấu hình observability và customizers. Tạo new RestTemplate() độc lập có thể bỏ qua builder/customization đó. Client Observation mô tả lần gọi outbound; server Observation ở dịch vụ đích mô tả request inbound. Trace context nối hai phía khi propagation được cấu hình đúng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích RestTemplate observation và vị trí của nó trong HTTP client observability.
2. Phân biệt outbound client Observation với inbound server Observation.
3. Cấu hình RestTemplate qua RestTemplateBuilder để nhận ObservationRegistry.
4. Hiểu low-cardinality keys như clientName, method, uri, status, outcome và error.
5. Phân biệt URI template với URL đầy đủ và kiểm soát metric cardinality.
6. Hiểu cách Observation tạo Micrometer metrics và tracing spans qua handlers.
7. Theo dõi HTTP client errors, status code, timeouts và exception.
8. Hiểu context propagation từ server request qua RestTemplate tới downstream service.
9. Tùy chỉnh ClientRequestObservationConvention an toàn.
10. Kiểm thử metrics/traces và điều tra khi outbound call không xuất hiện.

## 2. RestTemplate observation là gì?

RestTemplate là synchronous HTTP client của Spring Framework. Nó gửi request và chờ response, thường thông qua ClientHttpRequestFactory. Spring Framework tích hợp Micrometer Observation vào RestTemplate để ghi nhận một observation cho mỗi HTTP exchange khi ObservationRegistry được cấu hình.

Observation tiêu chuẩn thường có tên http.client.requests. Observation có thể được xử lý bởi:
- DefaultMeterObservationHandler để tạo Micrometer Timer/metrics.
- Micrometer Tracing handler để tạo client span.
- Các handler khác nếu ứng dụng đăng ký.

Một observation ghi nhận vòng đời client exchange: bắt đầu trước khi gửi request, kết thúc khi response được nhận hoặc lỗi xảy ra. Convention đọc context để tạo key-values, nhưng bản thân Observation không phải exporter.

~~~mermaid
sequenceDiagram
    participant API as OrderController
    participant RT as RestTemplate
    participant INV as Inventory Service
    participant H as Observation handlers
    API->>RT: getForEntity(...)
    RT->>H: Start http.client.requests
    RT->>INV: HTTP request + trace context
    INV-->>RT: HTTP response
    RT->>H: Stop observation with status/timing
    RT-->>API: ResponseEntity
~~~

Client Observation và server Observation là hai operation khác nhau:
- Client: Order Service gọi Inventory mất bao lâu và nhận kết quả gì?
- Server: Inventory nhận request nào, xử lý mất bao lâu và trả status gì?

Khi trace propagation hoạt động, client span thường là parent của server span qua network boundary.

## 3. Cấu hình RestTemplate trong Spring Boot

Trong Spring Boot, inject RestTemplateBuilder thay vì tự tạo RestTemplate rời rạc:

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://inventory.internal")
                .build();
    }
}
~~~

Spring Boot có thể customizer RestTemplateBuilder với các thành phần như ObservationRegistry, message converters, request factory và customizers đã cấu hình. Chi tiết auto-configuration phụ thuộc dependency và phiên bản Spring Boot.

Sử dụng bean được inject:

~~~java
@Service
class InventoryClient {

    private final RestTemplate restTemplate;

    InventoryClient(RestTemplate inventoryRestTemplate) {
        this.restTemplate = inventoryRestTemplate;
    }

    InventoryView find(String sku) {
        return restTemplate.getForObject(
                "/api/inventory/{sku}",
                InventoryView.class,
                sku);
    }
}
~~~

Không tạo RestTemplate mới trong mỗi method hoặc gọi new RestTemplate() rồi giả định nó nhận customizers từ Spring Boot. Instance tạo trực tiếp bên ngoài builder có thể không có ObservationRegistry, interceptors, error handler hoặc timeout configuration của ứng dụng.

### 3.1 Khi nào cần tự gắn ObservationRegistry?

Nếu không dùng Spring Boot builder, Spring Framework cho phép cấu hình ObservationRegistry trực tiếp trên RestTemplate bằng API tương ứng phiên bản, ví dụ:

~~~java
RestTemplate restTemplate = new RestTemplate();
restTemplate.setObservationRegistry(observationRegistry);
~~~

Cần xác nhận method/API có trong Spring Framework version đang dùng. Trong ứng dụng Spring Boot, dùng builder và customizer thường giúp giữ cấu hình nhất quán hơn.

### 3.2 Điều kiện để có metrics và traces

| Thành phần | Vai trò |
|---|---|
| RestTemplate | Tạo HTTP client Observation |
| ObservationRegistry | Điều phối Observation và handlers |
| MeterObservationHandler | Chuyển Observation thành Micrometer meter |
| TracingObservationHandler | Tạo span cho Observation |
| MeterRegistry | Lưu/export Micrometer metrics |
| Tracer/exporter | Gửi spans tới backend qua tracing pipeline |

Có thể thấy metric nhưng không thấy span nếu MeterObservationHandler có nhưng tracing handler/exporter chưa được cấu hình. Ngược lại, trace có thể xuất hiện trong khi registry metrics chưa export.

## 4. Client Observation context và convention

Spring Framework dùng context chuyên biệt cho HTTP client Observation, thường là ClientRequestObservationContext. Context chứa request/response, request URI/template, exception và dữ liệu cần thiết để convention tạo KeyValues.

Convention mặc định thường cung cấp các low-cardinality keys:

| Key | Ý nghĩa | Ví dụ |
|---|---|---|
| clientName | Host/service đích đã chuẩn hóa | inventory.internal |
| method | HTTP method | GET, POST |
| uri | URI template hoặc fallback | /api/inventory/{sku} |
| status | HTTP response status | 200, 404, 503 |
| outcome | Nhóm kết quả theo status | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| error | Exception type hoặc none | ResourceAccessException, none |

Tên key và tập giá trị chính xác phụ thuộc Spring Framework/Micrometer convention version. Một số convention có thêm high-cardinality values như URL đầy đủ để dùng trong trace; high-cardinality values không nên được chuyển thành metric tags.

### 4.1 Low-cardinality và high-cardinality

Low-cardinality values được dùng làm dimensions cho metrics. Giá trị phải có tập hữu hạn và ổn định, ví dụ method, status family, route template hoặc client name đã chuẩn hóa.

High-cardinality values có thể khác nhau mỗi request, ví dụ full URL với query, request ID, user ID hoặc token. Chúng có thể hữu ích cho trace/log cụ thể nhưng không phù hợp làm metric labels.

~~~text
Low cardinality:
  clientName = inventory.internal
  method = GET
  uri = /api/inventory/{sku}
  status = 200
  outcome = SUCCESS

High cardinality:
  http.url = https://inventory.internal/api/inventory/SKU-9281?debug=true
  request.id = req-8a1...
~~~

Không dùng raw URL có query parameters nhạy cảm; không thêm token hoặc user input vào convention values.

## 5. Vì sao URI template rất quan trọng?

RestTemplate hỗ trợ URI templates:

~~~java
restTemplate.getForEntity(
        "https://inventory.internal/api/items/{sku}",
        InventoryView.class,
        sku);
~~~

URI template giữ đường dẫn ở dạng /api/items/{sku} để instrumentation có thể nhóm request cùng route. Nếu code truyền URI đã được dựng hoàn chỉnh:

~~~java
URI uri = URI.create(
        "https://inventory.internal/api/items/" + sku);
restTemplate.getForEntity(uri, InventoryView.class);
~~~

instrumentation có thể không còn biết template ban đầu. Tùy request factory và convention, uri low-cardinality có thể thành UNKNOWN hoặc fallback khác; URL đầy đủ nếu được ghi ở high-cardinality field vẫn có nguy cơ chứa ID/query. Hãy dùng overload có URI template và variables khi có thể.

### 5.1 Cardinality bùng nổ ảnh hưởng thế nào?

Giả sử mỗi phút có 100.000 SKU khác nhau. Nếu metric tag uri chứa /items/SKU-9281, hệ thống có thể tạo gần 100.000 series thay vì một series /items/{sku}. Điều này làm tăng:
- RAM trong application registry và backend index.
- Số time series cần scrape/ingest.
- Storage và chi phí retention.
- Thời gian query và dashboard rendering.

URI template là một phần của thiết kế chi phí metrics.

## 6. Status, outcome và error của HTTP client

Client Observation ghi response status khi nhận được response. Outcome nhóm status code. Error phản ánh exception được Observation ghi nhận.

| Tình huống | Status | Outcome thường gặp | Error có thể ghi |
|---|---:|---|---|
| Inventory trả OK | 200 | SUCCESS | none |
| Inventory trả Not Found | 404 | CLIENT_ERROR | none hoặc exception tùy error handler |
| Inventory trả Too Many Requests | 429 | CLIENT_ERROR | phụ thuộc error handling |
| Inventory trả Service Unavailable | 503 | SERVER_ERROR | phụ thuộc error handling |
| DNS/connect timeout trước response | UNKNOWN | UNKNOWN/fallback theo convention | ResourceAccessException hoặc exception cụ thể |
| TLS handshake thất bại | Không có HTTP status | UNKNOWN/fallback | SSL exception |

RestTemplate mặc định dùng DefaultResponseErrorHandler, thường ném exception cho 4xx/5xx sau khi nhận response. Vì thế status có thể là 404/503 trong Observation dù method call cuối cùng ném HttpClientErrorException/HttpServerErrorException.

Nếu ứng dụng thay ResponseErrorHandler để coi 404 là kết quả bình thường, Observation có thể ghi status 404 và không có exception error. Status và error không phải hai cách viết của cùng một giá trị.

### 6.1 Không có response status khi lỗi kết nối

Nếu DNS lookup, TCP connect hoặc TLS handshake thất bại trước khi nhận HTTP response, không có status code từ server. Instrumentation có thể dùng fallback như UNKNOWN và ghi exception type. Đừng tạo status giả 500 cho outbound request nếu server chưa hề trả 500; phân biệt transport failure với HTTP response 5xx.

### 6.2 Retry tạo nhiều client observations

Nếu application hoặc retry library gửi lại request, mỗi attempt có thể tạo một client Observation/span riêng, tùy integration. Một logical operation có thể gồm nhiều outbound attempts. Hãy xác định metric muốn đo:
- Mỗi attempt để thấy dependency load/retry volume.
- Logical call cuối cùng để đo trải nghiệm caller.
- Cả hai, nhưng dùng tên và dimensions phân biệt.

Không cộng retry attempts vào business request count mà không hiểu semantics.

## 7. Trace context propagation qua RestTemplate

Khi server request đang có Observation/tracing context hiện hành và RestTemplate được instrument đúng, tracing integration có thể inject trace context vào outbound HTTP request. Downstream server extract context và tạo server span con.

~~~mermaid
sequenceDiagram
    participant C as External client
    participant O as Order Service
    participant R as RestTemplate
    participant I as Inventory Service
    C->>O: POST /orders
    Note over O: Server span (trace T)
    O->>R: get inventory
    Note over R: Client span (child)
    R->>I: GET /items/SKU-1 + traceparent
    Note over I: Server span (child of client)
    I-->>R: 200 OK
    R-->>O: InventoryView
    O-->>C: 201 Created
~~~

Khi dùng W3C Trace Context, outbound request có thể mang traceparent và baggage nếu propagation được cấu hình. Client span nối thời gian chờ network/dependency vào trace tổng.

Lưu ý:
- Có client Observation không có nghĩa luôn có trace span; cần tracing handler.
- Có span không đảm bảo downstream nhận parent nếu proxy/client strips headers hoặc propagation formats khác nhau.
- Nếu gọi RestTemplate từ background task không có context, trace có thể bắt đầu độc lập hoặc không có parent.
- Không copy access token, session cookie hoặc PII vào baggage; propagation context không phải nơi lưu secrets.

## 8. Timeout và lỗi dependency

HTTP client cần timeout có giới hạn. Nếu không, request thread có thể chờ quá lâu, làm cạn pool và tăng latency lan truyền. Timeout là một phần hành vi cần quan sát.

Cấu hình request factory/timeout phụ thuộc Spring Boot và client implementation (JDK HttpClient, Apache HttpComponents, Jetty...). Ví dụ định hướng dùng builder customizer:

~~~java
@Bean
RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://inventory.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(5))
            .build();
}
~~~

Property/API timeout đã thay đổi giữa các phiên bản Spring Boot; kiểm tra builder methods và request factory tương ứng. Đặt connect timeout cho việc thiết lập kết nối và read/response timeout cho việc chờ dữ liệu; không giả định một timeout bao phủ mọi pha request.

Trong trace:
- Span duration dài có thể phản ánh server xử lý chậm hoặc client chờ network.
- Timeout exception có thể không có HTTP status.
- Downstream server có thể vẫn xử lý request sau khi caller timeout, tùy transport/cancellation.
- Retry có thể tạo thêm attempts và tăng tải dependency.

## 9. Custom ClientRequestObservationConvention

Có thể tùy chỉnh low-cardinality key-values cho client Observation, ví dụ phân nhóm client theo dependency role. Dùng convention để chuẩn hóa dữ liệu; không ghi raw URL, token hoặc dynamic request data vào metric tags.

Ví dụ khai báo convention mặc định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.observation.ClientRequestObservationConvention;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;

@Configuration
class ClientObservationConfiguration {

    @Bean
    ClientRequestObservationConvention clientObservationConvention() {
        return new DefaultClientRequestObservationConvention();
    }
}
~~~

Đây là cấu hình convention mặc định minh họa. Khi custom thật, có thể kế thừa DefaultClientRequestObservationConvention hoặc implement interface và trả về KeyValues hữu hạn. Xác nhận package/class API theo Spring Framework version.

### 9.1 Thêm dependency role

Nếu cần phân biệt downstream:
- inventory
- payment
- customer
- shipping

Dùng logical client name đã chuẩn hóa hoặc custom key dependency.role. Không lấy host header từ request người dùng hoặc URL tùy ý rồi gắn thành metric tag, vì attacker có thể tạo nhiều host values và làm cardinality tăng.

### 9.2 Giữ key chuẩn để tương thích dashboard

Nếu custom convention loại bỏ method/status/outcome/uri hoặc đổi ý nghĩa key, dashboard, alert và service-level metrics có thể bị ảnh hưởng. Khi thay convention:
1. Giữ key chuẩn nếu không có lý do rõ ràng.
2. Thêm key nghiệp vụ riêng với tập giá trị nhỏ.
3. Version hóa dashboard/query migration nếu key semantics thay đổi.
4. Kiểm tra metrics và tracing handlers vì cùng convention có thể cung cấp low/high cardinality KeyValues cho nhiều signal.

## 10. RestTemplate interceptors và Observation

RestTemplate có ClientHttpRequestInterceptor, thường dùng cho authentication, correlation headers, logging hoặc request decoration. Interceptor không tự động thay thế Observation instrumentation.

Một interceptor có thể thêm header correlation/auth từ security context, log metadata, thay đổi URI/header trước khi gửi hoặc wrap response. Hãy bảo đảm interceptor không:
- Ghi toàn bộ headers/body vào logs.
- Ghi Authorization/Cookie/API key vào span attributes.
- Xóa traceparent/baggage do tracing integration inject.
- Đọc body theo cách làm response stream không còn cho converter.
- Tạo thêm Timer/span trùng với Observation chuẩn mà không có chủ đích.

Nếu interceptor cần thêm telemetry, dùng Observation context/current Observation phù hợp thay vì tự dựng HTTP client metric khác cho cùng exchange.

## 11. Quan sát status và latency trong metrics

HTTP client Timer có thể được nhóm theo clientName, method, uri, status, outcome và error. Tên meter mặc định thường là http.client.requests; OTel semantic conventions có thể dùng http.client.request.duration tùy convention.

Ví dụ query conceptual:

~~~text
http.client.requests{
  clientName="inventory.internal",
  method="GET",
  uri="/api/items/{sku}",
  outcome="SUCCESS"
}
~~~

Dùng metrics để trả lời:
- Dependency nào có p95 latency cao?
- Tỷ lệ 5xx/timeout theo client là bao nhiêu?
- Route nào đang gọi dependency quá thường xuyên?
- Retry làm request volume tăng bao nhiêu?
- Dependency cụ thể có latency tăng sau deployment nào?

Không dùng full URL làm label. Dùng clientName và uri template để giữ dimensions hữu hạn.

## 12. Logs và traces liên kết với client Observation

Logs có thể bao gồm traceId/spanId để liên kết với client span. Khi outbound call lỗi, log message ngắn có dependency, operation và exception category:

~~~java
try {
    inventoryClient.find(sku);
} catch (ResourceAccessException ex) {
    log.warn("Inventory request failed dependency={} category={}",
            "inventory",
            "transport_error");
    throw ex;
}
~~~

Không log exception message nếu có thể chứa URL/query token, credentials hoặc remote response body. Nếu logging framework tự ghi stack trace, kiểm tra exception messages được phép xuất.

Trong trace backend, mở client span để xem:
- Parent server span của request ban đầu.
- Client operation name và peer/service.
- Method/URI/status theo convention.
- Duration và exception event nếu có.
- Downstream server span nếu trace context được propagate.

Một log đơn lẻ cho biết code path; client span cho biết dependency call nằm ở đâu trong trace và mất bao lâu.

## 13. Kiểm thử RestTemplate observation

Nên kiểm thử cả response và telemetry. Có thể dùng MockRestServiceServer để giả lập downstream HTTP mà không cần network thật.

Ví dụ khung test:

~~~java
@SpringBootTest
class InventoryClientObservationTest {

    @Autowired
    RestTemplate inventoryRestTemplate;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsClientRequest() {
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(inventoryRestTemplate).build();

        server.expect(requestTo(
                    "https://inventory.internal/api/items/SKU-1"))
                .andRespond(withSuccess(
                    "{\"sku\":\"SKU-1\",\"available\":true}",
                    MediaType.APPLICATION_JSON));

        inventoryRestTemplate.getForObject(
                "/api/items/{sku}",
                InventoryView.class,
                "SKU-1");

        server.verify();

        Timer timer = meterRegistry.find("http.client.requests")
                .tag("method", "GET")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

Đây là test skeleton; imports, JSON fixtures, URI, metric name và tag keys cần khớp version/convention. Một số test server mock cần bind đúng request factory hoặc dùng test ObservationRegistry để assert ObservationContext trực tiếp.

### 13.1 Kiểm thử error cases

Viết test riêng cho HTTP 404 với default error handler, HTTP 503 và HttpServerErrorException, custom ResponseErrorHandler coi 404 là response bình thường, connect/read timeout, URI template với nhiều SKU nhưng metric vẫn dùng một template, và trace propagation header được inject khi có current trace context.

### 13.2 Kiểm tra trace end-to-end

1. Gửi inbound request vào Order Service.
2. Order gọi Inventory qua RestTemplate.
3. Xác nhận client span là child của Order server span.
4. Xác nhận Inventory server span dùng cùng Trace ID và parent span ID là client span.
5. Thử bỏ propagation header để nhận diện triệu chứng trace bị tách.

Không chỉ assert có một span bất kỳ; cần kiểm tra quan hệ parent/child và Trace ID.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có http.client.requests | RestTemplate không có ObservationRegistry hoặc không dùng builder được cấu hình | Inject RestTemplateBuilder hoặc set registry trực tiếp |
| Có metric nhưng không có client span | Tracing handler/bridge/exporter chưa cấu hình | Kiểm tra Micrometer Tracing và tracing pipeline |
| Có trace nhưng không có metrics | MeterObservationHandler/registry/export chưa hoạt động | Kiểm tra Actuator, MeterRegistry và registry exporter |
| Mỗi SKU tạo một metric series | Dùng URI đầy đủ thay URI template | Dùng overload template + URI variables |
| uri=UNKNOWN | Instrumentation không nhận template/handler route | Kiểm tra URI overload và convention |
| status=UNKNOWN | Lỗi trước khi nhận HTTP response | Kiểm tra DNS, connect, TLS, timeout |
| 404 tạo exception | DefaultResponseErrorHandler coi 4xx là error | Xử lý exception hoặc cấu hình ResponseErrorHandler theo contract |
| 503 có status và error | Server response 5xx và client error handler ném exception | Dùng status/outcome/error để phân tích |
| Client span không nối downstream | Trace context không được inject/propagate hoặc bị strip | Kiểm tra ObservationRegistry, propagation và proxy |
| Interceptor làm mất traceparent | Interceptor thay/xóa headers | Giữ propagation headers và test outbound request |
| Request chậm nhưng server span không có | Network/DNS/TLS hoặc downstream không instrumented | Xem client span duration và transport logs |
| Retry làm metric count tăng | Mỗi attempt được instrument | Phân biệt attempt metrics và logical operation metrics |
| Timeout không dừng downstream | Caller timeout không đảm bảo remote work cancellation | Kiểm tra transport cancellation và server behavior |
| Logs chứa token | Interceptor log headers hoặc exception URL | Allowlist metadata và redact ở source |

## 15. Playbook: điều tra Inventory Service chậm

**Tình huống:** Order Service latency tăng nhưng HTTP server metrics của Order chưa giải thích được nguyên nhân.

1. Lọc traces theo service.name của Order Service và route đang chậm.
2. Mở server span của request và tìm client span tới Inventory.
3. So sánh client span duration với tổng server span duration.
4. Kiểm tra method, URI template, status, outcome và error.
5. Nếu status 503, mở downstream server span/log để tìm lỗi service.
6. Nếu status UNKNOWN và error là transport exception, kiểm tra DNS, connection pool, TLS và timeout.
7. Nếu client span có nhiều attempts, xác định retry policy và tổng thời gian chờ.
8. So sánh metrics p95/error rate theo clientName/uri template để xác định xu hướng hay request đơn lẻ.
9. Sau khi sửa, xác minh trace context nối Order client span với Inventory server span.

Không kết luận Inventory chậm chỉ từ latency tổng của Order; phần chậm có thể nằm ở connection setup, retry, serialization hoặc network.

## 16. Bài tập tự kiểm tra

**Bài 1 — Builder.** Vì sao nên inject RestTemplateBuilder trong Spring Boot thay vì tạo new RestTemplate() trực tiếp? Thành phần nào có thể bị bỏ qua?

**Bài 2 — Client và server.** Phân biệt client Observation của Order Service và server Observation của Inventory Service. Chúng liên hệ thế nào trong distributed trace?

**Bài 3 — URI template.** Một service gọi 10.000 SKU khác nhau. Vì sao truyền URI template /items/{sku} tốt hơn nối chuỗi URI đầy đủ cho metrics?

**Bài 4 — Status và error.** RestTemplate nhận HTTP 503 rồi ném HttpServerErrorException. Observation có thể ghi status và error ra sao? Vì sao chúng không mâu thuẫn?

**Bài 5 — Transport failure.** DNS lookup thất bại trước khi có response. Có HTTP status nào không? Metrics/traces nên biểu đạt gì?

**Bài 6 — Tracing.** Client span xuất hiện nhưng Inventory server span không nối cùng Trace ID. Hãy nêu các điểm cần kiểm tra.

**Bài 7 — Retry.** Một logical call thử ba lần mới thành công. Vì sao client request metric có thể tăng ba lần? Cần metric nào để đo logical operation?

**Bài 8 — Interceptor.** Một interceptor log toàn bộ request headers để debug. Những rủi ro nào có thể xảy ra và cách sửa?

### Gợi ý trả lời

1. Builder nhận các Boot customizers như ObservationRegistry, request factory và cấu hình khác; instance tự tạo có thể không được instrument.
2. Client Observation đo outbound exchange; server Observation đo inbound request. Client span thường là parent của server span khi context được inject/extract.
3. URI template giữ tag cardinality thấp; raw URI tạo series theo từng SKU.
4. Status 503 mô tả response; error có thể là HttpServerErrorException do default handler ném. Hai field mô tả hai khía cạnh khác nhau.
5. Không có HTTP response status. Ghi transport exception và fallback status/outcome phù hợp như UNKNOWN theo convention.
6. Kiểm tra ObservationRegistry/tracing handler, propagation format, traceparent header, proxy/interceptor và server extraction.
7. Mỗi attempt là một HTTP exchange riêng. Thêm business timer/counter quanh logical call nếu cần đo số lần gọi và thời gian cuối cùng.
8. Header có thể chứa Authorization/Cookie/API key. Allowlist headers an toàn hoặc log method/route/status đã chuẩn hóa.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — RestTemplate](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate API, request factories, interceptors và client configuration.
- [Spring Framework — HTTP Client Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): client observations, ClientRequestObservationContext và convention keys.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestTemplateBuilder và auto-configured client builders.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP client metrics, tags và customization.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers, conventions và context.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridge, span lifecycle và propagation.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP client attributes, status và error semantics.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): propagation qua process/network boundaries.
- [Spring Framework — RestTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestTemplate.html): API và ObservationRegistry configuration.

**Ghi nhớ:** RestTemplate observation ghi nhận từng HTTP outbound exchange. Dùng RestTemplateBuilder để nhận ObservationRegistry và Boot customizers; dùng URI template để giữ metric cardinality thấp; đọc status, outcome và error như các trường riêng. Observation handlers quyết định metrics/traces nào được tạo, còn tracing propagation nối client span với server span downstream. Khi dependency chậm hoặc lỗi, mở client span để tách thời gian network/timeout/retry khỏi xử lý nghiệp vụ và xác minh toàn bộ trace context.

