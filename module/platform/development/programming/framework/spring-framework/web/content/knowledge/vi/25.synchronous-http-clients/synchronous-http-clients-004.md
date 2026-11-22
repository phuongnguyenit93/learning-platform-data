# RestClient: retrieve, exchange và đọc status, header, body trong HTTP client đồng bộ

## 1. Mục tiêu: không chỉ đọc JSON, mà còn hiểu toàn bộ HTTP response

Một HTTP client gọi API đối tác thường không chỉ cần dữ liệu JSON. Nó cần biết request thành công hay thất bại, status code thực, thông tin về caching, correlation ID, Location của tài nguyên mới được tạo, và phải quyết định có retry hay không.

Ví dụ server trả:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/42
X-Request-ID: req-abc123

{"id":42,"name":"Sách Spring"}
```

Nếu chỉ deserialize body thành Java object, ta có thể bỏ mất tín hiệu **201 Created** và **Location**. Ngược lại, nếu chỉ xem status mà quên body, ta có thể đánh mất mã lỗi nghiệp vụ. Spring cung cấp API để lấy những phần này theo nhu cầu.

**Chủ đề trực tiếp:** `retrieve`, `exchange` và cách đọc **status, headers, body**, trong nhóm **HTTP client đồng bộ** của Spring Framework.

Với **Spring Framework 6.2.x / Spring Boot 3.5.x / Java 17+**, lựa chọn hiện đại cho client đồng bộ là **`org.springframework.web.client.RestClient`** (fluent API, xuất hiện từ Spring Framework 6.1). `RestTemplate` vẫn có thể gặp trong hệ thống cũ nhưng API và tên phương thức không hoàn toàn giống `RestClient`; `WebClient` thuộc nhánh non-blocking/reactive và có các kiểu trả về khác.

Bài này trả lời:

1. Khi nào gọi `retrieve().body(Type.class)`, `retrieve().toEntity(Type.class)` hoặc `retrieve().toBodilessEntity()`?
2. Làm sao đọc `ResponseEntity#getStatusCode()`, `getHeaders()`, `getBody()` đúng theo status?
3. Khi nào chọn `exchange((request, response) -> ...)` để tự phân tích response?
4. Vì sao `retrieve()` mặc định ném exception cho 4xx/5xx, còn `exchange()` không tự áp dụng status handlers?
5. `onStatus(...)` xử lý lỗi có khác `exchange(...)` không?
6. Làm sao đọc response body raw stream an toàn, không để stream escape callback hoặc đọc vô hạn bytes?
7. Cách cấu hình Spring Boot `RestClient.Builder`, timeout/request factory, test với `@RestClientTest` + `MockRestServiceServer`?
8. Vì sao các quyết định retry, caching, bảo mật dữ liệu và xử lý response rỗng là một phần của HTTP contract?

## 2. Bức tranh tổng thể HTTP request và response

```text
                         Spring application
                                  |
                         RestClient.get/post
                                  |
                    URI + request headers + body
                                  |
                                  v
                  ClientHttpRequestFactory
                      (JDK / Apache / ...)
                                  |
                           HTTP network
                                  |
                                  v
                 HTTP status + headers + bytes
                                  |
                  +---------------+---------------+
                  |                               |
             retrieve()                        exchange(...)
                  |                               |
       status handlers cho lỗi                 callback nhận
       + HttpMessageConverter                  request + response
                  |                               |
          .body(Type)                          tự kiểm tra
          .toEntity(Type)                      status/headers/body
          .toBodilessEntity()                  và trả giá trị
                  |                               |
                  +--------------+----------------+
                                 |
                      domain result / exception
```

**Một request synchronous có thể chặn thread gọi** cho tới khi hoàn tất mạng và phần body extraction. `RestClient` không biến phép gọi HTTP thành non-blocking. Trong Spring MVC Servlet, nó có thể được gọi trên request worker theo ngân sách concurrency và timeout phù hợp. Trong Spring WebFlux/Netty event loop, **không gọi `RestClient` trực tiếp**, nếu chưa cô lập sang scheduler dành cho blocking hoặc — tốt hơn — dùng `WebClient` reactive.

### 2.1. Cơ chế phía dưới

`RestClient` sử dụng:

- `ClientHttpRequestFactory`: thực thi request trên một HTTP transport cụ thể, ảnh hưởng kết nối, TLS, timeout và pooling.
- `HttpMessageConverter<?>`: encode Java object thành request bytes hoặc decode response bytes thành `String`, `byte[]`, JSON DTO hay các types khác.
- `HttpStatusCode`: biểu diễn HTTP status, gồm chuẩn và mã mở rộng.
- `HttpHeaders`: biểu diễn response headers (multi-value, case-insensitive semantics).
- `ResponseEntity<T>`: gói **status + headers + body**.
- `RestClientResponseException` và các subclasses: mặc định thể hiện HTTP error responses ở nhánh `retrieve`.

HTTP status không phải một JSON field. Một response có thể có `204 No Content`, `304 Not Modified` hoặc một số error response không mang body; code cần xử lý chính xác.

## 3. Tạo RestClient: sử dụng Boot-provided builder

Trong **Spring Boot 3.5**, dự án chỉ cần `spring-boot-starter-web` hoặc những dependencies tương thích với Spring Web để có `RestClient`, Jackson cho JSON và auto-configured `RestClient.Builder`.

Fragment của `build.gradle` trong project đã được tạo bởi Spring Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`RestClient` cũng có thể dùng bên ngoài HTTP server nếu bạn chỉ xây scheduled job/CLI app; khi đó dùng các module cần thiết cho HTTP client và converters, không bắt buộc mở embedded Tomcat. Bài này dùng Boot starter cho ví dụ và tests đơn giản.

### 3.1. Builder do Spring Boot cung cấp

```java
@Service
class CatalogGateway {
    private final RestClient http;

    CatalogGateway(RestClient.Builder builder) {
        this.http = builder
                .baseUrl("https://partner.example.test")
                .defaultHeader("X-Client-App", "catalog-sync")
                .build();
    }
}
```

Đây là **class fragment**; `RestClient.Builder` phải được import từ `org.springframework.web.client.RestClient`, và hostname ví dụ không phải API thật. Inject Boot-managed builder giúp nhận các customizations/observability phù hợp của Boot. Nếu gọi `RestClient.create()` độc lập, bạn **không nhất thiết** nhận mọi customization đã cấu hình cho builder Boot.

Một `RestClient` đã build có thể dùng lại qua nhiều threads; nên tái sử dụng thay vì tạo client và kết nối mới cho mỗi HTTP request. Đừng tự thêm `Authorization` token cố định vào default headers nếu nó có scope từng user; token từ request phải được truyền đúng theo security context và không bị cache rò rỉ giữa tenants.

### 3.2. Cấu hình base URL và URI variables

```java
Product product = http.get()
        .uri("/products/{id}", productId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

Đây là **method fragment**; `Product` và `productId` do ứng dụng định nghĩa. Spring xử lý template variable phù hợp hơn việc nối chuỗi:

```java
// Không nên tự nối dữ liệu user vào URI:
String raw = "/products/" + userSuppliedPath;
```

Với query:

```java
http.get()
    .uri(uriBuilder -> uriBuilder
        .path("/products")
        .queryParam("page", 2)
        .queryParam("q", query)
        .build())
    .retrieve()
    .toEntity(String.class);
```

Đây là fragment với `query` đã được khai báo. Khi request URL liên quan dữ liệu không đáng tin, cần phân biệt path/query values và base URI; đừng để user tự nhập host/URL tuyệt đối nếu không có SSRF policy.

## 4. `retrieve()`: cách đọc response thông dụng

Chuỗi dùng phổ biến:

```java
Product found = http.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

Ba bước:

1. `get().uri(...)` chuẩn bị HTTP request, chưa tự trả body.
2. `retrieve()` trả `RestClient.ResponseSpec` để cấu hình cách xử lý status/body; **bản thân `retrieve()` chưa thực thi request**.
3. **Terminal operation** `body(...)`, `toEntity(...)` hoặc `toBodilessEntity()` kích hoạt HTTP exchange và extraction.

Điểm quan trọng này giúp tránh anti-pattern:

```java
http.get().uri("/products/7").retrieve();
// Không gọi terminal method => không có HTTP request như mong đợi.
```

Nếu response body không quan trọng nhưng vẫn phải gửi HTTP request, hãy dùng `toBodilessEntity()` thay vì bỏ dở ở `retrieve()`.

### 4.1. `body(Class<T>)`

