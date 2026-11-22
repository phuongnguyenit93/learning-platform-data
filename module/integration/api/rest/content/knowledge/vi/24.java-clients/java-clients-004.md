# Thiết lập Accept, Content-Type, Authorization và metadata trong Java HTTP client

## 1. Vì sao cấu hình header là một phần của hợp đồng API?

Một Java service gọi **POST /orders** qua HTTPS. Payload JSON hoàn toàn đúng, nhưng server trả **415 Unsupported Media Type** vì client quên **Content-Type**. Một ứng dụng khác gửi **Accept: application/xml** dù API chỉ hỗ trợ JSON nên nhận **406 Not Acceptable**. Trường hợp nghiêm trọng hơn: HTTP client tự động chuyển hướng sang host bên ngoài và tiếp tục đính kèm **Authorization: Bearer ...**, làm lộ credential.

Client REST phải gửi đúng headers, đọc response status/metadata và bảo vệ credential; serialize DTO thôi chưa đủ.

Bài thuộc chương **Client Java**, module **INTEGRATION_API_REST**, liên hệ resource/URI, HTTP methods/status, dữ liệu, phân trang, cache, idempotency, OpenAPI, security và kiểm thử Java/Spring. Trọng tâm là **header và metadata ở HTTP client**.

**Mục tiêu:** phân biệt ba header cốt lõi, đọc response metadata, triển khai với JDK HttpClient/RestClient/WebClient và kiểm thử lỗi, redirect, credential và retry.

## 2. Ba header nền tảng, ba câu hỏi khác nhau

| Header | Ai gửi? | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- | --- |
| **Accept** | Chủ yếu request | *Client muốn nhận những representation nào?* | **Accept: application/json** |
| **Content-Type** | Request **và** response có nội dung | *Body của chính thông điệp này có định dạng gì?* | **Content-Type: application/json** |
| **Authorization** | Request | *Client gửi credential nào để server xác thực/quyết định quyền?* | **Authorization: Bearer token-value** |

Không có quy tắc “mọi request REST đều phải đặt cả ba header”:

- **GET** không body thông thường **không cần Content-Type**; nhưng có thể gửi **Accept** và Authorization.
- **POST/PUT/PATCH** có JSON body thường cần **Content-Type: application/json** và **Accept** cho loại phản hồi muốn nhận.
- Một tài nguyên công khai có thể không yêu cầu **Authorization**. Một resource riêng dù GET không body vẫn cần credential hợp lệ.
- **Response** tự có **Content-Type** nếu server gửi representation. Client phải kiểm tra media type **thực tế được trả**, không tin rằng Accept đã bảo đảm JSON.

### 2.1. Trao đổi HTTP minh họa

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json, application/problem+json
Content-Type: application/json
Idempotency-Key: order-req-8bf3
X-Request-ID: 8b982e08-9211-4699-9dc2-c9f945a4a34b

{
  "customerId": "22222222-2222-4222-8222-222222222222",
  "totalMinorUnit": 125000
}

HTTP/1.1 201 Created
Location: /orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json
Cache-Control: no-store
X-Request-ID: 8b982e08-9211-4699-9dc2-c9f945a4a34b

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "CREATED",
  "totalMinorUnit": 125000
}
~~~

Đây là **hai thông điệp HTTP đặt liên tiếp để đọc dễ hơn**, không phải một request chứa response bên trong. **Idempotency-Key** và **X-Request-ID** là hai loại metadata khác nhau: key chống trùng theo **hợp đồng ứng dụng**, request ID giúp đối chiếu log; request ID **không** chống double submit.

## 3. Accept: thương lượng dạng biểu diễn muốn nhận

Header **Accept** nói client có thể xử lý những media type nào:

~~~http
GET /orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>
~~~

Nếu cần xử lý lỗi theo **RFC 9457 Problem Details**, hợp đồng có thể dùng:

~~~http
Accept: application/json, application/problem+json
~~~

Điều này cho biết client hiểu JSON nghiệp vụ **và** Problem Details. Server vẫn phải kiểm tra các representation được hỗ trợ và quy tắc content negotiation; không phải cứ gửi Accept là server chắc chắn trả đúng kiểu ưu tiên.

