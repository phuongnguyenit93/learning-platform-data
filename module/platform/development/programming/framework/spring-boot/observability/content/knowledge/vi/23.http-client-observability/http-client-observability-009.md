# Status và outcome của HTTP client trong Spring Boot

Trong chương **HTTP client observability** của module **SPRING_BOOT_OBSERVABILITY**, status và outcome là hai thông tin liên quan nhưng không đồng nghĩa khi đo các lời gọi HTTP đi ra từ ứng dụng. **HTTP status** là mã phản hồi mà server trả về, chẳng hạn 200, 404 hoặc 503. **Outcome** là cách instrumentation phân loại kết quả của thao tác client để tổng hợp metrics và điều tra hành vi ứng dụng. Một lời gọi có thể không nhận được HTTP response nào, vì vậy không có status nhưng vẫn có outcome lỗi.

Spring Boot có thể instrument HTTP client requests thông qua Micrometer Observation và các integration phù hợp với RestClient, RestTemplate hoặc WebClient. Các observation thường cung cấp những dimension như method, URI template, client name, status, outcome và exception tùy stack/version. Phân biệt status với outcome giúp dashboard thể hiện đúng tỷ lệ lỗi, tránh hiểu nhầm rằng mọi request hoàn tất ở tầng HTTP đều là thành công nghiệp vụ.

Trong module **SPRING_BOOT_OBSERVABILITY**, HTTP client metrics cần được liên kết với logs và distributed tracing để điều tra dependency chậm, lỗi downstream và hành vi retry. Bài này đi từ semantics status/outcome tới cách Micrometer tạo observations, cách xử lý lỗi transport, retry, cardinality và kiểm thử kết quả.

## 1. HTTP status và client outcome khác nhau thế nào?

HTTP status mô tả phản hồi giao thức HTTP. Outcome mô tả kết quả quan sát ở góc nhìn của client. Ví dụ:

| Tình huống | HTTP status | Client outcome khái niệm | Có response? |
| --- | ---: | --- | --- |
| Server trả dữ liệu thành công | 200 | Thành công | Có |
| Server tạo tài nguyên | 201 | Thành công | Có |
| Server chuyển hướng | 302 | Redirect | Có |
| Tài nguyên không tồn tại | 404 | Client error | Có |
| Request bị giới hạn | 429 | Client error | Có |
| Server tạm thời không khả dụng | 503 | Server error | Có |
| DNS không resolve được | Không có | Lỗi transport | Không |
| TCP connection refused | Không có | Lỗi transport | Không |
| TLS handshake thất bại | Không có | Lỗi transport/TLS | Không |
| Client timeout trước khi nhận response | Không có | Timeout/transport error | Không |

Một số integration có thể biểu diễn outcome bằng nhóm SUCCESS, CLIENT_ERROR, SERVER_ERROR, REDIRECTION, UNKNOWN hoặc enum/label khác tùy phiên bản. Không hardcode tên label trước khi kiểm tra convention và metric output của stack đang chạy.

Điểm quan trọng: **status là thuộc tính của HTTP response; outcome là phân loại kết quả quan sát của client operation**. Với DNS failure hoặc timeout trước response, status có thể là giá trị fallback như CLIENT_ERROR, IO_ERROR, UNKNOWN hoặc không được ghi tùy implementation; exception/error signal mới là bằng chứng rõ hơn về loại lỗi.

## 2. Vì sao cần cả status và outcome?

Chỉ nhìn status có thể bỏ sót lỗi không nhận được response. Chỉ nhìn outcome có thể mất chi tiết phân loại HTTP cụ thể. Kết hợp hai chiều giúp trả lời:

- Downstream đang trả 4xx hay 5xx?
- Client có bị timeout hoặc không kết nối được trước khi nhận response không?
- Lỗi tập trung ở một dependency hay nhiều dependency?
- Retry có làm tăng số lần gọi downstream không?
- Một HTTP 404 là kết quả nghiệp vụ mong đợi hay lỗi cần alert?

Ví dụ:

```text
HTTP client observation
  method = GET
  uri = /inventory/{sku}
  client.name = inventory-service
  status = 503
  outcome = SERVER_ERROR
  exception = none
```

Một trường hợp khác:

```text
HTTP client observation
  method = GET
  uri = /inventory/{sku}
  client.name = inventory-service
  status = none / fallback
  outcome = transport error
  exception = ConnectException
```

