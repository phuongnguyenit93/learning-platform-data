# WebClient observation trong Spring Boot

> **Chương:** HTTP client observability  
> **Bài:** WebClient observation  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần quan sát HTTP client?

Một service Spring Boot hiếm khi hoạt động độc lập. Khi xử lý một request, service có thể gọi inventory, payment, identity hoặc một API bên ngoài. Nếu chỉ đo thời gian HTTP server, nhóm vận hành biết request chậm nhưng chưa biết thời gian bị tiêu tốn ở database, business logic hay dependency HTTP.

**WebClient observation** ghi nhận hoạt động của HTTP client được thực hiện bằng Spring WebClient. Observation có thể cung cấp dữ liệu cho metrics và distributed tracing: method, URI template, trạng thái response, thời gian, exception và context liên kết với request hiện tại.

Ví dụ một luồng:

~~~mermaid
sequenceDiagram
  participant Caller as API caller
  participant Order as order-service
  participant Obs as Observation / tracing
  participant Web as WebClient
  participant Inv as inventory-service
  Caller->>Order: POST /orders
  Order->>Obs: Start client observation
  Obs->>Web: Instrument exchange
  Web->>Inv: HTTP request + trace context
  Inv-->>Web: HTTP response
  Web-->>Obs: status / error / duration
  Obs->>Obs: Stop observation and span
  Order-->>Caller: HTTP response
~~~

Không chỉ đo “có gọi API hay không”. Cần biết request được gửi tới dependency nào, thời gian bao lâu, response status gì, có lỗi transport hay không, và trace có nối đúng với server span của dependency hay không.

## 2. WebClient là gì và instrumentation nằm ở đâu?

Spring WebClient là HTTP client reactive, non-blocking, dựa trên Reactor và thường dùng trong Spring WebFlux. Nó có thể được dùng trong ứng dụng Spring MVC như một HTTP client mà không cần biến toàn bộ server thành WebFlux.

Instrumentation của WebClient có thể được tích hợp ở builder/exchange function/filter layer. Khi dùng Spring Boot Actuator và Micrometer Observation với phiên bản hỗ trợ, WebClient được cấu hình qua auto-configured builder có thể tự tạo client observations.

Điều này có một hệ quả quan trọng: **hãy dùng WebClient.Builder do Spring quản lý** nếu muốn nhận các customizer/observation instrumentation mà Boot cấu hình.

~~~java
@Service
public class InventoryClient {
    private final WebClient webClient;

