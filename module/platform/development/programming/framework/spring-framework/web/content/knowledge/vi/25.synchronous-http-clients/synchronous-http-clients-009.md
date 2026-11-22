# RestTemplate trong hệ thống sẵn có và chuyển dần sang RestClient — deprecation từ Spring Framework 7

> **Phạm vi:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+ cho ví dụ có thể chạy; có đối chiếu thông báo deprecation ở Spring Framework **7.0** và kế hoạch annotation Java `@Deprecated` ở **7.1**. Bài học tập trung vào **hệ thống đang sử dụng RestTemplate**: thời điểm nên giữ, những khả năng tái sử dụng, hai bước chuyển sang RestClient, tương đương phương thức gọi, khác biệt trong lỗi/status, kiểm thử hồi quy, timeouts, connection pool, auth và kế hoạch rollout/rollback. Không đề xuất chuyển sang WebClient chỉ vì RestTemplate cũ: cả RestTemplate và RestClient đều là HTTP client **đồng bộ**.

## 1. Nắm đúng thông báo “deprecated từ Spring 7”

### 1.1. Mốc phiên bản cần phân biệt

| Phiên bản | Trạng thái RestTemplate | Việc nên làm |
| --- | --- | --- |
| Spring Framework 6.0 | RestTemplate tiếp tục được hỗ trợ; chưa có RestClient | Duy trì, bảo đảm request factory/timeouts |
| Spring Framework 6.1 | RestClient xuất hiện, API fluent đồng bộ | Có thể bắt đầu migration song song |
| Spring Framework 6.2 / Spring Boot 3.5 | RestTemplate còn hoạt động; RestClient là API ưu tiên cho code sync mới | Chuyển dần module có kiểm thử |
| Spring Framework 7.0 | **Deprecated theo tài liệu/reference và release notes**; khuyến nghị RestClient | Tránh viết RestTemplate mới; lập roadmap migration |
| Spring Framework 7.1 (dự kiến phát hành sau tháng 10/2026) | **Kế hoạch** gắn Java `@Deprecated` cho RestTemplate và các loại liên quan | Xác minh Javadoc của phiên bản 7.1 thực sự dùng trước khi dựa vào compiler warning |
| Spring Framework 8.0 (chưa định ngày) | Spring công bố **kế hoạch loại bỏ** RestTemplate | Không chờ đến lúc nâng phiên bản mới bắt đầu chuyển |

Spring Team công bố kế hoạch vào ngày 30/09/2025. Release notes Spring 7.0 làm rõ: deprecation đã ở tài liệu 7.0, còn Java annotation `@Deprecated` được dự kiến ở 7.1; removal dự kiến cho 8.0. **Đừng ghi “RestTemplate bị xóa từ Spring 7” hoặc “Spring 7.0 bắt buộc compiler warning”**. Đây là hai khẳng định sai.

Theo kế hoạch công khai của Spring, thời điểm chính xác cho 7.1/8.0 có thể thay đổi. Đừng suy từ tài liệu SNAPSHOT rằng một phiên bản chưa phát hành đã là release ổn định.

Nguồn chính thức:
- [Spring Framework 7.0 Release Notes — Deprecations](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes).
- [The state of HTTP clients in Spring — Spring Blog, 30/09/2025](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/).
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html).

### 1.2. Deprecated không có nghĩa phải rewrite ngay

Với hệ thống đang chạy, câu hỏi đúng không phải “xóa RestTemplate hôm nay?”, mà là:
- Có bao nhiêu call sites và khả năng test?
- Đang dùng `ClientHttpRequestFactory`/Apache HttpClient/JDK client nào?
- Có custom `ResponseErrorHandler`, `ClientHttpRequestInterceptor`, `HttpMessageConverter`, `UriTemplateHandler` hoặc certificate/pool config?
- Có lịch nâng Spring Framework 7/8 hay thay đổi JDK?
- Business endpoints có retry, 404 semantics, timeout và auth riêng?
- Có thể chuyển từng service/client bean với compatibility tests mà không thay hành vi bên ngoài không?

Một RestTemplate đã được cấu hình và giám sát tốt **có thể tiếp tục được sử dụng khi migration từng bước**. Nhưng tạo thêm mã RestTemplate mới trong hệ Spring 6.2+ làm tăng số call sites phải chuyển trong tương lai. Với HTTP đồng bộ **mới**, nên chọn RestClient.

## 2. Vì sao RestClient thay RestTemplate?

RestTemplate là API kiểu template-method từ Spring 3.0:

```java
Item item = restTemplate.getForObject(
        "/items/{id}", Item.class, 7L);

ResponseEntity<Item> response = restTemplate.getForEntity(
        "/items/{id}", Item.class, 7L);
```

RestClient có API fluent từ Spring Framework 6.1:

```java
Item item = restClient.get()
        .uri("/items/{id}", 7L)
        .retrieve()
        .body(Item.class);

ResponseEntity<Item> response = restClient.get()
        .uri("/items/{id}", 7L)
        .retrieve()
        .toEntity(Item.class);
```

Các đoạn trên là **snippets**, cần khai báo clients, `Item` và base URL. **Cả hai vẫn synchronous/blocking ở caller** khi thực hiện exchange. Lợi ích chính của RestClient là builder fluent, cấu hình status handler theo request và dễ mở rộng API ở tầng cao; **không tự chuyển request thành reactive I/O**.

### 2.1. Cơ sở hạ tầng chung giúp migration nhỏ

RestTemplate và RestClient cùng sử dụng:
- `ClientHttpRequestFactory` (chọn HTTP transport, timeout/connection behavior);
- `HttpMessageConverter<?>` (JSON, String, byte[], form, Resource);
- `ClientHttpRequestInterceptor`;
- `ClientHttpRequestInitializer`;
- `UriBuilderFactory`/URI template handling;
- cơ chế error mapping, với adapter hỗ trợ tái sử dụng `ResponseErrorHandler`.

Vì vậy Spring cung cấp `RestClient.create(existingRestTemplate)` và `RestClient.builder(existingRestTemplate)` để khởi tạo client **dựa trên cấu hình đã có**.

```java
RestClient newClient = RestClient.create(restTemplate);
// Hoặc nếu muốn tùy chỉnh thêm trước khi build:
RestClient customized = RestClient.builder(restTemplate)
        .defaultHeader("Accept", "application/json")
        .build();
```

Từ Spring Framework 6.1, overload này lấy cấu hình cũ như request factory, converters, interceptors, initializers, URI builder factory và error handler. Đây là **lợi thế migration lớn nhất**: bạn có thể chuyển **cách gọi API** trước, rồi cải tổ **cách dựng client** sau. Không nhất thiết thay pool/certificates/cookie/auth cùng lúc.

### 2.2. Cái gì không được hứa tự tương đương?