### 3.1. Nhiều media type và hệ số q

~~~http
Accept: application/json;q=1.0, application/xml;q=0.5
~~~

**q** là *relative quality weight*, miền **0 đến 1**; giá trị cao hơn biểu thị ưu tiên khi có nhiều lựa chọn phù hợp. Không nên hiểu q là xác suất hoặc số phiên bản API. Khi API chỉ hỗ trợ JSON, nên khai báo chính xác JSON thay vì dùng wildcard không có chủ đích.

**application/xml** khi server chỉ có JSON có thể gây **406 Not Acceptable**. Wildcard hoặc không gửi Accept cho phép server chọn linh hoạt hơn; vẫn phải đọc Content-Type phản hồi. **406 nói về response representation**, không phải JSON request sai; một số server có thể chọn dạng mặc định.

### 3.2. Accept khác Accept-Encoding và Accept-Language

- **Accept**: media type như application/json, text/csv.
- **Accept-Encoding**: content coding như gzip, br, identity; làm thay đổi chuỗi byte truyền, quan trọng khi tải file theo Range.
- **Accept-Language**: ngôn ngữ ưu tiên như vi-VN, en-US; không tự thay định dạng JSON hay status.

Chỉ dùng khi API và client có contract tương ứng. Nếu response phụ thuộc ngôn ngữ/encoding, server có thể gửi **Vary**; cache phải tôn trọng biến thể. Không ghép byte gzip và identity từ hai phản hồi khác nhau.

## 4. Content-Type: mô tả body đang gửi hoặc nhận

Với POST JSON:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":125000}
~~~

Nếu body là JSON nhưng header nói **text/plain**, server có thể trả **415 Unsupported Media Type**. Nếu header đúng nhưng JSON **bị lỗi cú pháp**, thường gặp **400 Bad Request**. Nếu JSON parse được nhưng vi phạm quy tắc, server có thể trả **400 hoặc 422** theo hợp đồng.

**Phân loại:** 415 cho media type request không hỗ trợ, 400 cho JSON hỏng, 400/422 cho input sai quy tắc, 406 cho response không thương lượng được; 401/403 thuộc xác thực/phân quyền, không phải định dạng JSON.

**Content-Type của request không buộc response cùng Content-Type.** POST JSON có thể trả 201 JSON, 202 với body job metadata, 204 không body, hoặc lỗi **application/problem+json**. Client đọc status và Content-Type phản hồi trước khi chọn decoder.

### 4.1. Charset và body thực tế

Khi encode JSON, dùng **UTF-8** và serializer JSON phù hợp. Media type đăng ký **application/json** không định nghĩa tham số charset chuẩn hóa như text/plain; nên ưu tiên **Content-Type: application/json**, gửi byte UTF-8, không tự thêm charset tùy ý.

Nếu dùng **multipart/form-data** để upload, phải có **boundary** đúng với body; để HTTP library sinh Content-Type cùng boundary, không ép header trần rồi gửi body khác. Với **application/octet-stream**, media type chỉ phản ánh dữ liệu nhị phân, không tự nói filename an toàn.

**GET không body không cần Content-Type**; thêm mặc định trên mọi GET có thể làm mơ hồ contract và gây hành vi proxy/CORS không mong muốn.

## 5. Authorization: Bearer token và ranh giới an toàn

Với OAuth2 access token, client thường gửi:

~~~http
Authorization: Bearer eyJ...<redacted>
~~~

**Bearer** nghĩa là ai nắm token có thể sử dụng trong phạm vi quyền còn hiệu lực. **Không** gắn token vào query string, log, URL chuyển hướng, exception message hoặc telemetry. Luôn dùng **HTTPS với TLS validation hoạt động**, không tắt kiểm tra certificate/hostname.

Một số nguyên tắc:

