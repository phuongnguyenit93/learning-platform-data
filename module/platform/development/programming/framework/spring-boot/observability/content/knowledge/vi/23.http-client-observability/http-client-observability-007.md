# URI template trong HTTP client observability với Spring Boot

Khi một service gọi HTTP tới service khác, mỗi request có thể chứa một path khác nhau, chẳng hạn /customers/101/orders và /customers/102/orders. Nếu instrumentation ghi nguyên URI vào metric tag, mỗi customer ID có thể tạo một time series mới. Dashboard khó tổng hợp, Prometheus cardinality tăng và chi phí lưu trữ tăng theo traffic. **URI template** giải quyết vấn đề bằng cách biểu diễn endpoint theo cấu trúc ổn định, ví dụ /customers/{customerId}/orders, để telemetry nhóm các request cùng loại mà không phụ thuộc giá trị path cụ thể.

Trong module **SPRING_BOOT_OBSERVABILITY**, URI template là một phần của HTTP client observability cùng Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương **HTTP client observability**, tập trung vào **URI template**: cách template được tạo và truyền tới instrumentation, khác biệt giữa template với expanded URI, tích hợp RestClient/RestTemplate/WebClient, ảnh hưởng tới metrics/traces, custom Observation, encoding, bảo mật, kiểm thử và troubleshooting.

## Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích URI template và vì sao cần dùng nó trong HTTP client telemetry.
2. Phân biệt template URI, expanded URI và raw URL.
3. Cấu hình HTTP client Spring để instrumentation nhận được template thay vì chỉ URI đã mở rộng.
4. Hiểu cách Micrometer Observation dùng URI template trong metrics và tracing.
5. Kiểm soát cardinality của client metrics và span attributes.
6. Xử lý query parameters, encoding, path variables và URI builder.
7. Kiểm thử template tags cho RestClient, RestTemplate và WebClient.
8. Điều tra khi URI tag là UNKNOWN, raw path hoặc template bị mất.

## 1. URI template là gì?

URI template là mẫu URI có các biến đại diện cho phần thay đổi theo request:

~~~text
Template: /customers/{customerId}/orders/{orderId}
Expanded: /customers/101/orders/9001
Expanded: /customers/205/orders/9002
Expanded: /customers/310/orders/9003
~~~

Ba URI đã mở rộng đại diện ba request khác nhau nhưng cùng một loại operation. Khi HTTP client instrumentation giữ template, telemetry có thể nhóm cả ba dưới một dimension ổn định.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| URI template | /customers/{customerId}/orders/{orderId} | Mẫu logic của endpoint |
| Expanded URI | /customers/101/orders/9001 | URI cụ thể sau khi thay variables |
| Raw URI | https://api.example.test/customers/101/orders?view=full | URI thực tế gồm host/path/query |
| HTTP method | GET | Loại thao tác HTTP |
| Client name/peer | inventory-service | Đích logic hoặc dependency |

### 1.1. Vì sao không dùng expanded URI làm metric tag?

~~~text
GET /customers/101/orders
GET /customers/102/orders
GET /customers/103/orders
~~~

Nếu tag uri mang giá trị đầy đủ, mỗi customer ID trở thành một giá trị tag mới. Với hàng triệu customers, số time series có thể tăng rất nhanh. URI template gom chúng thành GET /customers/{customerId}/orders, cho phép so sánh request count, error ratio và latency theo loại endpoint.

### 1.2. URI template không tự che dữ liệu

Nếu code tạo URL bằng cách nối chuỗi, HTTP client có thể chỉ nhìn thấy URI đã mở rộng và không biết phần nào là biến. Instrumentation không thể luôn suy ra chính xác mọi ID trong path. Hãy dùng URI builder/template API hoặc cơ chế truyền template mà client hỗ trợ.

## 2. URI template trong HTTP client observability

HTTP client instrumentation thường tạo client Observation/span cho request ra ngoài và ghi nhận method, URI/template, status, outcome, peer/service và duration theo conventions của phiên bản.