Tái sử dụng cấu hình không miễn phí cho mọi behavior:
- Status/error handling với `RestClient.retrieve()` khác `RestClient.exchange(...)`; cần xem bên dưới.
- Một request converter hoặc custom interceptor có thể phụ thuộc header order/body buffering.
- URI template vs URI builder, percent encoding, slash, query params có thể đổi nếu bạn thay base URL/builder trong khi migrate.
- Method GET/HEAD/POST và body extraction phải được thay bằng terminal operation chính xác.
- Multipart/form payload, download dạng streaming, ETag, content-length và redirects cần tests riêng.
- Cấu hình shared mutable ở `RestTemplate` không nên được sửa khi đang phục vụ requests; RestClient.create(template) không biến việc mutate này thành thread-safe.
- TLS/proxy pool/client library phải được kiểm tra ở environment thật, không chỉ mock.
- Không mặc định mọi custom `ResponseErrorHandler` đều tương đương với request-specific `onStatus` khi bạn thay cấu hình.

**Mục tiêu:** giữ wire contract với downstream ổn định, không “đổi API rồi tiện tay rewrite luôn retries/errors/auth”.

## 3. Kế hoạch migration hai giai đoạn

### Giai đoạn A — giữ hạ tầng, chuyển call sites

1. Đánh dấu các nhóm RestTemplate theo downstream: catalog, pricing, identity, payments; ghi nhận base URL, interceptors, timeout, error handler.
2. Chọn một nhóm nhỏ có unit/integration tests tốt.
3. Tạo RestClient từ **bean RestTemplate cũ** bằng `RestClient.create(template)` hoặc `builder(template)`.
4. Thay `getForObject/getForEntity/exchange/postForEntity/...` bằng chain RestClient tương đương, **không** thay request factory/pool/auth cùng lúc.
5. So sánh URI, method, headers, request body, JSON mapping, status/exceptions và latency với tests.
6. Đưa lên staging, canary, đo 4xx/5xx, pool wait, timeout và correlation IDs.
7. Rollback bằng route hoặc cấu hình chọn implementation nếu có regression.

```text
Legacy endpoints                  New endpoints
       |                                 |
 RestTemplate ----------------> RestClient.create(template)
       |                         (config lấy từ template)
       +------------+--------------------+
                    |
       same request factory / interceptors /
       URI builder / message converters / error handler
                    |
                HTTP transport
                    |
               Downstream API
```

Trên giai đoạn này, có thể giữ song song RestTemplate và RestClient đã dựng. Đừng xóa legacy bean trước khi chắc chắn không còn consumer. Về tài nguyên, cần kiểm tra chúng có chia sẻ request factory/pool như mong muốn, không tạo nhiều HTTP clients độc lập gây tăng connections.

### Giai đoạn B — thay cách cấu hình khi call sites đã ổn

Khi toàn bộ service methods đã dùng RestClient:
1. Dựng `RestClient.Builder` riêng với `baseUrl`, `requestFactory`, `messageConverters`, `requestInterceptors` và `defaultStatusHandler` theo nhu cầu.
2. Dùng config của Spring Boot `RestClient.Builder` nếu phù hợp để không mất customization/observability.
3. Di chuyển custom error handler sang status-handler fluent API đã test.
4. Xóa RestTemplate bean khi không còn consumers; gỡ adapter chỉ phục vụ migration.
5. Rà soát dependency và Java/Spring version trước khi nâng Spring Framework 7.x/8.x.
6. Giữ các tests đã tạo làm **regression contract**, không chỉ code compilation.

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .requestFactory(configuredRequestFactory)
        .requestInterceptor(configuredTracingInterceptor)
        .defaultStatusHandler(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException("Remote service failure");
                })
        .build();
```

**Snippet** minh họa API builder, cần khai báo request factory và interceptor. Production nên dùng typed exception và không nuốt upstream status/body cần monitoring. Nếu Spring Boot cung cấp builder được customizer cấu hình, tránh tạo `RestClient.builder()` tùy tiện và vô tình bỏ qua SSL/observability từ Boot.

## 4. Phương thức tương đương: RestTemplate → RestClient

| RestTemplate cũ | RestClient mới (trong Spring 6.2) | Lưu ý |
| --- | --- | --- |
| `getForObject(url, Dto.class, id)` | `get().uri(url,id).retrieve().body(Dto.class)` | DTO có thể null nếu không có body |
| `getForEntity(url, Dto.class, id)` | `get().uri(url,id).retrieve().toEntity(Dto.class)` | Lấy status/headers |
| `postForObject(url, request, Dto.class)` | `post().uri(url).body(request).retrieve().body(Dto.class)` | Kiểm tra Content-Type/JSON |
| `postForEntity(url, request, Dto.class)` | `post().uri(url).body(request).retrieve().toEntity(Dto.class)` | Đọc Location/status 201 |
| `put(url, request, id)` | `put().uri(url,id).body(request).retrieve().toBodilessEntity()` | Trả ResponseEntity<Void>, method caller có thể bỏ result |
| `delete(url, id)` | `delete().uri(url,id).retrieve().toBodilessEntity()` | Không đòi body trên 204 |
| `exchange(url,GET,...,ParameterizedTypeReference)` | `get().uri(url).retrieve().toEntity(ParameterizedTypeReference)` | Giữ generic type |
| `exchange(url,PUT/POST,HttpEntity,...)` | `method(HttpMethod.X).uri(...).headers(...).body(...).retrieve()...` | Headers/body phải tách đúng |
| `headForHeaders(url,id)` | `head().uri(url,id).retrieve().toBodilessEntity().getHeaders()` | HEAD có headers, không body |
| `execute(url, method, callback, extractor)` | `exchange((request,response)->...)` | **Tự** xử lý status/body/cleanup đúng |
| `setErrorHandler(handler)` | `RestClient.builder(template)` giữ handler; về sau `defaultStatusHandler(...)` | Status override/order cần test |

Các biểu thức trong bảng là **mapping patterns**, không phải một thay thế text-to-text có thể áp dụng vô điều kiện cho mọi overload. Một số methods trả kết quả khác kiểu (ví dụ delete/put cũ là `void`, chain RestClient trả ResponseEntity<Void>); thay call sites sao cho không ảnh hưởng service API contract.

### 4.1. GET với URI template

**Trước:**

```java
ItemView item = restTemplate.getForObject(
        "/items/{id}", ItemView.class, itemId);
```

**Sau:**

```java
ItemView item = restClient.get()
        .uri("/items/{id}", itemId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ItemView.class);
```

`.uri("/items/{id}", ...)` dùng URI template, không tự ghép string bằng input có thể chứa slash/space. Nếu path variable có constraint numeric, validate từ domain layer. URI encoding giữa hai API/cấu hình URI factory cần regression test; không cho client cung cấp absolute target URI tùy ý vì SSRF.

### 4.2. Lấy status và headers

**Trước:**

```java
ResponseEntity<ItemView> response =
        restTemplate.getForEntity("/items/{id}", ItemView.class, id);
```

**Sau:**

```java
ResponseEntity<ItemView> response = restClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .toEntity(ItemView.class);
```

Dùng `ResponseEntity` khi cần `ETag`, `Last-Modified`, `Location`, status 204/206 hoặc headers nghiệp vụ. Với `retrieve()`, 4xx/5xx mặc định ném `RestClientResponseException` trừ status handlers đã custom.

### 4.3. POST và Location

```java
record CreateItem(String name) {}

ResponseEntity<ItemView> created = restClient.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateItem("Spring"))
        .retrieve()
        .toEntity(ItemView.class);

