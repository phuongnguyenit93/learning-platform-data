# Đọc status, header, nội dung rỗng và Problem Details

## 1. Client REST không được chỉ đọc JSON

`DELETE` trả **204 No Content** không có JSON; `GET` có `If-None-Match` trả **304 Not Modified** cần cache; `POST` trả **409 Conflict** kèm `application/problem+json` mô tả lỗi nghiệp vụ. Cả ba response đều đòi cách xử lý khác nhau.

Luôn gọi `parseJson(response.body())` sẽ làm hỏng xử lý body rỗng và mất `ETag`/`Location`/`Retry-After`.

Bài thuộc chương **Client Java** của **INTEGRATION_API_REST**: vận dụng resource/URI, HTTP status, hợp đồng dữ liệu, cache, idempotency, OpenAPI, bảo mật và kiểm thử Java/Spring để **đọc response đúng ngữ nghĩa**.

Bạn sẽ biết đọc **status → header → body**, phân biệt 0 byte/`null`/`{}`, xử lý Problem Details (RFC 9457) và viết kiểm thử cho Java `HttpClient`, Spring `RestClient`/`WebClient`.

## 2. Ba phần của response: status → headers → content

Ví dụ một response thông thường:

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/o-103
ETag: "order-v1"
Content-Type: application/json
Cache-Control: private, no-store

{"id":"o-103","status":"CREATED"}
~~~

Client nên xử lý theo thứ tự:

~~~mermaid
flowchart TD
    R["Nhận HTTP response"] --> S["Đọc status nguyên gốc"]
    S --> H["Đọc headers liên quan"]
    H --> D{"Có body theo ngữ nghĩa HTTP?"}
    D -->|Không: HEAD/1xx/204/304...| N["Không deserialize JSON"]
    D -->|Có thể có| L{"Body thực sự có bytes?"}
    L -->|Không| E["Xử lý empty theo hợp đồng"]
    L -->|Có| T{"Content-Type là gì?"}
    T -->|application/problem+json| P["Parse Problem Details"]
    T -->|application/json| J["Parse DTO khi status cho phép"]
    T -->|Khác/không hợp lệ| F["Lỗi giao thức hoặc fallback an toàn"]
~~~

**Status quyết định ngữ nghĩa**, header cung cấp metadata, body chỉ được đọc theo status/contract. `Content-Length` có thể vắng mặt hoặc bị ảnh hưởng bởi transfer/content encoding; JSON `status` không thay HTTP status line.

### 2.1. Những phản hồi không mang content

Theo HTTP Semantics (RFC 9110), **1xx, 204 và 304 không có response content**; response đối với phương thức **HEAD cũng không có content**. `205 Reset Content` cũng không được tạo content theo định nghĩa riêng của mã trạng thái đó.

| Tình huống | Client cần hiểu | Việc không nên làm |
|---|---|---|
| `HEAD /files/f-9` → **200** | Header mô tả representation tương ứng, **không có body** | Deserialize `FileDto` |
| `DELETE /orders/o-42` → **204** | Thao tác thành công, **không có body** | Coi JSON rỗng là server hỏng |
| `PUT` → **205** | Thành công và yêu cầu client reset trạng thái biểu mẫu/đầu vào | Chờ JSON thành công |
| `GET` có `If-None-Match` → **304** | Không có representation mới; có thể tái sử dụng bản cache hợp lệ | Trả `null` coi như mất resource |
| `GET` → **200**, body dài **0 byte** | HTTP có thể hợp lệ, nhưng **sai hợp đồng** nếu yêu cầu JSON object | Tự bịa DTO mặc định |
| `GET` → **200**, body `null` | **Bốn ký tự JSON**, một JSON value hợp lệ | Đồng nhất với 0 byte |
| `GET` → **200**, body `{}` | JSON object rỗng, khác `null` | Coi là không có nội dung |

Với **204**, server có thể trả header metadata như `ETag` sau khi cập nhật; hãy giữ header đó. Với **304**, chỉ sử dụng cached representation **đã được client lưu và xác minh đúng cache key/variant**; nếu client không có cache tương ứng, cần GET lại không điều kiện theo chính sách.