~~~mermaid
flowchart TD
    App["Application service"] --> Client["HTTP client"]
    Client --> Template["URI template"]
    Template --> Expand["Expand path variables"]
    Expand --> Request["HTTP request"]
    Client -. "Observation context" .-> Convention["HTTP client convention"]
    Convention --> Metrics["Client metrics"]
    Convention --> Span["Client span"]
    Metrics --> Registry["MeterRegistry"]
    Span --> Exporter["Tracing exporter"]
    Request --> Remote["Remote service"]
~~~

Request cần giữ được thông tin template tới observation convention. Nếu chỉ còn expanded URI, convention có thể không khôi phục template chính xác.

Template mô tả operation mà code định gọi. Nó không phải Trace ID, request ID, customer/order ID, query string, Authorization token hoặc nhãn metric riêng cho từng request. Template nên ổn định và phản ánh route logic. API version như /v1/orders thường là một phần của template vì nó phân biệt API contract.

### 2.1. Client template và server route template

Client URI template mô tả endpoint mà client gọi; server route template mô tả handler mà server nhận request. Chúng thường tương tự nhưng không nhất thiết giống nhau: client có thể gọi gateway route, proxy hoặc API version khác. Không lấy server route để thay thế template phía client.

## 3. RestClient: khai báo template cùng path variables

Spring Framework cung cấp RestClient với API URI builder hỗ trợ template variables:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CustomerApiClient {
    private final RestClient restClient;

    public CustomerApiClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://customer-api.example.test")
                .build();
    }

    public String getOrders(String customerId) {
        return restClient.get()
                .uri("/customers/{customerId}/orders", customerId)
                .retrieve()
                .body(String.class);
    }
}
~~~

Code khai báo template /customers/{customerId}/orders và truyền customerId riêng. API builder mở rộng template thành request URI nhưng có thể giữ thông tin template cho các thành phần instrumentation tương thích.

Tránh nối chuỗi URL nếu cần template telemetry:

~~~java
String uri = "/customers/" + customerId + "/orders";
~~~

### 3.1. Cấu hình RestClient.Builder

Trong Spring Boot, ưu tiên builder được auto-configure và inject từ context để giữ customizers, observation registry và thiết lập chung. Tự gọi constructor tạo RestClient độc lập có thể bỏ qua customizers/observation convention đã cấu hình.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CustomerClientConfiguration {
    @Bean
    RestClient customerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://customer-api.example.test")
                .build();
    }
}
~~~

Khi Spring Boot quản lý builder, HTTP client observation có thể được tích hợp theo version và cấu hình. Kiểm tra dependency và auto-configuration thực tế; không giả định mọi RestClient tự tạo đều được instrument.

### 3.2. URI builder với nhiều biến

~~~java
restClient.get()
        .uri("/tenants/{tenantId}/customers/{customerId}",
                tenantId, customerId)
        .retrieve()
        .body(Customer.class);
~~~

Template có hai biến nhưng chỉ tạo một loại operation. Tránh đưa tenantId/customerId vào tên Observation hoặc metric tags.

## 4. RestTemplate: truyền URI template vào exchange

RestTemplate có overload hỗ trợ URI template và variables:

~~~java
import org.springframework.web.client.RestTemplate;

public Customer getCustomer(
        RestTemplate restTemplate,
        String customerId
) {
    return restTemplate.getForObject(
            "https://customer-api.example.test/customers/{customerId}",
            Customer.class,
            customerId
    );
}
~~~

Cách gọi này giữ lại mẫu URI trong API client. Nếu tự tạo URI từ chuỗi đã nối, template metadata có thể mất.

### 4.1. RestTemplate cần được cấu hình instrumentation

Dùng RestTemplate được tạo từ builder/configuration của Spring Boot để nhận customizers và observation integration tương ứng:

~~~java
@Bean
RestTemplate customerRestTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Tên builder/import và auto-configuration phụ thuộc Spring Boot version. Kiểm tra builder bean hiện hữu và cấu hình Micrometer Observation/Tracing trước khi thêm interceptor thủ công.

### 4.2. Tránh tạo client span trùng