Các giá trị trong hai ví dụ là minh họa semantics, không phải cam kết chính xác về tên tag của mọi phiên bản. Instrumentation có thể dùng status fallback hoặc lưu exception tag riêng khi không có HTTP response. Hãy xem metric/observation thực tế.

## 3. Phân loại HTTP status theo nhóm

| Nhóm | Dải | Ý nghĩa chung | Góc nhìn client |
| --- | --- | --- | --- |
| 1xx | 100–199 | Informational | Thông tin trung gian của protocol |
| 2xx | 200–299 | Successful | Server xử lý request thành công ở tầng HTTP |
| 3xx | 300–399 | Redirection | Cần chuyển hướng hoặc dùng response redirect |
| 4xx | 400–499 | Client error | Request không được xử lý như mong đợi theo semantics server |
| 5xx | 500–599 | Server error | Server/proxy gặp lỗi khi xử lý request |

Không nên gom tất cả status 4xx thành lỗi hệ thống. 404 có thể là kết quả tìm kiếm hợp lệ; 409 có thể là conflict nghiệp vụ; 429 có thể báo rate limit và cần backoff. Tương tự, 5xx thường đáng chú ý nhưng cần phân biệt lỗi tạm thời, lỗi cấu hình và lỗi upstream proxy.

Một số client tự xử lý redirect hoặc retry trước khi observation kết thúc. Khi đó status cuối cùng mà instrumentation quan sát có thể khác status của response trung gian. Nếu cần biết cả redirect chain hoặc từng attempt, cần instrumentation/logging bổ sung có chủ đích.

## 4. Outcome không phải lúc nào cũng suy ra chỉ từ status

Outcome thường được convention suy ra từ response status khi response tồn tại. Tuy nhiên, semantics của client operation còn phụ thuộc lỗi xảy ra ở giai đoạn nào:

1. **Trước khi gửi request:** URL invalid, lỗi cấu hình hoặc serialization.
2. **Trong lúc kết nối:** DNS, TCP, proxy hoặc TLS failure.
3. **Trong lúc gửi/đọc:** connection reset, socket timeout, response body decode failure.
4. **Sau khi nhận response:** HTTP status 4xx/5xx, body parsing hoặc business validation.
5. **Sau retry:** một attempt lỗi nhưng attempt cuối thành công.

Ví dụ một request nhận status 200 nhưng JSON response không hợp lệ. Ở tầng HTTP, response status là success; ở tầng client decoding/business operation, thao tác có thể thất bại. Không tự thay status 200 thành 500 trong HTTP client metrics nếu server thực sự trả 200. Hãy ghi exception/operation outcome riêng để phản ánh lỗi decode.

Ngược lại, status 404 không nhất thiết là lỗi kỹ thuật. Nếu client đang kiểm tra tài nguyên có tồn tại hay không, 404 có thể là nhánh nghiệp vụ bình thường. Dashboard cần phân biệt “HTTP client nhận 4xx” với “business operation thất bại”.

## 5. HTTP client observations trong Micrometer

Micrometer Observation cung cấp vòng đời observation cho thao tác client. Các HTTP client integrations của Spring Framework/Spring Boot có thể tạo observation khi gửi request và ghi các key-values liên quan.

Các dimension thường gặp, tùy convention và phiên bản:

| Dimension | Ví dụ | Cách dùng |
| --- | --- | --- |
| Method | GET, POST | Phân nhóm theo HTTP method |
| URI | /products/{productId} | Route/path template ổn định |
| Client name | catalog-service | Nhận diện dependency |
| Status | 200, 404, 503 hoặc fallback | Mã phản hồi/fallback theo integration |
| Outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR hoặc enum tương ứng | Phân loại tổng quát |
| Exception | ConnectException, SocketTimeoutException hoặc none | Loại lỗi đã chuẩn hóa |

Tên observation và tag keys có thể khác giữa Spring Boot/Spring Framework/Micrometer versions và giữa client implementations. Ví dụ metric HTTP client thường được biểu diễn bằng timer như http.client.requests ở các stack hỗ trợ, nhưng cần xác nhận qua Actuator/registry thay vì giả định.

### Low-cardinality và high-cardinality

Status, method, outcome, client name và URI template thường phù hợp làm metric dimensions nếu các giá trị được kiểm soát. Exception class cũng cần kiểm soát để không tạo vô số giá trị do proxy-generated class hoặc exception name tùy biến.

Không đưa các giá trị sau vào metric tags:

- Raw URL hoặc raw path chứa ID.
- Query string hoặc request body.
- Correlation ID, Trace ID, Span ID.
- Exception message nguyên văn.
- Header tùy ý từ caller.

Thông tin chi tiết cho một request nên nằm ở structured logs hoặc trace attributes theo chính sách dữ liệu, không nằm trong metric labels.

## 6. Ví dụ RestClient trong Spring Boot

Spring Framework RestClient là HTTP client đồng bộ. Với builder được Spring Boot quản lý và observation support được cấu hình, client request có thể được instrument tự động.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
```

Khi sử dụng builder auto-configured của Spring Boot, observation registry/convention có thể được kết nối theo cấu hình framework. Nếu tự tạo client/builder độc lập, không nên giả định observation instrumentation được bật giống builder do Boot cung cấp. Kiểm tra đúng version và customizer của ứng dụng.

Ví dụ gọi client:

```java
CatalogItem item = catalogClient.get()
        .uri("/products/{productId}", productId)
        .retrieve()
        .body(CatalogItem.class);
```

URI template /products/{productId} giúp instrumentation có cơ hội ghi route ổn định thay vì raw identifier. Nếu truyền một URI đã được dựng thành chuỗi chứa product ID, tùy client/convention, tag URI có thể bị cardinality cao; hãy xác minh output.

## 7. RestTemplate và WebClient

RestTemplate là client đồng bộ lâu đời, còn WebClient hỗ trợ reactive/non-blocking. Spring Boot có thể cấu hình observation cho các builder/client được quản lý phù hợp.

### RestTemplate

```java
RestTemplate restTemplate = restTemplateBuilder.build();

CatalogItem item = restTemplate.getForObject(
        "http://catalog-service/products/{productId}",
        CatalogItem.class,
        productId);
```

Dùng RestTemplateBuilder được Spring Boot inject để nhận các customizers/observation configuration đã áp dụng. Nếu tạo new RestTemplate() trực tiếp, các customizer và instrumentation của Boot có thể không được áp dụng.

### WebClient

```java
WebClient webClient = webClientBuilder
        .baseUrl("http://payment-service")
        .build();

Mono<PaymentResult> result = webClient.post()
        .uri("/payments/{paymentId}/authorize", paymentId)
        .retrieve()
        .bodyToMono(PaymentResult.class);
```

Với WebClient, observation bao quanh quá trình subscribe/execute theo reactive lifecycle. Tạo publisher nhưng không subscribe có thể chưa phát sinh request. Cần quan sát đúng thời điểm request thật sự chạy; không đo số lần tạo Mono như số lần gọi HTTP.

Các builder nên được cấu hình theo cơ chế Spring Boot/Spring Framework của phiên bản đang dùng. Đừng thêm interceptor tự viết tạo timer trùng với observation tự động nếu mục tiêu chỉ là metrics HTTP client cơ bản.

## 8. Exception và status khi không có response

Khi DNS/TCP/TLS/timeout lỗi trước khi response được nhận, không có HTTP status để phân loại. Client integration thường kết thúc observation với exception/error signal và một status fallback tùy convention.

Ví dụ:

```java
try {
    return catalogClient.get()
            .uri("/products/{productId}", productId)
            .retrieve()
            .body(CatalogItem.class);
} catch (ResourceAccessException ex) {
    log.warn("Catalog service is unreachable", ex);
    throw ex;
}
```

ResourceAccessException là ví dụ ở một số Spring synchronous client paths; loại exception thực tế phụ thuộc client implementation. WebClient có thể phát các exception khác, và lỗi decode có thể xảy ra sau khi response đã nhận. Không viết dashboard chỉ dựa vào một exception class duy nhất cho mọi client.

Exception tag nên là class/type đã chuẩn hóa, không phải message. Message có thể chứa hostname động, URL, query, user input hoặc dữ liệu nhạy cảm, đồng thời tạo cardinality cao.

## 9. Retry ảnh hưởng status và outcome như thế nào?

Retry làm một logical operation có nhiều HTTP attempts. Cần xác định metrics đang đo **mỗi attempt** hay **toàn bộ logical operation**:

```text
Business operation: load product
       |
       +--> Attempt 1: HTTP 503 (server error)
       |
       +--> Attempt 2: connection timeout
       |
       +--> Attempt 3: HTTP 200 (success)
       |
       v