### 2.2. Phân loại status mà không mất ý nghĩa nghiệp vụ

| Status | Điều nên làm trong client |
|---|---|
| **200 OK** | Đọc representation theo media type; với GET JSON kỳ vọng object/array đúng schema |
| **201 Created** | Đọc `Location` để biết URI resource mới, body có thể có hoặc rỗng theo contract |
| **202 Accepted** | Theo dõi URI job/operation; **chưa kết luận nghiệp vụ đã hoàn thành** |
| **204 No Content** | Thành công không body; trả một kết quả kiểu `Completed`/`void` |
| **206 Partial Content** | Xử lý `Content-Range`/multipart theo hợp đồng download, **không coi là JSON đầy đủ** |
| **301/302/303/307/308** | Đánh giá redirect policy, không tự chuyển token sang host lạ |
| **304 Not Modified** | Cập nhật cache metadata và dùng representation cache hợp lệ |
| **400/422** | Đầu vào/validation không hợp lệ; phân tích Problem Details nếu có |
| **401 Unauthorized** | Credential thiếu/hết hạn/sai; xem `WWW-Authenticate`, xử lý refresh theo policy |
| **403 Forbidden** | Đã xác thực nhưng thiếu quyền, không retry vòng lặp với cùng credential |
| **404/410** | Không tồn tại hoặc resource đã bị xóa vĩnh viễn theo contract |
| **409 Conflict** | Xung đột trạng thái/idempotency, cần xử lý nghiệp vụ |
| **412/428** | HTTP precondition sai hoặc thiếu, cần làm mới `ETag`/điều kiện |
| **429/503** | Có thể retry có giới hạn nếu operation retry-safe; xem `Retry-After` |
| **500/502/504** | Lỗi hạ tầng/đường truyền; retry chỉ khi đủ điều kiện an toàn |

**Không coi mọi 2xx là có DTO**: UI/worker cần biết khi nào poll job, reload cache, nhập lại dữ liệu hoặc dừng vì thiếu quyền.

## 3. Header quan trọng: đọc có chọn lọc

Tên header **không phân biệt hoa/thường**; value có thể lặp và phải parse theo đúng ngữ nghĩa từng header.

| Header | Khi nào cần | Cách diễn giải |
|---|---|---|
| `Content-Type` | Trước khi deserialize content | Phân biệt `application/json`, `application/problem+json`, binary và tham số `charset` |
| `Location` | `201`, `202`, redirect | URI resource hoặc nơi theo dõi; có thể là relative reference |
| `ETag` | GET/HEAD/PUT, 204/304 | Validator của selected representation; gửi `If-None-Match`/`If-Match` khi thích hợp |
| `Last-Modified` | Conditional GET | HTTP-date, độ chính xác khác ETag; không coi là version unique |
| `Cache-Control`, `Vary` | Cache nội dung | Không trộn response giữa tenant, bearer token, language hay representation |
| `Retry-After` | 429/503, đôi khi 202/redirect | Số giây hoặc HTTP-date; giới hạn thời gian chờ thực tế |
| `WWW-Authenticate` | 401, challenge | Thông tin cơ chế xác thực, không phải token |
| `Content-Range` | 206/416 | Phạm vi bytes, phải xác minh tương ứng request `Range` |
| `Link` | Pagination/hypermedia | URI và relation; parse theo RFC, không split mù bằng dấu phẩy |
| `X-Request-Id`/trace ID | Quan sát lỗi | Chỉ là correlation metadata, không là danh tính hoặc bằng chứng phân quyền |

### 3.1. Location phải được kiểm tra trước khi gọi tiếp

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/job-701
Retry-After: 3
Content-Type: application/json

{"id":"job-701","status":"QUEUED"}
~~~

`Location` có thể relative; resolve rồi kiểm tra **scheme/host/port** và allowlist, không gửi bearer/cookie sang host lạ. Với redirect **301/302/303/307/308**, chính sách method/body khác nhau; cấu hình rõ trước khi cho phép tự theo.