Nếu HTTP client instrumentation đã tạo Observation/span, interceptor tự viết để tạo thêm client span cho cùng request có thể làm trace chứa hai spans tương đương và metrics đếm hai lần. Interceptor custom chỉ nên bổ sung metadata hoặc behavior thực sự chưa có, đồng thời giữ đúng lifecycle và parent context.

## 5. WebClient: URI template trong reactive HTTP client

WebClient hỗ trợ URI builder/template variables:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryWebClient {
    private final WebClient webClient;

    public InventoryWebClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://inventory-api.example.test")
                .build();
    }

    public Mono<Inventory> getInventory(String sku) {
        return webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

Khi dùng builder do Spring Boot quản lý, customizers và observation integration có thể được áp dụng. WebClient là reactive; context propagation khác với ThreadLocal thuần túy. Đừng giả định MDC hoặc thread-local context luôn hiện diện khi pipeline đổi scheduler.

### 5.1. URI builder function

Có thể dùng UriBuilder để tạo query parameters có encode:

~~~java
webClient.get()
        .uri(builder -> builder
                .path("/inventory/{sku}")
                .queryParam("include", "{include}")
                .build(sku, "availability"))
        .retrieve()
        .bodyToMono(Inventory.class);
~~~

Kiểm tra overload và cách encode variable của Spring Framework version. Không tự nối query string bằng tay vì có thể làm sai encoding và vô tình làm lộ giá trị động trong telemetry.

### 5.2. WebClient observation context

WebClient instrumentation có thể ghi nhận URI template nếu request được tạo bằng API template và observation convention nhận được thông tin đó. Nếu chỉ truyền URI hoàn chỉnh, template có thể không tồn tại. Kiểm tra observation/span tags thực tế trong test.

## 6. URI template ảnh hưởng tới metrics và traces

URI template thường hữu ích làm low-cardinality dimension cho HTTP client metrics. Với traces, URI template cũng là thuộc tính mô tả operation, trong khi expanded URL có thể không cần thiết hoặc cần được lọc.

| Dimension | Ví dụ | Lưu ý |
| --- | --- | --- |
| method | GET | Tập nhỏ |
| uri | /customers/{customerId}/orders | Dùng template |
| status | 200, 404, 503 | Giá trị hữu hạn |
| outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR | Phân loại ổn định |
| client/service | customer-api | Tên dependency logic |
| exception | IOException | Tránh exception message động |

Tên meter và tag keys phụ thuộc Spring Boot/Micrometer version và registry. Kiểm tra meter thực tế thay vì hard-code giả định.

### 6.1. Ví dụ PromQL

~~~promql
sum by (method, uri) (
  rate(http_client_requests_seconds_count[5m])
)
~~~

Tỷ lệ lỗi 5xx từ client perspective:

~~~promql
sum(rate(http_client_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_client_requests_seconds_count[5m]))
~~~

p95 latency với classic histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_client_requests_seconds_bucket[5m])
  )
)
~~~

Các truy vấn giả định registry export meter http_client_requests dưới dạng seconds và labels method/uri/status. Tên thực tế, unit, bucket và labels có thể khác theo version/configuration. Xem scrape output trước khi sử dụng dashboard.

### 6.2. Metric tags và span attributes có ngân sách khác nhau

Low-cardinality URI template phù hợp cho metrics. Span có thể chứa metadata chi tiết hơn, nhưng raw URI/query string vẫn có thể tăng indexing/storage cost hoặc tiết lộ dữ liệu. Không copy mọi path/query values vào span attributes.

## 7. Query parameters, encoding và path variables

URI template thường mô tả path; query parameters có thể thay đổi theo request và đôi khi chứa dữ liệu nhạy cảm.

~~~text
Template:
  /search?category={category}&page={page}
Request A:
  /search?category=books&page=1
Request B:
  /search?category=books&page=2
~~~

Nếu query values được đưa vào metric tag, cardinality tăng theo giá trị filter/page. Thông thường chỉ dùng path template cho metric dimensions, không dùng query string đầy đủ.

### 7.1. Encoding path variables