    public InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Không tự gọi WebClient.create() ở khắp nơi rồi giả định mọi builder customizer của Spring Boot sẽ tự áp dụng. Một WebClient tự tạo độc lập có thể thiếu instrumentation hoặc cấu hình chung.

## 3. Dependencies và cấu hình nền tảng

Với Spring Boot 3.x, Actuator tích hợp observability và Micrometer Observation. WebClient cần starter/module tương ứng với reactive client và HTTP connector.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Đây là một lựa chọn minh họa cho tracing qua OpenTelemetry bridge và OTLP exporter. Nếu dùng Brave/Zipkin hoặc stack khác, dependency tracing/exporter sẽ khác. Dùng Spring Boot BOM để quản lý version tương thích, không trộn nhiều tracing bridge cho cùng một application context.

Ví dụ cấu hình tracing:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Property và auto-configuration cụ thể phụ thuộc Spring Boot minor version và exporter. Trong Docker/Kubernetes, thay localhost bằng DNS/service endpoint mà application có thể truy cập.

## 4. WebClient.Builder và auto-configuration

Spring Boot có thể cung cấp WebClient.Builder được tùy biến thông qua các WebClientCustomizer. Những customizer này có thể cấu hình codec, connector, observation registry, observation convention và các thành phần chung khác.

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Tiêm builder thay vì tự tạo WebClient mới cho mỗi method giúp:
- Dùng chung cấu hình và customizers.
- Áp dụng observation instrumentation do Boot cấu hình.
- Chuẩn hóa connector, timeout, codec và filter.
- Dễ kiểm thử bằng cách thay base URL hoặc connector trong test.

Không nên tạo một builder mới ngoài Spring context nếu cần các customizers đó. Nếu có nhiều WebClient cho nhiều dependency, có thể tạo nhiều bean từ builder và đặt base URL/config riêng.

### 4.1. Tạo client độc lập có chủ đích

Có trường hợp cần WebClient không dùng cấu hình mặc định, ví dụ test hoặc connector riêng. Khi đó phải chủ động cấu hình ObservationRegistry/filter tương ứng và xác minh instrumentation. Đừng suy ra một client độc lập có đầy đủ metrics/tracing chỉ vì classpath chứa Actuator.

## 5. Vòng đời WebClient observation

Một client observation thường bắt đầu khi WebClient thực thi exchange, sau đó theo dõi response hoặc lỗi. Với reactive flow, thời điểm subscription quan trọng: WebClient request thường không thực sự chạy cho tới khi publisher được subscribe.

~~~mermaid
flowchart TD
  A["Build WebClient request"] --> B["Create reactive publisher"]
  B --> C["Subscribe / exchange begins"]
  C --> D["Start client observation/span"]
  D --> E["Inject propagation headers"]
  E --> F["Send HTTP request"]
  F --> G{"Exchange result"}
  G -->|"Response"| H["Capture status / response metadata"]
  G -->|"Transport or exchange error"| I["Record error"]
  H --> J["Stop observation when exchange completes"]
  I --> J
~~~

Nếu code tạo Mono/Flux nhưng không subscribe, request có thể chưa được gửi; không có client observation hoàn chỉnh cho một exchange chưa diễn ra. Nếu publisher được subscribe nhiều lần, mỗi lần subscription có thể tạo một HTTP exchange mới và observation tương ứng.

Với response body, lifecycle và thời điểm body được tiêu thụ phụ thuộc API/connector và cách WebClient được sử dụng. Đừng giữ response body vô hạn hoặc đọc body hai lần chỉ để ghi log.

## 6. Metrics do WebClient observation tạo ra

Micrometer observation handlers có thể ghi metrics từ client observations. Trong Spring Boot/Micrometer, tên meter và tag conventions phụ thuộc phiên bản và integration. Một tên thường gặp là:

~~~text
http.client.requests
~~~

Các dimensions phổ biến của HTTP client metrics có thể gồm:
- method: HTTP method.
- uri: URI template hoặc route pattern đã chuẩn hóa.
- client.name: host/service name hoặc nhóm destination theo convention.
- status: response status code.
- outcome: nhóm kết quả.
- exception: loại exception hoặc none/unknown.
- tên/giá trị khác theo convention và version.

Kiểm tra meter thực tế trong registry/Actuator endpoint, không hard-code assumptions từ một phiên bản khác.

Ví dụ truy vấn PromQL minh họa:

~~~text
Request rate:
  sum(rate(http_client_requests_seconds_count[5m]))

Client 5xx ratio:
  sum(rate(http_client_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_client_requests_seconds_count[5m]))
~~~

Metric names có thể được đổi khi export sang Prometheus và suffix phụ thuộc timer/histogram configuration. Truy vấn cần điều chỉnh theo metric thực tế.

### 6.1. URI template và cardinality

Dùng URI template như /products/{id} thay vì URL đầy đủ /products/12345. Nếu mỗi ID tạo một tag value, số time series tăng nhanh.

Không đưa vào metric tags:
- order ID, customer ID, user ID.
- query string hoặc raw URL.
- request/response body.
- token, cookie hoặc authorization header.
- exception message tự do.

Client name/host cũng nên được kiểm soát. Nếu destination được tạo động từ dữ liệu đầu vào, cần chuẩn hóa thành nhóm hữu hạn hoặc service identity phù hợp.

## 7. Distributed tracing và propagation headers

Khi WebClient được instrument với tracing integration, client observation có thể tạo client span và inject trace context vào outbound request. Server instrumentation ở dependency extract context để tạo server span có parent relation.

Với W3C Trace Context, header thường có dạng:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Nếu dependency hỗ trợ B3, propagation headers có thể khác. Cấu hình propagator phải tương thích giữa caller, proxy và callee.

Một trace phân tán có thể hiển thị:

~~~text
order-service: POST /orders                 [SERVER]
  order-service: inventory GET /items/{id}  [CLIENT]
    inventory-service: GET /items/{id}      [SERVER]
~~~

Client span và server span ở dependency là hai phía của cùng một network call; không phải duplicate instrumentation nếu span kind và parent-child relation đúng.

Nếu trace bị tách, kiểm tra:
- WebClient được tạo từ builder có instrumentation không.
- Propagator W3C/B3 có tương thích không.
- Proxy/service mesh có forward headers không.
- Downstream server instrumentation có extract context không.
- Async/reactive context có được giữ tới thời điểm subscribe không.

## 8. WebClient observation và error semantics

Không phải mọi response 4xx/5xx đều tạo exception ở tầng WebClient exchange. WebClient có thể nhận một HTTP response bình thường ở mức transport, sau đó code ứng dụng quyết định xử lý status bằng retrieve/onStatus hoặc exchangeToMono.

Ví dụ:

~~~java
webClient.get()
    .uri("/items/{id}", itemId)
    .retrieve()
    .bodyToMono(Item.class);
~~~

Trong cách dùng retrieve(), status 4xx/5xx thường được chuyển thành WebClientResponseException theo default status handling. Với exchangeToMono(), code có thể tự phân nhánh theo response status.

~~~java
webClient.get()
    .uri("/items/{id}", itemId)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        if (response.statusCode().is4xxClientError()) {
            return response.createException()
                    .flatMap(Mono::error);
        }
        return response.createException()
                .flatMap(Mono::error);
    });
