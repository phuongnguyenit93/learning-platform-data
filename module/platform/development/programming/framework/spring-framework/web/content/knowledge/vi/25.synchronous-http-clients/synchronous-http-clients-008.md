# Interceptor, xử lý mã lỗi và thiết kế retry theo tính lặp lại của thao tác

## 1. Vì sao HTTP client đồng bộ cần ba cơ chế riêng?

Một ứng dụng Spring gọi HTTP tới dịch vụ khác thường cần thêm thông tin chung cho request, diễn giải phản hồi lỗi và thử lại khi có sự cố tạm thời. Ba vấn đề liên quan nhau nhưng **không phải một cơ chế duy nhất**:

1. **Interceptor**: can thiệp trước/sau một lời gọi HTTP ở client để thêm correlation ID, header phù hợp, quan sát thời gian phản hồi, trace hoặc policy dùng chung.
2. **Xử lý mã lỗi**: phân loại HTTP 4xx/5xx, lỗi transport, timeout, body không hợp lệ và chuyển chúng thành kết quả/exception có ý nghĩa nghiệp vụ.
3. **Retry theo tính lặp lại (idempotency)**: chỉ thực hiện lại yêu cầu khi việc lặp là an toàn theo **HTTP method, operation semantics, trạng thái request body, server contract, số lần thử và ngân sách thời gian**.

Điểm quan trọng nhất: **một kết nối timeout không chứng minh server chưa xử lý yêu cầu**. Client có thể đã gửi POST, server đã ghi DB, nhưng response bị mất. Nếu client tự POST lại, có thể tạo hai đơn hàng hoặc thanh toán hai lần.

Bài thuộc nhóm **HTTP client đồng bộ**, lấy **Spring Framework 6.1 / Spring Boot 3.3.5 / Java 17** làm nền tảng. API chính là `RestClient` (được giới thiệu trong Spring Framework 6.1), kèm đối chiếu với `RestTemplate` trong hệ thống hiện hữu. `RestClient` là synchronous/blocking client, **không phải WebClient reactive**.

### Bạn sẽ làm được gì?

- Phân biệt vị trí `ClientHttpRequestInterceptor` với status/error handler và retry wrapper.
- Viết interceptor chỉ thực thi request đúng một lần mỗi attempt, ghi logs an toàn và tránh giữ response chưa đóng.
- Biết default error behavior của `RestClient.retrieve()`, `onStatus(...)`, `defaultStatusHandler(...)`, `exchange(...)` và `RestTemplate.ResponseErrorHandler`.
- Phân loại đúng 400, 401, 403, 404, 409, 412, 422, 429, 500, 502, 503, 504 và lỗi network.
- Hiểu HTTP *safe*, *idempotent*, *non-idempotent* và sự khác nhau giữa "HTTP method idempotent" với "business operation có thể lặp lại".
- Lựa chọn những operation được phép retry, xử lý `Retry-After`, exponential backoff, jitter, max attempts, timeout và budget.
- Thiết kế `Idempotency-Key` phía client **và phía server**, không nhầm một header tùy ý với bảo đảm chống duplicate.
- Viết dự án Maven chạy với `RestClient`/`MockRestServiceServer`, kiểm tra chính xác số lần gọi qua 4xx/5xx/timeout.
- Biết các vấn đề production như circuit breaker, retry storms, distributed tracing, logging PII, pool starvation và concurrency.

## 2. Đường đi của một lời gọi RestClient

Một request HTTP đồng bộ có thể đi qua các lớp:

```text
Business service
   |
   v
Retry boundary (chỉ với operation đủ điều kiện)
   |
   +--> attempt 1
   |       |
   |       v
   |     RestClient request specification
   |       |
   |       v
   |     ClientHttpRequestInterceptor chain
   |       |
   |       v
   |     ClientHttpRequestFactory -> HTTP transport
   |       |
   |       v
   |     HTTP response
   |       |
   |       v
   |     retrieve() status handler -> body conversion
   |       |
   |       +--> success value
   |       +--> typed HTTP exception
   |       +--> transport exception
   |
   +--> (nếu retryable và còn budget)
   |       attempt 2 -> toàn bộ RestClient execution mới
   |
   v
Final success / terminal failure
```

**Retry nên bao quanh toàn bộ một attempt** thay vì gọi `execution.execute(...)` tùy tiện nhiều lần bên trong interceptor. Cấu trúc này cho phép status handler của `retrieve()` nhìn từng response, và caller quyết định có được lặp thao tác hay không.

Một interceptor có thể quan sát cả HTTP 404 và HTTP 503 mà **không tự biến chúng thành exception**. Status handler hoạt động sau giai đoạn transport/interception của `RestClient.retrieve()`. Các lỗi network trước khi nhận response cần được phân biệt với lỗi HTTP đã có status.

### Các abstraction liên quan

| Loại | Package/đối tượng | Trách nhiệm |
| --- | --- | --- |
| Fluent client | `org.springframework.web.client.RestClient` | Tạo request, gửi đồng bộ, nhận response |
| Legacy synchronous client | `org.springframework.web.client.RestTemplate` | API template, vẫn gặp trong nhiều ứng dụng |
| Interceptor | `org.springframework.http.client.ClientHttpRequestInterceptor` | Can thiệp request/response trước/sau HTTP execution |
| Request factory | `ClientHttpRequestFactory` | Kết nối, timeout, transport implementation |
| RestClient status handler | `retrieve().onStatus(...)` | Ánh xạ lỗi theo từng request |
| Global status handler | `RestClient.Builder.defaultStatusHandler(...)` | Rule mặc định cho nhiều requests |
| RestTemplate handler | `ResponseErrorHandler` | Xác định error và xử lý response lỗi |
| HTTP response exception | `RestClientResponseException` | Status, response headers và error body |
| I/O exception | `ResourceAccessException` | Transport timeout, connection, TLS và các I/O issues |
| Client mock | `MockRestServiceServer` | Test requests, headers, responses, số lần retry |

## 3. RestClient và RestTemplate khác nhau ở đâu?

### RestClient: fluent API của Spring Framework 6.1

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

CatalogItem item = client.get()
        .uri("/items/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(CatalogItem.class);
```

Đây là snippet; `CatalogItem` là DTO ở ví dụ hoàn chỉnh. Lệnh gọi `body(...)` thực hiện request đồng bộ, đọc và convert response. Trong tình huống bình thường, nếu upstream trả HTTP 4xx/5xx thì `retrieve()` **mặc định tạo RestClientException**, thường là các subclasses của `RestClientResponseException`.

### RestTemplate trong ứng dụng cũ

```java
RestTemplate template = new RestTemplate();

ResponseEntity<CatalogItem> response = template.exchange(
        "https://catalog.example.test/items/{id}",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        CatalogItem.class,
        42);
```

`RestTemplate` vẫn hữu ích với code đã có. Nó sử dụng `ResponseErrorHandler` (mặc định có `DefaultResponseErrorHandler`) và hỗ trợ cùng `ClientHttpRequestInterceptor`. Spring có `RestClient.builder(restTemplate)` để lấy cấu hình nền khi muốn migrate từng phần.

**Không cần rewrite toàn bộ RestTemplate chỉ để thêm interceptor/retry.** Quan trọng hơn là hợp đồng API, timeout, status mappings, test và dữ liệu giao dịch. Cũng không thay RestClient thành WebClient chỉ vì muốn có retry; WebClient sử dụng pipeline reactive khác và không tự sửa được non-idempotent POST.

## 4. ClientHttpRequestInterceptor là gì?

Chữ ký cốt lõi:

```java
@FunctionalInterface
public interface ClientHttpRequestInterceptor {
    ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution)
            throws IOException;
}
```

Đây là bản trình bày chữ ký của API Spring, không phải interface cần tự định nghĩa.

- `request` chứa HTTP method, URI và mutable headers.
- `body` là bytes của request body đã được chuẩn bị cho execution; cần thận trọng với memory và secrets.
- `execution.execute(request, body)` gọi interceptor tiếp theo hoặc request factory/transport.
- `ClientHttpResponse` cho phép xem status/headers và phản hồi từ server.
- Interceptor có thể short-circuit nhưng lúc đó phải trả response hợp lệ hoặc throw một exception có semantics rõ.

Một interceptor thông thường nên gọi **`execution.execute(...)` chính xác một lần trên đường thành công**. Tự chạy nhiều lần vì status 503 trong interceptor có thể vô tình phát lại POST, mất body replay guarantees và khiến error handling khó kiểm soát.

### Thứ tự nhiều interceptors

`RestClient.Builder.requestInterceptor(...)` thêm interceptor vào chain; `requestInterceptors(...)` cho quyền quản lý danh sách. Thứ tự quyết định:
- Header auth được gắn trước signing hay sau?
- Trace span bao gồm giai đoạn nào?
- Logs có nhìn thấy request headers sau khi đã chỉnh sửa không?
- Retry (nếu có thành phần ngoại vi) ở ngoài hay trong metrics/observability?

Đừng dựa vào class name hay thứ tự quét bean không được bảo đảm. Xác định thứ tự tường minh trong config và test headers ở HTTP mock.

### Không đọc/ghi logs toàn bộ request body

`byte[] body` có thể chứa PII, password, access token, payment data hoặc file upload. Logging nó là một rủi ro bảo mật. Nên log:
- Logical service name.
- HTTP method và endpoint template (không raw query parameters chứa secrets).
- HTTP status/code family.
- Duration, attempt count, server trace/request ID được phép.
- Error category (timeout/4xx/5xx), không dump authorization headers.

Không log `Authorization`, `Cookie`, `Set-Cookie` hay raw `ResponseEntity` có body nhạy cảm.

## 5. Interceptor không phải điểm nên retry mặc định

Phản ví dụ:

```java
// PHẢN VÍ DỤ — interceptor tự gọi upstream nhiều lần.
return execution.execute(request, body);
// ...nếu 503 thì execution.execute(request, body) một lần nữa...
```

Ngoài việc chỉ ra flow sai, ý tưởng trên còn có vấn đề:
1. Interceptor **không biết chắc** operation business có thể lặp.
2. HTTP body có thể là stream/file upload không replayable theo kiểu request factory hiện tại.
3. Mỗi interceptor có thể được tái sử dụng bởi GET, POST, PUT, DELETE và những requests đặc biệt.
4. Nếu response đã được tạo nhưng interceptor quyết định retry, nó phải **đóng response cũ** chính xác; không làm sẽ leak connection/pool resources.
5. Status/error handler của `RestClient.retrieve()` thường chưa chạy trong interceptor.
6. Auth refresh, idempotency key, tracing và metrics có thể bị trộn vào nhau.
7. Client-cancel/interrupted thread có thể bị bỏ qua khi ngủ backoff trong interceptor.

**Thiết kế ưu tiên:** để interceptor làm transport decoration/observability; để **retry boundary** ở service method hoặc resilience policy có metadata rõ cho từng operation; để `RestClient.retrieve()`/`onStatus` quyết định error mapping.

## 6. Error status: RestClient.retrieve() và RestClient.exchange()

### Default retrieve()

```java
CatalogItem item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .body(CatalogItem.class);
```

Mặc định, phản hồi thuộc **4xx và 5xx** được xử lý như error; code thường nhận subclasses của `RestClientResponseException`, có thông tin:
- `getStatusCode()` (Spring `HttpStatusCode`).
- `getResponseHeaders()`.
- `getResponseBodyAsString()` hoặc bytes.
- HTTP response metadata khác theo implementation.

Không đem nguyên error body từ dịch vụ nội bộ trả cho public client nếu nó có hostname, stack trace hay secrets.

### onStatus per request

```java
CatalogItem item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                code -> code.value() == 404,
                (request, response) -> {
                    throw new CatalogNotFoundException(
                            "Catalog item unavailable");
                })
        .body(CatalogItem.class);