### 3.2. Retry-After không phải lệnh retry vô hạn

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 7
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/rate-limit",
 "title":"Rate limit exceeded","status":429}
~~~

`Retry-After` là **số giây không âm** hoặc **HTTP-date**. Xử lý clock skew, dữ liệu sai, deadline, retry budget và jitter. **Không tự retry POST không có idempotency bảo đảm**.

### 3.3. ETag không phải JSON field

~~~http
GET /v1/orders/o-42 HTTP/1.1
If-None-Match: "order-v7"

HTTP/1.1 304 Not Modified
ETag: "order-v7"
Cache-Control: private, max-age=30
~~~

Client trả lại bản JSON `order-v7` đang cache nếu key và quyền còn hợp lệ, đồng thời cập nhật metadata theo quy tắc cache. `ETag` có thể là weak validator (`W/"..."`); **`If-Match` dùng phép so sánh strong**, không sử dụng weak ETag cho optimistic write precondition. Không coi mọi ETag là hash nội dung; cách tạo là trách nhiệm origin.

## 4. Problem Details (RFC 9457): lỗi máy hiểu được

**Problem Details** là dạng mô tả lỗi chuẩn hóa, thường được gửi dưới `Content-Type: application/problem+json`. Nó không thay thế status HTTP. Một response có thể là:

~~~http
PATCH /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
If-Match: "order-v7"

{"note":"Giao giờ hành chính"}

HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-912

{
  "type":"https://api.example.com/problems/order-already-closed",
  "title":"Order cannot be changed",
  "status":409,
  "detail":"Đơn đã đóng và không thể sửa ghi chú.",
  "instance":"/v1/problems/occurrences/evt-92",
  "code":"ORDER_ALREADY_CLOSED",
  "requestId":"req-912"
}
~~~

| Trường | Ý nghĩa | Cách client dùng |
|---|---|---|
| `type` | **Định danh chính** của loại vấn đề dưới dạng URI reference; mặc định `about:blank` nếu thiếu | Phân nhánh theo ID ổn định, không theo ngôn ngữ mô tả |
| `title` | Tóm tắt dành cho người đọc | Hiển thị đã kiểm soát; có thể được địa phương hóa |
| `status` | Mã HTTP được ghi lại, **chỉ mang tính tham khảo** | Ưu tiên status thực từ response để quyết định protocol |
| `detail` | Giải thích cho một lần xảy ra | Có thể hiển thị, **không parse chuỗi để điều khiển logic** |
| `instance` | URI reference nhận diện lần xảy ra | Dùng cho hỗ trợ/audit nếu policy cho phép |
| `code`, `invalidParams` | **Extension** do API tự định nghĩa | Chỉ parse khi hợp đồng ghi rõ kiểu/cấu trúc |

`type` là ID chuẩn; `code` là extension. Khi body `"status":400` nhưng HTTP trả `503`, **ưu tiên 503** và ghi nhận contract drift. Không tự truy cập `type` URL (nguy cơ SSRF/rò dữ liệu).

### 4.1. Nhận dạng đúng media type và body rỗng

Chỉ parse Problem Details khi:

1. Response thật sự có body bytes.
2. `Content-Type` phù hợp `application/problem+json`, có thể chứa tham số (ví dụ `; charset=utf-8`), so sánh media type không phân biệt hoa/thường.
3. Body là JSON object có cấu trúc hợp lệ; nếu field vắng mặt, sử dụng mặc định RFC và giữ lại status HTTP.

`500` có thể kèm HTML gateway; `401` có thể không body nhưng có `WWW-Authenticate`. Giữ status/header khi parse thất bại; `application/json` hay một media type `+json` bất kỳ **không tự chứng minh** là Problem Details.

### 4.2. Validation lỗi theo nhiều trường

Response `422 application/problem+json` có thể mang `code=VALIDATION_FAILED` và extension `"invalidParams":[{"name":"quantity","reason":"must be at least 1"}]`. `invalidParams` **không thuộc trường chuẩn RFC**, phải validate cấu trúc theo API contract. `detail`/`reason` có thể được dịch, không dùng làm mã máy; tránh log extension chứa PII.