Khi chỉ cần nội dung và không phải ra quyết định dựa vào status/headers:

```java
String text = http.get()
        .uri("/health")
        .retrieve()
        .body(String.class);

Product product = http.get()
        .uri("/products/7")
        .retrieve()
        .body(Product.class);

byte[] bytes = http.get()
        .uri("/small-binary")
        .retrieve()
        .body(byte[].class);
```

Đây là fragments; types và endpoints minh họa. Converter được chọn dựa trên Java type, content type và dependencies. Với body rỗng, phương thức `body(Type)` **có thể trả null** theo contract, đặc biệt `204 No Content`. Đừng khẳng định chắc chắn nó luôn tạo object.

`body(byte[].class)` không phù hợp để tải file nhiều GB vì có thể giữ toàn response trong RAM. Với dữ liệu lớn, cần streaming extraction bằng API thích hợp và giới hạn tổng bytes.

### 4.2. `body(ParameterizedTypeReference<T>)` cho generics

```java
List<Product> products = http.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(new ParameterizedTypeReference<
                List<Product>>() {});
```

Khác `List.class`, `ParameterizedTypeReference<List<Product>>` giữ **element type** cho JSON converter. Nếu dùng raw list, các phần tử có thể trở thành `LinkedHashMap`, dẫn đến `ClassCastException` khi cast thành `Product`.

Đừng dùng `body(new ParameterizedTypeReference<List<Product>>() {})` với một endpoint có thể trả **triệu phần tử** nếu toàn bộ dữ liệu sẽ được tích lũy; cần pagination, streaming reader hoặc giải pháp đồng bộ theo trang.

### 4.3. Không nhầm Content-Type với Accept

- `.accept(MediaType.APPLICATION_JSON)` đặt request header **Accept: application/json**, nói client mong định dạng response nào.
- `.contentType(MediaType.APPLICATION_JSON)` trên POST/PUT/PATCH cho biết **request body** đang gửi là JSON.
- Server có thể trả 406/415 nếu không có representation phù hợp; xử lý response status là việc client phải quan tâm.
- `Content-Type` response là do server trả về, không được tin hoàn toàn khi chuyển dữ liệu không đáng tin vào hệ thống.

## 5. `retrieve().toEntity(Class<T>)`: lấy đủ status, headers, body

Khi cần metadata của response:

```java
ResponseEntity<Product> response = http.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntity(Product.class);

HttpStatusCode status = response.getStatusCode();
HttpHeaders headers = response.getHeaders();
Product body = response.getBody();
```

Từ đó:

```java
int code = status.value();
MediaType contentType = headers.getContentType();
String requestId = headers.getFirst("X-Request-ID");
String etag = headers.getETag();
URI location = headers.getLocation();
long length = headers.getContentLength();
```

Đây là **method fragments** cho response có metadata thích hợp. Giá trị các headers có thể **null** hoặc vắng mặt; `getContentLength()` dùng giá trị sentinel nếu không biết. Từng API có semantics riêng (ví dụ ETag hợp lệ gồm dấu nháy kép trong trường hợp strong validator); đừng mặc định mọi header đều có trên HTTP response.

### 5.1. ResponseEntity không có nghĩa body luôn tồn tại

```java
ResponseEntity<Void> r = http.delete()
        .uri("/products/{id}", id)
        .retrieve()
        .toBodilessEntity();
```

Với response 204, `r.getBody()` là null; `r.getStatusCode().value()` là 204. Với response 202, không nên tự coi processing đã hoàn tất chỉ vì request thành công. Với 201, header `Location` giúp client biết URI tài nguyên mới.

### 5.2. HEAD và 304

Một HEAD request có headers/status nhưng **không có HTTP response body**:

```java
ResponseEntity<Void> head = http.head()
        .uri("/products/7")
        .retrieve()
        .toBodilessEntity();

String etag = head.getHeaders().getETag();
```

`304 Not Modified` cũng không mang representation body theo HTTP semantics. Nếu dùng conditional GET:

```java
ResponseEntity<Product> r = http.get()
        .uri("/products/7")
        .header(HttpHeaders.IF_NONE_MATCH, cachedEtag)
        .retrieve()
        .toEntity(Product.class);
```

`cachedEtag` phải là ETag đúng format. Khi server trả 304, response body thường null; ứng dụng phải dùng cache trước đó thay vì coi đây là “dữ liệu mất” hoặc retry vô hạn. Vấn đề cache còn liên quan Cache-Control, Vary, validators và tenant/auth scoping.

## 6. `toBodilessEntity()`: thực thi request nhưng không decode body

Nhiều APIs thành công mà không cần đọc body:

```java
ResponseEntity<Void> response = http.post()
        .uri("/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateProduct("Spring Basics"))
        .retrieve()
        .toBodilessEntity();
```

Khi server trả 201 Created:

```java
if (response.getStatusCode().value() == 201) {
    URI location = response.getHeaders().getLocation();
    // Validate expected host/path before following Location.
}
```

**Đây là fragment**, giả định record `CreateProduct` có trong ứng dụng. Dù method tên `toBodilessEntity`, HTTP response vẫn được xử lý/giải phóng theo client API; nếu server gửi body lỗi 4xx/5xx, nhánh `retrieve` mặc định **ném exception** trước khi cho caller một entity bình thường.

### 6.1. Vì sao không chỉ gọi retrieve?

```java
http.post()
        .uri("/jobs")
        .body(command)
        .retrieve();
```

Điều này chỉ tạo `ResponseSpec`, **chưa gửi request**. Dùng `toBodilessEntity()` nếu bạn quan tâm status + headers nhưng không cần body.

### 6.2. HTTP semantics của 201, 202, 204

| Status | Ý nghĩa | Header cần quan tâm |
| --- | --- | --- |
| 200 OK | Request thành công, thường có representation | Content-Type, ETag, Cache-Control |
| 201 Created | Đã tạo resource | Location, có thể ETag/body |
| 202 Accepted | Đã chấp nhận để xử lý, chưa chắc hoàn tất | Location/status endpoint, Retry-After theo contract |
| 204 No Content | Thành công, không có representation body | ETag hoặc metadata khác nếu có |
| 304 Not Modified | Có thể tái sử dụng cached representation | ETag/Cache-Control/Vary |
| 400 Bad Request | Input/protocol không hợp lệ | Error response body |
| 401 Unauthorized | Thiếu/chưa hợp lệ authentication | WWW-Authenticate |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền | Error code an toàn |
| 404 Not Found | Không tìm thấy hoặc ẩn resource | Client quyết định not-found semantics |
| 409 Conflict | Xung đột trạng thái/uniqueness | Stable error code |
| 429 Too Many Requests | Vượt quota/rate limit | Retry-After nếu server cung cấp |
| 500 Internal Server Error | Lỗi server | Correlation ID |
| 503 Service Unavailable | Tạm hết capacity/downstream unavailable | Retry-After nếu có |

Không có một status-code mapping chung nào thích hợp mọi service; cần hợp đồng API của đối tác.

## 7. `retrieve()` xử lý 4xx/5xx mặc định ra sao?

Theo Spring Framework 6.2, `retrieve` mặc định ném một subclass của `RestClientException` khi nhận HTTP response **4xx hoặc 5xx**. Các lỗi status thường là:

- `HttpClientErrorException` cho 4xx, có thể là specialized subclasses như `HttpClientErrorException.NotFound`.
- `HttpServerErrorException` cho 5xx.
- `RestClientResponseException` là base phù hợp để đọc status/body/headers của **HTTP error response**.
- `ResourceAccessException` thường bọc lỗi I/O/network như connect timeout, read timeout, DNS/TLS — **không có HTTP status** nếu server chưa trả HTTP response.
- `UnknownContentTypeException` có thể xảy ra khi converter không xử lý representation mong đợi.
- Lỗi Jackson conversion/serialization có thể nằm trong hierarchy `RestClientException`/conversion exceptions, cần phân loại theo context.

### 7.1. Bắt exception HTTP đúng cách

```java
try {
    Product product = http.get()
            .uri("/products/{id}", id)
            .retrieve()
            .body(Product.class);
    // Xử lý product.
} catch (RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    HttpHeaders headers = ex.getResponseHeaders();
    String message = ex.getResponseBodyAsString(
            StandardCharsets.UTF_8);

    // Chỉ phân loại/sanitize thông tin để log/đưa ra client.
} catch (ResourceAccessException ex) {
    // I/O failure: có thể chưa nhận response/status nào.
}
```