```

Đây là snippet, `CatalogNotFoundException` là custom exception do ứng dụng định nghĩa. Handler `onStatus` ở request này nhận quyền xử lý 404; ví dụ chủ động throw domain exception. Tránh swallow error mà tiếp tục decode 404 body như DTO thành công ngoài ý định.

Một số API có thể muốn 404 → `Optional.empty()` thay exception. Thiết kế contract rõ; có thể dùng `exchange(...)` để trực tiếp đọc status và trả Optional, nhưng **exchange không tự áp dụng default retrieve status handlers**.

### defaultStatusHandler toàn client

```java
RestClient restClient = RestClient.builder()
        .defaultStatusHandler(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Upstream server returned 5xx");
                })
        .build();
```

Đây là snippet minh họa, không phải lựa chọn production lý tưởng vì đã **làm mất status và Retry-After** của exception mặc định. Khi cần retry theo 502/503/504, giữ nguyên `RestClientResponseException` hoặc wrap thành custom exception chứa code/headers/retry hints.

Các `defaultStatusHandler` chạy theo thứ tự đăng ký, sau request-specific handlers. Đừng cài một catch-all status handler rồi vô tình biến 404/409 thành 500 hoặc biến 429 thành domain invalid input.

### exchange(...) bypass status handlers của retrieve()

```java
Boolean exists = client.head()
        .uri("/items/{id}", 42)
        .exchange((request, response) ->
                response.getStatusCode().is2xxSuccessful());
```

Đây là snippet; 404 được trả dưới dạng `false` chứ không tự ném exception theo default `retrieve()`, vì callback của `exchange` tự chịu trách nhiệm status handling. Chỉ dùng khi bạn chủ động kiểm tra các status/headers và bảo đảm phản hồi được xử lý/đóng phù hợp. Với service có retry policy dựa trên `RestClientResponseException`, thay retrieve bằng exchange sẽ **làm thay đổi điều kiện retry**.

### Status handler vs transport errors

Nếu DNS không phân giải, TLS handshake thất bại hoặc socket timeout **trước khi có HTTP response**, không có HTTP status 503 để `onStatus` xử lý. Những lỗi này thường đi qua `ResourceAccessException` hoặc lỗi client I/O khác. Cần phân loại riêng và giữ nguyên cause/trace nội bộ.

## 7. Bảng phân loại mã lỗi để thiết kế retry

| Mã | Ý nghĩa thường gặp | Retry tự động? |
| --- | --- | --- |
| 200/201/204 | Thành công | Không |
| 301/302/307/308 | Redirect | Không phải lỗi để retry đơn giản; kiểm tra redirect/credentials/method |
| 400 | Request sai cấu trúc/vi phạm validation | Không; sửa input |
| 401 | Chưa authenticated/token hết hạn | Không retry vô hạn; có thể refresh credentials tối đa một lần theo policy |
| 403 | Không có quyền | Không; sửa authz/ACL |
| 404 | Không thấy resource | Thường không; eventual consistency chỉ khi contract cho phép và bounded |
| 408 | Request Timeout | Có thể retry **nếu operation an toàn** và context phù hợp |
| 409 | Conflict | Không mặc định; kiểm tra version/concurrency |
| 412 | Precondition Failed | Không; làm mới ETag/state |
| 422 | Unprocessable Content | Không; sửa dữ liệu |
| 425 | Too Early | Có trường hợp client retry khi không dùng early data; cần TLS/protocol policy |
| 429 | Too Many Requests | Có thể theo Retry-After/quota, chỉ nếu operation replay-safe |
| 500 | Internal Server Error | Không mặc định; phụ thuộc API/incident semantics |
| 502 | Bad Gateway | Có thể là transient; retry có kiểm soát |
| 503 | Service Unavailable | Thường transient; cân nhắc Retry-After |
| 504 | Gateway Timeout | Có thể transient, **server có thể đã thực hiện side effect** |
| Transport timeout/reset | Không có response tin cậy | Chỉ retry nếu business operation replay-safe |
| TLS certificate error | Cấu hình bảo mật sai | Không retry trong vòng lặp; cần sửa cấu hình |

Bảng là **điểm khởi đầu**, không phải luật bất biến. Một `GET /export/start` làm phát sinh job/tính phí có thể vi phạm yêu cầu safe dù dùng GET; một `POST /payments` có idempotency key hợp lệ có thể được phép retry khi phía server đã có dedup atomic.

**Đừng viết `if (status >= 500) retry` cho mọi method.** Mã 500 có thể là bug nghiệp vụ/cấu hình không cải thiện sau nhiều attempts; hơn nữa 504 không chứng minh operation chưa chạy.

## 8. Safe, idempotent và replayable khác nhau

Theo RFC 9110:

- **Safe methods**: về semantics, client không yêu cầu làm thay đổi trạng thái server. GET, HEAD, OPTIONS, TRACE được định nghĩa là safe, dù server vẫn có thể log/đếm thống kê.
- **Idempotent methods**: nhiều requests giống nhau có intended effect trên server tương đương một request. Các safe methods cùng với **PUT** và **DELETE** là idempotent theo định nghĩa HTTP semantics.
- **Không mặc định idempotent**: POST và PATCH (trừ khi server thiết kế semantics/idempotency riêng).

### Ví dụ GET

`GET /catalog/items/42` chỉ đọc một item. Khi socket reset sau khi gửi request, gọi lại thường không tạo dữ liệu mới. Tuy vậy:
- API server phải tuân thủ semantics.
- Request có thể chứa one-time token hoặc counter không đáng lặp.
- Retry vẫn tiêu tốn quota và có thể đẩy server đang yếu vào overload.

### Ví dụ PUT

`PUT /users/42` với resource representation và cùng ETag/precondition có thể được coi idempotent theo intended effect. Nhưng:
- Nếu yêu cầu dùng `If-Match`, retry sau khi lần đầu thành công có thể trả **412** vì version đã thay đổi. Điều đó không có nghĩa trạng thái cuối sai; cần logic nghiệp vụ/ETag để diễn giải.
- Upload body phải replayable.
- Một server implement "PUT tăng số lần truy cập có tính phí" không tuân thủ semantics mong muốn; không tin method name hơn hợp đồng thật.

### Ví dụ DELETE

`DELETE /resources/42` hai lần thường có desired effect "resource không còn tồn tại". Lần 2 có thể trả 404 trong khi lần 1 thành công: **idempotency không có nghĩa responses giống hệt nhau**. Nếu backend phát sinh side effect phi idempotent khi DELETE, phải sửa contract hoặc tắt retry.

### Ví dụ POST thanh toán

`POST /payments` tạo charge. Nếu client timeout ngay sau gửi, request **có thể đã được ghi**; retry có thể charge hai lần. Không retry tự động chỉ vì mã 503/timeout. Có thể dùng server-supported Idempotency-Key và lưu kết quả dedup, nhưng yêu cầu bảo đảm hệ thống chứ không chỉ đặt header.

### Ba điều kiện nên có trước retry

1. **Semantically safe/idempotent hoặc được server bảo vệ bằng dedup**.
2. **Request replayable** (body không phải one-shot stream và credentials/headers còn hợp lệ).
3. **Retry budget** với max attempts, deadline, backoff và phân loại lỗi thật sự transient.

Nếu thiếu một điều kiện, **không tự retry**.

## 9. Tại sao "đã gửi nhưng chưa nhận response" nguy hiểm?

Hình dung:

```text
Client                Network                 Payment service
  | POST /payments       |                           |
  |--------------------->|-------------------------->|
  |                      |                        Ghi charge
  |                      |<--------------------------|
  |    timeout / reset   X                           |
  |                      |                           |
  | Client không biết operation đã commit hay chưa    |
  |                      |                           |
  | POST /payments lại   |                           |
  |--------------------->|-------------------------->|
  |                      |                       Charge lần 2?