URI location = created.getHeaders().getLocation();
```

Mã trên là snippet, cần RestClient bean, DTO và imports. Nếu server tạo 201 nhưng không trả body, `created.getBody()` có thể null; đừng ném NPE. Khi Location tương đối, không tin raw remote header để redirect browser ngoài trust boundary.

### 4.4. PUT, PATCH và DELETE

```java
ResponseEntity<Void> updated = restClient.put()
        .uri("/items/{id}", id)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new UpdateItem("Renamed"))
        .retrieve()
        .toBodilessEntity();

ResponseEntity<Void> deleted = restClient.delete()
        .uri("/items/{id}", id)
        .retrieve()
        .toBodilessEntity();
```

Snippet cần DTO. Nếu server trả 204, response không body, đó là expected; đừng cố `body(ItemView.class)` cho 204. PATCH cần request factory/underlying HTTP transport thực sự hỗ trợ method PATCH, không chỉ code compile; test lại nếu legacy RestTemplate đã dùng custom Apache HttpClient factory.

### 4.5. Danh sách generic

```java
List<ItemView> items = restClient.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ItemView>>() {});
```

Không dùng `List.class` rồi cast list elements thành ItemView — JSON decoder có thể trả Map vì mất generic type. Chính xác tương đương với `RestTemplate.exchange(..., new ParameterizedTypeReference<List<ItemView>>() {})`.

### 4.6. Query params, headers và authentication

```java
ItemView item = restClient.get()
        .uri(builder -> builder
                .path("/items/{id}")
                .queryParam("lang", "vi")
                .build(id))
        .headers(headers -> {
            headers.setBearerAuth(validAccessToken);
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .retrieve()
        .body(ItemView.class);
```

Snippet cần `validAccessToken`. Client credentials/service identity phải lấy từ OAuth2/trusted provider; không tự chuyển toàn bộ user bearer token sang bất kỳ upstream nào. Tránh đưa token vào URL/query hoặc exception logs. Khi migrate interceptors, kiểm tra có vô tình đặt hai Authorization headers hay lặp tracing headers.

## 5. Điểm dễ sai: retrieve() khác exchange()

### 5.1. RestClient retrieve()

```java
ItemView item = restClient.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .body(ItemView.class);
```

`retrieve()` chọn high-level API; phép thực hiện exchange thường xảy ra ở terminal `body(...)`, `toEntity(...)`, `toBodilessEntity()`. Với status 4xx/5xx, mặc định RestClient ném exception. Có thể custom trên request:

```java
ItemView item = restClient.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new ItemMissingException("not found");
                })
        .body(ItemView.class);
```

Đây là snippet; `ItemMissingException` phải được định nghĩa. Status predicate chỉ match 404; mặc định 500 vẫn thành server exception nếu không thay các default handlers. Không ném `RuntimeException` tùy tiện làm mất ngữ nghĩa status nếu API cần phân biệt auth, 404 và transient errors.

### 5.2. RestClient exchange() không dùng retrieve status handlers

```java
ResponseEntity<String> raw = restClient.get()
        .uri("/items/{id}", 7)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            if (status.isError()) {
                throw new IllegalStateException("Upstream HTTP error");
            }
            String body = new String(
                    response.getBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            return ResponseEntity.status(status).body(body);
        });
```

Snippet có imports `StandardCharsets`, `HttpStatusCode` và `ResponseEntity`; ví dụ chỉ đọc body nhỏ, không dùng `readAllBytes()` với response lớn/stream vô hạn. **Quan trọng:** `exchange(...)` **không áp dụng** `onStatus` và `defaultStatusHandler` dành cho `retrieve()`, vì người gọi phải kiểm soát response. Nếu code RestTemplate cũ dùng `execute(...,ResponseExtractor)` để stream file, migration bằng `RestClient.exchange(...)` cần kiểm thử quản lý input stream và tài nguyên trước khi trả khỏi callback.

### 5.3. RestTemplate error handler được carry over

```java
RestTemplate template = new RestTemplate();
// Đã cấu hình template.setErrorHandler(customHandler) nếu cần.
RestClient restClient = RestClient.create(template);
```

Theo Javadoc Spring, overload này **dựa trên** template cũ gồm error handler. Khi tạo RestClient mới từ template đã có `ResponseErrorHandler`, hãy kiểm thử với 400, 404, 429, 500:
- Error handler có throw đúng exception subtype không?
- Có đọc response body làm mất dữ liệu để decoder dùng tiếp không?
- Behavior có khác giữa `retrieve` và `exchange`?
- Handler có lộ PII hay token không?

Đừng đồng thời đăng ký default status handlers mới và cũ mà không kiểm tra order: policy có thể bị override hoặc xử lý hai lần không mong muốn.

### 5.4. Mất dữ liệu khi body rỗng

`RestTemplate.getForObject(...)` và `RestClient.retrieve().body(...)` có thể trả null nếu 2xx không body. `toEntity(Dto.class)` giúp lấy status/headers kể cả body null. Nếu service contract yêu cầu item phải có, validate null rõ trước khi dereference và quyết định exception nghiệp vụ.

## 6. Chiến lược xử lý HTTP status khi chuyển

| HTTP / tình huống | Hành vi nên kiểm tra |
| --- | --- |
| 200 JSON object | Body decode đúng DTO |
| 201 Created | Status, Location, body tùy downstream |
| 202 Accepted | Có thể là tác vụ async phía server; không coi 202 là completed |
| 204 No Content | Không dereference null body |
| 206 Partial Content | Range/content headers và body streaming semantics |
| 301/302/307/308 | Redirect được HTTP transport xử lý thế nào, có giữ method/token không? |
| 304 Not Modified | ETag/cache logic, không expect body |
| 400 Validation | Trả lỗi domain phù hợp, không nuốt lỗi |
| 401/403 | Auth/permission; không retry mù |
| 404 | Resource thiếu hay upstream misconfiguration tùy business |
| 409/412 | Conflict/precondition failure, optimistic lock |
| 429 | Rate-limit/Retry-After, có giới hạn retry |
| 500/502/503/504 | Server/downstream failure; logging, timeout, circuit breaker |
| Timeout/DNS/TLS failure | I/O exception, không nhất thiết có HTTP status |
| JSON malformed | Message conversion exception, khác HTTP status |
| Response body quá lớn | Giới hạn read/buffering, test memory/OOM |

**Không “catch mọi RestClientException rồi trả 404”.** Exception transport khác status error, và upstream 404 không mặc định bằng resource 404 của API facade.

### 6.1. RestClientException là umbrella type

Một số nhóm thường gặp:
- `RestClientResponseException` và subclasses: server có HTTP response lỗi, exception giữ status/headers/body nếu được capture.
- `ResourceAccessException`: I/O errors, connect/read timeout, DNS/socket issues.
- `UnknownContentTypeException`/message conversion failures: không giải mã được representation.
- Custom exception từ `onStatus`/domain layer.

Từng phiên bản/library có subtype cụ thể khác. Đừng chỉ assert exact class cho mọi lỗi network trong integration tests; assert status, cause category và behavior cần thiết. Khi log, không in raw upstream body chứa personal data.

### 6.2. Retry có điều kiện

Với synchronous HTTP client, retry thông qua policy tầng service hoặc resilience layer (Spring Retry, Resilience4j…) khi đã thêm dependencies/config và xác định request idempotency. Không viết vòng `while(true)` hoặc retry mọi IOException bất kể POST đã có side effects.

Ví dụ phác thảo logic business (không phải chương trình hoàn chỉnh):

```text
attempt request
  -> success: return
  -> 400/401/403: no retry
  -> 404: theo domain contract, thường no retry
  -> 429: xét Retry-After + budget + jitter
  -> 503/timeouts: chỉ retry khi operation idempotent và còn deadline
  -> exhausted: sanitized error + metrics + tracing