Đây là **fragment** với imports `RestClientResponseException`, `ResourceAccessException`, `StandardCharsets`. `message` chứa raw error response body từ server không đáng tin; không hiển thị trực tiếp nó như thông báo public hoặc log toàn bộ dữ liệu nhạy cảm.

### 7.2. Một response 404 là exception, không phải ResponseEntity bình thường

```java
ResponseEntity<Product> r = http.get()
        .uri("/products/999")
        .retrieve()
        .toEntity(Product.class);
```

Nếu server trả 404, **mặc định không vào nhánh xử lý `r.getStatusCode()==404`** vì `toEntity` ném exception. Muốn 404 thành domain exception, hãy dùng `onStatus`. Muốn 404 thành một **giá trị bình thường** để xử lý đa dạng status, có thể dùng `exchange`.

### 7.3. Đừng catch-all rồi trả null

```java
// Anti-pattern:
try {
    return callPartner();
} catch (Exception ignored) {
    return null;
}
```

Cách này khiến 401/403/429/503/DNS timeout đều biến thành “không có sản phẩm”, dẫn đến dữ liệu sai, retry hỏng và che lỗi hệ thống. Dùng typed exceptions/codes, đo status và thông báo sự cố phù hợp.

## 8. `onStatus(...)`: custom status handling trong retrieve

Mỗi `retrieve()` có thể gắn xử lý theo status:

```java
Product value = http.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            (request, response) -> {
                throw new ProductMissingException(id);
            })
        .body(Product.class);
```

Đây là **fragment**; custom exception được khai báo trong demo. Handler nhận **request và response**, có thể đọc HTTP status, headers và body error nếu cần. Thay vì trả raw error JSON của đối tác lên người dùng, hãy map sang lỗi domain an toàn, ví dụ PRODUCT_NOT_FOUND.

### 8.1. Thứ tự xử lý

Khi có nhiều status handlers, ưu tiên phụ thuộc cấu hình và thứ tự chúng được đăng ký. Nên đặt handlers đặc hiệu trước handlers rộng, và kiểm tra bằng unit tests với 404/409/429/500.

Nếu có default status handlers cấu hình trên `RestClient.Builder`, các handlers của từng response có thể được dùng trước defaults tùy contract Spring 6.2. Đừng suy đoán “status handler này luôn chạy” nếu một handler khác đã match và throw trước.

### 8.2. onStatus không phải exchange

`retrieve().onStatus(...)` phù hợp khi chỉ cần đổi cách **biến lỗi thành exception** và vẫn muốn dùng `body(Class)`/`toEntity(Class)` cho success.

`exchange(...)` phù hợp khi cần **phân nhánh theo status**, đọc headers/raw bytes ngay tại callback hoặc trả một kiểu domain result khác nhau mà không để mặc định 4xx/5xx ném trước.

### 8.3. Đừng đè mọi 4xx thành “not found”

Không nên:

```java
.onStatus(HttpStatusCode::is4xxClientError,
    (req, res) -> {
        throw new ProductMissingException(id);
    })
```

Vì 401, 403, 409 và 429 có ý nghĩa hoàn toàn khác 404. Tránh làm mất nguyên nhân do authentication, conflict hoặc quota. Hãy nhận diện chính xác và giữ thông tin kỹ thuật an toàn trong logs/metrics.

## 9. `exchange(...)`: toàn quyền xem request và raw response

Spring 6.2 `RestClient.RequestHeadersSpec#exchange(...)` nhận callback:

```java
T result = http.get()
        .uri("/products/{id}", id)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            HttpHeaders headers = response.getHeaders();
            InputStream body = response.getBody();
            // Tự đọc/biến đổi/xử lý tại đây.
            return someResult;
        });
```

Đây là **fragment**; `someResult` cần được xác định cụ thể. `exchange` cho quyền điều khiển mạnh hơn và yêu cầu developer nắm rõ HTTP response contract.

**Điểm bắt buộc nhớ: `exchange(...)` không áp dụng default status handlers hay `retrieve().onStatus`.** Nếu server trả 404 hoặc 500, callback vẫn có thể nhận HTTP response bình thường để bạn xử lý; client không tự ném `HttpClientErrorException.NotFound` chỉ vì status 404 trong đường này.

### 9.1. Một callback có thể trả kiểu kết quả riêng

```java
record StatusProbe(
        int status,
        String requestId,
        String contentType,
        String body) {}
```

Ví dụ:

```java
StatusProbe probe = http.get()
        .uri("/probe/{id}", id)
        .exchange((request, response) -> {
            HttpHeaders headers = response.getHeaders();

            byte[] bytes = response.getBody()
                    .readNBytes(1025);

            if (bytes.length > 1024) {
                throw new OversizedProbeException();
            }

            MediaType contentType = headers.getContentType();

            return new StatusProbe(
                response.getStatusCode().value(),
                headers.getFirst("X-Request-ID"),
                contentType != null
                    ? contentType.toString() : null,
                new String(bytes, StandardCharsets.UTF_8));
        });
```

Đây là **method fragment** với `OversizedProbeException` được khai báo trong demo. `InputStream#readNBytes` (Java 17) có thể ném `IOException`; callback API cho phép throws IOException. Đọc tối đa **1.025 bytes**, từ chối nếu vượt 1.024; không dùng `readAllBytes()` vô hạn với response không đáng tin.

`new String(bytes, UTF_8)` chỉ phù hợp dữ liệu text mà bạn dự kiến; với file binary, decode thành String có thể làm hỏng dữ liệu. Với payload JSON phức tạp, prefer message converters trên đường `retrieve` hoặc converter API phù hợp thay vì tự parse String thủ công.

### 9.2. Ai đóng response và InputStream?

Spring 6.2 overload `exchange(callback)` mặc định đóng `ClientHttpResponse` sau khi callback kết thúc. Do đó:

- Đọc xong/copy xử lý **bên trong callback**.
- **Không trả `response.getBody()`** ra ngoài callback rồi đọc sau: stream có thể đã bị đóng.
- Khi dùng overload `exchange(callback, false)`, **người gọi chịu trách nhiệm** quản lý đóng response; chỉ dùng khi hiểu resource ownership.
- Một response không được tiêu thụ/đóng đúng có thể gây leak HTTP connections và làm connection pool cạn.
- Với file lớn, stream/copy dữ liệu đến sink có kiểm soát **bên trong callback** thay vì tích toàn bộ trong heap.

### 9.3. exchange không tự biến lỗi status thành exception

```java
record CheckResult(int status, boolean retryable) {}

CheckResult result = http.get()
        .uri("/health")
        .exchange((request, response) -> {
            int code = response.getStatusCode().value();

            return new CheckResult(
                code,
                code == 429 || code == 503);
        });
```

Với 503, callback vẫn có thể trả `CheckResult(503,true)` thay vì ném. Nhưng **không tự retry request** chỉ vì `retryable=true`. Phải xem method có an toàn/idempotent, Retry-After, retry budget, backoff và tình trạng downstream.

### 9.4. exchange không đồng nghĩa RestTemplate.exchange

Cần phân biệt:

```java
// RestClient:
restClient.get()
        .uri("/products/7")
        .exchange((request, response) ->
                response.getStatusCode().value());
```

và:

```java
// RestTemplate:
ResponseEntity<Product> r =
        restTemplate.exchange(
                "/products/7",
                HttpMethod.GET,
                HttpEntity.EMPTY,
                Product.class);
```

`RestTemplate.exchange(...)` là phương thức **template-style** có thể trả `ResponseEntity` trực tiếp và mặc định dùng `ResponseErrorHandler`. `RestClient.exchange(...)` nhận callback và **bỏ qua status handlers mặc định**. Đừng copy nhận định về exception/error handling của một API sang API kia.

## 10. Đọc status: HttpStatusCode và các trường hợp không đơn giản

`HttpStatusCode` thể hiện một status; nên dùng:

```java
HttpStatusCode status = response.getStatusCode();

boolean success = status.is2xxSuccessful();
boolean clientError = status.is4xxClientError();
boolean serverError = status.is5xxServerError();
int code = status.value();
```

Đây là fragments. Không cần ép mọi status sang `HttpStatus` enum bằng `HttpStatus.valueOf`, vì có HTTP status codes mở rộng không có trong enum. Với codes đối tác trả bất thường, hãy xử lý an toàn theo family/status.

### 10.1. `2xx` không phải cùng một ý nghĩa

