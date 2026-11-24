# Client name trong HTTP client observability của Spring Boot

## 1. Mục tiêu và bối cảnh

Một ứng dụng thường gọi nhiều dịch vụ HTTP: payment, inventory, identity, shipping, notification hoặc API đối tác. Khi latency hay tỷ lệ lỗi tăng, đội vận hành cần biết **dependency đích nào** đang gây ảnh hưởng. Chỉ nhìn method, status và route của request outbound đôi khi chưa đủ để nhóm dữ liệu theo dịch vụ.

Spring Boot và Micrometer cung cấp low-cardinality key **client.name** trong HTTP client observation. Mặc định, giá trị này được suy ra từ host của request URI. Metrics nhờ đó có thể nhóm latency/error theo remote host mà không đưa toàn bộ URL hoặc từng request identifier vào time series.

Bài thuộc chương **HTTP client observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể:
1. Giải thích client.name trong http.client.requests.
2. Phân biệt client.name, URI template và http.url.
3. Hiểu giá trị mặc định được suy ra từ host của request URI.
4. Bảo đảm RestClient, RestTemplate và WebClient được instrument bằng builder phù hợp.
5. Tùy biến tên client bằng ClientRequestObservationConvention khi cần.
6. Tránh cardinality cao do host động, tenant subdomain hoặc URL chứa dữ liệu request.
7. Dùng metrics, traces và logs để điều tra dependency latency/failure.
8. Kiểm thử client.name và các tags trong ứng dụng.

**Baseline:** Spring Boot 3.5.x, Java 17+, Micrometer Observation, Actuator. Ví dụ blocking dùng RestClient; WebClient có convention trong package reactive riêng. API cụ thể cần xác minh theo Spring Framework/Spring Boot version thực tế.

## 2. client.name là gì?

HTTP client observation mặc định có tên **http.client.requests**. Nó bao quanh một lần trao đổi HTTP outbound, từ lúc client thực hiện request tới khi nhận response và xử lý body theo lifecycle của client.

Các low-cardinality keys thường gặp:

| Key | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| method | HTTP method | GET, POST |
| uri | URI template đã cung cấp cho client | /v1/orders/{id} |
| client.name | Tên client/host đích | inventory.internal |
| status | HTTP status hoặc mã lỗi client | 200, 503, IO_ERROR |
| outcome | Nhóm kết quả | SUCCESS, SERVER_ERROR |
| error | Tên class exception trong exchange | ResourceAccessException |

High-cardinality key thường có **http.url**, chứa URI cụ thể của request. Không đưa giá trị high-cardinality vào metric labels.

Ví dụ request:

```java
restClient.get()
        .uri("https://inventory.internal/v1/items/{sku}", sku)
        .retrieve()
        .body(Item.class);
```

Observation có thể tạo các giá trị:
- client.name: inventory.internal
- uri: /v1/items/{sku}
- method: GET
- status: 200
- http.url: URL đầy đủ với host, path và giá trị sku thực tế (high cardinality)

client.name cho biết **dependency đích**, còn uri cho biết route template trên dependency đó.

## 3. Giá trị mặc định của client.name

Theo convention mặc định của Spring Framework, client.name được suy ra từ host trong request URI.

| Request URI | client.name mặc định |
| --- | --- |
| https://payment.internal/v1/charge | payment.internal |
| https://inventory.example.com/items/42 | inventory.example.com |
| http://localhost:8081/health | localhost |
| https://api.partner.example/v2/search?q=abc | api.partner.example |

Protocol, port và path không phải thành phần của host-derived client.name. Hai endpoint cùng host nhưng khác path có thể được group dưới cùng client.name.

Lưu ý:
- Nếu môi trường tạo host khác nhau theo tenant/request, số client.name có thể tăng cao.
- Nếu service discovery tạo nhiều hostname theo instance, metrics có thể bị phân mảnh.
- Nếu gọi qua proxy/gateway, client.name mặc định có thể là hostname proxy thay vì dependency logic phía sau.
- Nếu URI không có host hợp lệ hoặc request không được tạo thành công, giá trị có thể là none theo convention/framework version.

client.name mặc định không phải service registry hay logical dependency catalog. Nó phản ánh cách convention nhận diện host từ request.

## 4. Kích hoạt HTTP client observation

Spring Boot Actuator quản lý instrumentation cho RestClient, RestTemplate và WebClient. Điều kiện quan trọng là dùng builder đã được Spring Boot auto-configure.