Logical operation: success after 3 attempts
```

Nếu client instrumentation tạo observation cho từng attempt, metrics có thể ghi hai lỗi và một thành công. Business-level metric có thể ghi một logical operation thành công nhưng có retry. Cả hai góc nhìn đều hữu ích:

- HTTP client metrics cho biết tải thật mà dependency nhận và độ ổn định từng attempt.
- Business operation metrics cho biết người dùng/ứng dụng cuối cùng có hoàn thành công việc không.
- Retry metrics cho biết số attempt, retry count và exhausted retries.

Không cộng số attempt thành số logical requests. Nếu dashboard cần retry rate, tạo metric riêng với tags hữu hạn như dependency, retry outcome và policy name đã chuẩn hóa. Không gắn request ID hoặc exception message vào metric.

### Retry có thể che giấu dependency degradation

Nếu attempt đầu thường xuyên 503 nhưng attempt sau thành công, business success rate có thể vẫn cao trong khi downstream đang suy giảm và latency tăng. Vì vậy cần theo dõi cả status/outcome của client attempts, retry count và logical operation result.

## 10. Redirect, 404 và 429 cần semantics rõ

Không phải mọi non-2xx đều có cùng ý nghĩa:

| Response | Cách hiểu thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| 301/302/307/308 | Redirect | Client có follow redirect? Có tạo thêm attempt/span? |
| 400 | Request không hợp lệ | Lỗi client code hay dữ liệu đầu vào hợp lệ bị từ chối? |
| 401/403 | Authentication/authorization | Token/config/permission hay policy dự kiến? |
| 404 | Không tìm thấy | Expected lookup miss hay endpoint sai? |
| 409 | Conflict | Business conflict hay retryable conflict? |
| 429 | Rate limited | Retry-After, backoff và quota |
| 500 | Internal server error | Lỗi ứng dụng downstream |
| 502/503/504 | Gateway/service unavailable/timeout | Proxy, service health và network path |

Dashboard nên hiển thị status code hoặc status class cùng dependency/route để nhóm vận hành tìm nguyên nhân. Alert không nên bắn chỉ vì có bất kỳ 404 nào nếu nghiệp vụ thường xuyên lookup tài nguyên chưa tồn tại.

Với 429, retry ngay lập tức có thể làm tình trạng rate limiting nặng hơn. Dùng backoff/jitter và tôn trọng Retry-After nếu client policy hỗ trợ. Retry phải giới hạn số lần và tổng deadline.

## 11. Liên kết status/outcome với logs và traces

HTTP client observation thường có thể tạo client span khi tracing integration được bật. Trace giúp thấy dependency call nằm ở bước nào của request tổng:

```text
orders-service server span
    |
    +--> order.load
             |
             +--> HTTP GET catalog-service
             |       status=503
             |       outcome=SERVER_ERROR
             |
             +--> retry attempt
                     status=200
                     outcome=SUCCESS