Giá trị path có thể chứa dấu cách, slash, Unicode hoặc ký tự reserved. Dùng URI builder của Spring để encode variables theo quy tắc URI. Tránh tự encode hai lần hoặc nối chuỗi. Test ký tự đặc biệt để xác nhận request URI đúng và telemetry vẫn dùng template.

### 7.2. Query string có thể chứa secret

Một số API sai thiết kế đặt API key, token hoặc PII trong query string. URI đầy đủ có thể xuất hiện trong logs, spans, proxy access logs hoặc exception messages. Không log/export raw query string; chuyển credentials sang header bảo mật và redaction URI nếu hệ thống có thể ghi giá trị nhạy cảm.

### 7.3. Base URL và host

Host có thể thay đổi theo môi trường hoặc load balancing. Không nhất thiết đưa raw host/port vào metric tag. Nếu cần phân biệt dependency, dùng tên logical ổn định như customer-api hoặc inventory-service. Nếu host quan trọng cho điều tra, có thể lưu ở trace attributes đã kiểm soát nhưng cân nhắc cardinality và privacy.

## 8. Custom ObservationConvention cho HTTP client

Khi cần chuẩn hóa metadata client, dùng ObservationConvention hoặc custom Observation phù hợp extension point của client. Không tạo một Observation thứ hai cho cùng HTTP request nếu client đã tự instrument.

Một custom business Observation bao quanh lời gọi client có thể bổ sung operation nghiệp vụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PricingService {
    private final RestClient restClient;
    private final ObservationRegistry registry;

    public PricingService(RestClient restClient, ObservationRegistry registry) {
        this.restClient = restClient;
        this.registry = registry;
    }

    public Price getPrice(String productCode) {
        return Observation.createNotStarted("pricing.lookup", registry)
                .lowCardinalityKeyValue("pricing.source", "catalog")
                .observe(() -> restClient.get()
                        .uri("/products/{code}/price", productCode)
                        .retrieve()
                        .body(Price.class));
    }
}
~~~

pricing.lookup là business operation bao quanh HTTP client call; HTTP client instrumentation vẫn quan sát request HTTP. Tag pricing.source có tập giá trị nhỏ. Không thêm productCode vào low-cardinality tag.

### 8.1. Không dùng URI động làm observation name

Không đặt observation name như GET /customers/101/orders. Tên động làm metric dimension không ổn định và có thể lộ dữ liệu. Dùng tên operation ổn định và template URI riêng.

## 9. URI template, tracing propagation và correlation

URI template mô tả đích gọi; trace context mô tả quan hệ giữa các thao tác. Hai khái niệm bổ sung cho nhau.

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant Client as HTTP client
    participant Inventory as inventory-service
    participant Collector
    Order->>Client: GET /inventory/{sku}
    Note over Client: Client span + URI template
    Client->>Inventory: GET /inventory/ABC-1 + traceparent
    Note over Inventory: Server span + route template
    Inventory-->>Client: HTTP 200
    Client-->>Order: Inventory response
    Order->>Collector: Export client span
    Inventory->>Collector: Export server span
~~~

URI template cho biết operation gọi tới endpoint nào; Trace ID liên kết client span với server span; Span ID xác định thao tác; Resource attributes cho biết service phát span; logs có thể mang traceId/spanId qua MDC.

Nếu URI template bị mất, trace vẫn có thể tồn tại nhưng endpoint grouping trong metrics/traces kém hữu ích. Nếu trace propagation mất, URI template vẫn có thể ghi nhận client operation nhưng không liên kết được với server span downstream.

## 10. Kiểm soát cardinality và dữ liệu nhạy cảm

| Giá trị | Metric tag? | Trace attribute? | Ghi chú |
| --- | --- | --- | --- |
| URI template | Có | Có, theo convention | Ổn định |
| Expanded path chứa ID | Không | Tránh hoặc redact | High cardinality |
| Query string đầy đủ | Không | Không mặc định | Có thể chứa PII/secrets |
| HTTP method | Có | Có | Tập nhỏ |
| Status/outcome | Có | Có | Tập hữu hạn |
| Dependency logical name | Có | Có | Chuẩn hóa |
| Trace ID | Không | Context field | Correlation, không làm label |
| Customer ID | Không | Chỉ khi cần và được duyệt | PII/cardinality |
| Authorization token | Không | Không | Secret |
| Exception message | Không | Không mặc định | Có thể chứa giá trị động |