### 4.3. Định nghĩa result theo dữ liệu nghiệp vụ

Thiết kế client tốt phân biệt rõ:

~~~text
Found<Order>              // 200 + DTO hợp lệ
Created<Order>            // 201 + URI mới + optional body
Accepted<Operation>       // 202 + nơi theo dõi, chưa hoàn tất
Completed                 // 204, không body
NotModified               // 304, yêu cầu cached representation phù hợp
RemoteFailure             // non-2xx + status, headers, optional Problem Details
TransportFailure          // DNS, TLS, timeout, reset kết nối: CHƯA có HTTP status
ProtocolFailure           // status/media type/schema/body không đúng contract
~~~

**Transport failure không đồng nghĩa server chưa xử lý.** Ví dụ client POST bị timeout sau khi server commit có thể đã tạo resource. Retry phải dựa vào idempotency key, trạng thái operation hoặc truy vấn đối soát, không suy rằng exception mạng là “chưa tạo”.

## 5. Java 17+ HttpClient: xử lý response theo status trước

`java.net.http.HttpClient` có sẵn trong JDK (Java 11+). Ví dụ dưới đây dùng Java 17, Jackson `ObjectMapper` và DTO giả định. Đây là **khung adapter HTTP tập trung vào contract**: các import, repository logic, retry và wire integration được tách riêng.

### 5.1. Mô hình kết quả không làm mất status

~~~java
record OrderView(String id, String status, long totalAmount) {}

record RemoteProblem(
    String type, String title, String detail, String code
) {}

record ClientReply<T>(
    int status,
    Optional<T> value,
    Optional<RemoteProblem> problem,
    Optional<String> etag,
    Optional<URI> location
) {}
~~~

`ClientReply` giữ metadata nhưng có thể chứa tổ hợp sai (vừa `value` vừa `problem`). Production nên dùng **sealed outcome types**/factory có invariant; đây là ví dụ tập trung vào cách đọc HTTP.

### 5.2. Thực hiện GET, kiểm tra header và body

~~~java
class OrderHttpClient {
    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
    private final ObjectMapper mapper = new ObjectMapper();

    ClientReply<OrderView> getOrder(URI uri, String bearer)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(8))
            .header("Accept",
                "application/json, application/problem+json")
            .header("Authorization", "Bearer " + bearer)
            .GET()
            .build();

        HttpResponse<byte[]> response =
            http.send(request, HttpResponse.BodyHandlers.ofByteArray());
        int status = response.statusCode();
        byte[] bytes = response.body();
        HttpHeaders headers = response.headers();
        String type = headers.firstValue("Content-Type").orElse("");
        Optional<String> etag = headers.firstValue("ETag");
        Optional<URI> location = headers.firstValue("Location")
            .flatMap(v -> safeLocation(uri, v));

        // Không parse response không được mang content.
        if (status == 204 || status == 304) {
            return new ClientReply<>(status, Optional.empty(),
                Optional.empty(), etag, location);
        }
        if (status == 200) {
            if (bytes.length == 0 || !isMediaType(type, "application/json")) {
                throw new InvalidRemoteResponseException(
                    "200 GET phải có JSON theo hợp đồng");
            }
            OrderView value;
            try {
                value = mapper.readValue(bytes, OrderView.class);
            } catch (IOException badJson) {
                throw new InvalidRemoteResponseException(
                    "HTTP 200: JSON không đúng schema OrderView");
            }
            if (value == null) {
                throw new InvalidRemoteResponseException(
                    "JSON null không phải OrderView");
            }
            return new ClientReply<>(status, Optional.of(value),
                Optional.empty(), etag, location);
        }

        Optional<RemoteProblem> problem = Optional.empty();
        if (bytes.length > 0
                && isMediaType(type, "application/problem+json")) {
            try {
                JsonNode p = mapper.readTree(bytes);
                if (p != null && p.isObject()) {
                    problem = Optional.of(new RemoteProblem(
                        p.path("type").asText("about:blank"),
                        p.path("title").asText(""),
                        p.path("detail").asText(""),
                        p.path("code").asText("")
                    ));
                }
            } catch (IOException malformed) {
                // Ghi nhận protocol anomaly có kiểm soát; giữ nguyên status.
            }
        }
        return new ClientReply<>(status, Optional.empty(),
            problem, etag, location);
    }

    private static boolean isMediaType(String raw, String expected) {
        return raw.split(";", 2)[0].trim().equalsIgnoreCase(expected);
    }

    private static Optional<URI> safeLocation(URI base, String raw) {
        try {
            URI absolute = base.resolve(URI.create(raw));
            // Chỉ giữ Location cùng scheme/host/port theo policy ví dụ.
            if (!Objects.equals(base.getScheme(), absolute.getScheme())
                    || !Objects.equals(base.getHost(), absolute.getHost())
                    || base.getPort() != absolute.getPort()) {
                return Optional.empty();
            }
            return Optional.of(absolute);
        } catch (IllegalArgumentException e) {
            return Optional.empty();
        }
    }
}
~~~