1. Lấy access token từ **credential provider** hoặc OAuth client thích hợp; không hard-code token vào source hay Git.
2. Dùng token đúng **audience, issuer, scope** của API đích. Token cho service A không tự dùng được với service B.
3. Đặt Authorization **theo request hoặc theo client đã scope một origin/identity rõ ràng**; đừng dùng default token tenant A cho tenant B.
4. Khi server trả **401** kèm **WWW-Authenticate**, client có thể xử lý challenge, refresh token theo OAuth flow được phép và thử lại **có giới hạn**. Không refresh vô hạn, không retry 403 thiếu scope như lỗi hết token.
5. Với Basic authentication nếu legacy API yêu cầu, chỉ dùng trên TLS, tránh lưu password trong log; ưu tiên OAuth2/OIDC hoặc cơ chế chính thức nếu có.

### 5.1. 401 và 403 khác nhau

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Content-Type: application/problem+json
~~~

**401** cho biết chưa xác thực hợp lệ; WWW-Authenticate mô tả challenge. **403** cho biết request bị từ chối dù danh tính đã được nhận diện, như thiếu scope orders.write hoặc không có quyền với order. Client không nên mặc định “đăng nhập lại sẽ giải quyết 403”.

**HTTP client chỉ gửi credential**, không cấp quyền nghiệp vụ. Server phải kiểm tra quyền theo tenant/resource trên mỗi request.

### 5.2. Cẩn trọng redirect và forwarding credential

Không giả định thư viện Java xử lý redirect giống trình duyệt. Nếu theo **Location**, phải kiểm tra **scheme, host, port, method, body và Authorization policy**; tránh chuyển bearer token sang host lạ hoặc hạ cấp HTTP.

Với credential, mặc định an toàn là **không tự theo redirect**, hoặc chỉ theo đích đã xác minh trong allowlist cùng trust boundary. **303** thường chuyển POST sang GET; **307/308** giữ method/body và có thể phát lại POST nguy hiểm. Redirect không thay idempotency hay phân quyền.

## 6. Metadata request và response có chủ đích

Metadata là **thông tin giao thức giúp thực hiện contract**, không phải nơi cất bí mật.

| Metadata | Bên gửi phổ biến | Client cần làm gì? |
| --- | --- | --- |
| **X-Request-ID / traceparent** | Request, đôi khi response | Gắn correlation/trace đúng chuẩn, giới hạn và redaction. |
| **Idempotency-Key** | Request tạo/cập nhật có side effect | Retry cùng key/payload theo contract; server lưu key nguyên tử. |
| **If-Match / If-None-Match** | Conditional request | Chống lost update, cache revalidation; hiểu 412/304. |
| **Location** | Response 201/3xx và một số 202 | URI mới, redirect hoặc monitor; đọc **theo status**. |
| **ETag / Last-Modified** | Response | Lưu validator theo representation, phân biệt strong/weak. |
| **Retry-After** | Response 429/503 và một số trường hợp | Chờ đúng định dạng và chỉ retry khi an toàn. |
| **Cache-Control / Vary** | Response | Không cache private data trái chính sách; tôn trọng biến thể. |
| **WWW-Authenticate** | Response 401 | Hiểu challenge, không log credential. |
| **Link** | Response | Có thể chứa next page, docs, deprecation; chỉ follow quan hệ được tin. |
| **Content-Disposition** | Response file | Sanitize filename khi lưu. |

**Lưu ý:** traceparent có chuẩn W3C; Idempotency-Key cần scope/retention; X-Request-ID không bảo đảm exactly-once hoặc quyền.

### 6.1. Conditional GET và ETag

~~~http
GET /orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"
Cache-Control: private, no-cache

{"id":"11111111-1111-4111-8111-111111111111","status":"CREATED"}
~~~

Lần sau:

~~~http
GET /orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
If-None-Match: "order-v7"
Authorization: Bearer <access-token>

HTTP/1.1 304 Not Modified
ETag: "order-v7"
Cache-Control: private, no-cache
~~~

**304 không có JSON body**. Chỉ tận dụng khi có cache hợp lệ. PATCH/PUT chống ghi đè dùng strong **If-Match**, không khớp thường **412**.

### 6.2. Rate limit và Retry-After

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Content-Type: application/problem+json

{
  "type":"https://api.example.com/problems/rate-limited",
  "title":"Rate limited",
  "status":429
}
~~~

**Retry-After** có thể là số giây hoặc HTTP-date; không hiểu số **5** là timestamp. Client cần deadline, backoff, jitter và giới hạn thử lại. Không retry POST gây side effect chỉ vì gặp 429/503 nếu không có idempotency phù hợp.