```

**At-least-once attempts** không đồng nghĩa **exactly-once business effects**. Muốn chống duplicate:
- Client tạo một idempotency key ổn định cho **một logical business operation**.
- Server lưu key, request fingerprint, trạng thái đang xử lý/kết quả và trả lại kết quả đã có theo policy.
- Key phải atomic với transaction tạo side effect (hoặc có chiến lược consistency đủ mạnh).
- Cần TTL, concurrency conflict rules và tenant/user scoping.
- Client gửi lại **cùng key** khi retry **cùng operation**, không tạo key mới mỗi attempt.
- Nếu cùng key nhưng payload khác, server nên báo conflict theo contract.
- Không dựa chỉ vào reverse proxy hay Redis cache đơn giản nếu side effect commit mà dedup record thất bại.

### Key không tự mang phép màu

`Idempotency-Key: abc123` chỉ là header. Nếu server không triển khai lưu và kiểm tra, gửi lại POST vẫn có thể tạo charge thứ hai. Nếu server chỉ ghi key sau khi DB transaction commit nhưng mất điện trước khi ghi key, còn có race. Idempotency cần thiết kế xuyên storage/transaction/broker.

Không reuse một key cho các operation khác nhau. Không gửi key nhạy cảm trong URL. Giới hạn TTL, entropy và scope; tránh cho client đoán key của user khác rồi lấy cached response.

## 10. Retry-After: server yêu cầu đợi bao lâu?

`Retry-After` có hai dạng HTTP phổ biến:

1. **delta-seconds**: `Retry-After: 5` — đợi ít nhất 5 giây.
2. **HTTP-date**: `Retry-After: Wed, 21 Oct 2026 15:00:00 GMT` — thời điểm có thể thử lại.

Dạng HTTP-date chịu ảnh hưởng clock skew giữa client/server; parser cần dùng RFC 1123/HTTP-date hợp lệ và đưa giá trị âm về 0 khi thời điểm đã qua.

Một server có thể gửi 429 hoặc 503 kèm Retry-After. Nếu giá trị yêu cầu **lâu hơn budget mà client có**, lựa chọn hợp lý là **không retry trong call đó**, chuyển failure cho caller/circuit breaker hoặc lập lịch công việc bên ngoài; **không** bí mật rút ngắn Retry-After rồi spam server.

Retry-After không phải lệnh bắt buộc rằng mọi request sẽ thành công sau khi chờ. Các policies về auth, idempotency, deadline và server quota vẫn quyết định cuối cùng.

### Khi Retry-After thiếu

Có thể dùng **exponential backoff + jitter**. Với base 100 ms và max 2 s, các attempts có thể được đợi theo những khoảng tăng dần nhưng ngẫu nhiên (full jitter) để tránh hàng nghìn clients đồng loạt đánh lại đúng một nhịp.

Đừng dùng `Thread.sleep(100)` trong vòng lặp vô hạn. Một request đồng bộ giữ một thread trong thời gian sleep; ở server chịu tải, chiến lược này phải có giới hạn thấp hoặc chuyển sang queue/async processing.

## 11. Retry budget và nguy cơ retry storm

Một service call có thể có nhiều tầng retries:

```text
Browser retry 2 lần
   |
   v
API gateway retry 3 lần
   |
   v
Application retry 3 lần
   |
   v
Load balancer retry 2 lần
   |
   v
Downstream dependency
```

Trong worst case, một logical action có thể tạo **2 × 3 × 3 × 2 = 36 attempts** ở downstream. Nếu downstream đang overload, retries có thể làm sự cố nặng hơn. Đó là lý do:
- Đặt **retry ở một tầng sở hữu rõ** nếu có thể.
- Giới hạn **max attempts**, bao gồm attempt đầu tiên.
- Giới hạn **per-call deadline** (connect + read + sleeps + attempts).
- Giới hạn **retry concurrency/budget** cho toàn process, không chỉ từng request.
- Tôn trọng 429/503 Retry-After và health signals.
- Dùng circuit breaker, bulkhead, rate limit khi thích hợp.
- Có telemetry phân biệt logical requests và raw attempts.

**Không hứa một total timeout = readTimeout**: readTimeout thường áp cho một giai đoạn network I/O, không nhất thiết bao gồm DNS, queue wait, nhiều attempts và sleeps. Deadline end-to-end phải đo/tính riêng.

## 12. Thiết kế ba tầng trong Spring

Kiến trúc gọn, dễ test:

```text
OrderFacade / business operation
   |
   +--> CatalogGateway.get(id) -- gọi RetryExecutor cho GET
   |                                 |
   |                                 +--> RestClient.get().retrieve()
   |
   +--> PaymentGateway.create(...) -- không auto retry POST
                                     |
                                     +--> RestClient.post().retrieve()

RestClient configuration
   +--> baseUrl
   +--> connect/read timeouts
   +--> ClientHttpRequestInterceptor (trace/log an toàn)
   +--> request factory
   +--> codecs / Jackson
   +--> status handling theo từng operation
```

**Phân chia trách nhiệm:**
- Interceptor: trace attempt, header từ cấu hình tin cậy, metrics/diagnostics.
- Gateway method: biết URL, DTO, domain status, operation semantics.
- RetryExecutor: biết lỗi retryable, method whitelist, budget, backoff, Retry-After.
- Business service: quyết định nếu thiếu resource, conflict, authorization hay cần idempotency key.
- Server downstream: thực sự bảo đảm dedup/transactions khi cho retry unsafe method.

Không đưa tên operation/payment vào retry utility bằng `if (path.startsWith("/payments"))`; truyền policy tường minh tốt hơn string matching path.

## 13. Dự án Maven hoàn chỉnh — Java 17, Spring Boot 3.3.5

Demo dùng `RestClient` gọi một upstream catalog giả định. Runtime có:
- `SimpleClientHttpRequestFactory` với connect/read timeout cụ thể.
- `ClientHttpRequestInterceptor` gắn `X-Client-Attempt-Id` per attempt và log method/status/duration.
- `RetryExecutor` chỉ cho `GET`/`HEAD`; lỗi transport/408/429/502/503/504 được cân nhắc.
- Backoff ngẫu nhiên bounded và hỗ trợ `Retry-After` dạng seconds/HTTP-date; nếu server yêu cầu đợi quá budget, dừng retry.
- `CatalogGateway` có `get` an toàn theo policy và `create` POST **không retry**.
- Unit/integration-style client tests với `MockRestServiceServer` và không cần gọi Internet.

**Giới hạn chủ động của demo:** Không có transaction/idempotency-key server hay distributed retry budget. `ResourceAccessException` được coi có thể transient trong demo **chỉ cho GET/HEAD**; sản phẩm thật cần phân loại TLS certificate/DNS configuration failures không đáng thử lại. Deadline tổng, bulkhead/circuit breaker và metrics phải bổ sung tùy workload.

### 13.1. Cấu trúc project

```text
sync-http-retry-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/syncclient/
    │   │   ├── SyncClientApplication.java
    │   │   ├── HttpClientConfig.java
    │   │   ├── CatalogItem.java
    │   │   ├── CatalogDraft.java
    │   │   ├── RetryExecutor.java
    │   │   └── CatalogGateway.java
    │   └── resources/application.properties
    └── test/java/example/syncclient/
        └── CatalogGatewayTest.java
```

### 13.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>sync-http-retry-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot Web starter cung cấp Spring Web, Jackson và logging. `spring-boot-starter-test` cung cấp JUnit 5, `MockRestServiceServer` và Spring MVC test utilities. **Không cần WebFlux starter** để có RestClient.

### 13.3. Application class

**`src/main/java/example/syncclient/SyncClientApplication.java`**

```java
package example.syncclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SyncClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(SyncClientApplication.class, args);
    }
}
```

Đây là Spring Boot app hoàn chỉnh. Không định nghĩa `CommandLineRunner` tự động gọi catalog giả định: chạy server không có nghĩa bắt buộc phải kết nối Internet. Code client được gọi từ service hoặc tests khi cần.

### 13.4. Cấu hình URL

**`src/main/resources/application.properties`**

```properties
catalog.base-url=https://catalog.example.test
```

Domain `example.test` là placeholder hợp lệ cho demo, **không phải dịch vụ catalog đang hoạt động**. Các bài test dùng MockRestServiceServer nên vẫn chạy offline. Trong production, dùng environment-specific trusted base URL qua application config/secrets management; không lấy host từ request của người dùng để tránh SSRF.

### 13.5. Cấu hình RestClient và interceptor

**`src/main/java/example/syncclient/HttpClientConfig.java`**

```java
package example.syncclient;