Mã dùng `java.net.URI`, `java.net.http.*`, `java.io.IOException`, `java.time.Duration`, `java.util.*`, Jackson `ObjectMapper/JsonNode` và exception giả định `InvalidRemoteResponseException`. Token lấy từ credential provider, không ghi vào URI/log.

**Giới hạn:** `ofByteArray()` buffer toàn bộ body; chỉ dùng với response nhỏ và giới hạn kích thước ở transport. File lớn cần `ofFile`/`ofInputStream`, capped reader và cleanup. Phân biệt `IOException` mạng với lỗi JSON; không biến mọi `IOException` thành “400”.

### 5.3. 304 và 204 phải được xử lý theo operation

`304` chỉ trả metadata; tầng gọi phải có cache đúng key/variant. `204` hợp lệ cho nhiều thao tác ghi nhưng có thể **vi phạm hợp đồng GET Order** nếu GET luôn phải trả object. Rẽ nhánh theo **method + endpoint + status**.

`sendAsync` trả `CompletableFuture<HttpResponse<T>>`; timeout có thể bị bọc trong `CompletionException`, không khiến retry tự nhiên an toàn.

## 6. Spring RestClient và WebClient: chọn đường xử lý chủ động

Spring có **`RestClient`** đồng bộ (Framework 6.1+, Boot 3.2+) và **`WebClient`** reactive:

- `RestClient.retrieve()` mặc định xử lý 4xx/5xx bằng exception; `exchange(...)` cho phép đọc status/body chủ động.
- `WebClient.retrieve()` mặc định phát error signal cho 4xx/5xx; `exchangeToMono(...)` cho phép tự quyết định.
- `ResponseEntity<T>` có status/headers, còn `T=null` **không phân biệt** 204, 304 và 200 rỗng.

### 6.1. RestClient: giữ status và body ở một chỗ

~~~java
record RawReply(int status, String contentType,
                String etag, byte[] bytes) {}

RestClient client = RestClient.builder()
    .baseUrl("https://api.example.com")
    .build();

RawReply reply = client.delete()
    .uri("/v1/orders/{id}", "o-42")
    .header("Authorization", "Bearer " + token)
    .exchange((request, response) -> {
        int status = response.getStatusCode().value();
        String type = response.getHeaders().getFirst("Content-Type");
        String etag = response.getHeaders().getETag();
        // Chỉ minh họa cho response nhỏ; production phải giới hạn bytes.
        byte[] data = response.getBody().readAllBytes();
        return new RawReply(status, type, etag, data);
    });

if (reply.status() == 204) {
    // Xóa thành công, không parse JSON.
} else if (reply.status() == 409) {
    // Nếu content type là application/problem+json thì parse problem.
} else {
    // Các status khác được phân nhánh riêng.
}
~~~

`exchange` **không áp dụng status handlers của `retrieve`**. Client tự kiểm tra 409/204 và không parse body rỗng. `readAllBytes` chỉ dành cho response nhỏ; file lớn phải đọc giới hạn/streaming.

GET đơn giản có thể dùng `retrieve().body(OrderView.class)`; operation có 201/202/204/304 cần adapter phân nhánh.