### 6.3. Không tin tuyệt đối metadata nhận được

**Location, Link, Content-Disposition, filename, correlation header** có thể đến từ thành phần bên ngoài hoặc bị điều khiển. Validate scheme/host/port, sanitize filename, giới hạn log và không để redirect dẫn tới SSRF hay rò bearer token.

## 7. JDK HttpClient: header theo từng request

**java.net.http.HttpClient** (JDK 11+) hỗ trợ HTTPS, HTTP/1.1 hoặc HTTP/2, redirect policy, timeout, đồng bộ và bất đồng bộ. Nó **không tự serialize JSON object Java**; bạn cần serializer (Jackson hoặc tương đương) và BodyPublisher phù hợp.

### 7.1. Một client đọc và tạo Order

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

public final class OrdersJdkClient {
    private static final String ACCEPT =
            "application/json, application/problem+json";
    private final URI base = URI.create("https://api.example.com/");
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .version(HttpClient.Version.HTTP_2)
            .build();

    public HttpResponse<String> getOrder(
            UUID id, String accessToken)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                base.resolve("orders/" + id))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", ACCEPT)
                .header("Authorization", "Bearer " + accessToken)
                .header("X-Request-ID", UUID.randomUUID().toString())
                .GET()
                .build();
        return http.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public HttpResponse<String> createOrder(
            String jsonBody, String accessToken, String idempotencyKey)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                base.resolve("orders"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", ACCEPT)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + accessToken)
                .header("Idempotency-Key", idempotencyKey)
                .header("X-Request-ID", UUID.randomUUID().toString())
                .POST(HttpRequest.BodyPublishers.ofString(
                        jsonBody, StandardCharsets.UTF_8))
                .build();
        return http.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }
}
~~~

**Giới hạn:** token/key do provider tin cậy cấp; base URI cố định HTTPS, ID là UUID. **jsonBody do serializer tạo**, không nối raw user input. BodyHandlers.ofString **đọc toàn body vào RAM**, chỉ dùng cho JSON nhỏ; file lớn dùng ofFile/ofInputStream có quota và cleanup.

**Redirect.NEVER** để client tự xét Location; HTTP_2 có thể fallback HTTP/1.1. **Không tắt TLS validation**.

### 7.2. Đọc status và media type trước khi parse

~~~java
import java.net.http.HttpResponse;
import java.util.Locale;
import java.util.Optional;

static String mediaType(HttpResponse<?> response) {
    return response.headers().firstValue("Content-Type")
            .map(value -> value.split(";", 2)[0]
                    .trim().toLowerCase(Locale.ROOT))
            .orElse("");
}

static void inspect(HttpResponse<String> response) {
    int status = response.statusCode();
    String type = mediaType(response);
    Optional<String> requestId =
            response.headers().firstValue("X-Request-ID");

    if (status == 204 || status == 304) {
        // Không parse JSON body.
        return;
    }
    if (status >= 200 && status < 300
            && type.equals("application/json")) {
        // Dùng ObjectMapper/Jackson parse Order DTO,
        // kiểm tra schema và giới hạn dung lượng.
        return;
    }
    if (status >= 400
            && type.equals("application/problem+json")) {
        // Parse Problem Details theo HTTP status và problem type.
        return;
    }
    if (status >= 300 && status < 400) {
        // Đọc Location, xác minh đích trước khi follow.
        return;
    }
    // Status hoặc media type bất ngờ: báo lỗi giao thức.
}
~~~

Đây là logic minh họa, chưa phải error handler đầy đủ. **401/403** có thể có body trống hoặc khác media type; client vẫn phải xử lý theo **status** và challenge. Không log nguyên response body chứa dữ liệu riêng. HTTP header names **không phân biệt chữ hoa/thường**.

**Gọi bất đồng bộ:** HttpClient.sendAsync(request, bodyHandler) trả CompletableFuture, nhưng hủy future không đồng nghĩa rollback tác dụng phụ server. connectTimeout khác timeout từng request; cần retry budget và giới hạn đồng thời.

## 8. Spring RestClient: fluent API với headers rõ ràng