```

Khi client POST payment/create order timeout, server có thể đã commit; retry vô điều kiện sẽ tạo kết quả trùng. Dùng idempotency key, lookup reconciliation hoặc saga/outbox theo nghiệp vụ.

## 7. Cấu hình request factory, timeout và pool

### 7.1. Cấu hình RestTemplate hiện hữu qua Boot

Spring Boot 3.5 có RestTemplateBuilder:

```java
@Bean
RestTemplate catalogTemplate(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://catalog.example.test")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

Snippet cần import `Duration`, `RestTemplateBuilder`. API `connectTimeout/readTimeout` của Boot 3.5 sử dụng Duration. Với Spring Boot cũ, tên method có thể là `setConnectTimeout/setReadTimeout`. Trong Boot 4, kiểm tra package và autoconfiguration mới; không trộn imports Boot 3.5 và 4.

Tạo RestClient giai đoạn A:

```java
@Bean
RestClient catalogRestClient(RestTemplate catalogTemplate) {
    return RestClient.create(catalogTemplate);
}
```

Đây là cách giữ cấu hình template. Tuy nhiên **timeout cần đo thực trên HTTP transport**: connect timeout, socket/read, connection pool lease và overall deadline khác nhau. Read timeout không tự bao DNS/TLS/queue/retry. Mọi trường hợp timeouts cần test với mock HTTP server đáp ứng chậm.

### 7.2. Cấu hình RestClient trực tiếp trong giai đoạn B

```java
@Bean
RestClient catalogClient(RestClient.Builder builder,
                         ClientHttpRequestFactory factory) {
    return builder
            .baseUrl("https://catalog.example.test")
            .requestFactory(factory)
            .build();
}
```

Snippet cần provider bean `factory` do app chọn/config theo transport. Nếu cần Apache HttpClient, hãy kiểm tra dependencies/classpath và `HttpComponentsClientHttpRequestFactory` thực sự được dùng; không mặc định mọi factory có connection pooling mạnh. Timeout/certificates/proxy/compression cấu hình ở **factory/underlying HTTP client** phù hợp.

### 7.3. Những timeout thường bị nhầm

- DNS: resolve hostname; có thể có policy riêng của OS/network/library.
- Connect: mở TCP connection.
- TLS handshake: xác thực certificate và hoàn thành TLS.
- Connection pool acquire: chờ lấy connection rảnh.
- Response/read: đợi server data và đọc bytes.
- Overall deadline: tổng thời gian, gồm redirects/retries/backoff.
- Idle timeout: connection keepalive/pool eviction, không cùng request deadline.

**Không đặt mỗi “3 giây” ở một option rồi kết luận mọi request chắc chắn kết thúc dưới 3 giây.** Phải đo với slow downstream, connection exhaustion, DNS/TLS failure, large responses, retries.

### 7.4. Pool và thread concurrency

RestTemplate/RestClient vẫn chặn caller trong một synchronous exchange. Nếu MVC application có 200 worker threads cùng gọi downstream chậm, có thể giữ 200 threads dù HTTP pool nhỏ hơn. Một pool 20 connections và 200 callers có thể làm 180 callers chờ acquire hoặc lỗi timeout. Cần capacity planning theo:
- inbound RPS/concurrency;
- downstream latency p95/p99;
- max connections, per-route limits và pending queue;
- max servlet threads và scheduled workers;
- rate limiter/bulkhead;
- retries có thể nhân tải.

REST API fluent không tự cấp rate limiting hay non-blocking resource control.

## 8. Message converters, JSON và generic types

RestTemplate và RestClient dùng `HttpMessageConverter`. Nhưng migration có thể làm lộ differences nếu bạn bỏ cấu hình converter cũ.

### 8.1. Converter tùy biến

```java
RestClient client = RestClient.builder()
        .messageConverters(converters -> {
            // Đăng ký custom converter nếu business cần.
            // Tránh xóa converter mặc định vô ý.
        })
        .build();
```

Đây là snippet, không phải cấu hình JSON production. Trong Spring 7, một số APIs converter configuration thay đổi/deprecate; code khóa Spring 6.2 phải đối chiếu Javadoc tương ứng.

### 8.2. Kiểu generic

**Trước:**

```java
ResponseEntity<List<ItemView>> response =
        restTemplate.exchange(
                "/items", HttpMethod.GET, HttpEntity.EMPTY,
                new ParameterizedTypeReference<List<ItemView>>() {});
```

**Sau:**

```java
List<ItemView> items = restClient.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ItemView>>() {});
```

Đây là snippets, cần ItemView DTO và imports. `List.class` chỉ giữ kiểu thô; JSON objects có thể trở thành maps, rồi gây ClassCastException khi dùng như DTO. Với generic wrappers `PageEnvelope<ItemView>`, dùng cùng ParameterizedTypeReference.

### 8.3. Multipart, form và download

Không đơn giản thay `RestTemplate.execute(..., ResponseExtractor)` đọc file lớn bằng `RestClient.retrieve().body(byte[].class)`: cách mới có thể gom toàn response vào heap. Với download, đánh giá `RestClient.exchange(...)` xử lý stream trong callback và đóng/cleanup đúng; tests large payload và client disconnect cần riêng.

Nếu legacy client gửi multipart form (files, strings, repeated keys), so request wire format:
- multipart boundary, Content-Disposition, filename escaping;
- Content-Type của từng part;
- Content-Length vs chunked transfer;
- encoded form parameters;
- request buffering/streaming và memory;
- HTTP method PATCH/PUT support của request factory.

Một test JSON 200 không thay thế tests multipart.

## 9. Security, headers và URI encoding

### 9.1. Interceptor có thể tái sử dụng, nhưng quyền truy cập vẫn phải kiểm tra

```java
RestTemplate template = new RestTemplate();
template.getInterceptors().add((request, body, execution) -> {
    request.getHeaders().set("X-Service-Name", "catalog-reader");
    return execution.execute(request, body);
});

RestClient client = RestClient.create(template);
```

Snippet minh họa interceptor chung; header `X-Service-Name` không phải authentication credential và client có thể tự spoof header nếu inbound proxy không kiểm soát. Không dùng nó như bằng chứng quyền. Với auth thật, dùng OAuth2/token provider/signed requests phù hợp và bảo đảm không gửi bearer token sang host lạ.

### 9.2. Không tự ghép URL từ input

```java
// Nguy cơ sai encoding và SSRF nếu userInput là URL tùy ý:
String unsafe = baseUrl + "/items/" + userInput;
```

URI template expansion:

```java
client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .body(ItemView.class);
```

Nhưng URI encoding **không tự chống SSRF** khi vẫn cho người dùng nhập absolute `http://internal.host/...`. Với dynamic URLs, dùng host/scheme/port allowlist, network egress restrictions, redirect restrictions và DNS rebinding defenses theo threat model.

### 9.3. Không làm mất security/observability khi chuyển sang builder mới

Nếu `RestTemplate` cũ có `ClientHttpRequestInterceptor` để thêm:
- Authorization từ service credential provider;
- traceparent/request ID;
- tenant context/locale;
- metrics/timing;
- mTLS client certificate qua request factory;

thì cách dựng RestClient mới **phải** giữ tương đương. Với Spring Security/OAuth2, token context propagation có thể phụ thuộc thread/scheduler; đừng lấy JWT từ ThreadLocal không thuộc request. Test rằng headers đã được đặt một lần, không bị nhân đôi hoặc lộ sang redirect khác origin.

### 9.4. ResponseEntity và cache headers

Một số endpoints trả 304 với ETag/If-None-Match. Khi chuyển client, phải giữ:
- request conditional headers;
- status 304 và không có body;
- ETag, Last-Modified, Cache-Control response headers;
- xử lý cache ở business layer.

Đừng mã hóa logic như “body null = 404” nếu 204/304 là kết quả hợp lệ theo HTTP.

## 10. Ví dụ chạy được: hai clients, một cấu hình

Demo Spring Boot 3.5/Java 17 chạy **Spring MVC server** và có mock supplier trong chính application:
- `GET /remote/items/7` là upstream demo;
- `GET /bridge/old/7` gọi nó bằng RestTemplate;
- `GET /bridge/new/7` gọi bằng RestClient được tạo từ RestTemplate đã cấu hình;
- `GET /bridge/new-meta/7` cho thấy status/headers với ResponseEntity;
- `GET /bridge/new-list` dùng generic type;
- `POST /bridge/old` và `POST /bridge/new` tạo item qua hai clients.

**Lưu ý demo:** sync HTTP call từ MVC handler quay lại cùng server ở localhost:8080 chỉ để dễ quan sát, không phải kiến trúc production; trong load lớn kiểu self-call này có thể làm cạn servlet worker threads. Trong thực tế client nên gọi upstream service độc lập qua trusted URL và phải có pool/deadline cụ thể.

### 10.1. Project Maven và dependency

Từ [Spring Initializr](https://start.spring.io/) tạo Maven project:
- Spring Boot **3.5.x**;
- Java **17**;
- dependency **Spring Web**.

POM fragment (parent, plugins và dependency management do Initializr tạo):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Không cần spring-boot-starter-webflux cho migration **đồng bộ** này.

### 10.2. Java source đầy đủ

Lưu toàn bộ nội dung vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RestTemplate legacyTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://localhost:8080")
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Bean
    RestClient migratedClient(RestTemplate legacyTemplate) {
        // Giai đoạn A: kế thừa cấu hình HTTP hiện hữu.
        return RestClient.create(legacyTemplate);
    }
}

record Item(long id, String name) {
}

record CreateItem(String name) {
}

record ApiError(String code, int upstreamStatus) {
}

// Server giả lập một upstream độc lập (chỉ dùng trong demo).
@RestController
@RequestMapping("/remote/items")
class RemoteItemController {

    private final AtomicLong nextId = new AtomicLong(7);
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();

    RemoteItemController() {
        items.put(7L, new Item(7L, "Spring Framework"));
    }

    @GetMapping("/{id}")
    ResponseEntity<Item> get(@PathVariable("id") long id) {
        Item item = items.get(id);
        return item == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(item);
    }

    @GetMapping
    List<Item> list() {
        return items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .toList();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> create(@RequestBody CreateItem command) {
        if (command.name() == null || command.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.incrementAndGet();
        Item item = new Item(id, command.name().trim());
        items.put(id, item);

        return ResponseEntity
                .created(URI.create("/remote/items/" + id))
                .body(item);
    }
}

// Bước chuyển từ call sites cũ sang fluent RestClient.
@RestController
@RequestMapping("/bridge")
class BridgeController {

    private final RestTemplate oldClient;
    private final RestClient newClient;

    BridgeController(RestTemplate legacyTemplate,
                     RestClient migratedClient) {
        this.oldClient = legacyTemplate;
        this.newClient = migratedClient;
    }

    @GetMapping("/old/{id}")
    Item oldGet(@PathVariable("id") long id) {
        return oldClient.getForObject(
                "/remote/items/{id}", Item.class, id);
    }

    @GetMapping("/new/{id}")
    Item newGet(@PathVariable("id") long id) {
        return newClient.get()
                .uri("/remote/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Item.class);
    }

    @GetMapping("/new-meta/{id}")
    ResponseEntity<Item> newGetWithHeaders(
            @PathVariable("id") long id) {
        return newClient.get()
                .uri("/remote/items/{id}", id)
                .retrieve()
                .toEntity(Item.class);
    }

    @GetMapping("/new-list")
    List<Item> newList() {
        return newClient.get()
                .uri("/remote/items")
                .retrieve()
                .body(new ParameterizedTypeReference<List<Item>>() {});
    }

    @PostMapping(path = "/old",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> oldCreate(
            @RequestBody CreateItem input) {
        return oldClient.postForEntity(
                "/remote/items", input, Item.class);
    }

    @PostMapping(path = "/new",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> newCreate(
            @RequestBody CreateItem input) {
        return newClient.post()
                .uri("/remote/items")
                .contentType(MediaType.APPLICATION_JSON)
                .body(input)
                .retrieve()
                .toEntity(Item.class);
    }
}

@RestControllerAdvice
class ClientErrorAdvice {

    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<ApiError> handle(
            RestClientResponseException ex) {
        return ResponseEntity.status(ex.getStatusCode())
                .body(new ApiError(
                        "UPSTREAM_HTTP_ERROR",
                        ex.getStatusCode().value()));
    }
}
```

### 10.3. Giải thích code

- Java 17 cho phép `record`; một file chỉ có một public top-level class `DemoApplication`.
- `@SpringBootApplication` quét các @RestController cùng package và tạo embedded Tomcat mặc định của Spring MVC starter.
- `legacyTemplate(RestTemplateBuilder)` là bean cấu hình **một lần** với root URL và Duration timeouts. Không thay cấu hình khi nhiều threads đang dùng nó.
- `migratedClient(RestTemplate)` dùng `RestClient.create(template)` kế thừa request factory, converters, interceptors, initializers, URI builder và error handler của template.
- `RemoteItemController` là upstream tự dựng trong cùng process. Endpoint GET/POST dùng in-memory map và AtomicLong, không có database/auth.
- `BridgeController` cho thấy hai HTTP client cùng trả domain type `Item`, chỉ khác cách gọi.
- `newGetWithHeaders` trả ResponseEntity để giữ status/headers; `newList` dùng ParameterizedTypeReference tránh raw List.
- `ClientErrorAdvice` là **demo policy**: forward upstream 404 hoặc 500 status để tiện so sánh. Trong production, upstream 500 thường nên map thành 502/503 của facade hoặc lỗi nghiệp vụ phù hợp; không chuyển mọi upstream status mù quáng.
- `RestClient` và `RestTemplate` đều synchronous; MVC worker thread chờ remote call hoàn tất. Không hứa sẽ nhanh hơn do fluent syntax.
- Các bean tạo ở startup, không phát sinh HTTP client mới cho mỗi request.
- Nếu đổi `server.port` khỏi 8080, phải đổi `rootUri("http://localhost:8080")`; đây là cấu hình demo cố định.
- Không có auth/CSRF/CORS/rate limiting/mTLS/retry/observability/persistence; không public deploy.

### 10.4. Chạy

Trong thư mục Maven project do Initializr sinh:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc CMD
mvnw.cmd spring-boot:run
```

### 10.5. GET qua hai clients

```bash
curl -i 'http://localhost:8080/bridge/old/7'
curl -i 'http://localhost:8080/bridge/new/7'
curl -i 'http://localhost:8080/bridge/new-meta/7'
```

Cả ba response khi hoạt động bình thường:
- Status 200;
- Content-Type JSON phù hợp;
- body tương đương:

```json
{"id":7,"name":"Spring Framework"}
```

JSON whitespace và thứ tự headers không phải business contract. `/bridge/new-meta/7` chứng minh dùng `ResponseEntity` để giữ status và response headers. Legacy RestTemplate vs RestClient chỉ khác lập trình API ở client side.

### 10.6. Generic list

```bash
curl -i 'http://localhost:8080/bridge/new-list'
```

Khi mới khởi động, JSON body có một item:

```json
[{"id":7,"name":"Spring Framework"}]
```

Sau các POST, list có thêm items theo ID tăng dần vì controller sắp xếp theo Item.id.

### 10.7. POST qua hai clients

```bash
curl -i -X POST 'http://localhost:8080/bridge/old' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"Legacy-created"}'

curl -i -X POST 'http://localhost:8080/bridge/new' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"RestClient-created"}'
```

Khi mới khởi động, POST đầu tiên tạo ID 8, POST thứ hai ID 9 nếu không có request đồng thời; mỗi response là HTTP 201 Created, header `Location: /remote/items/{id}` và JSON body `{"id":8,"name":"Legacy-created"}` hoặc ID phù hợp. Chú ý: Location trỏ **resource của remote endpoint demo**, không nhất thiết là endpoint bridge.

### 10.8. 404 qua legacy và modern

```bash
curl -i 'http://localhost:8080/bridge/old/999'
curl -i 'http://localhost:8080/bridge/new/999'
```

Upstream demo trả HTTP 404. Legacy RestTemplate và migrated RestClient sẽ nhận HTTP status error theo cơ chế mặc định; `ClientErrorAdvice` biến thành cùng response policy demo:

```json
{"code":"UPSTREAM_HTTP_ERROR","upstreamStatus":404}
```

Không dựa vào điều này để khẳng định mọi custom error handler trong app thật luôn được copy và chạy giống hệt. Cần regression test cho handler thực, đặc biệt với `RestClient.exchange` và request-specific `onStatus`.

### 10.9. Windows PowerShell

```powershell
curl.exe -i "http://localhost:8080/bridge/old/7"
curl.exe -i "http://localhost:8080/bridge/new/7"
curl.exe -i "http://localhost:8080/bridge/new-list"
curl.exe -i "http://localhost:8080/bridge/new/999"
```

Nếu shell Windows khó escape JSON quotes, tạo `request.json` UTF-8:

```json
{"name":"RestClient-created"}
```

Gửi qua:

```powershell
curl.exe -i -X POST "http://localhost:8080/bridge/new" -H "Content-Type: application/json" --data-binary "@request.json"
```

## 11. Kiểm thử migration: không chỉ assert HTTP 200

Migration thành công nghĩa là **hành vi hai clients tương đương ở ranh giới HTTP**, không chỉ cùng DTO. Cần test method, path/query encoding, headers, body bytes/JSON, 200/201/204, 404/429/5xx, TLS/proxy, connection reuse và deadlines.

### 11.1. Unit tests với MockRestServiceServer

Spring Test hỗ trợ `MockRestServiceServer.createServer(RestTemplate)` và `MockRestServiceServer.bindTo(RestClient.Builder)`. Điều này giúp mock HTTP boundary và so URI/method/JSON một cách deterministic.

Với Boot 3.5, thêm POM fragment:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Lưu `src/test/java/com/example/demo/MigrationClientTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.DefaultUriBuilderFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class MigrationClientTest {

    private static RestTemplate templateWithBaseUri() {
        RestTemplate template = new RestTemplate();
        template.setUriTemplateHandler(
                new DefaultUriBuilderFactory("https://catalog.example.test"));
        return template;
    }

    @Test
    void oldTemplateSendsExpectedGet() {
        RestTemplate template = templateWithBaseUri();

        MockRestServiceServer server =
                MockRestServiceServer.createServer(template);

        server.expect(requestTo(
                        "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Framework\"}",
                        MediaType.APPLICATION_JSON));

        Item item = template.getForObject(
                "/items/{id}", Item.class, 7);

        assertNotNull(item);
        assertEquals(7, item.id());
        assertEquals("Spring Framework", item.name());
        server.verify();
    }

    @Test
    void newClientCopiesLegacyUriConfiguration() {
        RestTemplate template = templateWithBaseUri();

        RestClient.Builder builder = RestClient.builder(template);

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Framework\"}",
                        MediaType.APPLICATION_JSON));

        Item item = client.get()
                .uri("/items/{id}", 7)
                .retrieve()
                .body(Item.class);

        assertNotNull(item);
        assertEquals(7, item.id());
        assertEquals("Spring Framework", item.name());
        server.verify();
    }

    @Test
    void newClientRetrieveStillThrowsOn404() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/items/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        RestClientResponseException exception = assertThrows(
                RestClientResponseException.class,
                () -> client.get()
                        .uri("/items/{id}", 99)
                        .retrieve()
                        .body(Item.class));

        assertEquals(404, exception.getStatusCode().value());
        server.verify();
    }
}
```

Giải thích tests:
- Test 1 giữ RestTemplate API cũ và URI base.
- Test 2 tạo `RestClient.Builder` **từ template đã có cấu hình**, sau đó `bindTo(builder)` đưa mock request factory vào builder trước `build()`. Test chỉ tập trung URI/method/JSON, không thực hiện DNS/TLS.
- Test 3 bảo vệ contract 404 từ `retrieve()`; mặc định `RestClientResponseException` là base type phù hợp.
- Việc mock builder thay request factory nghĩa là **không chứng minh** connection pool, SSL, timeout của factory cũ; cần integration test riêng cho những behavior đó.

### 11.2. Additional test matrix

| Hành vi | Kiểm tra cụ thể |
| --- | --- |
| JSON GET 200 | DTO fields, UTF-8, Content-Type |
| List generic | ParameterizedTypeReference giữ type |
| POST 201 | Location, request Content-Type, response status/body |
| Empty 204 | Không NPE, code xử lý body null |
| 304/ETag | Headers, conditional GET nếu sử dụng |
| 400/401/403 | Không retry và không leak raw upstream body |
| 404 | Policy: resource missing vs dependency misconfiguration |
| 409/412 | Conflict/ETag behavior |
| 429/Retry-After | Rate limit/backoff, không retry storm |
| 500/503/504 | Typed service errors, metrics, deadlines |
| Connect/read timeout | Thử với slow HTTP server, kiểm tra không giữ worker vô hạn |
| TLS/proxy | Certificate/host validation, ALPN, proxies theo prod |
| Multipart/PATCH | Request factory hỗ trợ method, binary body đúng |
| Authorization/tracing | Không mất/nhân đôi interceptor headers |
| Query/path encoding | Có space, Unicode, slash, dấu %, repeated query |
| Concurrency | Thread pool, connection reuse, saturation |
| Redirect | Có forward Authorization ngoài trust boundary không? |

### 11.3. Chạy tests

```bash
# Linux / macOS
./mvnw test

# Windows
mvnw.cmd test
```

**Không coi việc README có source/test code là kết quả thực thi.** Để xác nhận runnable trong dự án thật, hãy chạy `./mvnw test` và các curl steps trong môi trường Spring Boot 3.5/JDK17 phù hợp. Nếu có custom beans/security/autoconfiguration, cần điều chỉnh tests theo chính sách ứng dụng.

## 12. Rollout, monitoring và rollback từng bước

### 12.1. Inventory toàn bộ RestTemplate consumers

Ghi bảng theo service/call site (không cần tạo spreadsheet mới nếu đang ở một dự án):

| Mục tiêu kiểm kê | Điều cần ghi |
| --- | --- |
| Tên bean và consumer | Service dùng RestTemplate nào? |
| Downstream logical name | Catalog, payments, identity, shipping |
| Method/path | GET, POST, PATCH, multipart/stream |
| Timeout/request factory | Connect/read/pool acquisition limits |
| Interceptors | Auth, tracing, tenancy, metrics, signatures |
| Converters | JSON/XML/custom, multipart |
| Error handler | Class, status mapping, body behavior |
| Resilience | Retry, circuit breaker, fallback, idempotency |
| Bảo mật | Credentials, redirect/SSRF restrictions |
| Test coverage | 200/4xx/5xx, timeouts, encoding |
| Migration status | Legacy, dual-client, converted, validated |

### 12.2. Canary theo client bean hoặc service

Có thể giữ hai implementations cùng interface:

```java
interface CatalogGateway {
    ItemView load(long id);
}

class LegacyCatalogGateway implements CatalogGateway {
    // RestTemplate getForObject...
}

class MigratedCatalogGateway implements CatalogGateway {
    // RestClient get().retrieve().body()...
}
```

Đây là design snippet, không phải full source. Chọn implementation bằng Spring Profiles/feature flag server-side và đo canary. Cần chú ý **không gửi song song hai POST thực tế** chỉ để shadow-compare, vì side effects có thể bị nhân đôi. Nếu shadow GET read-only, vẫn phải kiểm tra quota, auth/PII và cost.

### 12.3. Metrics trước và sau

So sánh trước/sau migration:
- error rate 4xx/5xx và I/O timeouts;
- latency p50/p95/p99 ở từng downstream;
- connection pool active/idle/pending;
- JVM thread states, servlet pool usage, heap/gc;
- request volume và retry attempts;
- URI templates/HTTP method distributions;
- response payload bytes/codec errors;
- authorization/correlation header propagation.

Không dùng raw user IDs, order IDs, email, request IDs làm high-cardinality Micrometer tags. Dùng templates và logical service names.

### 12.4. Tiêu chí rollback

Rollback nếu:
- 404/500 mapping thay đổi không theo contract;
- 429/throttling hoặc connection pool timeout tăng mạnh;
- mất/mismatch auth signature hoặc redirect sang host khác;
- POST trùng do retry;
- multipart/streaming payload sai;
- tỷ lệ JSON decode lỗi tăng;
- request timeouts không còn chặn được slow downstream;
- có data leak, SSRF hoặc security regression.

Vì giai đoạn A giữ RestTemplate cũ cùng request factory/config, rollback có thể đơn giản là chuyển call site/service implementation về RestTemplate, miễn không sửa đổi dữ liệu nghiệp vụ ngoài ý muốn.

## 13. Khi nào phải xem lại kiến trúc thay vì chỉ chuyển API?

### 13.1. Nếu dùng WebFlux event loop

Không thay RestTemplate bằng RestClient rồi gọi trực tiếp trong WebFlux handler: **RestClient vẫn blocking**. Trong ứng dụng WebFlux native, ưu tiên WebClient để compose network I/O, hoặc tạm bridge một số blocking calls sang `Schedulers.boundedElastic()` có giới hạn:

```java
Mono<ItemView> bridged = Mono.fromCallable(
                () -> restClient.get()
                        .uri("/items/{id}", id)
                        .retrieve()
                        .body(ItemView.class))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet reactive bridge, không biến RestClient thành non-blocking HTTP transport. Cần kiểm soát boundedElastic queue/concurrency và downstream pool. Nếu ứng dụng chủ yếu dùng JDBC/JPA và sync HTTP, Spring MVC có thể hợp lý hơn WebFlux.

### 13.2. HTTP Service Client interface-first

Spring 6+ cho phép khai báo HTTP interface:

```java
@HttpExchange("/items")
interface CatalogApi {
    @GetExchange("/{id}")
    ItemView get(@PathVariable("id") long id);
}
```

Và tạo proxy trên RestClient:

```java
CatalogApi catalog = HttpServiceProxyFactory
        .builderFor(RestClientAdapter.create(restClient))
        .build()
        .createClient(CatalogApi.class);
```

Đây là snippets cần imports và RestClient bean. HTTP Service Client là **interface/proxy trên RestClient**, không phải transport mới, và method vẫn đồng bộ nếu dùng RestClientAdapter. Có ích khi nhiều endpoints cùng một remote contract, giảm boilerplate và dễ mock interface. Không bắt buộc đổi RestTemplate sang HTTP interface nếu bài toán chỉ cần một GET.

### 13.3. Với tác vụ streaming rất lớn

RestClient hỗ trợ low-level exchange để xử lý InputStream trong callback, nhưng vẫn có caller thread chờ. WebClient thích hợp hơn với event streams/NDJSON/high concurrency và reactive processing. Không ép tất cả tasks streaming sang `body(byte[].class)` vì có thể giữ toàn bộ payload trong RAM.

## 14. Các lỗi migration thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| RestClient không có trong Spring 6.0 | API bắt đầu từ 6.1 | Nâng theo compatibility plan |
| Code nói RestTemplate đã bị xóa Spring 7 | Hiểu sai deprecation | 7.0 docs deprecation; 7.1 planned @Deprecated; 8.0 planned removal |
| Cứ dùng RestTemplate mãi vì không thấy warning | Spring 7.0 chưa nhất thiết có annotation | Làm migration plan dựa trên roadmap |
| Đổi RestClient mà mất auth headers | Bỏ interceptor/customizer cũ | `RestClient.create(template)` + integration test |
| URI route khác trước | Đổi URI builder/baseUrl/encoding | So HTTP requests byte-level |
| 404/500 xử lý khác | Không giữ error handler/status policy | Test retrieve/onStatus/defaultStatusHandler |
| Dùng `exchange` và không throw cho 4xx | exchange bỏ retrieve status handlers | Tự check status và body |
| Request không được gửi | Gọi `retrieve()` nhưng không terminal method | `body/toEntity/toBodilessEntity` |
| 204 làm NullPointerException | Body rỗng là hợp lệ | Check null/ResponseEntity |
| JSON List thành List<Map> | Type erasure | ParameterizedTypeReference |
| POST bị nhân đôi khi retry | Không có idempotency | Key + reconciliation |
| Download gây OOM | Thay stream extractor bằng byte[] | Streaming exchange và giới hạn |
| PATCH hoạt động trên client này nhưng lỗi client khác | Request factory khác | Test transport-specific PATCH |
| HTTP pool bão hòa | Connection limits không theo load | Pool metrics/bulkhead/timeouts |
| Vẫn nghẽn Netty WebFlux | RestClient vẫn blocking | WebClient/native reactive |
| SSL/certificates lỗi sau migration | Chọn request factory mới bỏ cấu hình mTLS | Reuse/test TLS config |
| Redirect làm lộ token | Auto-follow cross-origin không hạn chế | Policy redirect/auth/allowlist |
| Chỉ test happy-path | Thiếu 4xx/5xx/timeout/encoding tests | Contract test matrix |
| Tạo RestClient ở mỗi request | Pool/client lifecycle lãng phí | Reuse bean |
| Cập nhật RestTemplate config khi có concurrent calls | Unsafe mutation | Startup-only configuration |
| Gọi deprecated annotation không đúng phiên bản | 7.0 docs khác 7.1 API | Đọc Javadoc/release notes đúng version |

## 15. Checklist triển khai

- [ ] Khóa Spring/JDK version; hiểu sự khác nhau giữa deprecation **docs 7.0** và **Java annotation dự kiến 7.1**.
- [ ] Phân loại tất cả RestTemplate beans và consumers, ghi rõ contracts và owners.
- [ ] Giai đoạn A dùng `RestClient.create(existingRestTemplate)`, không thay cùng lúc factory/pool/auth.
- [ ] Mapping các method cũ sang fluent API kèm terminal operation đúng.
- [ ] Có test status 201/204/404/429/5xx, ResponseEntity headers, body rỗng.
- [ ] Có test Generic `List<T>`, URI template, Unicode/encoding, query params.
- [ ] Có test custom ResponseErrorHandler và interceptors migrated.
- [ ] RestClient.retrieve vs exchange được phân biệt, không bỏ status policy.
- [ ] Connect/read/pool/TLS/deadline được cấu hình và đo với real HTTP server.
- [ ] Retry/idempotency/circuit breaker/rate limit giữ đúng business semantics.
- [ ] Security credentials, mTLS, tracing/tenant propagation không mất hoặc leak.
- [ ] Với multipart/download/PATCH, có transport-specific contract tests.
- [ ] Client beans được tái sử dụng; shared template không bị mutate khi xử lý concurrent requests.
- [ ] Có canary/rollback và metrics so sánh trước/sau với URI template tags.
- [ ] Không giả định RestClient thành async/reactive; chọn WebClient khi cần non-blocking.
- [ ] Bước B chỉ bỏ RestTemplate bean sau khi mọi consumers đã chuyển và vượt qua test.
- [ ] Nếu nâng Spring 7/Boot 4, xem lại import/versions và chính sách deprecation của bản đang dùng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Spring Framework 7.0 có xóa RestTemplate không?

**Đáp án:** Không. Spring 7.0 deprecated RestTemplate trong tài liệu; annotation Java `@Deprecated` dự kiến ở 7.1 và removal thuộc kế hoạch 8.0 chưa định ngày.

**Câu 2.** Có thể chuyển API mà không sửa connection pool ngay không?

**Đáp án:** Có. Dùng `RestClient.create(restTemplate)` hoặc `builder(restTemplate)` để tái sử dụng request factory và các cấu hình liên quan.

**Câu 3.** RestClient có giúp MVC thread không bị block khi network chậm không?

**Đáp án:** Không. Nó là synchronous client giống RestTemplate. WebClient mới có non-blocking HTTP model.

**Câu 4.** Tại sao không nên thay `RestTemplate.execute(...,ResponseExtractor)` thành `body(byte[].class)` với file lớn?

**Đáp án:** Cách mới có thể gom toàn body vào RAM, gây memory pressure hoặc OOM; phải thiết kế streaming/cleanup đúng.

**Câu 5.** `RestClient.get().retrieve()` đã trả Item chưa?

**Đáp án:** Chưa. Cần terminal `body(Item.class)`, `toEntity` hoặc operation tương ứng.

**Câu 6.** `RestClient.exchange` có áp dụng default status handlers của retrieve không?

**Đáp án:** Không. Callback tự chịu trách nhiệm xử lý status/body.

**Câu 7.** Khi một 204 trả body null, có phải upstream lỗi không?

**Đáp án:** Không. 204 No Content không có body là hợp lệ.

**Câu 8.** Khi copy RestTemplate error handler, có được bỏ 404 regression test không?

**Đáp án:** Không. Thứ tự status handler, request-specific override và retrieve/exchange có thể khác, nên phải test.

**Câu 9.** Việc shadow-compare hai POST payment cùng lúc có an toàn không?

**Đáp án:** Không. Có thể tạo side effects hai lần; dùng contract tests/mocks, idempotency và controlled canary.

**Câu 10.** Nếu muốn HTTP client reactive trong WebFlux, chọn RestClient hay WebClient?

**Đáp án:** WebClient, vì RestClient vẫn blocking ngay cả khi API syntax hiện đại hơn.

## 17. Nguồn tham khảo chính thức

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestTemplate/RestClient/WebClient, converters, error handling.
- [Spring Framework — Migrating to RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#migrating-to-restclient): hướng dẫn hai giai đoạn và equivalence table.
- [Spring Framework 7.0 — Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): deprecation ở tài liệu 7.0 và dự định @Deprecated ở 7.1.
- [Spring Blog — The state of HTTP clients in Spring (30/09/2025)](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): roadmap migration và removal.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html): `create(RestTemplate)`, `builder(RestTemplate)`, retrieve/exchange.
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html): template methods, thread configuration.
- [Spring Framework 6.2 — RestClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.Builder.html): requestFactory/converters/interceptors/defaultStatusHandler.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestTemplateBuilder/RestClient.Builder.
- [Spring Framework — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): Test RestTemplate và RestClient.Builder.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): credentials, authorized HTTP calls.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): non-blocking option when architecture changes.

**Kết luận:** `RestTemplate` là legacy synchronous client vẫn hoạt động trong Spring 6.2 và không bị xóa trong Spring 7.0. Spring 7.0 tuyên bố deprecation ở tài liệu, 7.1 dự kiến đánh dấu `@Deprecated`, 8.0 dự kiến loại bỏ. Chọn **RestClient** cho mã HTTP đồng bộ mới và **migrate từng service** bằng `RestClient.create(restTemplate)` để giữ hạ tầng trước, rồi mới cải tổ builder và xóa bean cũ. Migration tốt phải bảo toàn HTTP status, headers/body, error policy, timeout/pool, auth và side effects — chứ không chỉ thay syntax.