import java.io.IOException;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {

    private static final Logger log =
            LoggerFactory.getLogger(HttpClientConfig.class);

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            Environment environment) {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(3_000);

        ClientHttpRequestInterceptor interceptor =
                (request, body, execution) -> {
                    // Mỗi attempt có một ID riêng.
                    request.getHeaders().set(
                            "X-Client-Attempt-Id",
                            UUID.randomUUID().toString());

                    long start = System.nanoTime();
                    try {
                        ClientHttpResponse response =
                                execution.execute(request, body);

                        long elapsedMs =
                                (System.nanoTime() - start)
                                        / 1_000_000;

                        log.info(
                                "catalog method={} status={} durationMs={}",
                                request.getMethod(),
                                response.getStatusCode().value(),
                                elapsedMs);

                        return response;
                    } catch (IOException error) {
                        log.warn(
                                "catalog method={} transportError={}",
                                request.getMethod(),
                                error.getClass().getSimpleName());
                        throw error;
                    }
                };

        String baseUrl = environment.getProperty(
                "catalog.base-url",
                "https://catalog.example.test");

        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .requestInterceptor(interceptor)
                .build();
    }
}
```

**Vì sao interceptor này an toàn hơn "logging interceptor" thường thấy?**

- Một attempt gọi `execution.execute(request, body)` **một lần**.
- Header `X-Client-Attempt-Id` thay đổi theo attempt để điều tra network logs; **nó không phải Idempotency-Key**.
- Không log body/URL query/authentication headers.
- Log method/status/duration từ metadata ít nhạy cảm.
- Interceptor không tự retry. Khi retry boundary chạy một request mới, interceptor được gọi lại, tạo attempt ID mới.
- `ClientHttpResponse` được return cho RestClient xử lý/đóng theo flow bình thường. Nếu interceptor **đã nhận response rồi tự throw**, nó phải đóng response trước khi throw theo contract API; đoạn này không throw sau khi đã có response.
- Cấu hình timeout ở request factory giúp request đồng bộ không chờ vô hạn ở một số giai đoạn cơ bản.

**Hạn chế:** `SimpleClientHttpRequestFactory` dựa trên JDK URLConnection; ứng dụng production có thể chọn Apache HttpClient/JDK HttpClient request factory và connection pooling/TLS/proxy settings phù hợp. Connect/read timeout **không tự là tổng deadline**. Nếu có RestClient interceptors khác do Boot customizers cài sẵn, kiểm tra thứ tự/headers và không vô hiệu hóa instrumentation ngoài ý muốn.

### 13.6. DTO records

**`src/main/java/example/syncclient/CatalogItem.java`**

```java
package example.syncclient;

public record CatalogItem(long id, String name) {}
```

**`src/main/java/example/syncclient/CatalogDraft.java`**

```java
package example.syncclient;

public record CatalogDraft(String name) {}
```

Jackson trong Spring Boot xử lý Java records theo DTO. `CatalogDraft` không có validation framework ở demo vì trọng tâm là HTTP client; trong sản phẩm thật cần validate input trước khi gọi upstream và xử lý response schema/versions.

### 13.7. RetryExecutor: whitelist GET/HEAD, max 3 attempts

**`src/main/java/example/syncclient/RetryExecutor.java`**

```java
package example.syncclient;