**RestClient** (Spring Framework 6.1+, ví dụ Spring Boot 3.2+) là HTTP client đồng bộ. Nó dùng **HttpMessageConverter** để serialize/deserialize DTO khi có converter JSON tương ứng.

### 8.1. POST JSON, Bearer token, Location

~~~java
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

record CreateOrder(UUID customerId, long totalMinorUnit) {}
record OrderView(UUID id, String status, long totalMinorUnit) {}

class OrdersRestClient {
    private final RestClient client;

    OrdersRestClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://api.example.com")
                .build();
    }

    ResponseEntity<OrderView> create(
            CreateOrder dto, String accessToken, String key) {
        return client.post()
                .uri("/orders")
                .accept(
                        MediaType.APPLICATION_JSON,
                        MediaType.parseMediaType(
                                "application/problem+json"))
                .contentType(MediaType.APPLICATION_JSON)
                .headers(h -> h.setBearerAuth(accessToken))
                .header("Idempotency-Key", key)
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(dto)
                .retrieve()
                .toEntity(OrderView.class);
    }
}
~~~

**toEntity** giữ status, headers và DTO; kiểm 201/Location, không xem 202/204/3xx là Order mới.

**retrieve()** mặc định ném exception trên 4xx/5xx. Dùng **onStatus** hoặc RestClientResponseException để đọc status/headers/Problem Details, không retry mù.

### 8.2. Header nào nên đặt mặc định?

RestClient.Builder có thể cấu hình defaults, nhưng **không gắn Bearer token cụ thể cho một client chia sẻ nhiều tenant**:

~~~java
import org.springframework.http.HttpHeaders;

RestClient client = RestClient.builder()
        .baseUrl("https://api.example.com")
        .defaultHeader(
                HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .build();
~~~

**Accept mặc định** phù hợp nếu mọi endpoint trả JSON; **Content-Type mặc định trên GET/file upload** có thể sai hợp đồng. **Authorization nên đặt theo request**, lấy đúng identity và audience. Builder dùng chung không giữ credential tenant A khi gọi thay tenant B.

**RestTemplate** là client đồng bộ legacy; RestClient cũng đồng bộ nhưng dùng fluent API. Dùng WebClient nếu cần non-blocking I/O.

## 9. Spring WebClient: headers trong reactive pipeline

**WebClient** phù hợp cho WebFlux hoặc luồng non-blocking. Nó vẫn tuân cùng contract:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com")
        .build();

Mono<ResponseEntity<OrderView>> created = webClient.post()
        .uri("/orders")
        .accept(
                MediaType.APPLICATION_JSON,
                MediaType.parseMediaType("application/problem+json"))
        .contentType(MediaType.APPLICATION_JSON)
        .headers(h -> h.setBearerAuth(accessToken))
        .header("Idempotency-Key", key)
        .bodyValue(dto)
        .retrieve()
        .toEntity(OrderView.class);
~~~

Ví dụ giả định có **dto**, **accessToken**, **key** và **OrderView**. **Không gọi block()/subscribe() thủ công trong WebFlux handler**; trả Mono để framework quản lý. retrieve() phát error signal trên 4xx/5xx mặc định. Dùng **onStatus** hoặc **exchangeToMono** khi cần phân loại lỗi/status và đọc metadata; bảo đảm body được tiêu thụ/giải phóng đúng. ResponseEntity giữ Location/ETag ở response thành công.

### 9.1. Filter và metadata đa tenant

- **JDK HttpClient:** tạo HttpRequest theo lần, token provider theo audience.
- **RestClient:** request interceptors cho tracing/timeout; token theo identity và đích.
- **WebClient:** ExchangeFilterFunction có thể gắn trace/request ID từ context; không gửi token của request hiện tại tới mọi upstream.

Không log token qua wiretap, proxy diagnostics hay tracing attributes. **Reactor Context không tự biến thành ThreadLocal/MDC**. Chính sách redirect của từng underlying client có thể khác: phải kiểm thử thực tế thay vì sao chép giả định giữa thư viện.

## 10. Xử lý lỗi và retry theo status, không theo “có JSON”

| Status | Chiến lược |
| --- | --- |
| **200/201/202** | Kiểm tra media type, Location; 202 chưa hoàn tất công việc. |
| **204/304** | Không parse body; 304 cần cache validator hợp lệ. |
| **3xx** | Kiểm tra Location, origin, method và token policy trước khi follow. |
| **400/406/415/422** | Sửa request/media type/data; retry y nguyên thường vô ích. |
| **401/403** | 401 xét challenge/refresh giới hạn; 403 thường là quyền/scope. |
| **404/410/409/412** | Không có/hết vòng đời/xung đột/precondition; xử lý theo contract. |
| **429/503** | Tôn trọng Retry-After và retry budget. |
| **5xx/network timeout** | Retry đọc có giới hạn; ghi chỉ khi chống trùng. |

### 10.1. Problem Details khác JSON dữ liệu

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 422,
  "detail": "totalMinorUnit không hợp lệ",
  "code": "INVALID_AMOUNT"
}
~~~