~~~

Client observation có thể ghi nhận status code kể cả khi code không ném exception. Exception metadata phản ánh lỗi transport/decode hoặc error mapping trong client API. Khi đọc trace/metrics, phân biệt response status với exception type.

Một HTTP 404 từ inventory có thể là expected result; một 503 có thể là dependency availability issue. Outcome phụ thuộc contract và chính sách retry/fallback.

## 9. Timeout, retry và cancellation

Timeout và retry làm thay đổi số lượng client exchanges và latency mà người vận hành quan sát.

Ví dụ timeout ở Reactor:

~~~java
webClient.get()
    .uri("/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(Stock.class)
    .timeout(Duration.ofSeconds(2));
~~~

Timeout operator có thể kết thúc subscription bằng TimeoutException. Tùy nơi đặt timeout, timeout có thể xảy ra trước khi response tới, trong lúc body được tiêu thụ hoặc do một tầng connector khác. Kiểm tra span/error thực tế thay vì giả định mọi timeout có cùng exception.

Ví dụ retry có giới hạn:

~~~java
webClient.get()
    .uri("/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(Stock.class)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Mỗi lần retry có thể tạo một HTTP exchange mới. Tùy instrumentation và subscription boundaries, có thể có nhiều client spans hoặc một operation span cùng các attempt spans. Quan sát waterfall thực tế và tránh tự tạo span trùng cho cùng attempt.

Cancellation cũng là một kết quả cần phân biệt. Client disconnect, Reactor cancellation hoặc timeout không phải lúc nào cũng là lỗi server. Ghi nhận cancellation/timeout theo semantics, không gán mọi trường hợp thành 5xx.

## 10. Tùy biến WebClient ObservationConvention

Micrometer cho phép tùy biến convention để bổ sung low-cardinality/high-cardinality metadata cho client observation. API cụ thể phụ thuộc phiên bản Micrometer/Spring Boot và loại client observation.

Ví dụ minh họa convention:

~~~java
public class InventoryClientObservationConvention
        implements ClientRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ClientRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of("dependency", "inventory"),
                KeyValue.of("operation", "lookup-stock"));
    }
}
~~~

Ví dụ là khung minh họa; interface, context type và cách đăng ký bean cần khớp dependency version thực tế. Có thể dùng convention để thay tên observation hoặc thêm metadata ổn định theo client/dependency.

Chỉ thêm low-cardinality values có tập hữu hạn như dependency=inventory, operation=lookup-stock, region group hoặc API version. Không thêm SKU, order ID, raw URI hay customer ID thành metric tags.

### 10.1. URI mapping và custom filters

Nếu URL được tạo động, cấu hình URI template đúng cách:

~~~java
webClient.get()
    .uri("/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

Dùng template giúp instrumentation biết route pattern. Nếu nối chuỗi trực tiếp:

~~~java
webClient.get()
    .uri("/items/" + sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

instrumentation có thể chỉ thấy URI đầy đủ hoặc không chuẩn hóa được, dẫn tới cardinality cao. Tránh dynamic host/path từ dữ liệu không tin cậy; dùng allowlist và cấu hình base URL.

## 11. Gắn thêm ExchangeFilterFunction có cần thiết không?

WebClient hỗ trợ ExchangeFilterFunction để xử lý request/response, thêm headers hoặc quan sát behavior. Tuy nhiên, filter custom không nên tạo thêm một observation/span nếu built-in instrumentation đã làm việc đó.

Ví dụ filter phục vụ logging metadata an toàn:

~~~java
ExchangeFilterFunction requestLog = ExchangeFilterFunction.ofRequestProcessor(request -> {
    log.debug("Calling dependency method={} url={}",
            request.method(), request.url().getPath());
    return Mono.just(request);
});
~~~

Đây là log minh họa. Cần tránh ghi query string, credentials hoặc URL có identifiers. Không ghi request body mặc định vì body có thể chứa PII/secrets và việc đọc body có thể tiêu thụ publisher.

Khi thêm filter:
- Chỉ thêm hành vi chưa có ở instrumentation mặc định.
- Không log toàn bộ headers.
- Không tạo trace ID thủ công.
- Không subscribe bên trong filter.
- Không consume response body rồi trả lại một response đã bị tiêu thụ.
- Kiểm tra thứ tự filter và behavior khi exception.

## 12. Context propagation trong reactive flow

WebClient request được thực thi theo reactive subscription. Trace context cần được giữ qua Reactor operators và thread switches. Spring Boot/Micrometer tracing integration có thể cung cấp context propagation phù hợp khi dependencies và configuration tương thích.

~~~java
return Mono.deferContextual(contextView ->
        webClient.get()
            .uri("/items/{id}", itemId)
            .retrieve()
            .bodyToMono(Item.class));
~~~

Ví dụ này không tự tạo hoặc inject trace context; nó chỉ minh họa reactive context access. Dùng WebClient instrumentation và context propagation của stack đang chạy.

Tránh:
- Lưu trace ID vào static variable.
- Copy MDC bằng tay giữa mọi callback mà không khôi phục/clear đúng cách.
- Gọi subscribe() bên trong service để tách flow khỏi caller.
- Dùng ThreadLocal tự quản lý thay cho context integration.
- Dùng một WebClient builder tự tạo rồi cho rằng Boot customizers tự áp dụng.

Kiểm tra trace ID ở server span của caller, client span và server span dependency khi thực thi qua scheduler/parallel operators.

## 13. WebClient và log correlation

Logs của client call nên giúp xác định dependency, operation, status và trace context. Nếu logging correlation được cấu hình, traceId/spanId có thể được thêm vào log thông qua MDC hoặc structured logging integration.

Ví dụ log an toàn:

~~~text
WARN order-service traceId=4bf92f... dependency=inventory operation=lookup-stock status=503 retry=1
~~~

Không log authorization headers, cookies, access token, raw response body hoặc query parameters nhạy cảm. Dùng structured fields và các giá trị đã allowlist.

Không đưa trace ID thành metric label. Log correlation dùng ID để tìm trace; metrics cần low-cardinality labels. Nếu trace bị sampling loại, log vẫn có thể tồn tại theo logging policy riêng.

## 14. Kiểm thử WebClient observation

Không chỉ test response body. Cần xác minh instrumentation thực sự tạo observation và propagation đúng.

### 14.1. Test với MockWebServer hoặc WireMock

Có thể dùng mock HTTP server để kiểm soát status, latency và response. Ví dụ test cần xác minh:
- WebClient.Builder được inject từ Spring context.
- Request tới đúng URI template.
- Response 2xx ghi nhận thành công.
- Response 4xx/5xx có status và exception semantics phù hợp.
- Timeout/cancellation được quan sát.
- Trace context header được inject khi tracing được bật.

### 14.2. Test ObservationRegistry

Có thể dùng ObservationRegistry test handler để ghi nhận start/stop và key values. Cách tạo handler phụ thuộc Micrometer version.

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();

Observation observation = Observation.createNotStarted(
        "http.client.test", registry);

observation.observe(() -> {
    // Execute a controlled operation.
});
~~~

Đây là ví dụ minh họa API test của Micrometer; thêm handler hoặc assertion phù hợp version đang dùng. Với WebClient auto-instrumentation, test Spring application context và builder thật để xác minh customizers được áp dụng.

### 14.3. Test propagation

Mock server có thể kiểm tra header traceparent hoặc B3 khi có current trace. Không hard-code trace ID random do SDK tạo; kiểm tra cấu trúc header, trace ID hợp lệ và mối quan hệ parent trong test tracing integration.

## 15. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không có client metrics | Dùng WebClient.create() không có customizer hoặc thiếu registry/handler | Dùng injected Builder, kiểm tra ObservationRegistry |
| Có metrics nhưng không có spans | Thiếu tracing bridge/exporter hoặc sampling loại trace | Kiểm tra tracing integration và sampling |
| Client span không có trace ID chung với server | Context propagation bị đứt | Kiểm tra Reactor context, propagator và headers |
| URI tag có hàng nghìn giá trị | Dùng raw URL/path chứa ID | Dùng URI template |
| Status 503 nhưng exception tag none | Response được xử lý như response bình thường hoặc mapping khác | Kiểm tra retrieve/exchangeToMono và convention |
| Timeout không hiện như mong muốn | Timeout ở tầng khác hoặc subscription/body lifecycle | Xác định timeout operator và span lifecycle |
| Có span trùng | Java agent, custom filter và Boot instrumentation cùng tạo span | Kiểm tra waterfall/span kind/parent |
| Builder customizer không chạy | Tự tạo WebClient hoặc builder ngoài context | Inject WebClient.Builder |
| Trace bị mất sau publishOn/subscribeOn | Context propagation chưa tương thích/cấu hình | Kiểm tra version Reactor/Micrometer và context hooks |
| Logs thiếu traceId | Logging correlation chưa bật hoặc context bị mất | Kiểm tra MDC integration và async flow |
| App bị chậm khi logging request | Log body/headers hoặc filter blocking | Loại body logging, tránh blocking |
| Metrics không khớp request count | Retry tạo nhiều client exchanges | Phân biệt logical operation với từng attempt |

### Quy trình điều tra

1. Kiểm tra WebClient được tạo từ Spring-managed Builder.
2. Xác nhận Actuator/Observation và registry/handlers đã có.
3. Kiểm tra client metric xuất hiện trong registry.
4. Bật tracing bridge/exporter và xác minh sampler.
5. Kiểm tra traceparent/B3 trên outbound request và downstream.
6. Kiểm tra URI template và tags thực tế.
7. Kiểm tra retry/timeout/cancellation semantics.
8. Loại bỏ instrumentation/filter trùng.
9. Đối chiếu logs bằng traceId/spanId.

## 16. Tình huống thực tế: order-service gọi inventory-service

**Bối cảnh:** order-service dùng WebClient để kiểm tra tồn kho. p95 của POST /orders tăng. Metrics HTTP server cho thấy request chậm nhưng chưa rõ dependency nào là nguyên nhân.

### Bước 1 — tạo WebClient dùng builder

~~~java
@Configuration
class InventoryClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

### Bước 2 — gọi bằng URI template

~~~java
public Mono<Stock> findStock(String sku) {
    return webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);
}
~~~

### Bước 3 — quan sát dependency

Metrics client cho biết request rate, latency và status theo dependency/URI template. Trace cho thấy client span inventory nằm dưới server span order-service. Nếu có retry, mỗi attempt cần được nhận diện đúng.

### Bước 4 — tìm nguyên nhân

Nếu client span chiếm gần toàn bộ thời gian, kiểm tra inventory service, network, connection pool và timeout. Nếu client span ngắn nhưng server span dài, kiểm tra business logic, database hoặc queue ở order-service.

### Bước 5 — kiểm chứng sau sửa

Theo dõi p95 HTTP server và client, 5xx/timeout rate, retry count và trace waterfall. Xác nhận trace context đi qua WebClient và không có URI cardinality explosion.

**Kết quả mong muốn:** nhóm vận hành nhìn thấy dependency nào làm request chậm, request status/exception nào xuất hiện và trace liên kết được caller với callee.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — WebClient auto observation

Tạo Spring Boot app có Actuator và WebFlux. Inject WebClient.Builder, gọi một mock service. Xác minh client observation và meter được tạo. So sánh với WebClient.create() độc lập trong test.

### Bài tập B — tracing propagation

Bật Micrometer Tracing với bridge đã chọn. Gọi downstream bằng WebClient. Kiểm tra trace ID chung, client/server span relation và propagation headers. Thử ngắt header để quan sát trace bị tách.

### Bài tập C — status và exception

Mock response 200, 404, 429, 503 và một transport timeout. Quan sát status attribute, exception metadata và span status. Giải thích vì sao HTTP response 404 không nhất thiết là transport exception.

### Bài tập D — URI cardinality

Gọi /items/{id} cho hàng nghìn ID. So sánh URI template với nối chuỗi raw path. Kiểm tra số tag values/time series và sửa về template.

### Bài tập E — retry và timeout

Thiết lập timeout 2 giây và retry tối đa hai lần. Tạo downstream chậm rồi thất bại. Kiểm tra số client exchanges/spans, latency và exception. Đảm bảo không log/đếm duplicate một logical operation sai semantics.

### Bài tập F — custom observation metadata

Tạo convention thêm dependency=inventory và operation=lookup-stock. Xác minh tags có cardinality thấp trên metrics và span attributes trên trace theo handler đang dùng.

### Câu hỏi tự kiểm tra

1. WebClient observation đo lifecycle nào?
2. Vì sao nên dùng WebClient.Builder do Spring quản lý?
3. Observation bắt đầu ở thời điểm tạo publisher hay subscription/exchange?
4. Client metrics thường có những dimensions nào?
5. Vì sao URI template quan trọng với cardinality?
6. WebClient tracing inject propagation headers thế nào?
7. Client span và downstream server span khác nhau ra sao?
8. Vì sao 404 có thể không phải transport exception?
9. Timeout operator có thể kết thúc reactive flow ở thời điểm nào?
10. Retry ảnh hưởng số HTTP exchanges và spans ra sao?
11. Cancellation có luôn là lỗi server không?
12. Khi nào nên dùng custom ClientRequestObservationConvention?
13. Vì sao không nên tạo span trong custom ExchangeFilterFunction nếu đã có instrumentation?
14. Context propagation hoạt động thế nào qua Reactor scheduler?
15. Cách xác minh WebClient observation qua registry, trace backend và mock server?

**Tiêu chí hoàn thành:** cấu hình WebClient bằng Spring-managed Builder; hiểu Observation lifecycle; đọc metrics/tags; nối client/server spans bằng context propagation; xử lý status/exception/timeout/retry/cancel; kiểm soát cardinality; test instrumentation và chẩn đoán duplicate spans.

## 18. Ghi nhớ

- WebClient observation cung cấp metadata và lifecycle cho HTTP client calls; metrics/tracing handlers có thể chuyển observation thành signals.
- Dùng WebClient.Builder được Spring Boot quản lý để nhận customizers/instrumentation khi auto-configuration hỗ trợ.
- Reactive request thường thực thi khi publisher được subscribe; mỗi subscription có thể tạo một exchange mới.
- Client metrics thường mô tả method, URI template, status, outcome, exception và dependency theo convention/version.
- Dùng URI template và low-cardinality metadata; không đưa IDs, raw URL, query string hay body vào metric tags.
- Tracing instrumentation inject trace context để nối client span với downstream server span; kiểm tra W3C/B3 compatibility.
- HTTP response status và exception là hai thông tin khác nhau. 4xx/5xx không phải lúc nào cũng tạo cùng exception semantics.
- Timeout, retry và cancellation có lifecycle riêng; quan sát từng attempt và logical operation đúng cách.
- Context propagation trong Reactor cần integration tương thích; không dựa vào ThreadLocal tự quản lý.
- Tránh duplicate spans giữa Boot instrumentation, Java agent và custom filters. Kiểm tra waterfall thực tế.
- Metrics, traces và logs có policy riêng; dùng metrics cho xu hướng, traces cho đường đi và logs cho chi tiết sự kiện.

## Tài liệu tham khảo

- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