import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class RetryExecutor {

    @FunctionalInterface
    public interface Sleeper {
        void sleep(Duration delay) throws InterruptedException;
    }

    private static final Duration MAX_DELAY =
            Duration.ofSeconds(2);

    private final int maxAttempts;
    private final Sleeper sleeper;

    public RetryExecutor(int maxAttempts, Sleeper sleeper) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.sleeper = sleeper;
    }

    public <T> T execute(
            HttpMethod method,
            Supplier<T> action) {

        // Demo chỉ tự retry hai phương thức đọc an toàn.
        // PUT/DELETE có thể idempotent theo HTTP nhưng cần
        // xác minh replayable body và upstream contract riêng.
        if (method != HttpMethod.GET &&
                method != HttpMethod.HEAD) {
            return action.get();
        }

        for (int attempt = 1; ; attempt++) {
            try {
                return action.get();
            } catch (RestClientException error) {
                if (attempt >= maxAttempts
                        || !isRetryable(error)) {
                    throw error;
                }

                Duration wait = delayFor(attempt, error);

                // Retry-After quá dài -> bỏ cuộc,
                // KHÔNG thử lại sớm hơn server yêu cầu.
                if (wait.compareTo(MAX_DELAY) > 0) {
                    throw error;
                }

                try {
                    sleeper.sleep(wait);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Retry interrupted", interrupted);
                }
            }
        }
    }

    private boolean isRetryable(RestClientException error) {
        if (error instanceof ResourceAccessException) {
            // Chỉ cho read-only GET/HEAD; production cần
            // lọc DNS/certificate/configuration failures.
            return true;
        }

        if (error instanceof RestClientResponseException http) {
            int code = http.getStatusCode().value();
            return code == 408 || code == 429
                    || code == 502 || code == 503
                    || code == 504;
        }

        return false;
    }

    private Duration delayFor(
            int attempt,
            RestClientException error) {

        Duration requested = retryAfter(error);
        if (requested != null) {
            return requested;
        }

        // Full jitter, exponential growth, giới hạn nhỏ.
        int shift = Math.min(attempt - 1, 3);
        long upperMs = Math.min(400L, 50L << shift);
        long chosenMs = ThreadLocalRandom.current()
                .nextLong(upperMs + 1);
        return Duration.ofMillis(chosenMs);
    }

    private Duration retryAfter(RestClientException error) {
        if (!(error instanceof RestClientResponseException http)) {
            return null;
        }

        HttpHeaders headers = http.getResponseHeaders();
        if (headers == null) {
            return null;
        }

        String raw = headers.getFirst(HttpHeaders.RETRY_AFTER);
        if (raw == null || raw.isBlank()) {
            return null;
        }

        String value = raw.trim();
        try {
            long seconds = Long.parseLong(value);
            if (seconds < 0) {
                return null;
            }
            return Duration.ofSeconds(seconds);
        } catch (NumberFormatException ignored) {
            // HTTP-date thay cho delta-seconds.
        }

        try {
            Instant when = ZonedDateTime.parse(
                    value, DateTimeFormatter.RFC_1123_DATE_TIME)
                    .toInstant();
            Duration remaining = Duration.between(
                    Instant.now(), when);
            return remaining.isNegative()
                    ? Duration.ZERO
                    : remaining;
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }
}
```

### Giải thích chính sách của RetryExecutor

1. Chỉ `GET`/`HEAD` được xét retry tự động. **PUT/DELETE** dù idempotent theo HTTP vẫn bị tắt trong demo vì phải xác minh replayable request body và per-operation contract.
2. `maxAttempts = 3` nghĩa **tối đa 3 HTTP attempts gồm attempt đầu tiên**, không phải 1 + 3 retries.
3. `ResourceAccessException` được xem là candidate transient chỉ khi method safe; điều này vẫn quá rộng cho production nếu có TLS cert hoặc DNS misconfiguration.
4. Với HTTP status, chỉ chọn 408, 429, 502, 503, 504; 400/401/403/404/409/412/422/500 không được retry mặc định.
5. `Retry-After` dạng seconds hoặc RFC 1123 date được ưu tiên. Nếu yêu cầu đợi quá **2 giây per-backoff budget**, code **dừng** thay vì retry trước hạn.
6. Khi không có Retry-After, dùng exponential backoff nhỏ có full jitter. Số thực có thể thay đổi mỗi lần; tests không assert một delay tuyệt đối.
7. Interrupted thread được restore flag; không swallow interruption rồi tiếp tục HTTP call.
8. Retry wrapper ở ngoài RestClient: mỗi attempt đi qua interceptor, transport, status handlers như một request mới.
9. **Không có tổng deadline tuyệt đối** trong code demo; trong production nên thêm total budget và tính cả attempt time. Với 3 seconds read timeout trên mỗi attempt, tổng thời gian có thể vượt nhiều giây.
10. `Thread.sleep` ở Sleeper implementation là blocking **có chủ đích** vì bài nói về synchronous client; không dùng utility này trên Reactor Netty event loop hoặc task executor không đủ threads.

### Một điểm về HTTP-date và clock skew

`Instant.now()` lấy clock máy client. Nếu đồng hồ lệch, HTTP-date có thể dẫn tới duration không chính xác. Production có thể dùng injected `Clock` và cân nhắc HTTP `Date` header/time skew, nhưng không bao giờ nên coi một server-supplied date rất xa là lý do giữ thread ngủ hàng giờ. Với budget nhỏ, code chọn fail-fast.

### Khi nào mở rộng policy?

Khi upstream xác nhận PUT/DELETE replay-safe và có body có thể tái tạo, hãy truyền một **operation-level policy** thay vì chỉ sửa whitelist toàn app. Với POST được bảo vệ bằng Idempotency-Key, policy phải được bật cụ thể ở method đó và server có dedup atomic; không bật retry toàn bộ POST vì một endpoint hỗ trợ key.

### 13.8. Đăng ký RetryExecutor với Spring

Thêm Bean vào chính class cấu hình **`HttpClientConfig.java`** ở mục 13.5, trước dấu ngoặc đóng class:

```java
@Bean
RetryExecutor catalogRetryExecutor() {
    return new RetryExecutor(
            3,
            delay -> Thread.sleep(delay.toMillis()));
}
```

Đây là **đoạn bổ sung đặt vào class `HttpClientConfig`**, không phải một source file độc lập. Class config đã import `Bean`. Vì `RetryExecutor` và config cùng package, không cần import type đó. Trong production, config max attempts/backoff từ validated properties chứ không hardcode.

### 13.9. CatalogGateway: retry GET, không retry POST

**`src/main/java/example/syncclient/CatalogGateway.java`**

```java
package example.syncclient;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogGateway {

    private final RestClient client;
    private final RetryExecutor retry;

    public CatalogGateway(
            RestClient catalogRestClient,
            RetryExecutor catalogRetryExecutor) {
        this.client = catalogRestClient;
        this.retry = catalogRetryExecutor;
    }

    public CatalogItem get(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "id must be positive");
        }

        return retry.execute(HttpMethod.GET, () -> {
            CatalogItem item = client.get()
                    .uri("/items/{id}", id)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(CatalogItem.class);

            if (item == null) {
                throw new IllegalStateException(
                        "Empty catalog response");
            }
            return item;
        });
    }

    public void create(CatalogDraft draft) {
        if (draft == null || draft.name() == null
                || draft.name().isBlank()) {
            throw new IllegalArgumentException(
                    "name required");
        }

        // POST cố ý chỉ thực hiện MỘT attempt.
        // Retry chỉ khi server có Idempotency-Key
        // contract và client giữ ổn định key.
        client.post()
                .uri("/items")
                .contentType(MediaType.APPLICATION_JSON)
                .body(draft)
                .retrieve()
                .toBodilessEntity();
    }
}
```

**Tại sao không catch 404 và gọi lại?** HTTP 404 thường là kết quả cuối cho resource không tồn tại. Caller có thể chuyển thành domain "catalog item not found", không cần retry. Nếu `get` nhận 503 và policy cho phép, RetryExecutor tự chạy lại tối đa 3 attempts.

**Tại sao POST không retry dù trả 503?** Upstream có thể đã tạo item nhưng reverse proxy trả 503 hoặc response bị mất. Chỉ khi catalog API có idempotency/dedup contract thật mới xem xét bật retry có key ổn định.

### Bước dùng code demo

- `mvn test`: chạy tests với mock upstream, không cần kết nối mạng đến domain giả.
- `mvn spring-boot:run`: khởi động app bình thường; Bean RestClient trỏ tới demo catalog URL chỉ **khi có code gọi CatalogGateway**. Domain `example.test` không phục vụ API thật.
- Khi tích hợp dịch vụ catalog thật, cấu hình `catalog.base-url` tới trusted endpoint và gọi `CatalogGateway` từ business service; không gửi host tùy ý từ client.

## 14. MockRestServiceServer: kiểm tra số lần thử thật

`MockRestServiceServer` mô phỏng downstream HTTP responses mà **không mở socket thật**. Nó cho phép assert:
- Method, URI, headers mà RestClient gửi.
- Mã status trả về trên từng attempt.
- Có đúng 1 hay 3 request.
- DTO response được decode.
- Retry-After dài có làm dừng retry không.
- POST và HTTP lỗi không phù hợp có tránh retry không.

### 14.1. Test file đầy đủ

**`src/test/java/example/syncclient/CatalogGatewayTest.java`**

```java
package example.syncclient;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogGatewayTest {

    private MockRestServiceServer server;
    private CatalogGateway gateway;
    private RetryExecutor retries;

    @BeforeEach
    void prepare() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test")
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Client-Attempt-Id", "from-test");
                    return execution.execute(request, body);
                });

        server = MockRestServiceServer.bindTo(builder).build();

        // Không ngủ thật trong unit tests.
        retries = new RetryExecutor(
                3,
                duration -> { });

        gateway = new CatalogGateway(builder.build(), retries);
    }

    @Test
    void get200ReturnsDecodedDtoAndInterceptorHeader() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Client-Attempt-Id", "from-test"))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Pen\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals(new CatalogItem(7, "Pen"),
                gateway.get(7));
        server.verify();
    }

    @Test
    void get503Then200RetriesExactlyOnce() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/8"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        server.expect(requestTo(
                    "https://catalog.example.test/items/8"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":8,\"name\":\"Notebook\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals("Notebook", gateway.get(8).name());
        server.verify();
    }

    @Test
    void get429Then200CanRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/9"))
                .andRespond(withStatus(
                        HttpStatus.TOO_MANY_REQUESTS)
                        .header("Retry-After", "0"));

        server.expect(requestTo(
                    "https://catalog.example.test/items/9"))
                .andRespond(withSuccess(
                        "{\"id\":9,\"name\":\"Ruler\"}",
                        MediaType.APPLICATION_JSON));

        assertEquals("Ruler", gateway.get(9).name());
        server.verify();
    }

    @Test
    void get404DoesNotRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/11"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(11));
        server.verify();
    }

    @Test
    void get400DoesNotRetry() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/12"))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(12));
        server.verify();
    }

    @Test
    void get500DoesNotRetryByThisPolicy() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/13"))
                .andRespond(withStatus(
                        HttpStatus.INTERNAL_SERVER_ERROR));

        assertThrows(HttpServerErrorException.class,
                () -> gateway.get(13));
        server.verify();
    }

    @Test
    void get502ExhaustsThreeAttempts() {
        for (int n = 0; n < 3; n++) {
            server.expect(requestTo(
                        "https://catalog.example.test/items/14"))
                    .andExpect(method(HttpMethod.GET))
                    .andRespond(withStatus(
                            HttpStatus.BAD_GATEWAY));
        }

        assertThrows(HttpServerErrorException.class,
                () -> gateway.get(14));
        server.verify();
    }

    @Test
    void tooLongRetryAfterSkipsFurtherAttempts() {
        server.expect(requestTo(
                    "https://catalog.example.test/items/15"))
                .andRespond(withStatus(
                        HttpStatus.TOO_MANY_REQUESTS)
                        .header("Retry-After", "30"));

        assertThrows(HttpClientErrorException.class,
                () -> gateway.get(15));
        server.verify();
    }

    @Test
    void post503MustNotBeRetried() {
        server.expect(requestTo(
                    "https://catalog.example.test/items"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        assertThrows(HttpServerErrorException.class,
                () -> gateway.create(
                        new CatalogDraft("Keyboard")));
        server.verify();
    }

    @Test
    void retryExecutorWillNotRetryPostEvenForIoError() {
        AtomicInteger calls = new AtomicInteger();

        assertThrows(ResourceAccessException.class,
                () -> retries.execute(HttpMethod.POST, () -> {
                    calls.incrementAndGet();
                    throw new ResourceAccessException(
                            "simulated socket reset");
                }));

        assertEquals(1, calls.get());
    }

    @Test
    void retryExecutorCanRetryIoErrorForGet() {
        AtomicInteger calls = new AtomicInteger();

        String value = retries.execute(HttpMethod.GET, () -> {
            int n = calls.incrementAndGet();
            if (n == 1) {
                throw new ResourceAccessException(
                        "simulated transient I/O error");
            }
            return "ok";
        });

        assertEquals("ok", value);
        assertEquals(2, calls.get());
    }
}
```

**11 test methods**, không ngủ thật nhờ injected `Sleeper` no-op. Mỗi `server.expect(...)` tạo kỳ vọng về **một** request; `server.verify()` xác nhận mọi expectations đã được thực hiện. Nếu RetryExecutor lặp một request 404, 400, 500 hoặc POST không đúng policy, test sẽ thất bại vì có request ngoài expectations.

### Cần đọc kỹ assertions

- Test 503→200 và 429→200: xác nhận transient response và successful retry.
- Test 502 exhausted: có ba HTTP attempts đúng bằng max attempts.
- Test 404/400/500: fail ngay, không sinh request thứ hai.
- Test Retry-After 30 giây: vì per-backoff budget chỉ 2 giây, code **không retry**; không chờ 2 giây rồi gửi request vi phạm chỉ dẫn 30 giây.
- Test POST 503: client **chỉ gửi một POST** vì không có idempotency server contract.
- Test transport exception GET: policy minh họa cho retry read-only.
- Test transport exception POST: ngay cả khi chưa có HTTP status, thao tác unsafe vẫn không được lặp.
- Test header: chứng minh interceptor chạy và thêm request metadata, không cần ngủ hoặc kết nối Internet.

### Ghi chú runtime QA

Mã được biên soạn để phù hợp Java 17, Spring Boot 3.3.5, Spring Framework 6.1 và các APIs `MockRestServiceServer.bindTo(RestClient.Builder)`. Trong phạm vi tạo Knowledge trên Google Sheets, **không có bước chạy Maven trên workspace**; đây là ví dụ cần người triển khai chạy `mvn test` với toolchain đã cài. Không coi phần mô tả expected assertions là kết quả test đã thực thi.

### Kiểm thử bổ sung cần cho production

- HTTP-date Retry-After với injected Clock và time skew.
- Read timeout xảy ra sau khi server đã nhận request.
- TLS certificate errors và DNS configuration failures được đánh dấu nonretryable.
- Redirect policy, bảo toàn Authorization và tránh redirect cross-host.
- Body replayability khi retry PUT/POST; streaming upload.
- Connect/read timeout thực với local test server, không chỉ MockRestServiceServer.
- Tổng retry budget khi một attempt treo 3 giây và nhiều sleeps.
- Pool exhaustion và bulkhead behavior dưới concurrent load.
- Idempotency-Key end-to-end với server atomic dedup và parallel duplicate submits.
- Partial success/business 409/412 behavior.
- Observability: logical request vs attempt spans và masking PII.
- Proxy, mTLS, rate limit, circuit breaker, client cancellation/interruption.

## 15. Một ví dụ xử lý 404 thành Optional thay vì exception

Nếu application contract coi missing catalog item là expected outcome, có thể dùng `exchange`:

```java
Optional<Boolean> result = client.head()
        .uri("/items/{id}", id)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            if (status == 404) {
                return Optional.empty();
            }
            if (status >= 200 && status < 300) {
                return Optional.of(Boolean.TRUE);
            }
            throw new IllegalStateException(
                    "Unexpected upstream status " + status);
        });