- 200: thường có representation body.
- 201: nên xét Location/new resource.
- 202: request accepted để xử lý sau, có thể có job ID.
- 204: không có body; `body(Product.class)` có thể trả null.
- 206 Partial Content: dùng Range/Content-Range, không coi bytes nhận được là toàn resource.

Nếu service trả 204 nhưng code bắt buộc `body != null`, cần chuyển API contract sang `Optional<Product>` hoặc result type phân biệt trường hợp empty.

### 10.2. Lỗi 3xx và redirect

Redirect handling phụ thuộc `ClientHttpRequestFactory`/HTTP client và cấu hình redirect policy. Không mặc định một request sẽ luôn trả 302 cho code, hoặc luôn theo redirect. Khi redirect đi sang host khác, không chuyển nhầm Authorization headers/cookies; cấu hình client/transport theo security policy.

### 10.3. 401 và 403

- 401 thường cần xem `WWW-Authenticate` để hiểu authentication scheme/challenge; không log bearer credentials.
- 403 cho biết không có quyền trong context; auto retry cùng credentials thường không có ích.
- Đối tác đôi khi ẩn resource bằng 404 để tránh tiết lộ thông tin; client cần tuân contract, không đoán privilege từ response.

## 11. Đọc headers có kiểu dữ liệu rõ

`HttpHeaders` hỗ trợ nhiều getters và kiểu values:

```java
HttpHeaders headers = entity.getHeaders();

MediaType type = headers.getContentType();
URI location = headers.getLocation();
String etag = headers.getETag();
long contentLength = headers.getContentLength();
long modifiedEpochMillis = headers.getLastModified();
String requestId = headers.getFirst("X-Request-ID");
List<String> cacheControl = headers.get(HttpHeaders.CACHE_CONTROL);
```

Đây là fragments, một số values có thể null hoặc sentinel. Khi dùng cùng tên header nhiều lần, `headers.get(name)` có thể trả **danh sách**; `getFirst` bỏ các giá trị sau. Chọn theo semantics của header, không tùy tiện gộp Set-Cookie với dấu phẩy.

### 11.1. Location phải được hiểu đúng

Server có thể trả:

```http
Location: /api/products/42
```

Đây là URI **relative**, không phải URL tuyệt đối. Nếu cần theo liên kết, resolve theo request URI/public base URI đã kiểm tra. Với Location tuyệt đối từ bên ngoài, **không tự động follow sang mọi host**; SSRF hoặc token leakage có thể xảy ra nếu server/compromised upstream trả host nội bộ.

### 11.2. Retry-After có hai định dạng

Header `Retry-After` có thể biểu diễn:
- **delta-seconds**, ví dụ `Retry-After: 5`.
- **HTTP-date**, ví dụ một ngày GMT theo chuẩn HTTP.

Đừng luôn `Integer.parseInt(headers.getFirst("Retry-After"))` vì giá trị date sẽ gây lỗi. Thiết kế parser có upper bound, clock skew handling, jitter và retry budget. Không retry request POST tạo resource nếu không có idempotency strategy.

### 11.3. ETag, Last-Modified và caching

`ETag` là validator của representation. Conditional GET có thể gửi `If-None-Match`, nhận 304 và dùng cached bytes tương ứng. Cache phải được khóa theo URI, headers ảnh hưởng representation (`Vary`), authentication/tenant và policy `Cache-Control`; không chia sẻ dữ liệu riêng tư giữa người dùng chỉ vì cùng path.

### 11.4. Correlation ID

`X-Request-ID`/`traceparent` có thể giúp đối chiếu calls, nhưng nếu upstream tự gửi requestId bất kỳ, đừng tin nó như authenticated identity. Khi log, sanitize length/characters và không đưa raw URI/query/token vào logs.

## 12. Đọc body có kiểu: String, DTO, List, bytes và empty

| Body target | Dùng khi | Nguy cơ |
| --- | --- | --- |
| `String.class` | Plain text hoặc debug response nhỏ | Dữ liệu text có thể chứa secrets; memory nếu quá lớn |
| `Product.class` | JSON object | Jackson schema mismatch / fields không có |
| `byte[].class` | Binary nhỏ | Tích toàn bộ bytes vào heap |
| `ParameterizedTypeReference<List<Product>>` | JSON list nhỏ/vừa | Heap tăng với số phần tử |
| `Void.class` / `toBodilessEntity()` | Không cần body | Đừng chờ DTO trên 204 |
| `exchange(callback)` với InputStream | Custom parsing/stream copy/bounded inspection | Tự quản status, resource và size |
| `Resource.class` | Response dạng tài nguyên theo converter | Phải xem transport, streaming và close semantics cụ thể |

Không coi Java type thành bằng chứng dữ liệu an toàn. DTO có thể được deserialize nhưng vẫn sai constraints nghiệp vụ. Nếu bắt buộc validate, dùng Jakarta Validation/service validation sau khi đọc body trước khi side effects.

### 12.1. Body bị tiêu thụ và response đã đóng

`RestClient` synchronous extraction có thể đóng response sau terminal operation. Đừng nghĩ có thể gọi:

```java
RestClient.ResponseSpec spec =
        http.get().uri("/products/7").retrieve();

Product p = spec.body(Product.class);
String raw = spec.body(String.class); // Không nên: tái dùng spec.
```

Mỗi terminal invocation có thể kích hoạt exchange riêng hoặc rơi vào behavior không mong đợi; không dùng pattern này để “đọc body hai lần” với giả định cùng HTTP response. Nếu cần cả body + headers, dùng **một** `toEntity`. Nếu cần raw bytes + status, dùng **một** `exchange` callback.

### 12.2. Không tự động tin Content-Length

Content-Length có thể thiếu, response chunked/HTTP2, compressed content size khác decoded size, hoặc server báo sai. **Cần giới hạn thực tế trong lúc đọc bytes**, không chỉ kiểm tra `getContentLength()` trước khi `readAllBytes()`.

Ví dụ `readNBytes(MAX+1)` từ phần `exchange` giới hạn việc giữ dữ liệu; với stream copy lớn, đếm bytes trên từng chunk và abort khi vượt quota.

### 12.3. JSON không đúng schema

HTTP 200 không bảo đảm JSON body hợp lệ theo DTO. Jackson có thể gặp `HttpMessageNotReadableException` hoặc conversion-related exception tùy call path/framework version. Cần classify **decoder/schema error** riêng với network timeout hay 404, không retry vô hạn vì một field type không khớp.

## 13. Khi nào nên dùng retrieve và khi nào dùng exchange?

| Nhu cầu | Cách khuyến nghị | Lý do |
| --- | --- | --- |
| Chỉ cần JSON object từ success response | `retrieve().body(Product.class)` | Ngắn gọn, converter tự xử lý |
| Cần status/headers và body DTO | `retrieve().toEntity(Product.class)` | `ResponseEntity` bao gồm cả ba |
| POST nhận 201 + Location, không cần body | `retrieve().toBodilessEntity()` | Có metadata, không decode body |
| Đọc generic JSON list | `retrieve().body(ParameterizedTypeReference)` | Giữ generic type |
| 404 thành domain exception | `retrieve().onStatus(...).body(...)` | Đổi cách xử lý lỗi nhưng vẫn dùng converter |
| Muốn 404/503 là values, không ném mặc định | `exchange(...)` | Tự inspect status |
| Xử lý raw stream và byte cap | `exchange(...)` | Full callback, giữ resource scope |
| Chọn parser dựa vào status/header | `exchange(...)` hoặc thiết kế reader phù hợp | Có response metadata trước khi decode |
| Đơn giản tìm body text và vẫn theo dõi metadata | `retrieve().toEntity(String.class)` | Không cần exchange |
| Cần response streaming non-blocking | `WebClient`/reactive body | RestClient sync có thể giữ thread |

**Không chọn exchange chỉ vì “nó mạnh hơn”.** Nó khiến bạn phải chịu trách nhiệm áp HTTP status policy, parse body, đóng resource và kiểm soát input size — những việc `retrieve` đã làm tiện lợi trong use case thông thường.

## 14. Ví dụ ứng dụng hoàn chỉnh: Java 17 + Spring Boot 3.5

Mục tiêu demo: gọi một **API đối tác giả lập trong unit tests**, không kết nối network thật. Tạo `PartnerCatalogClient` sử dụng Spring Boot-managed `RestClient.Builder`:

- `find`: `retrieve().body`, trả DTO trên 200.
- `withMetadata`: `retrieve().toEntity`, lấy status + headers + DTO.
- `list`: `ParameterizedTypeReference<List<Product>>`.
- `create`: POST `toBodilessEntity`, đọc 201 + Location.
- `findOrThrow`: `onStatus(404)` đổi sang custom exception.
- `probe`: `exchange` đọc status/headers/body tối đa 1.024 bytes, kể cả khi response 404 hoặc 503.
- `inspectWithPolicy`: `exchange` chủ động ném lỗi khi 5xx, chứng minh developer phải quyết định.

**Giới hạn:** demo đặt host `https://partner.example.test` để làm mock, không phải endpoint hoạt động trên Internet. Không có authentication, retry, network transport tuning hoặc persistent DB. Các tests sẽ mock HTTP responses qua Spring test infrastructure mà không phụ thuộc Internet.

### 14.1. Cấu trúc file

```text
restclient-response-demo/
├── build.gradle
└── src/
    ├── main/java/demo/restread/
    │   └── RestReadApplication.java
    └── test/java/demo/restread/
        └── PartnerCatalogClientTests.java
```

### 14.2. Toàn bộ source Java

Tạo `src/main/java/demo/restread/RestReadApplication.java`:

```java
package demo.restread;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class RestReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(RestReadApplication.class, args);
    }
}

record Product(long id, String name) {}

record CreateProduct(String name) {}

record Probe(
        int status,
        String requestId,
        String contentType,
        String body) {}

final class ProductMissingException extends RuntimeException {
    ProductMissingException(long id) {
        super("Product " + id + " not found");
    }
}

final class PartnerUnavailableException extends RuntimeException {
    PartnerUnavailableException(int status) {
        super("Partner unavailable, HTTP " + status);
    }
}

final class OversizedProbeException extends RuntimeException {
    OversizedProbeException() {
        super("Probe response exceeds 1024 bytes");
    }
}

@Service
class PartnerCatalogClient {
    private static final int MAX_PROBE_BYTES = 1024;

    private final RestClient http;

    PartnerCatalogClient(RestClient.Builder builder) {
        // Host chỉ dành cho mock HTTP tests.
        this.http = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    Product find(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Product.class);
    }

    ResponseEntity<Product> withMetadata(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(Product.class);
    }

    List<Product> list() {
        return http.get()
                .uri("/products")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(new ParameterizedTypeReference<
                        List<Product>>() {});
    }

    ResponseEntity<Void> create(CreateProduct input) {
        return http.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(input)
                .retrieve()
                .toBodilessEntity();
    }

    Product findOrThrow(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                    status -> status.value() == 404,
                    (request, response) -> {
                        throw new ProductMissingException(id);
                    })
                .body(Product.class);
    }

    Probe probe(long id) {
        return http.get()
                .uri("/probe/{id}", id)
                .exchange((request, response) -> {
                    HttpHeaders headers = response.getHeaders();

                    byte[] bytes = response.getBody()
                            .readNBytes(MAX_PROBE_BYTES + 1);
                    if (bytes.length > MAX_PROBE_BYTES) {
                        throw new OversizedProbeException();
                    }

                    MediaType type = headers.getContentType();

                    return new Probe(
                        response.getStatusCode().value(),
                        headers.getFirst("X-Request-ID"),
                        type != null ? type.toString() : null,
                        new String(bytes,
                                StandardCharsets.UTF_8));
                });
    }

    int inspectWithPolicy(long id) {
        return http.get()
                .uri("/probe/{id}", id)
                .exchange((request, response) -> {
                    HttpStatusCode status =
                            response.getStatusCode();

                    if (status.is5xxServerError()) {
                        throw new PartnerUnavailableException(
                                status.value());
                    }

                    return status.value();
                });
    }
}
```

**Vì sao file này có thể compile với Java 17?**

- Có một top-level `public class RestReadApplication` khớp tên file.
- Các `record`/exceptions/`PartnerCatalogClient` là package-private dưới `demo.restread`.
- `@SpringBootApplication` component scan phát hiện `@Service PartnerCatalogClient`.
- Spring Boot 3.5 cung cấp bean `RestClient.Builder` thông qua auto-configuration.
- `@RestClientTest(PartnerCatalogClient.class)` trong phần test sẽ tạo đúng service và builder có mock customization.
- `exchange` callback cho phép xử lý `IOException` từ `InputStream.readNBytes` theo method signature của Spring 6.2.
- `Probe` được tạo **trong callback**, không trả `InputStream` đã sắp đóng ra ngoài.
- `onStatus` chỉ xử lý chính xác 404, không làm mất 401, 409 hoặc 429.
- `ResponseEntity<Void>` cho POST làm rõ rằng body không được dùng để đọc Location.

### 14.3. Mẫu sử dụng kết quả

```java
ResponseEntity<Product> response =
        partner.withMetadata(7);

if (response.getStatusCode().is2xxSuccessful()) {
    String id = response.getHeaders()
            .getFirst("X-Request-ID");
    Product product = response.getBody();
    // Persist/cache/return product theo policy.
}
```

`partner` ở đây là `PartnerCatalogClient` đã được inject vào service tương ứng; fragment không phải `main` độc lập. Khi status 404, `withMetadata` mặc định ném exception nên nhánh if không xử lý 404; chọn `probe` hoặc `findOrThrow` nếu cần hành vi khác.

## 15. Kiểm thử đầy đủ với @RestClientTest và MockRestServiceServer

`@RestClientTest` trong Boot 3.5 auto-configures `RestClient.Builder`, JSON converters và `MockRestServiceServer` để kiểm tra một HTTP client **đồng bộ** không cần mở server socket thật. Nó là slice test: thông thường chỉ đăng ký component được chỉ định thay vì toàn bộ application beans.

Tạo `src/test/java/demo/restread/PartnerCatalogClientTests.java`:

```java
package demo.restread;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;

@RestClientTest(PartnerCatalogClient.class)
class PartnerCatalogClientTests {
    private static final String BASE =
            "https://partner.example.test";

    @Autowired
    PartnerCatalogClient partner;

    @Autowired
    MockRestServiceServer server;

    @Test
    void retrieveBodyMapsJsonToDto() {
        server.expect(requestTo(BASE + "/products/7"))
                .andExpect(method(GET))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"id":7,"name":"Guide"}
                        """));

        Product result = partner.find(7);

        assertEquals(new Product(7, "Guide"), result);
        server.verify();
    }

    @Test
    void toEntityProvidesStatusHeadersAndBody() {
        server.expect(requestTo(BASE + "/products/8"))
                .andRespond(withStatus(HttpStatus.OK)
                    .header("X-Request-ID", "req-8")
                    .header(HttpHeaders.ETAG, "\\"v8\\"")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"id":8,"name":"Metadata"}
                        """));

        ResponseEntity<Product> response =
                partner.withMetadata(8);

        assertEquals(200,
                response.getStatusCode().value());
        assertEquals("req-8",
                response.getHeaders()
                        .getFirst("X-Request-ID"));
        assertEquals("\\"v8\\"",
                response.getHeaders().getETag());
        assertEquals(new Product(8, "Metadata"),
                response.getBody());
        server.verify();
    }

    @Test
    void listPreservesGenericProductType() {
        server.expect(requestTo(BASE + "/products"))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        [{"id":1,"name":"A"},
                         {"id":2,"name":"B"}]
                        """));

        List<Product> values = partner.list();

        assertEquals(
                List.of(new Product(1, "A"),
                        new Product(2, "B")),
                values);
        server.verify();
    }

    @Test
    void postReadsCreatedStatusAndLocationWithoutBody() {
        server.expect(requestTo(BASE + "/products"))
                .andExpect(method(POST))
                .andRespond(withStatus(HttpStatus.CREATED)
                    .header(HttpHeaders.LOCATION,
                            "/products/41"));

        ResponseEntity<Void> response =
                partner.create(
                        new CreateProduct("Created"));

        assertEquals(201,
                response.getStatusCode().value());
        assertEquals(URI.create("/products/41"),
                response.getHeaders().getLocation());
        assertEquals(null, response.getBody());
        server.verify();
    }

    @Test
    void retrieveDefaultsToExceptionFor404() {
        server.expect(requestTo(BASE + "/products/404"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"code":"NOT_FOUND"}
                        """));

        RestClientResponseException error =
                assertThrows(
                    RestClientResponseException.class,
                    () -> partner.find(404));

        assertEquals(404,
                error.getStatusCode().value());
        server.verify();
    }

    @Test
    void onStatusMaps404ToTypedDomainError() {
        server.expect(requestTo(BASE + "/products/99"))
                .andRespond(
                    withStatus(HttpStatus.NOT_FOUND));

        ProductMissingException error =
                assertThrows(
                    ProductMissingException.class,
                    () -> partner.findOrThrow(99));

        assertTrue(error.getMessage()
                .contains("99"));
        server.verify();
    }

    @Test
    void exchangeSees404WithoutDefaultException() {
        server.expect(requestTo(BASE + "/probe/4"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .header("X-Request-ID", "req-4")
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("missing"));

        Probe response = partner.probe(4);

        assertEquals(404, response.status());
        assertEquals("req-4",
                response.requestId());
        assertEquals("text/plain",
                response.contentType());
        assertEquals("missing", response.body());
        server.verify();
    }

    @Test
    void exchangeLetsApplicationReject503() {
        server.expect(requestTo(BASE + "/probe/5"))
                .andRespond(
                    withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        PartnerUnavailableException error =
                assertThrows(
                    PartnerUnavailableException.class,
                    () -> partner.inspectWithPolicy(5));

        assertTrue(error.getMessage()
                .contains("503"));
        server.verify();
    }

    @Test
    void probeRefusesPayloadOver1024Bytes() {
        server.expect(requestTo(BASE + "/probe/6"))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("A".repeat(1025)));

        assertThrows(
                OversizedProbeException.class,
                () -> partner.probe(6));
        server.verify();
    }
}
```