Parse **application/problem+json** vào lỗi riêng với type/status/detail/code (extension nếu có), dùng HTTP status thực làm nền tảng, không tin mù trường status trong body. Hạn chế hiển thị detail raw nếu nó chứa dữ liệu nhạy cảm hoặc ngôn ngữ không phù hợp.

### 10.2. Retry và idempotency

POST có thể đã commit dù client timeout trước khi nhận response. Gửi lại **không có idempotency** có thể tạo hai đơn. Với Idempotency-Key được hỗ trợ, server phải ràng buộc cùng key + payload + actor/operation theo contract và tránh ghi trùng bằng lưu trạng thái nguyên tử.

Retry cần **max attempts, total deadline, exponential backoff, jitter và cancellation**. Đừng retry chỉ vì gặp Retry-After nếu thao tác gây side effect không an toàn. Client thường **không biết chắc** server đã commit hay chưa khi mất kết nối.

## 11. Kiểm thử headers và response bằng Java/Spring

**Test cần kiểm tra request ở HTTP boundary**, không chỉ Java DTO hoặc log nội bộ.

### 11.1. MockRestServiceServer kiểm tra RestClient

Ví dụ Spring Test, dùng **RestClient.Builder** và mock server gắn vào builder **trước khi build**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import java.net.URI;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class OrdersRestClientTest {
  @Test
  void createSendsContractHeaders() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://api.example.com");
    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    RestClient client = builder.build();

    server.expect(requestTo("https://api.example.com/orders"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.ACCEPT,
                    "application/json, application/problem+json"))
            .andExpect(header(HttpHeaders.CONTENT_TYPE,
                    "application/json"))
            .andExpect(header(HttpHeaders.AUTHORIZATION,
                    "Bearer test-token"))
            .andExpect(header("Idempotency-Key", "req-001"))
            .andRespond(withStatus(HttpStatus.CREATED)
                    .header(HttpHeaders.LOCATION, "/orders/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"id\":\"11111111-1111-4111-8111-111111111111\","
                            + "\"status\":\"CREATED\","
                            + "\"totalMinorUnit\":125000}"));

    ResponseEntity<OrderView> result = client.post()
            .uri("/orders")
            .accept(MediaType.APPLICATION_JSON,
                    MediaType.parseMediaType("application/problem+json"))
            .contentType(MediaType.APPLICATION_JSON)
            .headers(h -> h.setBearerAuth("test-token"))
            .header("Idempotency-Key", "req-001")
            .body(new CreateOrder(
                    UUID.fromString("22222222-2222-4222-8222-222222222222"),
                    125000))
            .retrieve().toEntity(OrderView.class);

    assertEquals(201, result.getStatusCode().value());
    assertEquals(URI.create("/orders/1"),
            result.getHeaders().getLocation());
    server.verify();
  }
}
~~~

Đoạn test dùng **record CreateOrder/OrderView ở phần 8** và Spring Test/JUnit/Jackson đã cấu hình. Token chỉ là **test-token giả**; không dùng access token thật trong fixture. Test này kiểm tra request/response contract của client, **không** chứng minh TLS, redirect, scope hoặc server authorization. Test wire-level qua HTTP test server và gateway thật để kiểm chứng những phần đó.

### 11.2. Ma trận test bắt buộc