```

Đây là snippet với `client`/`id` đã có và import `Optional`. Nó thể hiện cách **không dùng default retrieve() exceptions** khi muốn kiểm soát status trực tiếp. Không làm `if (status >= 400) return Optional.empty()` vì sẽ che 429/503 thành "resource không có".

**Quan trọng:** snippet này không có retry. Nếu muốn retry sau `exchange`, phải chuyển status 429/502/503/504 thành typed error hoặc custom result có retry metadata mà RetryExecutor hiểu. Mọi error mapping thay đổi tác động đến retry policy.

Với `RestClient.retrieve()`, nếu 404 là expected, có thể dùng `onStatus` để throw domain exception riêng rồi xử lý ở caller. Đó là lựa chọn API semantics, không có một cách áp dụng đúng cho mọi client.

## 16. RestTemplate: interceptor và ResponseErrorHandler

Trong codebase dùng `RestTemplate`:

```java
RestTemplate restTemplate = new RestTemplate();

restTemplate.setInterceptors(
        List.of((request, body, execution) -> {
            request.getHeaders().set(
                    "X-Caller-Service", "inventory");
            return execution.execute(request, body);
        }));

restTemplate.setErrorHandler(
        new DefaultResponseErrorHandler());
```

Snippet cần imports `List`, `RestTemplate`, `DefaultResponseErrorHandler`. Handler mặc định đã thường có sẵn; dòng `setErrorHandler` ở đây để minh họa điểm cấu hình. Nó xử lý 4xx/5xx theo template semantics; custom implementation có thể đổi cách phân loại.

Nếu muốn chuyển sang RestClient mà giữ cấu hình nền từ template:

```java
RestClient client = RestClient.builder(restTemplate)
        .build();
```

Đây là API supported, giúp lấy một số cấu hình RestTemplate vào builder (request factory, converters, interceptors, URI settings, error handler). Sau migrate phải test thứ tự interceptors, status exceptions, client metrics và retry counts; không giả định behavior tuyệt đối giống nhau với mọi custom RestTemplate extension.

### ResponseErrorHandler custom

`ResponseErrorHandler` có `hasError(ClientHttpResponse)` và `handleError(...)`. Hãy phân biệt:
- Custom handler chỉ thay status-to-error mapping.
- Không tự biết operation nào idempotent.
- Không tự cung cấp retry/backoff.
- Nếu handler chỉ swallow 503, caller có thể cố parse 503 body thành DTO success.

Vì vậy, vẫn để retry policy ở tầng operation/service, không nhúng retries vào `handleError`.

## 17. Timeout: connect, response/read và toàn call

Một synchronous HTTP call tiêu tốn thread khi:
- Chờ connection/DNS/TLS.
- Chờ server response.
- Đọc body bytes.
- Ngủ backoff rồi gửi attempt khác.

`SimpleClientHttpRequestFactory.setConnectTimeout(2_000)` và `setReadTimeout(3_000)` giúp đặt một số giới hạn thấp của transport. Tuy nhiên:
- DNS resolution có thể có behavior khác.
- Một response stream chuyển dữ liệu ít một có thể giữ tổng request lâu hơn read timeout mỗi lần chờ.
- TLS handshake/proxy timeout có thể cần config client implementation riêng.
- Connection pool wait không phải lúc nào cũng tính vào connect timeout.
- Ba attempts có thể mất xấp xỉ ba lần timeout cộng backoffs.

**Per-request timeout khác end-to-end deadline.** Nếu HTTP handler phía trên có deadline 2 giây nhưng retry wrapper có thể giữ thread tới 10 giây, request trên server sẽ vượt budget. Production cần tổng deadline từ caller, cancel/timeout policy đúng client implementation và resource pool.

### Không ngủ rất lâu trong thread của synchronous API

Nếu server gửi `Retry-After: 120`, có hai phương án:
1. Chuyển failure/metadata cho higher layer và không retry inline.
2. Lên lịch lại công việc qua durable queue/job scheduler nếu nhiệm vụ cho phép.

Không giữ một Tomcat request thread ngủ 120 giây chỉ để thử lại GET. Nếu caller thực sự là batch worker với ít concurrency, policy có thể khác; nhưng vẫn cần giới hạn.

## 18. Exponential backoff, jitter và các biến số

Công thức backoff thông dụng:

\[
B_n = \min(B_{\max}, B_0 \cdot 2^{n-1})
\]

Với full jitter:

\[
W_n \sim U(0,B_n)
\]

Trong đó:
- `n` là số attempt vừa thất bại (attempt đầu n=1).
- `B0` là base delay.
- `Bmax` là cap.
- `Wn` được chọn ngẫu nhiên trong khoảng từ 0 đến Bn.

Ví dụ base 100ms/cap 1.000ms:

| Lỗi sau attempt | Upper bound không jitter | Một delay hợp lệ |
| --- | --- | --- |
| 1 | 100 ms | 74 ms |
| 2 | 200 ms | 11 ms |
| 3 | 400 ms | 205 ms |
| 4 | 800 ms | 690 ms |
| 5 | 1000 ms | 447 ms |

Các delays bên phải **chỉ là ví dụ**, không phải output cố định khi chạy code. Jitter phân tán các requests của nhiều clients, tránh đồng bộ "thundering herd". **Không** dùng random jitter để phớt lờ `Retry-After` lớn hơn.

### Retry budget theo số lượng và thời gian

`maxAttempts=3` là giới hạn lần gọi, nhưng chưa đủ. Nếu mỗi attempt 10 giây và sleep 2 giây, một logical request có thể giữ thread >30 giây. Cần:
- Per-attempt connect/read timeout.
- Absolute deadline/remaining budget truyền từ caller.
- Limit tổng queue/concurrency.
- Budget thống nhất với gateway/client khác.
- Metrics logical latency và number-of-attempts.

### Circuit breaker khác retry

Retry phù hợp với lỗi tạm thời ngắn. Circuit breaker dừng gọi upstream khi nó đang fail/overloaded thường xuyên; bulkhead giới hạn số concurrent requests; rate limiter ngăn tạo quá nhiều load. Đây là các cơ chế **bổ sung**, không nên cấu hình để tất cả cùng retry ở nhiều tầng.

## 19. Idempotency-Key: contract phía server phải xử lý ra sao?

Một pattern phổ biến với POST create:

```http
POST /payments HTTP/1.1
Host: payments.example.test
Content-Type: application/json
Idempotency-Key: 2fb18684-1dbd-484e-b188-87dc29d4dace

{"orderId":"order-1024","amount":1500}
```

Key là minh họa. Hệ thống thật cần:
1. Validate principal/tenant và quy tắc tạo payment.
2. Khóa/deduplicate cùng key **theo tenant+operation scope**.
3. So sánh payload fingerprint; cùng key khác payload phải conflict.
4. Với first request, ghi side effect và result theo transaction/consistency policy.
5. Với retry cùng key, trả lại outcome có contract rõ (same status/body hoặc status retrieval).
6. Với concurrent identical submissions, chỉ một request thực hiện side effect; các request khác nhận cached result/in-progress status.
7. Có TTL phù hợp với client retry window; TTL hết rồi key có thể lại được xem như mới.
8. Có metrics/audit, không lộ kết quả operation của user khác.

Một client có thể gắn key qua:

```java
UUID logicalOperationId = UUID.randomUUID();

client.post()
        .uri("/payments")
        .header(
                "Idempotency-Key",
                logicalOperationId.toString())
        .body(paymentRequest)
        .retrieve()
        .toBodilessEntity();
```

Đây là **snippet không triển khai retries** và sử dụng biến `client`/`paymentRequest` giả định. Khi nghiệp vụ quyết định retry cùng logical operation, phải **giữ nguyên logicalOperationId** qua mọi attempts — đừng sinh UUID mới bên trong interceptor cho mỗi attempt.

**Không tự bật retry POST chỉ nhờ snippet này.** Nếu payment server không có idempotency-key handling, header không giúp chống duplicate. Và nếu body streaming không replayable, client còn phải tái tạo bytes cho mỗi attempt.

## 20. Observability: logical request vs từng attempt

Một logical operation có thể tạo ba physical HTTP attempts. Nên có hai cấp telemetry:

```text
Logical operation: catalog.get(id=42)
   |
   +-- attempt=1, status=503, duration=350ms
   +-- wait=100ms
   +-- attempt=2, status=502, duration=120ms
   +-- wait=200ms
   +-- attempt=3, status=200, duration=80ms
   |
   +-- finalOutcome=SUCCESS
   +-- logicalLatency=850ms