### 6.2. WebClient: không làm mất lỗi trong reactive chain

~~~java
record RawReactiveReply(
    int status, String contentType, String etag, String body) {}

WebClient client = WebClient.builder()
    .baseUrl("https://api.example.com")
    .build();

Mono<RawReactiveReply> reply = client.get()
    .uri("/v1/orders/{id}", "o-42")
    .headers(h -> h.setBearerAuth(token))
    .exchangeToMono(response -> {
        int status = response.statusCode().value();
        String type = response.headers().contentType()
            .map(MediaType::toString).orElse("");
        String etag = response.headers().asHttpHeaders().getETag();

        if (status == 204 || status == 304) {
            return Mono.just(new RawReactiveReply(status, type, etag, ""));
        }
        return response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RawReactiveReply(status, type, etag, body));
    });
~~~

Tầng gọi map `RawReactiveReply` theo status, chỉ parse Problem Details đúng media type. `exchangeToMono` giải phóng body chưa đọc khi publisher hoàn thành; stream dài cần API streaming và cancellation.

**Không `block()` trên Netty event-loop.** `bodyToMono(String.class)` buffer nội dung: giới hạn kích thước và timeout. `onErrorResume` phải phân biệt lỗi mạng/decoder, không nuốt tất cả thành `Mono.empty()`.

### 6.3. Chọn hướng xử lý theo mục tiêu

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Java thuần, JDK 17+, ít dependency | `java.net.http.HttpClient` |
| Spring MVC đồng bộ | `RestClient` với `exchange` hoặc status handler rõ ràng |
| Spring WebFlux hoặc streaming | `WebClient` với `exchangeToMono`/`exchangeToFlux` |
| SDK client cần domain error ổn định | Adapter riêng trả typed outcomes, không phơi exception thư viện ra mọi tầng |

Chọn theo stack, nhưng **diễn giải cùng một hợp đồng response nhất quán** trên mọi client.

## 7. Những lỗi triển khai thường gặp

| Phản mẫu | Hệ quả | Cách sửa |
|---|---|---|
| `mapper.readValue(response.body(), OrderView.class)` cho mọi response | 204/304 bị lỗi JSON; 409 bị parse sai DTO | Rẽ nhánh theo method/status trước khi deserialize |
| Tin `problem.status` hơn status HTTP | 503 có body ghi 400 bị xử lý sai | Giữ status thực; log contract inconsistency |
| `onErrorResume(ex -> Mono.empty())` cho mọi exception | 401/429/503 thành “không có resource” | Phân biệt remote/transport/protocol failure |
| Trả duy nhất `OrderView` | Mất `ETag`, `Location`, `Retry-After` | Dùng typed result kèm metadata cần thiết |
| JSON `null` xem như body rỗng | Không phát hiện schema drift | Kiểm tra schema và raw body length riêng |

Đặc biệt, khi gateway trả HTML `502`, không cố ép thành Problem Details; khi cache không còn representation, không dùng `304` để dựng lại DTO.

## 8. Bảo mật và độ tin cậy ở phía client

HTTP client là một **ranh giới tin cậy**: remote server, gateway và proxy có thể gửi header/body không đúng hợp đồng, kể cả vô tình. Những biện pháp quan trọng:

- **HTTPS/TLS:** dùng chứng chỉ tin cậy và hostname verification; không tắt validation để “sửa lỗi test”. Giới hạn host đích, không nhận URL tùy ý từ user nếu có thể dẫn tới SSRF.
- **Bearer token:** lấy từ credential provider tin cậy, giới hạn scope/audience. Không log `Authorization`, cookie, raw Problem Details có PII hoặc signed URL. Với `401`, chỉ refresh token theo policy; tránh refresh loop.
- **Redirect/Location:** mặc định từ chối chuyển credential sang host khác. Khi poll `Location` hoặc theo `Link`, validate URI origin/scheme và đường dẫn theo quy ước; không tự GET mọi URI trong `type`/`instance` của lỗi.
- **Cache đa tenant:** key bao gồm resource, user/tenant, content negotiation và những điều kiện `Vary`; chú ý `Cache-Control: private/no-store`, không dùng 304 để lộ bản lưu của principal khác.
- **Giới hạn tài nguyên:** connect/response timeout, giới hạn response bytes và độ sâu JSON, decompression ratio khi thích hợp; có deadline cho retry và circuit breaker/bulkhead nếu ứng dụng cần.
- **Retry an toàn:** phân biệt transport timeout và HTTP 503; chỉ retry request có tính idempotent hoặc POST có idempotency key **được server thực thi**. Không tạo key mới cho retry cùng ý định.