| ID | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| H01 | GET JSON | **Accept** đúng; không ép Content-Type khi không có body. |
| H02 | POST JSON | Content-Type, body UTF-8, Bearer, Idempotency-Key đúng. |
| H03 | API trả 201 | Đọc được **Location** và DTO. |
| H04 | API trả 204/304 | Không cố deserialize JSON rỗng; validator/cache xử lý đúng. |
| H05 | 406/415 | Báo negotiation/representation error rõ ràng, không retry mù. |
| H06 | 401/403 | Refresh tối đa theo policy; 403 không biến thành vòng lặp token. |
| H07 | 429 với Retry-After hoặc timeout sau POST | Backoff có deadline; key không sinh job/order trùng. |
| H08 | 302/303/307 tới host lạ | Không phát lại bearer token hoặc POST body sang đích không tin. |
| H09 | Problem Details, Content-Type lạ, JSON sai | Parse theo status/media type, lỗi có kiểm soát. |
| H10 | Header do người dùng kiểm soát chứa CR/LF/URL | Không header injection, không SSRF, không log secrets. |

## 12. Bài tập: Java client gọi dịch vụ xuất báo cáo

Một API có **POST /exports** nhận JSON và trả **202 Location: /jobs/{id}**, **GET /jobs/{id}** trả JSON trạng thái; khi xong có thể trả **303 Location: /reports/{id}**. GET report trả CSV. API dùng OAuth2 Bearer, có ETag cho trạng thái và có thể trả 429.

Hãy xác định: (1) Accept/Content-Type/Authorization cho POST và GET job; (2) header nào chỉ đặt trên POST; (3) cách phân biệt Location của **202** và **303**; (4) cách tải CSV mà không gửi token sang origin lạ; (5) xử lý 304, 401, 429 và timeout sau POST; (6) các test cần viết cho header và redirect.

**Hướng giải:** POST có Accept JSON/Problem, Content-Type JSON, Bearer và Idempotency-Key. GET job có Accept JSON, Bearer, **không cần Content-Type**; có thể gửi If-None-Match khi có cached representation. **202 Location** là monitor URL theo contract, không bắt client tự redirect; **303 Location** là chỉ dẫn truy xuất kết quả bằng GET, nhưng cần xác minh đích và credential policy. CSV nên có Accept: text/csv, tải streaming với giới hạn kích thước. 304 dùng cache hợp lệ; 401 xử lý challenge/refresh có giới hạn; 429 theo Retry-After/backoff. Nếu POST timeout, retry chỉ bằng chính sách idempotency đã được server hỗ trợ.

## 13. Checklist trước khi phát hành Java HTTP client

- [ ] **Accept** mô tả response muốn nhận; **Content-Type** mô tả body gửi, không gắn mặc định vô lý vào GET.
- [ ] Đọc **response Content-Type và status** trước khi deserialize; tách JSON nghiệp vụ khỏi Problem Details.
- [ ] Authorization lấy từ credential provider, đúng audience/scope, dùng TLS có kiểm chứng; không log token.
- [ ] Client chia sẻ nhiều tenant không có bearer token mặc định của một tenant.
- [ ] Redirect kiểm scheme/host/port/method và không chuyển token/body tới nguồn không tin cậy.
- [ ] Location, ETag, Retry-After, WWW-Authenticate, Cache-Control và metadata khác được hiểu theo status/contract.
- [ ] GET 304/204 không parse body; POST 201 kiểm Location, POST 202 theo monitor.
- [ ] Retry có budget/backoff và idempotency khi cần; request ID không thay Idempotency-Key.
- [ ] Test cả happy path lẫn 401/403/406/415/429, redirect cross-origin, input header lạ và timeout.

**Kết luận:** một Java HTTP client đúng REST contract không chỉ biết gọi method và parse JSON. Nó phải **nói rõ representation muốn nhận (Accept), mô tả body gửi (Content-Type), gửi credential an toàn (Authorization), đọc metadata theo status và kiểm thử các nhánh lỗi/redirect/retry**. Giữ các quyết định này nhất quán giữa JDK HttpClient, Spring RestClient và WebClient giúp tích hợp dự đoán được, tránh rò thông tin và giảm lỗi khó tái hiện ở production.