Chạy:

```bash
./gradlew test
```

**Chín tests được thiết kế để pass** với Boot 3.5 / Spring Framework 6.2 / Java 17. Đây là **kỳ vọng qua rà soát API/source, chưa phải log của một lần thực thi Gradle**.

Các tests chứng minh:

- Converter đọc JSON DTO qua `retrieve().body`.
- `toEntity` giữ status, headers và body; ETag vẫn gồm dấu quote theo chuẩn.
- Generic list được deserialize thành `List<Product>`.
- POST đọc 201 + Location qua `toBodilessEntity`.
- 404 trên `retrieve` **mặc định ném exception**.
- `onStatus` đổi 404 thành `ProductMissingException`.
- 404 trên `exchange` **không bị status handler mặc định biến thành exception**.
- `exchange` có thể chủ động ném 503 theo policy.
- `exchange` đọc body có giới hạn, tránh buffer tùy ý.

### 15.1. Những gì slice test không chứng minh

`MockRestServiceServer` giả lập HTTP transport, không mở kết nối TLS/real socket. Chúng **không xác minh** DNS, proxy, SSL handshake, connection pooling, connect/read timeouts, redirect policy hay behavior thực của server remote. Để test phần đó cần integration tests với embedded server hoặc mock HTTP server và client transport thật (kèm network fault injection nếu cần).

`@RestClientTest` cũng không tự load mọi `@Configuration` trong application. Nếu production client phụ thuộc config bean khác, sử dụng `@Import` hoặc cấu hình đúng phạm vi slice test.

### 15.2. Tránh test dựa vào Internet thật

Nếu tests gửi request tới URL API public, kết quả sẽ dễ flaky vì network, rate limits, data thay đổi và credentials. Sử dụng `MockRestServiceServer` cho deterministic contract tests, thêm vài integration tests tới sandbox/staging của đối tác cho compatibility. Không ghi secrets vào repo hoặc mock expectations.

### 15.3. Test trên status and headers, không chỉ body

Một integration test tốt cần kiểm tra cả:
- HTTP method và đường dẫn.
- `Accept`, `Content-Type` và auth/correlation headers phù hợp.
- Status code chính xác.
- Location/ETag/Retry-After nếu hợp đồng yêu cầu.
- JSON DTO/field types.
- 4xx/5xx mapping và timeout/cancellation/retries theo policy.
- Body rỗng và unknown media type.
- Resource cleanup của raw exchange stream.

Không phải mọi endpoint đều cần assert mọi header; chỉ assert những gì là contract của chức năng.

## 16. Đọc response body lỗi an toàn

Một đối tác có thể trả:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://partner.example.test/problems/duplicate",
  "title": "Conflict",
  "status": 409,
  "detail": "Product name already exists"
}
```

Với `retrieve()`, bạn có thể:

1. Dùng `onStatus` cho **409** để map sang domain `DuplicateProductException`.
2. Hoặc bắt `RestClientResponseException` và đọc status/headers/bytes, rồi parse một error DTO sau khi kiểm tra max size, Content-Type và schema.

Không nên:

```java
catch (RestClientResponseException ex) {
    throw new RuntimeException(
            ex.getResponseBodyAsString());
}
```

Error body là dữ liệu từ remote server; nó có thể chứa HTML, stack trace, IDs, request data, các ký tự không mong đợi. Đừng đưa nguyên văn đến browser, logs hoặc metrics tags. Ánh xạ sang mã lỗi ổn định như `PARTNER_CONFLICT` và ghi `requestId` an toàn để tra cứu.

### 16.1. Đọc body sau HTTP exception khác callback raw response

`RestClientResponseException` lưu status/headers/body được framework trích xuất cho error case; developer có thể đọc qua exception. `exchange` cho trực tiếp stream response trong callback. **Không giữ `ClientHttpResponse` hoặc `InputStream` của exchange ra ngoài** khi overload mặc định đóng tài nguyên.

### 16.2. Lỗi do network không có HTTP status

`ResourceAccessException` khi connect timeout/DNS/TLS/read failure không thể luôn gắn status 503 do remote server: có thể **chưa nhận bất kỳ HTTP response nào**. Ghi loại lỗi nội bộ và áp policy retry có giới hạn, thay vì giả lập status code mà server chưa trả.

## 17. Cấu hình timeout và HTTP transport

`RestClient` có abstraction `ClientHttpRequestFactory`. Cách cấu hình timeout phụ thuộc HTTP backend đã chọn: JDK `HttpClient`, Apache HttpComponents, Simple/JDK request factory hoặc library khác.

**Không gán một property chung tưởng tượng rồi tin mọi RestClient đã có timeout hợp lý.** Cần xác nhận theo Spring Boot 3.5 auto-configuration và chosen HTTP client library.

Ví dụ Java fragment khi dùng JDK request factory:

```java
JdkClientHttpRequestFactory requestFactory =
        new JdkClientHttpRequestFactory();

requestFactory.setReadTimeout(
        Duration.ofSeconds(3));

RestClient client = RestClient.builder()
        .requestFactory(requestFactory)
        .baseUrl("https://partner.example.test")
        .build();