### 10.1. Ước lượng cardinality

Nếu một client metric có 20 URI templates, 5 HTTP methods, 6 status groups và 4 dependency names, số tổ hợp tối đa đơn giản là:

\[
20 \times 5 \times 6 \times 4 = 2.400
\]

Nếu thay 20 templates bằng 100.000 expanded paths, số tổ hợp tiềm năng tăng theo số path thực tế. Đây là mô hình minh họa; series thực tế phụ thuộc tổ hợp xuất hiện và labels khác.

### 10.2. Attribute filtering và redaction

Thiết lập allowlist attributes cần thiết. Nếu URI có token hoặc PII trong query, redaction nên xảy ra trước khi export/log. Không dựa vào việc backend che field trên giao diện vì payload đã rời khỏi process.

## 11. Kiểm thử URI template

Cần xác minh không chỉ request gửi đúng endpoint mà cả observation/metrics/tracing ghi đúng template.

### 11.1. Kiểm thử URI expansion

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponentsBuilder;
import static org.assertj.core.api.Assertions.assertThat;

class CustomerUriTest {
    @Test
    void expandsCustomerTemplate() {
        String uri = UriComponentsBuilder
                .fromPath("/customers/{customerId}/orders")
                .buildAndExpand("101")
                .encode()
                .toUriString();

        assertThat(uri).isEqualTo("/customers/101/orders");
    }
}
~~~

Test này chỉ xác minh URI expansion; nó không chứng minh HTTP client observation giữ template.

### 11.2. Kiểm thử Observation với client

Dùng test server (ví dụ MockWebServer/WireMock hoặc embedded HTTP server) và HTTP client được cấu hình như production:

1. Tạo request bằng template /customers/{customerId}/orders.
2. Gửi nhiều customer IDs khác nhau.
3. Thu Observation hoặc meter events.
4. Assert URI tag vẫn là template.
5. Assert request thực tế gửi tới expanded path đúng.
6. Assert không có customer ID trong metric tags.
7. Gửi response 4xx/5xx và kiểm tra status/outcome.
8. Nếu tracing bật, kiểm tra client span có template attribute và trace context được inject.

### 11.3. Test riêng từng client implementation

RestClient, RestTemplate và WebClient có API builder, instrumentation và lifecycle riêng. Không suy ra WebClient giữ template chỉ vì RestClient đã được kiểm tra. Tạo test cho từng client implementation thực tế.

### 11.4. Kiểm thử query và encoding

Dùng query values có dấu cách, Unicode, ký tự reserved và giá trị giống token giả lập. Xác minh request URI được encode đúng; template không chứa expanded IDs; query nhạy cảm không bị export/log; metrics cardinality không tăng theo query value.

## 12. Troubleshooting URI template

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Metric uri là UNKNOWN | Client chỉ nhận expanded URI hoặc template không được truyền | Dùng URI template overload/builder và kiểm tra observation context |
| Metric uri chứa customer ID | URL tạo bằng nối chuỗi | Dùng template API với variables |
| RestClient có template nhưng WebClient không | API/client instrumentation khác nhau | Test riêng từng client builder |
| Template bị encode thành %7B...%7D | Variables/template bị encode sai thứ tự | Dùng URI builder API phù hợp |
| Query values tạo nhiều series | Query string bị dùng làm tag | Bỏ query khỏi metric dimension |
| Metrics đếm hai lần | Auto instrumentation và interceptor custom cùng ghi | Loại instrumentation trùng |
| Span không có URI template | Convention không nhận template hoặc client không cung cấp | Kiểm tra span attributes |
| Raw token xuất hiện trong trace | Query/header bị capture | Redact/allowlist trước export |
| Host thay đổi làm series tăng | Raw host/port dùng làm tag | Dùng logical dependency name |
| URI sai khi có slash/Unicode | Tự nối hoặc encode thủ công | Dùng UriBuilder và test encoding |
| Trace client không nối server | Propagation headers/context sai | Kiểm tra W3C traceparent |
| HTTP client không có observation | Builder tự tạo bỏ qua Boot customizer | Dùng auto-configured builder và kiểm tra registry |