```

Log có cấu trúc có thể ghi:

```json
{
  "service.name": "orders-service",
  "event": "catalog.client.request.failed",
  "dependency": "catalog-service",
  "http.method": "GET",
  "http.route": "/products/{productId}",
  "http.status_code": 503,
  "outcome": "SERVER_ERROR",
  "retry.attempt": 1,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

Ví dụ trên minh họa fields; schema thực tế nên theo semantic conventions đang dùng. Không log raw URL, authorization header hoặc response body không được kiểm soát.

Metrics tổng hợp status/outcome theo dependency và route template; logs giữ event cụ thể; traces biểu diễn quan hệ parent-child và duration. Trace sampling có thể khiến một số request không có trace trong backend, nhưng metrics vẫn cần phản ánh các attempts theo pipeline của nó.

## 12. Xây dashboard và alert cho HTTP client

Một dashboard hữu ích nên chia theo dependency và route template:

| Góc nhìn | Metric/dimension | Câu hỏi |
| --- | --- | --- |
| Request volume | Count theo client name/method/URI template | Dependency nào nhận nhiều calls? |
| Status distribution | Status hoặc status class | Downstream đang trả 4xx/5xx? |
| Outcome | Success/error/redirect/unknown theo convention | Tổng thể client operation diễn biến ra sao? |
| Latency | Timer histogram, p50/p95/p99 | Dependency nào chậm? |
| Transport failures | Exception type đã chuẩn hóa | Có DNS/connect/TLS/timeout? |
| Retry | Attempts, retries, exhausted | Retry đang che giấu lỗi hay tạo tải? |

Alert nên dựa trên tỷ lệ và thời lượng trong cửa sổ đủ dài, tránh alert chỉ vì một response 404. Ví dụ:

- Tỷ lệ 5xx từ dependency vượt ngưỡng trong vài phút.
- Timeout rate tăng đồng thời với p95 latency.
- Retry exhausted tăng hoặc retry attempts/request vượt mức.
- Một dependency không có response thành công trong một cửa sổ thời gian.

Các metric names, labels và query language phụ thuộc registry/backend. Không sao chép query PromQL/Datadog chỉ từ tên tag phỏng đoán; kiểm tra series thực tế và semantics của counter/timer.

## 13. Kiểm thử status và outcome

Một test integration nên tạo các phản hồi có status khác nhau và lỗi transport:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Server trả 200 | Status và outcome success theo convention |
| Server trả 302 | Redirect được biểu diễn như mong đợi; xác định follow behavior |
| Server trả 404 | Status 404; business layer quyết định expected hay failure |
| Server trả 429 | Status/outcome và retry/backoff behavior |
| Server trả 503 | Status/outcome server error |
| Port không lắng nghe | Không có response status; exception/transport failure được ghi |
| DNS host không tồn tại | Không có HTTP response; exception type được chuẩn hóa |
| Client timeout | Timeout được phân biệt với response 504 từ server/proxy |
| Response 200 nhưng body decode lỗi | HTTP status vẫn 200; decode/business error riêng |
| Retry 503 rồi 200 | Thấy từng attempt và logical operation result riêng |

Không kiểm thử chỉ bằng cách gọi method service và assert exception. Cần xác minh observation/registry đã nhận đúng measurements, tags không chứa raw URL, và tracing/log correlation không bị ảnh hưởng.

## 14. Bài tập tình huống

Một ứng dụng gọi inventory-service qua HTTP client. Dashboard cho thấy:

- HTTP 5xx thấp.
- Client timeout tăng.
- Business operation success rate vẫn cao.
- Retry attempts/request tăng từ 1,0 lên 2,8.

Nhóm vận hành kết luận dependency đang khỏe vì tỷ lệ HTTP 5xx thấp.

**Câu hỏi:**

1. Vì sao HTTP 5xx thấp không chứng minh client dependency khỏe?
2. Timeout trước response được thể hiện bằng status nào?
3. Vì sao business success rate vẫn cao khi dependency đang suy giảm?
4. Cần dashboard những dimensions/metrics nào để phát hiện tình trạng này?
5. Nên phân biệt attempt outcome với logical operation outcome ra sao?

**Gợi ý phân tích:**

- Timeout trước khi nhận response không có HTTP status. Nó có thể được ghi qua exception/outcome fallback và cần transport failure metrics.
- Retry có thể khiến attempt đầu lỗi nhưng attempt sau thành công, làm business operation cuối cùng vẫn success.
- Theo dõi HTTP client latency, exception type, timeout rate, retry attempts, retry exhausted và status/outcome theo dependency/route template.
- Instrumentation có thể ghi mỗi attempt riêng; business layer ghi logical operation một lần. Không cộng hai loại counter như cùng semantics.
- Đặt deadline tổng, retry budget, backoff/jitter và alert khi retry tăng để tránh tạo tải bổ sung lên dependency.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| HTTP status | Mã response 1xx–5xx |
| Client outcome | Phân loại kết quả thao tác client, có thể không có response |
| Transport error | DNS/TCP/TLS/timeout không có status HTTP |
| Micrometer Observation | Biết HTTP client observation và convention |
| Spring clients | Phân biệt RestClient, RestTemplate, WebClient |
| Cardinality | Dùng URI template và exception type đã chuẩn hóa |
| Retry | Phân biệt attempt với logical operation |
| 3xx/4xx/5xx | Hiểu semantics theo dependency/business |
| Logs/traces | Liên kết status/outcome với trace và log fields |
| Dashboard/alerts | Theo dõi latency, error, timeout và retry |
| Integration tests | Kiểm tra response, transport failure và retry |

**Ghi nhớ:** HTTP status mô tả response mà client nhận được; outcome phân loại kết quả của thao tác client và vẫn cần thiết khi không có response do DNS, TCP, TLS hoặc timeout. Micrometer HTTP client observations có thể ghi method, URI template, dependency, status, outcome và exception theo convention/version. Theo dõi cả status lẫn transport errors, phân biệt mỗi retry attempt với logical operation, giữ tags ở cardinality thấp và liên kết metrics với logs/traces để hiểu đầy đủ độ khỏe của downstream service.