`403` không được khắc phục bằng retry cùng token; `409` chỉ retry nếu loại conflict/`type`/`code` và hợp đồng cho phép.

## 9. Kiểm thử status/header/body bằng response giả lập

### 9.1. Ma trận tối thiểu

| Ca | Response mô phỏng | Kỳ vọng |
|---|---|---|
| C01 | `200 application/json` với DTO hợp lệ | Parse đúng field |
| C02 | `200` body rỗng dù contract cần DTO | **Protocol failure**, không tạo DTO mặc định |
| C03 | `200` body là JSON `null` | Phân biệt với body 0 byte |
| C04 | `201` + `Location` relative | Resolve URI trong origin cho phép |
| C05 | `202` + `Location`/`Retry-After` | Nhận job, chưa đánh dấu completed |
| C06 | `204` + `ETag`, body rỗng | Thành công, giữ ETag, không parse JSON |
| C07 | `304` + `ETag` khi cache hợp lệ | Dùng cached representation đúng key |
| C08 | `304` nhưng không có cache | GET lại không điều kiện hoặc báo cache miss |
| C09 | `409 application/problem+json` hợp lệ | Giữ status, type/code; không parse thành DTO |
| C10 | `503` body HTML hoặc `401` không body | Giữ status/headers, fallback an toàn |
| C11 | `429 Retry-After` dạng giây hoặc HTTP-date | Parse, chặn retry quá hạn mức |
| C12 | Response có `Location` sang host lạ | Không gửi token sang host khác |
| C13 | HTTP 503 nhưng `problem.status=400` | Quyết định theo **503**, báo contract inconsistency |
| C14 | Request mất kết nối sau POST | Không coi là “chưa commit”, đối soát/idempotency |

### 9.2. MockRestServiceServer: chứng minh 304 không có DTO

Với Spring Framework 6.1+ có `MockRestServiceServer` tích hợp `RestClient.Builder`. Một unit/integration-style client test:

~~~java
@Test
void notModifiedKeepsEtagWithoutParsingJson() throws Exception {
    RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://api.example.test");
    MockRestServiceServer server =
        MockRestServiceServer.bindTo(builder).build();
    RestClient restClient = builder.build();

    server.expect(requestTo(
            "https://api.example.test/v1/orders/o-42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withStatus(HttpStatus.NOT_MODIFIED)
            .header("ETag", "\"order-v7\""));

    record Snapshot(int status, String etag, int bodySize) {}
    Snapshot observed = restClient.get()
        .uri("/v1/orders/{id}", "o-42")
        .exchange((request, response) -> new Snapshot(
            response.getStatusCode().value(),
            response.getHeaders().getETag(),
            response.getBody().readAllBytes().length));

    assertEquals(304, observed.status());
    assertEquals("\"order-v7\"", observed.etag());
    assertEquals(0, observed.bodySize());
    server.verify();
}
~~~

Ví dụ lược import; test riêng cache key, `Vary` và tenant để chặn rò dữ liệu.

### 9.3. Test Problem Details và 204

Với cùng mock server, mô phỏng:

~~~java
server.expect(requestTo("https://api.example.test/v1/orders/o-42"))
    .andRespond(withStatus(HttpStatus.CONFLICT)
        .contentType(MediaType.parseMediaType("application/problem+json"))
        .body("""
            {"type":"https://api.example.test/problems/order-closed",
             "title":"Conflict","status":409,
             "code":"ORDER_ALREADY_CLOSED"}
            """));
~~~

Adapter dùng `exchange` phải trả `status=409`, `problem.type` và `code`, **không ném Jackson parse exception vì cố đọc OrderView**. Test riêng `204` với body 0 byte và `ETag` sau DELETE, khẳng định không parse JSON; `200` body 0 byte phải tạo lỗi contract nếu endpoint bắt buộc trả DTO. Với `WebClient` có thể dùng mock HTTP server (ví dụ WireMock/MockWebServer) hoặc test `ExchangeFunction` ở mức phù hợp, đồng thời xác nhận không buffer vô hạn.

## 10. Bài tập thực hành và lời giải

**Bài tập:** Client Java gọi một API tạo báo cáo. Hãy xác định hành động tiếp theo khi nhận:

1. `POST /v1/reports` trả **202**, `Location: /v1/jobs/j-9`, `Retry-After: 5`, body `{"status":"QUEUED"}`.
2. `GET /v1/jobs/j-9` trả **200**, JSON `{"status":"SUCCEEDED","result":"/v1/reports/r-7"}`.
3. `DELETE /v1/reports/r-7` trả **204**, `ETag: "report-v8"`, không body.
4. `PATCH /v1/reports/r-7` trả **409**, `application/problem+json` có `type=.../report-locked`.
5. `GET` với `If-None-Match` trả **304** nhưng client đã xóa cache local.

**Lời giải:** (1) lưu trạng thái accepted, xác minh `Location` thuộc origin được phép, poll theo deadline/backoff (không coi 202 là đã hoàn thành); (2) sau khi job SUCCEEDED, lấy result URI theo policy và quyền; (3) xem là xóa thành công, giữ metadata cần thiết, không parse JSON; (4) giữ status/type/code, hiển thị lỗi nghiệp vụ hoặc hướng xử lý, không retry vô hạn; (5) không tự tạo dữ liệu từ 304, thực hiện GET không điều kiện hoặc báo cache miss để khôi phục representation.

**Câu hỏi nâng cao:** Nếu POST bị timeout ngay sau khi server lưu report nhưng trước response 202, bạn có gửi lại với idempotency key mới không? **Không.** Giữ cùng key nếu server hỗ trợ, hoặc truy vấn trạng thái bằng business reference/operation ID để tránh tạo báo cáo trùng.

## 11. Checklist trước khi phát hành Java client

- [ ] Mỗi operation có bảng status được hỗ trợ; phân biệt **200/201/202/204/304**.
- [ ] Không deserialize body của HEAD, 1xx, 204, 205, 304; phân biệt **0 byte / `null` / `{}`**.
- [ ] Đọc đúng `Content-Type` trước khi chọn DTO/Problem Details; có fallback khi body lỗi rỗng/HTML.
- [ ] Giữ **HTTP status thực** kể cả khi `problem.status` lệch; phân nhánh theo `type`/`code` đã công bố.
- [ ] Parse `Location`, `ETag`, `Retry-After`, `WWW-Authenticate` có kiểm tra, không truyền bearer qua origin lạ.
- [ ] Không dùng 304 nếu cache thiếu/sai user/tenant/variant; tuân thủ `Vary` và cache policy.
- [ ] Phân biệt **HTTP error**, **transport failure** và **protocol/serialization failure**.
- [ ] Retry có deadline, budget và idempotency; POST timeout không tự khẳng định rollback.
- [ ] Có timeout/giới hạn body, TLS validation, log không lộ token/PII và test 401/403/429/503.
- [ ] Contract test có các ca empty body, Problem Details, response sai schema và header bất thường.

**Nguồn tham khảo:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [Java HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html), [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html) và [Spring WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).

**Kết luận:** Java REST client đúng hợp đồng cần **đọc status trước**, giữ những header có ý nghĩa và chỉ deserialize **body khi thật sự có và đúng media type**. `204` là thành công không body, `304` là tình huống cache, còn Problem Details cung cấp mã lỗi có cấu trúc **nhưng không thay HTTP status**. Kết hợp các nguyên tắc này với bảo mật, giới hạn tài nguyên và kiểm thử response giả lập giúp client hoạt động đáng tin cậy trước cả lỗi nghiệp vụ lẫn sự cố mạng.