```

Con số latency là ví dụ. Nếu chỉ đếm attempts, request count sẽ tăng 3x và error-rate metric có thể cao dù logical caller cuối cùng thành công. Nếu chỉ đo logical operation, bạn có thể bỏ qua 503 storms upstream.

Nên đo:
- Logical outcome và attempts-per-operation.
- Status distribution theo upstream service và endpoint **template**, không raw ID/query.
- Retries attempted/exhausted/suppressed (unsafe, nonretryable, budget expired, Retry-After too long).
- Per-attempt duration vs overall latency.
- Connect/read timeout, pool wait, response deserialization errors.
- Concurrency, circuit breaker state và load.
- Trace IDs qua frameworks như Micrometer Observation/tracing; không tự ghi raw Authorization header.

### Correlation IDs

Một request attempt có thể có ID riêng cho debugging. Logical operation nên có trace/span hoặc business correlation ID ổn định ở tầng cao hơn. **Idempotency-Key là khóa chống lặp nghiệp vụ, không đồng nghĩa trace ID**, và không nên dùng UUID per attempt làm idempotency key.

## 21. Bảo mật và privacy trong interceptor

### Không log secrets

Đặc biệt thận trọng với:
- `Authorization`/Bearer tokens.
- `Cookie` và `Set-Cookie`.
- Basic auth credentials.
- JWT claims hoặc query tokens.
- Payment/card data và nội dung body.
- Request URLs chứa customer identifiers.

Có thể log HTTP method, upstream service name, status family, duration và correlation ID đã sanitize.

### Tránh SSRF

Đừng cho caller truyền host tuyệt đối hoặc URL từ user input vào `RestClient` được phép truy cập network nội bộ. Sử dụng trusted `baseUrl`, allowlist hosts/schemes và kiểm soát redirects. Một interceptor tự động gắn Authorization vào mọi redirects/cross-host calls có thể lộ credentials nếu không có redirect/host policy phù hợp.

### TLS và certificate

Không retry lỗi certificate validation như thể upstream chỉ tạm quá tải. Không tắt hostname verification để "fix" `ResourceAccessException`. Chọn trust store, mTLS/client cert, proxy/HTTPS configuration đúng.

### Headers và duplicate authorization

Một interceptor nên tránh ghi đè các headers do secure auth mechanism thiết lập, trừ khi có chủ đích. Với Spring Security OAuth2 client, sử dụng integrations tương ứng để refresh/attach token; không tự retry 401 mãi hoặc log tokens.

## 22. Những tình huống retry thực tế

### 22.1. GET catalog 503 rồi 200

Có thể retry bounded, tốt nhất tôn trọng Retry-After. Kết quả cuối là item 200 và hai attempts. Không cần data dedup vì GET là read-only theo contract.

### 22.2. GET 404 ngay sau tạo resource

Nếu upstream eventual-consistent và contract **cho phép đọc chậm**, có thể dùng polling/backoff theo "resource readiness" trong một **workflow riêng**, không tự bật retry 404 cho mọi GET. Timeout/polling budget và visibility semantics phải rõ.

### 22.3. PUT với If-Match

PUT idempotent về intended effect, nhưng retry có thể gặp 412 do lần đầu đã commit và ETag đổi. Client cần đọc lại resource/version để xác định trạng thái cuối. Không cố retry vô hạn bằng một ETag cũ.

### 22.4. DELETE đã thành công nhưng retry trả 404

Desired state "không còn resource" có thể đã đạt. Một API contract có thể coi 404 sau retry là acceptable, hoặc có semantics riêng. Cần phân biệt business operation thành công với HTTP status trên attempt cuối.

### 22.5. POST payment timeout

Không retry nếu thiếu server idempotency contract. Nếu có key/dedup, trả lại cùng logical operation và reconcile với payment status endpoint. Không tạo key mới từng attempt.

### 22.6. 429 với Retry-After: 60

Nếu caller chỉ còn budget 3 giây, fail fast hoặc schedule lại công việc sau 60 giây. Không ngủ 3 giây rồi gửi lại, vi phạm server hint.

### 22.7. 500 do deserialization/schema mismatch

Không retry: cùng response body hỏng sẽ tiếp tục hỏng. Tách mapping errors (Jackson/DTO versioning) khỏi status 500 từ upstream, alert schema compatibility.

### 22.8. 502/504 ở API gateway

Có thể xảy ra sau khi upstream đã nhận side-effecting request. Chỉ retry nếu idempotent/replay-safe. Gateway 504 không phải bằng chứng request chưa chạy.

## 23. Kiểm thử idempotency end-to-end với fake payment server

Một unit test client POST no-retry là cần thiết nhưng **không đủ** để chứng minh exactly-once charge. Với server hỗ trợ Idempotency-Key, integration test nên:

1. Gửi cùng `Idempotency-Key` và cùng payload hai lần.
2. Xác nhận **chỉ có một** payment record/charge trong DB/ledger.
3. Xác nhận response thứ hai theo contract (same ID/result).
4. Gửi cùng key với payload khác, server trả conflict.
5. Gửi hai requests đồng thời cùng key để tìm race.
6. Mô phỏng crash giữa charge commit và dedup persistence.
7. Kiểm tra TTL/key scope theo principal/tenant.
8. Mô phỏng response loss sau commit và retry cùng key.

Nếu server chỉ trả 200 cho hai attempts mà DB có hai charge, idempotency **đã thất bại** dù HTTP response trông hợp lệ. Exactly-once business effects đòi hỏi server-side atomicity/coordination và kiểm thử dưới concurrency/failures.

## 24. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| GET 503 không retry | Caller không dùng RetryExecutor hoặc custom status handler nuốt exception | Giữ typed error, gọi retry boundary đúng operation |
| POST bị tạo hai records | Retry unsafe operation thiếu idempotency contract | Không auto retry POST; server key + atomic dedup |
| Retry vô hạn | Không maxAttempts/deadline | Bounded attempts và total budget |
| Retry quá sớm so với Retry-After | Chỉ dùng fixed sleep/backoff | Parse Retry-After và skip khi vượt budget |
| Retry 400/403 | Coi mọi 4xx transient | Fail fast và sửa input/ACL |
| Retry 500 vô ích | Bug code hoặc schema mismatch | Phân loại lỗi, đừng blanket-retry 5xx |
| 429 response không còn header | Custom exception wrapper làm mất response headers | Preserve status, Retry-After, safe diagnostics |
| 404 bị biến thành empty DTO | Swallow status trong onStatus/handler | Map missing rõ thành Optional/domain exception |
| Dùng `exchange()` nhưng đợi `onStatus` chạy | `exchange` bypass status handlers | Xử lý status trực tiếp trong callback |
| Interceptor chạy hai lần một attempt | Nhiều registrations hoặc tự execute lặp | Kiểm tra registration/chain, one execute |
| Connection pool cạn | Response interceptor ném sau khi nhận nhưng không close | Close response trước throw, monitor pool |
| Logs lộ password | Dump body/Authorization/query | Sanitize metadata, không log raw bodies |
| Một idempotency key mới mỗi retry | Tạo UUID trong interceptor | Tạo key một lần tại logical business operation |
| Cùng key nhưng hai payload khác nhau | Không kiểm tra fingerprint/server scope | Server 409/conflict rule |
| TLS cert lỗi mà client cứ retry | ResourceAccessException bị coi mọi lỗi transient | Phân loại certificate/DNS config failure |
| Total latency rất dài | Chỉ giới hạn per-attempt timeout | End-to-end deadline và budget |
| Requests đồng loạt sau sự cố | Fixed sleep, không jitter | Full jitter/backoff/rate limits |
| Retry storm qua gateway/app | Mỗi tầng retry độc lập | Chọn owner một tầng, global budget |
| Error-rate metric tăng x3 | Đếm raw attempts như logical operations | Metrics tách logical và attempts |
| Client chuyển credentials sai host | Redirect/SSRF policy thiếu | Trusted base URL, redirect allowlist |
| Blocking threads bị nghẽn | Sleep lâu trong synchronous web request | Fail fast/deferred job hoặc async architecture |
| DELETE lần 2 trả 404 gây "thất bại" | Nhầm idempotency với response equality | Kiểm tra desired state và contract |
| PUT lần 2 trả 412 | If-Match stale sau lần đầu commit | Reconcile resource/ETag |
| Retry body stream lỗi | One-shot body không replayable | Buffer giới hạn/tái tạo request body |
| Test không xác nhận số lần gọi | Chỉ assert final 200 | MockRestServiceServer.verify và expectations cụ thể |

## 25. Checklist thiết kế HTTP client đồng bộ

- [ ] Chọn đúng API `RestClient`/`RestTemplate` theo project và hỗ trợ Spring version.
- [ ] Interceptor chỉ can thiệp request/response, không tự retry mọi requests.
- [ ] Ghi metadata an toàn; không log body/secrets.
- [ ] Không để response bị leak khi interceptor ném sau HTTP response.
- [ ] Lỗi HTTP và lỗi I/O được phân biệt.
- [ ] `retrieve()`/`exchange()` semantics được hiểu và test.
- [ ] 400/401/403/404/409/412/422/429/5xx có policy cụ thể.
- [ ] Retry chỉ bật khi operation semantically safe/idempotent/replayable.
- [ ] POST/PATCH không retry mặc định; Idempotency-Key chỉ có ý nghĩa khi server hỗ trợ.
- [ ] Max attempts tính cả attempt đầu, có per-attempt timeout và deadline tổng.
- [ ] Tôn trọng Retry-After seconds/HTTP-date.
- [ ] Backoff có jitter, không vượt caller budget.
- [ ] Không có retry storm qua gateway/app/load balancer.
- [ ] Không retry TLS certificate/configuration errors như lỗi transient.
- [ ] Một logical operation có trace ID; mỗi attempt có diagnostics riêng.
- [ ] Auth token refresh bounded, không bật infinite retry 401.
- [ ] Test chính xác requests/headers/status/attempt counts bằng MockRestServiceServer.
- [ ] Test socket timeout và real HTTP transport riêng.
- [ ] Test idempotency server-side dưới concurrent duplicate requests/failure injection.
- [ ] Quan sát circuit breaker, bulkhead và metrics trước rollout production.

## 26. Bài tập thực hành

### Bài 1 — RestClient status mapping

Cho mock upstream trả 404, 429, 500 và 503. Viết ba phiên bản:
1. `retrieve()` mặc định.
2. `retrieve().onStatus(...)` ánh xạ riêng 404.
3. `exchange(...)` trả một domain result tùy status.

Chứng minh rằng `exchange(...)` **không tự kích hoạt** các status handlers của retrieve và phải giữ đúng retry metadata khi cần.

### Bài 2 — Retry 503 với Retry-After

Mock GET trả 503 + `Retry-After: 0`, sau đó 200. Bảo đảm có **hai** attempts. Đổi Retry-After thành 30 seconds, budget 2 seconds: chỉ **một** attempt. Không sleep thật trong test; inject Sleeper và capture requested delays.

### Bài 3 — Lựa chọn method

Cho GET, HEAD, PUT, DELETE, POST và PATCH cùng gặp socket reset. Với RetryExecutor demo, chỉ GET/HEAD tự retry. Giải thích vì sao PUT/DELETE idempotent theo RFC nhưng cần chính sách riêng về body replayability/preconditions/server semantics trước khi bật.

### Bài 4 — Payment Idempotency-Key

Tạo một server giả có DB và unique constraint theo tenant + key. Gửi cùng key/payload hai lần, trả cùng payment ID. Gửi key đó với payload khác, trả conflict. Chạy hai requests đồng thời để tìm race; xử lý crash/TTL và không leak kết quả giữa các tenants.

### Bài 5 — Chặn retry storm

Mô phỏng gateway retry 2 lần và application retry 3 lần. Đo raw downstream attempts so với logical calls. Chọn một retry owner, thêm circuit breaker và budget; kiểm tra attempts giảm.

### Bài 6 — Phân loại I/O error

Giả lập connect timeout, connection reset, certificate validation failure và DNS configuration error. Cho một GET safe, quyết định lỗi nào đáng retry và lỗi nào fail fast. Đừng chỉ dùng `instanceof ResourceAccessException` cho mọi tình huống production.

### Bài 7 — Logging an toàn

Thêm interceptor logging method/status/latency/correlation ID. Assert logs **không** chứa bearer token, password trong body, customer ID trên query hoặc full exception response body. Nếu interceptor throw sau response, verify đã close.

## 27. Câu hỏi tự kiểm tra

1. `ClientHttpRequestInterceptor` nhận tham số nào và trả về gì?
2. Vì sao interceptor nên gọi `execution.execute` một lần mỗi attempt?
3. `RestClient.retrieve()` thường xử lý 4xx/5xx như thế nào?
4. `RestClient.exchange()` có chạy default status handlers không?
5. `onStatus` khác `defaultStatusHandler` về scope và order?
6. `RestTemplate.ResponseErrorHandler` có phải retry policy không?
7. `RestClientResponseException` khác `ResourceAccessException` ở đâu?
8. Có thể có server side effect dù client nhận timeout không?
9. Safe method và idempotent method giống/khác nhau ra sao?
10. Vì sao GET, HEAD thường dễ retry hơn POST?
11. PUT/DELETE idempotent có nghĩa response retry luôn bằng response đầu không?
12. Vì sao HTTP 504 không chứng minh operation chưa chạy?
13. Status 400/403/404/409/412 có nên retry tự động không?
14. 429 và 503 có thể kèm header nào gợi ý thời gian chờ?
15. Retry-After có những hai định dạng nào?
16. Nếu Retry-After 60s nhưng deadline còn 2s, xử lý thế nào?
17. MaxAttempts=3 nghĩa tối đa bao nhiêu HTTP requests?
18. Vì sao exponential backoff nên có jitter?
19. Vì sao nhiều tầng retries tạo retry storm?
20. Idempotency-Key giúp gì nếu server chưa triển khai dedup?
21. Vì sao key phải giữ nguyên cho cùng logical operation qua attempts?
22. Cùng key nhưng payload khác phải xử lý ra sao?
23. Có thể dựa vào process-local cache để bảo đảm exactly-once charge trong cluster không?
24. Vì sao không retry TLS certificate errors mãi?
25. Vì sao read timeout không phải total deadline?
26. Khi dùng `ResponseErrorHandler` tự viết, nó có biết business operation nào safe không?
27. Trong test, làm sao assert một GET 503 được gọi hai lần thay vì chỉ assert final 200?
28. Vì sao interceptor không nên log response body raw?
29. Khi dùng RestClient.Builder(RestTemplate), cần kiểm tra lại những gì?
30. Nếu request body là input stream one-shot, retry có nguy cơ gì?
31. Vì sao POST `Idempotency-Key` cần backend transaction/unique constraint?
32. `HttpStatusCode` có khác integer status không?
33. `onStatus` chỉ chạy khi đã có HTTP response hay cả khi DNS timeout?
34. Khi nào circuit breaker có ích hơn tiếp tục retry?
35. Mục tiêu chính của MockRestServiceServer trong bài là gì?

**Gợi ý:** (1) HttpRequest, byte[] body, execution; ClientHttpResponse. (2) Tránh duplicate side effect và leaking response. (3) Ném RestClientException cho error statuses. (4) Không. (5) Per request vs client-wide defaults. (6) Không. (7) Có HTTP response vs network access failure. (8) Có. (9) Safe không yêu cầu side effect, idempotent lặp có intended effect tương đương. (10) Read-only semantics. (11) Không. (12) Upstream có thể đã commit. (13) Không mặc định. (14) Retry-After. (15) delta-seconds, HTTP-date. (16) Fail/defer, không retry sớm. (17) Ba, gồm attempt đầu. (18) Giảm đồng loạt. (19) Multiplicative attempts. (20) Không có bảo đảm nếu server bỏ qua key. (21) Dedup cùng operation. (22) Conflict. (23) Không. (24) Configuration không tự hết lỗi. (25) Có nhiều phases/attempts/sleeps. (26) Không. (27) Expect hai requests và verify. (28) Secrets/privacy. (29) Factory, interceptors, codecs, error/status behavior. (30) Không replayable. (31) Chống double side effect race. (32) Spring abstraction cho status. (33) Có response. (34) Khi upstream unhealthy kéo dài. (35) Xác minh requests/status/attempts mà không cần Internet.

## 28. Tài liệu tham khảo chính thức

- [Spring Framework — REST Clients: RestClient và RestTemplate](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework 6.1 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Framework 6.1 — RestClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html)
- [Spring Framework 6.1 — ClientHttpRequestInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestInterceptor.html)
- [Spring Framework 6.1 — ClientHttpRequestExecution Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/ClientHttpRequestExecution.html)
- [Spring Framework 6.1 — RestClientResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClientResponseException.html)
- [Spring Framework 6.1 — DefaultResponseErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/DefaultResponseErrorHandler.html)
- [Spring Framework 6.1 — ResourceAccessException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/ResourceAccessException.html)
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html)
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html)
- [RFC 9110 — HTTP Semantics, Safe and Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9110 — Retry-After header](https://www.rfc-editor.org/rfc/rfc9110.html#field.retry-after)
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)

**Tổng kết:** `ClientHttpRequestInterceptor` là cơ chế bổ sung headers/observability quanh **mỗi HTTP attempt**, không nên là nơi tự động phát lại mọi request. `RestClient.retrieve()`, `onStatus`/`defaultStatusHandler` và `RestTemplate.ResponseErrorHandler` giúp chuyển HTTP statuses thành thông tin lỗi có cấu trúc, nhưng **không tự quyết định thao tác có được lặp hay không**. Retry phải được điều khiển theo semantics (safe/idempotent/replayable), error classification, `Retry-After`, backoff/jitter, total budget và Idempotency-Key phía server khi thao tác có side effects. Trong dịch vụ đồng bộ, retries giữ thread và có thể nhân tải — vì vậy **fail fast với lỗi không transient và POST unsafe**, kiểm thử số attempts chính xác, đo logical request lẫn attempts và chỉ thêm resilience features theo nhu cầu thật.