### 4.1. RestClient

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {
    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.internal")
                .build();
    }

    public Item findItem(String sku) {
        return client.get()
                .uri("/v1/items/{sku}", sku)
                .retrieve()
                .body(Item.class);
    }
}
```

Builder được inject có thể đã gắn ObservationRegistry và customizers của Boot. Request được instrument khi dependencies/configuration observability cần thiết có mặt.

Tránh tự tạo client bằng RestClient.create(...), vì cách tạo tĩnh không sử dụng auto-configured builder và có thể bỏ qua observation instrumentation, trừ khi ứng dụng tự cấu hình registry/customizer.

### 4.2. RestTemplate

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class LegacyInventoryClient {
    private final RestTemplate client;

    public LegacyInventoryClient(RestTemplateBuilder builder) {
        this.client = builder
                .rootUri("https://inventory.internal")
                .build();
    }
}
```

Spring Boot dùng RestTemplateBuilder để thêm observation customizer. Không giả định mọi RestTemplate tự tạo bằng constructor đều được instrument.

### 4.3. WebClient

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveInventoryClient {
    private final WebClient client;

    public ReactiveInventoryClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.internal")
                .build();
    }

    public Mono<Item> findItem(String sku) {
        return client.get()
                .uri("/v1/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

WebClient observation theo reactive lifecycle. Observation kết thúc theo quá trình subscribe/response/error/cancel, không chỉ tại thời điểm method trả về Mono.

## 5. Tùy biến client.name theo logical dependency

Host-derived name phù hợp với nhiều hệ thống. Tuy nhiên, host kỹ thuật có thể không đại diện dependency logic:
- Nhiều service dùng chung một API gateway.
- Service discovery tạo nhiều host instance cho cùng logical service.
- Host thay đổi giữa dev/staging/production nhưng dashboard cần tên ổn định.
- Client dùng proxy nhưng cần group theo downstream dependency thực tế.

Có thể tùy biến low-cardinality key bằng **ClientRequestObservationConvention**.

Spring Framework có hai interface theo client stack:
- Blocking RestClient/RestTemplate: org.springframework.http.client.observation.ClientRequestObservationConvention.
- Reactive WebClient: org.springframework.web.reactive.function.client.ClientRequestObservationConvention.

Spring Boot cho phép đăng ký convention bean tương ứng để tùy biến tags của client observation.

### 5.1. Chọn logical name từ allowlist

Một convention tùy chỉnh nên:
1. Đọc host từ ClientRequestObservationContext.
2. Map host đã biết sang tên logical ổn định.
3. Map host lạ về other/unknown.
4. Giữ các low-cardinality keys mặc định như method, uri, status, outcome và error.
5. Chỉ xuất đúng một key client.name.

Ví dụ mapping:

```yaml
observability:
  http-clients:
    names:
      inventory.internal: inventory
      payment.internal: payment
      identity.internal: identity
```

Với RestClient/RestTemplate, convention thuộc package org.springframework.http.client.observation. Với WebClient, convention thuộc package org.springframework.web.reactive.function.client. Hai stack có context và interface riêng; không dùng nhầm interface blocking cho WebClient.

API của DefaultClientRequestObservationConvention và cách Boot chọn convention có thể thay đổi theo Spring Framework version. Khi triển khai, dùng tài liệu/API đúng version và đảm bảo không append key client.name lần thứ hai bên cạnh giá trị mặc định. Kết quả cuối cần đúng một giá trị client.name ổn định.

Nếu không cần custom behavior, giữ convention mặc định. Có thể alias/group ở query/dashboard layer nếu điều đó đáp ứng nhu cầu mà không thay đổi telemetry contract.

## 6. client.name và cardinality

client.name được thiết kế là **low-cardinality key**, nhưng key chỉ low-cardinality nếu tập giá trị thực tế bị giới hạn.

Tốt:
- inventory
- payment
- identity
- shipping

Có nguy cơ cardinality cao:
- tenant-9821.api.example
- pod-7f89c6d9b5-xk2p
- customer-12345.partner.example
- hostname lấy từ user input

Nếu host thay đổi theo tenant/customer/request, host-derived client.name có thể tạo nhiều metric series. Map về logical service name từ allowlist.

### 6.1. Không dùng raw URL làm metric tag

Không tạo tag từ full URL gồm query parameters, raw path chứa order/customer ID, request/correlation ID, user-provided hostname hoặc dynamic tenant subdomain.

Ví dụ xấu:

```java
registry.counter("outbound.calls",
        "client.name", request.getParameter("targetHost"),
        "url", request.getRequestURI()).increment();
```

Ví dụ tốt:

```java
registry.counter("outbound.calls",
        "client.name", "inventory",
        "outcome", "success").increment();
```

Giá trị tag phải đến từ danh sách hữu hạn do ứng dụng kiểm soát.

### 6.2. Host và proxy

Nếu tất cả outbound requests đi qua proxy, host-derived client.name có thể chỉ ra proxy. Có hai cách:
- Giữ proxy làm client.name nếu đó là dependency vận hành cần theo dõi.
- Dùng custom convention để map sang logical downstream nếu ứng dụng biết chắc request đang nhắm service nào.

Không suy luận downstream từ dữ liệu tùy ý hoặc query string không đáng tin. Logical name nên đến từ client bean/configuration có kiểm soát, không phải user input.

## 7. Dùng client.name để điều tra dependency

Giả sử dashboard có http.client.requests với tags client.name, method, uri, status, outcome và error.

Có thể phân tích:
- Dependency nào có p95/p99 latency tăng?
- Dependency nào trả 5xx nhiều nhất?
- Timeout/IO_ERROR tập trung ở client nào?
- Route nào của inventory lỗi hay toàn service inventory?
- Lỗi chỉ xuất hiện ở một deployment/environment hay toàn hệ thống?

Ví dụ tổng hợp:

| client.name | uri | outcome | p95 latency | error rate |
| --- | --- | --- | ---: | ---: |
| inventory | /v1/items/{sku} | SUCCESS | 45 ms | 0.1% |
| payment | /v1/charges | SERVER_ERROR | 820 ms | 8.4% |
| identity | /oauth/token | SUCCESS | 110 ms | 0.2% |

Số liệu minh họa. Dashboard thực cần query meter backend và tags được export; p95/error rate không phải tag.

client.name group theo dependency; uri phân biệt operation/route. Trace cho biết request cụ thể chờ ở span nào; logs cho biết exception/message; metrics cho biết xu hướng và phạm vi.

## 8. Liên kết với distributed tracing

HTTP client observation thường tạo client span khi Micrometer Tracing được cấu hình. Span có thể chứa client/dependency context, HTTP method và route/URL attributes, status/error information, traceId/spanId và parent relationship.

Khi propagation hoạt động, outbound request gửi trace context sang downstream. Server span ở service đích có thể liên kết với client span để xem toàn bộ dependency call trong trace.

client.name là observation/metric key; nó không phải trace ID và không thay thế span name. Một logical client có thể có nhiều spans theo từng request. Không cần đưa client.name vào baggage chỉ để tạo metric grouping.

## 9. Timeout, status và error tags

HTTP client observation ghi nhận outcome của exchange:
- HTTP 2xx: response thành công.
- HTTP 4xx/5xx: response nhận được nhưng status phản ánh lỗi phía request/server.
- IOException/connect timeout/read timeout: không nhận response bình thường; status/error có thể phản ánh IO error hoặc exception class.
- DNS/TLS/connection pool failure: request có thể fail trước khi nhận status.

Đừng chỉ đo HTTP 5xx. Dependency có thể không trả response do timeout, DNS hoặc TLS; quan sát error/outcome tags và exception logs.

Với RestClient, retrieve() có thể ném exception cho response 4xx/5xx theo error handler mặc định. Observation vẫn đo exchange; exception được truyền cho caller. Nếu ứng dụng dùng onStatus hoặc custom error handler, behavior exception thay đổi nhưng status/outcome của exchange vẫn cần được quan sát.

## 10. Kiểm thử client.name

### 10.1. Kiểm tra auto-configured client

- Tạo RestClient từ RestClient.Builder được inject.
- Gọi mock server hoặc test endpoint.
- Xác nhận observation/meter http.client.requests xuất hiện.
- Xác nhận client.name bằng host request URI theo convention mặc định.
- Xác nhận uri là template, không chứa giá trị path variable.
- Xác nhận http.url (nếu được lưu trong tracing/high-cardinality context) không được đưa thành metric tag.

Lặp lại với RestTemplateBuilder và WebClient.Builder nếu ứng dụng dùng các stack đó.

### 10.2. Kiểm tra custom convention

- Host inventory.internal được map thành inventory.
- Host payment.internal được map thành payment.
- Host lạ được map thành other/unknown.
- Không có hai key client.name trong cùng KeyValues.
- Low-cardinality tags giữ tập giá trị hữu hạn.
- Convention reactive được dùng bởi WebClient và convention blocking bởi RestClient/RestTemplate.

Dùng ObservationRegistry test handler để kiểm tra context/KeyValues hoặc MeterRegistry test để kiểm tra meter/tags sau request. Chọn cách phù hợp với Spring Boot version; không chỉ test method mapping mà bỏ qua việc builder có thực sự bật instrumentation.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có http.client.requests | Dùng client tự tạo, thiếu Actuator/registry/customizer | Dùng auto-configured builder và kiểm tra dependencies |
| client.name là localhost | URI thực sự dùng localhost | Kiểm tra URL trong môi trường chạy |
| client.name là tên proxy | Request đi qua gateway/proxy | Map về logical dependency nếu policy cho phép |
| Nhiều client.name gần giống nhau | Instance/tenant hostname khác nhau | Map host về tập logical names hữu hạn |
| client.name là other/unknown | Host chưa có allowlist hoặc URI không hợp lệ | Kiểm tra mapping và request construction |
| WebClient không dùng convention | Đăng ký nhầm blocking convention | Dùng reactive ClientRequestObservationConvention |
| Metric cardinality tăng mạnh | Raw host, URL, tenant hoặc request ID thành tag | Chuẩn hóa client.name và bỏ dynamic tags |
| Có metrics nhưng không có client span | Tracing bridge/propagation chưa cấu hình hoặc sampling | Kiểm tra tracing integration |
| Có span nhưng metrics không có | Meter registry/exporter hoặc instrumentation handler khác | Kiểm tra metrics pipeline và builder customizers |
| Error rate thấp nhưng dependency chậm | Chỉ nhìn status errors, bỏ qua latency/timeouts | Theo dõi timer percentiles và IO_ERROR |
| Host/path không đúng kỳ vọng | URI template không được truyền hoặc URL build động | Dùng URI template và test observation keys |

## 12. Checklist production

- [ ] Dùng auto-configured RestClient.Builder, RestTemplateBuilder hoặc WebClient.Builder.
- [ ] Xác nhận http.client.requests được ghi.
- [ ] Hiểu client.name mặc định lấy từ URI host.
- [ ] Phân biệt client.name với uri template và http.url.
- [ ] Map host động về logical dependency name khi cần.
- [ ] Giữ client.name trong tập giá trị low-cardinality.
- [ ] Không dùng raw URL, request ID, tenant ID hoặc correlation ID làm metric tags.
- [ ] Dùng convention đúng package cho blocking và reactive clients.
- [ ] Đảm bảo convention không phát hai key client.name.
- [ ] Kiểm thử status, IO error, timeout và host lạ.
- [ ] Liên kết metrics với client spans và logs bằng trace context.
- [ ] Theo dõi latency và connection errors, không chỉ HTTP 5xx.

## 13. Câu hỏi tự luyện

1. client.name trong http.client.requests có ý nghĩa gì?
2. Vì sao mặc định client.name được suy ra từ host thay vì full URL?
3. uri template khác http.url ở điểm nào?
4. Vì sao client.name là low-cardinality key nhưng vẫn có thể gây cardinality cao?
5. Spring Boot yêu cầu builder nào cho RestClient, RestTemplate và WebClient để có observation?
6. Khi nào cần tùy biến ClientRequestObservationConvention?
7. Vì sao WebClient dùng convention interface ở package khác RestClient?
8. Nếu mọi request đi qua proxy, client.name mặc định phản ánh điều gì?
9. Làm sao map nhiều instance host về một logical service?
10. Timeout không có HTTP response được biểu diễn thế nào trong client observation?
11. client.name có thay thế traceId/spanId không?
12. Cần kiểm tra gì khi có metrics nhưng không có client spans?

## Tài liệu tham khảo

- [Spring Boot 3.5 — HTTP Client Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 4.0 — HTTP Client Metrics](https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html)
- [Spring Framework — HTTP Client Instrumentation](https://docs.spring.io/spring/reference/7.0/integration/observability.html)
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
- [Micrometer Observation — Concepts](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)