```

Đây là **fragment**, cần `java.time.Duration` và `org.springframework.http.client.JdkClientHttpRequestFactory`. Ngoài read timeout, **connect timeout** được cấu hình trên `java.net.http.HttpClient` tương ứng khi cần. Với Apache HttpComponents request factory, constructors/settings khác và cần dependency tương ứng; đừng copy code JDK sang Apache.

Cần phân biệt:
- DNS lookup/connection establishment.
- TLS handshake.
- Connection pool acquisition.
- Socket/read inactivity timeout.
- Overall request deadline.
- Retries/backoff và circuit breaker.
- HTTP response body streaming time.

Một timeout 3 giây không tự bảo đảm mọi phase/case chỉ mất tối đa ba giây nếu backend định nghĩa nó là read timeout; test failure modes thực tế.

### 17.1. RestClient là blocking, đừng lạm dụng trên WebFlux event loop

Nếu một controller WebFlux cần gọi API đồng bộ tạm thời:

```java
Mono<Product> result = Mono
        .fromCallable(() -> partner.find(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **fragment**, không phải cách dùng được khuyến nghị lâu dài nếu có WebClient. `boundedElastic` cô lập blocking call nhưng vẫn có thread/queue capacity và cần giới hạn concurrency/timeout. Nếu project đã thuần reactive, `WebClient` không chặn thread sẽ phù hợp hơn.

## 18. Retry, idempotency và status trong tích hợp hệ thống

Một API có thể trả 429/503/504, nhưng việc retry cần xem method và side effects:

| Method/case | Retry nên làm thế nào |
| --- | --- |
| GET idempotent, transient 503 | Có thể retry với budget/backoff/jitter |
| HEAD, transient network failure | Có thể retry nếu an toàn và server policy cho phép |
| POST tạo tài nguyên | Chỉ retry khi có idempotency key/deduplication hoặc contract rõ |
| PUT idempotent theo định nghĩa endpoint | Có thể retry với điều kiện identity/version/ETag |
| DELETE | Xem semantics/not-found state và idempotency thực tế |
| 400 malformed input | Không retry cùng payload |
| 401 token expired | Refresh token có kiểm soát, không vòng lặp |
| 403 forbidden | Không retry vô hạn |
| 404 missing | Thường domain outcome, trừ eventual consistency policy đặc biệt |
| 409 conflict | Cần reconcile và optimistic locking, không blind retry |
| 429 quota | Tôn trọng Retry-After/rate budgets |
| 503 overload | Backoff; tránh retry storm |

`retrieve`/`exchange` **không tự cung cấp chính sách retry an toàn cho business**. Muốn tự động hóa, xem retry library/circuit breaker như Resilience4j, nhưng phải thiết kế idempotency, tracing, timeouts, hedging và max attempts.

### 18.1. Khi có HTTP 202

Response 202 có thể chứa một job ID hoặc Location của status endpoint. Client cần polling với bounded cadence hoặc callback/webhook, không coi 202 là kết quả final. Đọc `Retry-After` như hint nếu được hỗ trợ. Nếu polling dùng `RestClient` blocking, đặt scheduler và giới hạn số jobs phù hợp.

## 19. Quan sát/metric/logging khi đọc status/header/body

Nên thu thập:
- Logical downstream service name (cardinality thấp).
- Route template hoặc operation name, method.
- Status family 2xx/4xx/5xx và error code chuẩn hóa.
- Latency p50/p95/p99 và timeout/retry count.
- HTTP client connection pool pending/active nếu có.
- Downstream request ID đã kiểm tra/sanitize.
- Body size/chunk counts khi có quan sát phù hợp.

Không log:
- Authorization, Proxy-Authorization, Cookie, Set-Cookie.
- Raw query strings nếu chứa tokens/PII.
- Body JSON có password, email, số điện thoại, token.
- Raw error HTML/stack traces do partner trả.
- URI với credentials nhúng.
- Metrics tags lấy trực tiếp từ product ID/user ID tạo cardinality không giới hạn.

Trong Spring Boot, inject builder giúp giữ nhiều customizations/observability. Khi tạo request factory riêng, phải test xem interceptors, TLS/proxy settings và tracing còn được áp không.

## 20. Bảo mật: SSRF, redirects, response limits, schema trust

### 20.1. SSRF với URI từ input

Nếu code xây URI từ một tham số user:

```java
String url = request.getParameter("url");

http.get()
    .uri(url)
    .retrieve()
    .body(String.class);
```

Đây là **anti-pattern**; user có thể cố buộc server gọi metadata service, loopback hoặc hosts nội bộ. Ngay cả có baseUrl, một absolute URL truyền vào `uri(...)` có thể thay host. Sử dụng allowlist base hosts, URI template path/query variables, DNS/IP/redirect policy, không cho client chọn scheme/host tùy ý.

### 20.2. HTTP redirects có thể làm leak credentials

Kiểm soát redirect following theo request factory; không cho bearer token, cookies hoặc client certificates được chuyển sang host không đáng tin. Nếu partner trả Location bất thường, xác minh scheme/hostname/port/path trước khi follow; không mặc định GET Location an toàn.

### 20.3. Response size và decompression

Server có thể trả payload rất lớn hoặc nén mạnh. `body(String.class)`/`byte[].class`/`List<Product>` có thể aggregate dữ liệu gây OOM. Giới hạn bytes sau decompression, record counts, JSON depth và concurrency; một check Content-Length trước khi đọc **không đủ**.

### 20.4. JSON object hợp lệ vẫn có thể sai nghiệp vụ

Jackson decode thành Product không kiểm chứng authorization, allowed identifiers hoặc business constraints. Validate fields/schema/server provenance theo contract. Không tự động persist mọi trường remote trả về vào entity có quyền/role/tenant ID.

## 21. RestClient vs RestTemplate vs WebClient

| Đặc điểm | RestClient | RestTemplate | WebClient |
| --- | --- | --- | --- |
| Mô hình | Đồng bộ, fluent | Đồng bộ, template methods | Reactive, non-blocking |
| Từ Spring Framework | 6.1+ | Đã có lâu | 5+ |
| Đọc body | `retrieve().body(Type)` | `getForObject(...)`, `exchange(...)` | `retrieve().bodyToMono(Type)` |
| Đọc status + headers | `retrieve().toEntity(Type)` | `getForEntity` / `exchange` | `retrieve().toEntity(Type)` trả `Mono<ResponseEntity<T>>` |
| Truy cập raw response | `exchange(callback)` | `execute(callbacks)` | `exchangeToMono/Flux` |
| Default 4xx/5xx | Throw ở terminal retrieve | `ResponseErrorHandler` | Error signal của Mono/Flux |
| Phạm vi status handler | `onStatus` cho retrieve | `setErrorHandler` | `onStatus` cho retrieve |
| Trả dữ liệu | T / ResponseEntity<T> | T / ResponseEntity<T> | Mono<T> / Flux<T> |
| Thread blocking | Có | Có | Không chặn I/O theo thiết kế |
| Môi trường điển hình | MVC/scheduled sync clients | Legacy MVC code | WebFlux/reactive integrations |

**Đặc biệt:** `RestTemplate.exchange(...)` và `RestClient.exchange(...)` trùng tên nhưng khác signatures và default error handling. `WebClient.exchangeToMono(...)` cũng không giống `RestClient.exchange(...)` về callback typing và body/resource lifecycle.

### 21.1. Migration RestTemplate sang RestClient

| RestTemplate cũ | RestClient tương đương |
| --- | --- |
| `getForObject(url,Product.class)` | `get().uri(url).retrieve().body(Product.class)` |
| `getForEntity(url,Product.class)` | `get().uri(url).retrieve().toEntity(Product.class)` |
| `postForEntity(url,input,Product.class)` | `post().uri(url).body(input).retrieve().toEntity(Product.class)` |
| `delete(url)` | `delete().uri(url).retrieve().toBodilessEntity()` |
| `exchange(url,GET,entity,Product.class)` | `method(GET).uri(url).headers(...).retrieve().toEntity(Product.class)` |
| `execute(url,method,callback,extractor)` | `method(method).uri(url).exchange(exchangeFunction)` |

Migration không phải chỉ đổi API names. Phải giữ auth headers, error mapping, pooling/timeouts, URI encoding, interceptors và testing contract.

## 22. Sơ đồ quyết định thực hành

```text
Cần gọi API đồng bộ?
  |
  +-- Không -> dùng WebClient / reactive client phù hợp
  |
  +-- Có -> dùng RestClient
              |
              +-- Chỉ cần body thành công?
              |      |
              |      +-- yes -> retrieve().body(Type)
              |
              +-- Cần cả status + headers + body DTO?
              |      |
              |      +-- yes -> retrieve().toEntity(Type)
              |
              +-- Không dùng body nhưng cần status/Location?
              |      |
              |      +-- yes -> retrieve().toBodilessEntity()
              |
              +-- Cần custom 404/409 -> domain exception?
              |      |
              |      +-- yes -> retrieve().onStatus(...)
              |
              +-- Cần mọi status làm value,
              |   hoặc raw body stream/conditional extraction?
                     |
                     +-- yes -> exchange(callback)
                                  |
                                  +-- tự kiểm status
                                  +-- giới hạn body
                                  +-- hoàn tất read trong callback
                                  +-- không leak resource
```

## 23. Các lỗi phổ biến và cách khắc phục

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi retrieve nhưng server không nhận request | Chưa gọi terminal operation | `body/toEntity/toBodilessEntity` |
| 404 mà code không vào `if(status==404)` | `retrieve` ném default exception | `onStatus` hoặc `exchange` |
| `exchange` trả 503 mà app coi thành success | `exchange` không áp default status handlers | Kiểm tra status tường minh |
| Không đọc được Location 201 | Chỉ gọi `body(Product.class)` | `toEntity` hoặc `toBodilessEntity` |
| Generic JSON list bị map thành LinkedHashMap | Dùng raw `List.class` | `ParameterizedTypeReference<List<Product>>` |
| `body(...)` trả null trên 204 | Không có response body | Dùng `ResponseEntity<Void>`, xử lý empty |
| Mất correlation ID | Chỉ lấy body | Đọc `getHeaders().getFirst(...)` |
| HTTP 429 bị coi là product missing | Status mapping quá rộng | Typed 429/rate limit policy |
| I/O exception bị gán 503 của server | Chưa chắc có HTTP response | Phân biệt `ResourceAccessException` |
| Read body sau `exchange` callback lỗi | Response tự đóng | Đọc/copy trong callback |
| Download file lớn gây OOM | `body(byte[].class)`/readAllBytes | Stream bounded với exchange hoặc HTTP client phù hợp |
| Retry POST tạo trùng resource | Timeout nhưng server đã commit | Idempotency key / dedupe |
| Header Retry-After không parse được | Giả định luôn là số | Hỗ trợ seconds hoặc HTTP-date |
| ETag cache trả sai giữa tenants | Cache key thiếu auth/Vary | Thiết kế cache key/policy |
| Test slice không inject service | `@RestClientTest` chỉ scan scope hẹp | Chỉ định component/`@Import` |
| HTTPS thật lỗi dù MockRestServiceServer pass | Mock không test TLS/transport | Real transport integration tests |
| WebFlux lag nặng khi gọi RestClient | Blocking trên event loop | `WebClient` hoặc boundedElastic tạm thời |
| Authorization header xuất hiện trong logs | Logging không redacted | Sanitize request/response logs |
| URI partner dùng user input host | SSRF | Allowlist scheme/host/IP/redirect policy |
| Connection pool cạn | Timeout lớn/response chưa đóng | Correct resource ownership, pool metrics |
| `onStatus` có nhưng exchange không dùng | Status handlers của retrieve không áp trong exchange | Kiểm tra status ngay callback |
| Nâng Spring major, method overload khác | API versions thay đổi | Đọc Javadoc/BOM phù hợp và chạy tests |

### 23.1. Debug theo thứ tự

1. Xác nhận runtime thực là Spring Framework 6.2/Spring Boot 3.5 và loại client `RestClient`.
2. Kiểm tra `baseUrl` + template variables + method/path/query/headers.
3. Bảo đảm terminal operation đã được gọi.
4. Xác định đang dùng `retrieve` hay `exchange` để hiểu error policy.
5. Kiểm tra HTTP status/headers trước khi kết luận body semantics.
6. Với 4xx/5xx, xem typed exception hoặc callback status policy.
7. Với network fail, xem DNS/TLS/connect/read timeout và request factory.
8. Với body null/JSON lỗi, xem status 204/304, Content-Type/schema.
9. Với file lớn, kiểm tra aggregate bytes, direct memory, resource closure.
10. Với tests, dùng MockRestServiceServer cho logic và real HTTP transport integration cho network.

## 24. Checklist trước khi tích hợp production

- [ ] Chọn đúng `RestClient` cho yêu cầu đồng bộ và `WebClient` khi cần reactive non-blocking.
- [ ] Inject Boot `RestClient.Builder` nếu cần auto-configured customizations.
- [ ] Tái sử dụng RestClient instance; không tạo client/connection vô hạn theo request.
- [ ] Gọi terminal operation sau `retrieve()`.
- [ ] Dùng `toEntity` nếu cần cả status, header, body.
- [ ] Dùng `toBodilessEntity` cho 201/202/204 không cần body.
- [ ] Hiểu `retrieve` mặc định throw 4xx/5xx; áp `onStatus` theo business.
- [ ] Nếu dùng `exchange`, tự phân loại status và đọc body trong callback.
- [ ] Không trả raw InputStream/ClientHttpResponse khỏi callback mặc định.
- [ ] Không đọc file lớn vô hạn vào `byte[]`/String/List.
- [ ] Dùng `ParameterizedTypeReference` cho generic JSON bodies.
- [ ] URI variables được encode và base URL/redirect theo allowlist chống SSRF.
- [ ] Timeout kết nối/đọc/deadline/pool có cấu hình và tests riêng.
- [ ] HTTP retry có max attempts/backoff/jitter/idempotency.
- [ ] Phân biệt 401/403/404/409/429/500/503 và I/O failures.
- [ ] Parse Retry-After đúng cả delta-seconds và HTTP-date nếu sử dụng.
- [ ] Kiểm tra ETag/304/cache Vary/auth scope đúng.
- [ ] Không log Authorization/cookies/PII/raw error body.
- [ ] Test with @RestClientTest + MockRestServiceServer cho success/errors/headers/body.
- [ ] Có integration tests với TLS/proxy/connection pools/real transport khi cần.
- [ ] Spring version/migration API và các header semantics được review sau nâng cấp.

## 25. Bài tập tự đánh giá

1. `RestClient.retrieve()` có phát HTTP request ngay không? Phương thức nào là terminal?
2. Vì sao chỉ dùng `body(Product.class)` chưa đủ khi API tạo trả 201 + Location?
3. Viết đoạn `retrieve().toEntity(Product.class)` lấy ETag, Content-Type và X-Request-ID.
4. Phân biệt `toBodilessEntity()` với `body(Void.class)` trong tình huống cần status/Location.
5. Vì sao `ResponseEntity<Product>.getBody()` có thể null dù status là 204?
6. API trả JSON array, dùng `ParameterizedTypeReference<List<Product>>` thay `List.class` để giải quyết lỗi nào?
7. Khi retrieve gặp 404, code phía sau `toEntity` có chạy bình thường không?
8. Thêm `onStatus` cho 404 thành ProductMissingException, giữ 401/429 theo default.
9. Gọi `exchange` với response 503. Vì sao không có default HttpServerErrorException?
10. Xây `Probe` chứa status, requestId và body text, có cap 1024 bytes trong callback.
11. Nếu trả `InputStream` từ `exchange` callback, chuyện gì có thể xảy ra khi caller đọc sau đó?
12. Khi cần xử lý file nhiều GB, tại sao `body(byte[].class)` không an toàn?
13. So sánh ý nghĩa `HttpHeaders#getFirst` với `get` khi header có nhiều giá trị.
14. Server trả `Retry-After: Wed, 21 Oct 2026 08:00:00 GMT`, parse int có được không?
15. Khi dùng ETag và 304, vì sao phải quan tâm Vary và tenant/auth cache key?
16. Nếu `RestClient` báo `ResourceAccessException` trước HTTP response, lấy status code từ đâu?
17. Một POST nhận timeout nhưng server có thể đã tạo resource. Nên retry thế nào?
18. Phân biệt 429 theo tenant quota với 503 downstream overload khi thiết kế retry.
19. Vì sao test `@RestClientTest` không bảo đảm DNS/TLS/redirect đúng ở production?
20. Dùng MockRestServiceServer test default 404, custom onStatus 404 và exchange 404 như ba trường hợp khác.
21. Một REST API trả body là HTML mặc dù Accept JSON. Client cần xem những thông tin nào trước khi deserialize?
22. Xây `RestClient` bằng Boot-provided Builder có lợi gì so với `RestClient.create()` trong ứng dụng lớn?
23. Nếu ứng dụng WebFlux dùng RestClient trên Netty event loop, triệu chứng và giải pháp nào?
24. Phân biệt `RestTemplate.exchange(...)` và `RestClient.exchange(...)` theo signatures và error policy.
25. Thêm timeout chính xác cho HTTP backend bạn dùng, và test connect timeout/read timeout bằng real mock server.
26. Thiết kế circuit breaker/retry policy cho partner API có 200, 404, 429, 503 và network timeout.
27. Nếu Location response trỏ sang `http://127.0.0.1/...`, vì sao không tự động follow?
28. Dùng status/headers/body trong một object ứng dụng mà không cho raw headers chứa secrets bị trả lại frontend.
29. Hãy viết test chứng minh response body 1025 bytes bị `OversizedProbeException` từ bounded read.
30. Khi nâng từ Spring Boot 3.5 lên Boot 4, cần xác minh những APIs, starters, test imports và request factories nào?

## 26. Tài liệu chính thức

- [Spring Framework 6.2 — REST Clients reference](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient synchronous API, retrieve/body/toEntity, status/error handling, exchange và so sánh RestTemplate.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.html): builder, fluent API.
- [Spring Framework 6.2 — RestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.ResponseSpec.html): `body`, `toEntity`, `toBodilessEntity`, `onStatus`.
- [Spring Framework 6.2 — RestClient.RequestHeadersSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html): `retrieve`, `exchange`, response lifecycle.
- [Spring Framework 6.2 — HttpHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/HttpHeaders.html): ETag, Location, Content-Type, contentLength, retry semantics.
- [Spring Framework 6.2 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): status, headers, body.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html#rest-message-conversion): converter selection và JSON mapping.
- [Spring Boot 3.5 — RestClientTest](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest` và MockRestServiceServer.
- [Spring Framework — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): request expectations, fake responses và verify.
- [Spring Framework — Client Request Factories](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html#rest-client-request-factories): request transport/timeouts.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): response status, Location, Retry-After, ETag và caching semantics.
- [Spring Framework — Reactive WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): khi cần asynchronous/non-blocking I/O.