### 12.1. Quy trình điều tra

1. Xác định client implementation thực tế: RestClient, RestTemplate hay WebClient.
2. Kiểm tra client được tạo từ builder nào và có auto-configuration/customizer không.
3. Xem request URI được tạo bằng template overload hay expanded URI thuần.
4. Thu Observation/meter/span thực tế để xem URI tag/attribute.
5. So sánh template với request URL đã gửi.
6. Kiểm tra query, encoding, host và dữ liệu nhạy cảm.
7. Kiểm tra instrumentation có bị đăng ký hai lần.
8. Nếu trace không nối downstream, kiểm tra propagation riêng với URI template.

## 13. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| URI template ổn định | Path variables dùng placeholder |
| Không dùng expanded URI làm metric tag | Test nhiều IDs cho cùng template |
| Client builder được quản lý | Spring Boot customizers/observation được áp dụng |
| RestClient/RestTemplate/WebClient đã test | Mỗi implementation giữ đúng template |
| HTTP method/status/outcome chuẩn hóa | Dashboard ổn định |
| Query string được kiểm soát | Không export token/PII |
| Path encoding chính xác | Test slash, Unicode và reserved chars |
| Dependency name ổn định | Không dùng host động làm metric label |
| Không duplicate instrumentation | Một HTTP request có một client observation chính |
| Tracing propagation đúng | Client/server spans cùng trace |
| Cardinality được đo | Số series theo template nằm trong ngân sách |
| Redaction trước export | Không dựa vào UI masking |
| Có runbook | Xử lý UNKNOWN/raw URI/missing span |

## 14. Bài thực hành: chuẩn hóa URI template cho HTTP clients

**Bối cảnh:** order-service gọi customer-api, inventory-api và pricing-api. Metrics hiện ghi URI đã mở rộng chứa customerId/productCode, khiến cardinality tăng. Một số WebClient spans không có URI template.

**Nhiệm vụ:**
1. Kiểm kê HTTP client đang dùng: RestClient, RestTemplate và WebClient.
2. Thay URL nối chuỗi bằng URI template và path variables.
3. Dùng builder do Spring Boot quản lý để giữ observation customizers.
4. Gửi nhiều customer IDs tới cùng endpoint và xác minh metric URI vẫn là /customers/{customerId}/orders.
5. Thêm query parameters bằng UriBuilder và test encoding.
6. Thu Observation/meter/span data để so sánh template với expanded URI.
7. Xác minh status/outcome và latency khi remote trả 4xx/5xx.
8. Kiểm tra client span truyền traceparent tới server và hai spans cùng trace ID.
9. Redact query/header nhạy cảm; xác minh không có token hoặc PII trong log/trace.
10. Viết test cardinality regression và runbook khi URI tag thành UNKNOWN hoặc raw path.

**Kết quả mong đợi:** client code dùng URI templates, metrics nhóm đúng endpoint, traces có operation metadata an toàn, test riêng cho client implementations và hướng dẫn điều tra URI template bị mất.

## 15. Ghi nhớ

**URI template** là mẫu endpoint ổn định, ví dụ /customers/{customerId}/orders; expanded URI là request cụ thể, ví dụ /customers/101/orders. Dùng template API của RestClient, RestTemplate hoặc WebClient để HTTP client instrumentation có thể giữ metadata này. Tránh nối chuỗi URL nếu cần template-aware telemetry.

URI template giúp metrics có cardinality thấp và traces mô tả operation dễ hiểu. Không đưa raw query string, customer ID, token hoặc URL động vào metric tags. Dùng builder do Spring Boot quản lý, kiểm thử từng client implementation, xác minh URI tag/span attribute thực tế và giữ trace context propagation độc lập với template. Metrics phục vụ request/error/latency aggregation; traces giúp điều tra dependency calls; logs cung cấp sự kiện đã được correlation và redaction.

**Tài liệu tham khảo:**
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-restclient)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot — HTTP Client Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)

