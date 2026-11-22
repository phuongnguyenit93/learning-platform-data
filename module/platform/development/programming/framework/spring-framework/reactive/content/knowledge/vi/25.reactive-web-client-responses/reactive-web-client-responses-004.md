# `WebClientResponseException` và nội dung phản hồi lỗi trong Spring WebFlux

## 1. Mục tiêu: đọc được cả status lẫn nội dung lỗi từ dịch vụ bên ngoài

Khi dùng `WebClient`, không phải mọi HTTP response đều là kết quả thành công. Một dịch vụ có thể trả `404 Not Found`, `409 Conflict`, `429 Too Many Requests` hoặc `500 Internal Server Error` kèm một body mô tả nguyên nhân. Ứng dụng gọi cần quyết định cách phân loại lỗi, lấy thông tin hữu ích từ response và chuyển nó thành hành vi phù hợp trong use case của mình.

Spring WebFlux cung cấp `WebClientResponseException` để giữ thông tin của một HTTP error response đã nhận được. Exception này có thể mang:

- HTTP status code và status text.
- Response headers, ví dụ `Content-Type`, `Retry-After`, `X-Request-Id`.
- Response body dưới dạng byte array.
- Nội dung body dưới dạng String theo charset của response.
- Request gốc đã tạo ra response lỗi.

Với `retrieve()`, các response 4xx và 5xx mặc định phát `WebClientResponseException`, có các subclass tương ứng với một số status phổ biến. Có thể thay đổi chính sách bằng `onStatus(...)`. Nếu cần toàn quyền quyết định cách đọc body theo từng status, dùng `exchangeToMono(...)` hoặc `exchangeToFlux(...)`.

Bài học sẽ giúp bạn:

1. Hiểu khi nào `WebClientResponseException` được tạo và khi nào không.
2. Đọc status, headers, request và error body.
3. Decode body lỗi JSON thành DTO như `ProblemDetail` hoặc một record riêng.
4. Phân biệt `retrieve()`, `onStatus(...)` và `exchangeToMono(...)`.
5. Biến lỗi HTTP của dịch vụ ngoài thành exception/domain result của ứng dụng.
6. Xử lý body rỗng, body không phải JSON, JSON sai định dạng và error body quá lớn.
7. Tránh làm rò rỉ response body, connection, credential và dữ liệu nhạy cảm.
8. Kiểm thử hành vi bằng `MockWebServer`, `StepVerifier` và JUnit.

## 2. Vị trí của `WebClientResponseException` trong request lifecycle

Một outbound request có thể kết thúc theo nhiều cách:

```text
WebClient request
       |
       v
HTTP connector gửi request
       |
       +---- Không nhận được HTTP response
       |          |
       |          v
       |    WebClientRequestException
       |    (DNS, connect, TLS, I/O...)
       |
       v
Nhận được HTTP response
       |
       +---- Status 2xx
       |       |
       |       v
       |    Decode response body
       |       |
       |       +---- thành công -> Mono<T> / Flux<T>
       |       |
       |       +---- lỗi decode -> DecodingException
       |
       +---- Status 4xx / 5xx với retrieve()
               |
               v
        WebClientResponseException
        (status + headers + body + request)
```

Điểm quan trọng: `WebClientResponseException` biểu diễn **một HTTP response lỗi đã nhận được**. Nó không phải exception chung cho mọi vấn đề khi gọi HTTP.

| Tình huống | Exception thường gặp | Có HTTP status response không? |
|---|---|---|
| Server trả 404 và dùng `retrieve()` mặc định | `WebClientResponseException.NotFound` | Có |
| Server trả 429 | `WebClientResponseException.TooManyRequests` | Có |
| Server trả 500 | `WebClientResponseException.InternalServerError` | Có |
| DNS lookup thất bại | `WebClientRequestException` hoặc lỗi connector tương ứng | Không |
| Không kết nối được tới host | `WebClientRequestException` hoặc lỗi connector tương ứng | Không |
| TLS handshake thất bại | Lỗi transport/security | Thường không |
| Response 200 nhưng JSON không decode được | `DecodingException` hoặc lỗi decode tương ứng | Có response 200 |
| Reactive pipeline bị timeout | `TimeoutException` hoặc lỗi timeout của operator/connector | Không nhất thiết |

Vì vậy, khi viết retry hoặc error mapping, đừng gom tất cả vào một `catch` rồi suy ra rằng server đã trả 4xx/5xx. Cần biết lỗi xảy ra ở tầng transport, HTTP status hay body decoding.

## 3. Hành vi mặc định của `retrieve()`

`retrieve()` là cách đơn giản để khai báo cách đọc response:

```java
Mono<Item> item = webClient.get()
        .uri("/items/{id}", "42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Item.class);
```

Nếu response có status thành công, WebClient decode body thành `Item`.

Nếu response có status 4xx hoặc 5xx, `retrieve()` mặc định tạo `WebClientResponseException`. Những status được Spring nhận diện có thể dùng subclass cụ thể như:

- `WebClientResponseException.BadRequest` — 400.
- `WebClientResponseException.Unauthorized` — 401.
- `WebClientResponseException.Forbidden` — 403.
- `WebClientResponseException.NotFound` — 404.
- `WebClientResponseException.MethodNotAllowed` — 405.
- `WebClientResponseException.NotAcceptable` — 406.
- `WebClientResponseException.Conflict` — 409.
- `WebClientResponseException.Gone` — 410.
- `WebClientResponseException.UnsupportedMediaType` — 415.
- `WebClientResponseException.UnprocessableEntity` — 422.
- `WebClientResponseException.TooManyRequests` — 429.
- `WebClientResponseException.InternalServerError` — 500.
- `WebClientResponseException.NotImplemented` — 501.
- `WebClientResponseException.BadGateway` — 502.
- `WebClientResponseException.ServiceUnavailable` — 503.
- `WebClientResponseException.GatewayTimeout` — 504.

Nếu status code không có subclass chuyên biệt, Spring có thể dùng `WebClientResponseException` hoặc `UnknownHttpStatusCodeException` tùy status và cách biểu diễn.

### Bắt subclass hay bắt lớp cha?

Có thể bắt riêng 404:

```java
return catalogClient.find(id)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.empty());
```

Hoặc phân loại qua status:

```java
return catalogClient.find(id)
        .onErrorResume(WebClientResponseException.class, error -> {
            if (error.getStatusCode().is4xxClientError()) {
                return Mono.error(new InvalidRemoteRequestException(error));
            }

            if (error.getStatusCode().is5xxServerError()) {
                return Mono.error(new RemoteServiceUnavailableException(error));
            }

            return Mono.error(error);
        });
```

Bắt subclass rõ nghĩa khi chỉ một status có hành vi riêng. Dùng lớp cha và `getStatusCode()` khi cần một chính sách chung cho nhiều status.

Không dùng `getRawStatusCode()` trong code mới. API này đã deprecated từ Spring Framework 6.0; dùng `getStatusCode()` trả về `HttpStatusCode`.

## 4. Những thông tin có thể đọc từ exception

`WebClientResponseException` chứa dữ liệu của response đã được WebClient thu nhận.

| API | Trả về | Dùng để |
|---|---|---|
| `getStatusCode()` | `HttpStatusCode` | Kiểm tra status và phân loại 4xx/5xx |
| `getStatusText()` | `String` | Đọc reason phrase/status text nếu có |
| `getHeaders()` | `HttpHeaders` | Đọc `Content-Type`, `Retry-After`, trace ID... |
| `getResponseBodyAsByteArray()` | `byte[]` | Lấy body thô |
| `getResponseBodyAsString()` | `String` | Đọc body theo charset của response |
| `getResponseBodyAsString(Charset)` | `String` | Chọn charset dự phòng khi response không khai báo charset |
| `getResponseBodyAs(Class<T>)` | `T` | Decode body lỗi thành DTO |
| `getResponseBodyAs(ParameterizedTypeReference<T>)` | `T` | Decode kiểu generic như `List<Violation>` |
| `getRequest()` | `HttpRequest` | Xem method/URI của request gốc |
| `getMessage()` | `String` | Thông điệp exception tổng quát |

Ví dụ:

```java
.onErrorResume(WebClientResponseException.class, error -> {
    int status = error.getStatusCode().value();
    String contentType = String.valueOf(
            error.getHeaders().getContentType());
    String requestUri = error.getRequest() == null
            ? "unknown"
            : error.getRequest().getURI().toString();

    log.warn(
            "Remote HTTP failure: status={}, contentType={}, uri={}",
            status, contentType, requestUri);

    return Mono.error(error);
});
```

Ví dụ chỉ log metadata. Không log toàn bộ headers hoặc URI nếu URL có thể chứa token/query secret. Tránh log raw body vì response lỗi có thể chứa email, thông tin tài khoản, access token hoặc dữ liệu cá nhân.

### Status và headers có thể hữu ích hơn message

Một số API trả `Retry-After` khi rate limit hoặc bảo trì:

```java
String retryAfter = error.getHeaders().getFirst("Retry-After");
```

Một số API trả correlation ID:

```java
String remoteTraceId =
        error.getHeaders().getFirst("X-Request-Id");
```

Hãy giữ các metadata cần thiết trong log có kiểm soát để hỗ trợ tra cứu giữa các dịch vụ. Không giả định mọi server đều có các header này.

## 5. Đọc nội dung body lỗi dưới dạng String hoặc byte array

### 5.1. Đọc String

Cách nhanh nhất để xem nội dung lỗi:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(Item.class)
        .onErrorResume(WebClientResponseException.class, error -> {
            String responseBody = error.getResponseBodyAsString();

            log.warn(
                    "Remote status={}, bodyLength={}",
                    error.getStatusCode().value(),
                    responseBody.length());

            return Mono.error(error);
        });
```

`getResponseBodyAsString()` dùng charset được khai báo trong media type nếu có; nếu không có thì fallback UTF-8. Có overload nhận charset dự phòng:

```java
String body = error.getResponseBodyAsString(
        StandardCharsets.ISO_8859_1);
```

Chỉ chọn charset dự phòng khác UTF-8 khi API đích có contract rõ ràng. Không nên tự đoán charset dựa trên nội dung hiển thị bị lỗi.

### 5.2. Đọc byte array

Nếu cần xử lý nội dung nhị phân hoặc tự quyết định cách decode:

```java
byte[] rawBody = error.getResponseBodyAsByteArray();
```

Có thể dùng khi body là dữ liệu không phải text, hoặc cần lưu mẫu response đã được lọc để điều tra. Hãy đặt giới hạn kích thước, chính sách retention và masking trước khi lưu.

### 5.3. Body rỗng

Không phải error response nào cũng có body. Một response 404, 429 hoặc 503 có thể chỉ có status và headers.

```java
String body = error.getResponseBodyAsString();

if (body.isBlank()) {
    log.warn("Remote API returned HTTP {} without an error body",
            error.getStatusCode().value());
}
```

Không gọi `getResponseBodyAsString()` rồi giả định luôn có JSON. Hãy xử lý body rỗng và body không theo schema như các trường hợp bình thường.

## 6. Decode error body JSON thành DTO

Nhiều REST API trả error body theo RFC 9457 Problem Details hoặc schema riêng.

Ví dụ JSON:

```json
{
  "type": "https://api.example.com/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 42 does not exist",
  "code": "ITEM_NOT_FOUND",
  "traceId": "remote-trace-123"
}
```

Có thể khai báo record:

```java
public record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String code,
        String traceId) {
}
```

Với `WebClientResponseException` do WebClient tạo qua `retrieve()` hoặc `ClientResponse.createException()`, có thể dùng:

```java
.onErrorResume(WebClientResponseException.class, error -> {
    ApiProblem problem =
            error.getResponseBodyAs(ApiProblem.class);

    if (problem != null) {
        log.warn(
                "Remote problem code={}, status={}",
                problem.code(),
                error.getStatusCode().value());
    }

    return Mono.error(error);
});
```

`getResponseBodyAs(Class<T>)` được hỗ trợ từ Spring Framework 6.0. WebClient thiết lập decoder function cho exception được tạo từ response để có thể decode body theo các codec đã cấu hình.

Nếu không có decoder phù hợp, API có thể ném `IllegalStateException`. Nếu body không đúng định dạng hoặc không tương thích với DTO, việc decode có thể ném `DecodingException`. Vì vậy, chỉ decode theo DTO khi đã biết response media type và schema của dịch vụ.

### 6.1. Decode collection hoặc kiểu generic

Với body dạng:

```json
{
  "errors": [
    {"field": "name", "code": "required"},
    {"field": "email", "code": "invalid"}
  ]
}
```

Có thể dùng record:

```java
public record FieldViolation(String field, String code) {
}

public record ValidationProblem(
        String title,
        int status,
        List<FieldViolation> errors) {
}
```

Nếu body là một collection trực tiếp như `List<FieldViolation>`, dùng `ParameterizedTypeReference`:

```java
List<FieldViolation> violations =
        error.getResponseBodyAs(
                new ParameterizedTypeReference<List<FieldViolation>>() {
                });
```

Cần import:

```java
import org.springframework.core.ParameterizedTypeReference;
```

### 6.2. Body không đúng JSON hoặc JSON không khớp DTO

Không nên để lỗi decode body thứ hai che mất status HTTP ban đầu. Có thể đọc String trước, rồi thử parse trong một bước có fallback:

```java
String raw = error.getResponseBodyAsString();

ApiProblem problem = null;

try {
    problem = objectMapper.readValue(raw, ApiProblem.class);
}
catch (JsonProcessingException ignored) {
    // Giữ lại raw body đã được giới hạn/masking nếu cần.
}
```

`ObjectMapper` ở đây là Jackson mapper đã được cấu hình trong ứng dụng. Trong production, không lưu raw body vô hạn và không trả nguyên body từ dịch vụ bên ngoài cho client của mình.

### 6.3. Phân biệt body lỗi từ xa và lỗi của ứng dụng hiện tại

Nếu ứng dụng A gọi B, rồi A trả lỗi cho client của A, không nên mặc định chuyển nguyên status/body của B ra ngoài. B có thể tiết lộ tên service, stack trace hoặc cấu trúc nội bộ.

Thường nên:

1. Đọc status/body của B để phân loại lỗi.
2. Chuyển thành exception hoặc error result của application A.
3. Ghi log an toàn với correlation ID.
4. Ánh xạ thành error contract công khai của A.

## 7. `onStatus(...)`: tùy chỉnh cách xử lý error response

`retrieve().onStatus(...)` cho phép khai báo predicate status và một hàm chuyển `ClientResponse` thành `Mono` phát ra exception.

Chữ ký về mặt ý tưởng:

```java
onStatus(
        Predicate<HttpStatusCode> statusPredicate,
        Function<ClientResponse, Mono<? extends Throwable>> exceptionFunction)
```

Ví dụ map 404 thành exception của ứng dụng:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException()
                        .map(ItemNotFoundException::new))
        .bodyToMono(Item.class);
```

`response.createException()` tạo `WebClientResponseException` có status, headers, body và request gốc. Ví dụ chuyển nó thành `ItemNotFoundException` để tầng application không phải phụ thuộc vào loại exception HTTP của Spring.

### 7.1. Map JSON error body thành exception riêng

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 409,
                response -> response.bodyToMono(ApiProblem.class)
                        .defaultIfEmpty(new ApiProblem(
                                null,
                                "Conflict",
                                409,
                                "The remote resource conflicts with current state",
                                "REMOTE_CONFLICT",
                                null))
                        .map(problem -> new ItemConflictException(
                                problem.code(),
                                problem.detail())))
        .bodyToMono(Item.class);
```

Ở đây callback tự consume body bằng `bodyToMono(ApiProblem.class)` rồi phát exception ứng dụng. Vì body đã được đọc trong callback, không thể tiếp tục decode cùng response body lần nữa.

Lưu ý: nếu JSON body sai cú pháp hoặc media type không hỗ trợ, lỗi decoding có thể thay thế exception nghiệp vụ dự định. Nếu dịch vụ ngoài không bảo đảm error schema, hãy tạo exception từ `response.createException()` để giữ raw response rồi decode có fallback ở nơi khác.

### 7.2. Trả `Mono.empty()` từ `onStatus(...)`

Nếu callback của `onStatus` trả `Mono.empty()`, Spring hiểu rằng status đó **không được coi là lỗi** và tiếp tục xử lý response theo pipeline bình thường:

```java
return webClient.get()
        .uri("/optional-items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.empty())
        .bodyToMono(Item.class);
```

Điều này không tự biến 404 thành `Mono.empty()` nếu response có body. Response body vẫn được chuyển cho `bodyToMono(Item.class)` và có thể không decode được nếu body là JSON Problem Details. Nếu muốn 404 chắc chắn thành empty result và không đọc body thành Item, `exchangeToMono(...)` thường rõ ràng hơn.

### 7.3. Thứ tự và phạm vi predicate

Có thể khai báo riêng 4xx và 5xx:

```java
.retrieve()
.onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.createException())
.onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException())
.bodyToMono(Item.class);
```

Đây chỉ là ví dụ minh họa. Nếu callback của bạn trả cùng `WebClientResponseException` mặc định thì không cần khai báo lại hai handler này. Chỉ dùng `onStatus` khi thực sự thay đổi mapping, bổ sung domain context hoặc tạo response policy khác.

Không tạo các predicate chồng lấn mà không hiểu handler nào được áp dụng trước. Khi có status đặc biệt như 404 hoặc 429, đặt logic cụ thể rõ ràng và kiểm thử riêng.

## 8. `exchangeToMono(...)`: tự quyết định cách đọc response

`exchangeToMono(...)` cung cấp quyền truy cập trực tiếp vào `ClientResponse`. Nó phù hợp khi status quyết định kiểu body, fallback hoặc cách xử lý.

Ví dụ:

```java
Mono<Item> item = webClient.get()
        .uri("/items/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Item.class);
            }

            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                        .then(Mono.<Item>empty());
            }

            return response.createError();
        });
```

Ý nghĩa:

- 2xx: decode thành `Item`.
- 404: release body rồi trả `Mono.empty()`.
- Status khác: `createError()` phát `WebClientResponseException` chứa status, headers, body và request.

### 8.1. Response body phải được consume hoặc release

Sau khi publisher do callback của `exchangeToMono`/`exchangeToFlux` trả về hoàn tất, WebClient kiểm tra response body. Nếu body chưa được consume, framework sẽ release để tránh memory/connection leak.

Điều đó có nghĩa callback phải quyết định cách dùng body ngay bên trong nó. Không trả `ClientResponse` ra ngoài rồi hy vọng đọc body sau khi callback kết thúc.

Các lựa chọn phổ biến:

- `response.bodyToMono(Type.class)` để decode body.
- `response.bodyToFlux(Type.class)` để stream nhiều object.
- `response.createException()` hoặc `response.createError()` để tạo lỗi HTTP.
- `response.releaseBody()` để bỏ body khi không cần.
- `response.toEntity(...)` hoặc `toBodilessEntity()` khi cần status/headers/body theo abstraction tương ứng.

### 8.2. Không dùng `exchange()` cũ

API `exchange()` trước đây đã deprecated từ Spring Framework 5.3 vì nguy cơ rò rỉ bộ nhớ/connection nếu caller không consume hoặc release body đúng cách. Dùng `exchangeToMono()` hoặc `exchangeToFlux()`.

### 8.3. Khi nào chọn `retrieve()` và khi nào chọn `exchangeToMono()`?

| Nhu cầu | API phù hợp |
|---|---|
| Đọc body thành DTO, lỗi 4xx/5xx dùng exception mặc định | `retrieve()` |
| Map một vài status thành exception ứng dụng | `retrieve().onStatus(...)` |
| Muốn đọc status rồi chọn kiểu body khác nhau | `exchangeToMono(...)` |
| 404 cần trả empty, 2xx trả DTO, status khác phát exception | `exchangeToMono(...)` |
| Cần xử lý stream response theo status | `exchangeToFlux(...)` |
| Chỉ cần status + headers và không cần body | `retrieve().toBodilessEntity()` hoặc API tương ứng |

## 9. `WebClientResponseException` và các loại lỗi khác

Khi xây dựng một HTTP client cho application service, hãy phân loại ít nhất các nhóm sau:

| Nhóm lỗi | Ví dụ | Xử lý thường gặp |
|---|---|---|
| 4xx từ dịch vụ ngoài | 400, 401, 403, 404, 409, 429 | Kiểm tra input, credential, quyền, resource hoặc rate limit |
| 5xx từ dịch vụ ngoài | 500, 502, 503, 504 | Đánh giá retry, circuit breaker, fallback và alert |
| Lỗi transport | DNS, connect, TLS, connection reset | Kiểm tra network, timeout, DNS và upstream availability |
| Timeout/cancel | Request vượt deadline hoặc bị hủy | Điều chỉnh timeout, propagate cancellation, tránh retry vô hạn |
| Decode response | HTTP 200 nhưng JSON sai schema | Kiểm tra contract/version/codec; không coi là HTTP error |
| Error body decode | HTTP 404 nhưng body không đúng error DTO | Giữ status và raw body an toàn; parse có fallback |

### 9.1. Không phải mọi 4xx đều là lỗi có thể retry

Ví dụ:

- 400: sửa request trước khi gửi lại.
- 401: làm mới credential theo auth flow; retry một lần có kiểm soát nếu phù hợp.
- 403: kiểm tra quyền; retry thường không giải quyết được.
- 404: tùy use case, có thể trả empty hoặc domain not-found.
- 409: cần xử lý conflict hoặc đọc lại trạng thái.
- 429: có thể retry theo `Retry-After` và policy.
- 422: sửa dữ liệu/logic nghiệp vụ.

### 9.2. Không phải mọi 5xx đều an toàn để retry

GET thường idempotent theo semantics HTTP. POST có thể đã thực hiện side effect dù client chỉ nhìn thấy timeout hoặc 502. Nếu retry POST, cần idempotency key hoặc cơ chế deduplication mà API đích hỗ trợ.

Dùng retry có giới hạn, backoff và jitter; đặt timeout tổng cho cả chuỗi retry. Tránh retry ngay lập tức và vô hạn khi upstream đang quá tải.

## 10. Đọc error body mà không làm lộ dữ liệu

Error response là dữ liệu do dịch vụ khác gửi về, không nên mặc định tin cậy.

Các nguyên tắc:

- Chỉ log field cần chẩn đoán như status, error code, request ID và route.
- Không log `Authorization`, cookie, API key, access token hoặc raw request/response body tùy tiện.
- Nếu cần lưu error body, mask dữ liệu cá nhân và đặt giới hạn kích thước/retention.
- Không trả raw body của upstream cho client bên ngoài nếu chưa kiểm soát nội dung.
- Không đưa hostname nội bộ, stack trace, SQL, đường dẫn filesystem hoặc thông tin cấu hình vào response công khai.
- Kiểm tra `Content-Type` trước khi decode JSON thành DTO.
- Xử lý body rỗng, JSON lỗi, media type lạ và charset không có.
- Đặt giới hạn codec phù hợp; body lỗi lớn có thể vượt `maxInMemorySize` khi WebClient gom nội dung để tạo exception.

`WebClientResponseException` giữ body dưới dạng byte array, nên việc đọc error body mặc định có thể cần buffering. Nó không phải cơ chế streaming cho một error payload lớn. Error contract nên ngắn gọn, có cấu trúc và giới hạn kích thước.

### Một mẫu log có kiểm soát

```java
private void logRemoteFailure(WebClientResponseException error) {
    String requestId =
            error.getHeaders().getFirst("X-Request-Id");

    log.warn(
            "Remote request failed: status={}, requestId={}, method={}",
            error.getStatusCode().value(),
            requestId,
            error.getRequest() == null
                    ? "unknown"
                    : error.getRequest().getMethod());
}
```

Không thêm `error.getResponseBodyAsString()` vào log mặc định. Nếu cần chẩn đoán body, hãy chỉ log error code đã parse và đã được kiểm soát.

## 11. Thiết kế exception của application khi gọi dịch vụ ngoài

Không phải tầng application nào cũng nên phụ thuộc trực tiếp vào `WebClientResponseException`. Có thể giữ exception Spring ở adapter HTTP client rồi chuyển thành exception mang ý nghĩa nghiệp vụ.

Ví dụ:

```java
public final class RemoteCatalogException extends RuntimeException {

    private final HttpStatusCode statusCode;
    private final HttpHeaders responseHeaders;
    private final String responseBody;

    public RemoteCatalogException(WebClientResponseException cause) {
        super("Catalog service returned HTTP "
                + cause.getStatusCode().value(), cause);

        this.statusCode = cause.getStatusCode();
        this.responseHeaders =
                HttpHeaders.readOnlyHttpHeaders(cause.getHeaders());
        this.responseBody = cause.getResponseBodyAsString();
    }

    public HttpStatusCode getStatusCode() {
        return statusCode;
    }

    public HttpHeaders getResponseHeaders() {
        return responseHeaders;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
```

Sau đó map trong client adapter:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                HttpStatusCode::is4xxClientError,
                response -> response.createException()
                        .map(RemoteCatalogException::new))
        .bodyToMono(Item.class);
```

Lợi ích:

- Application layer có một kiểu exception ổn định của ứng dụng.
- Cause gốc vẫn được giữ để điều tra.
- Status và headers vẫn có thể được dùng khi cần.
- Adapter có thể thay WebClient bằng HTTP client khác mà không phải thay toàn bộ use case.

Không nhất thiết phải lưu raw response body trong exception domain. Nếu body có thể chứa dữ liệu nhạy cảm, chỉ giữ error code/trace ID đã được chọn lọc.

## 12. Xử lý các trường hợp cụ thể

### 12.1. 404: không tìm thấy resource

Nếu không tìm thấy được xem là kết quả bình thường trong use case:

```java
public Mono<Item> findOptional(String id) {
    return webClient.get()
            .uri("/items/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Item.class);
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                            .then(Mono.<Item>empty());
                }

                return response.createError();
            });
}
```

Nếu 404 là lỗi nghiệp vụ cần báo ra ngoài, giữ `WebClientResponseException.NotFound` hoặc map thành `ItemNotFoundException`.

### 12.2. 429: rate limit và `Retry-After`

```java
return webClient.get()
        .uri("/reports")
        .retrieve()
        .bodyToFlux(Report.class)
        .onErrorResume(
                WebClientResponseException.TooManyRequests.class,
                error -> {
                    String retryAfter =
                            error.getHeaders().getFirst("Retry-After");

                    log.warn("Rate limited; retryAfter={}", retryAfter);
                    return Flux.error(error);
                });
```

`Retry-After` có thể là số giây hoặc HTTP date theo HTTP semantics. Nếu triển khai retry, cần parse đúng định dạng, có giới hạn thời gian chờ và tổng số lần thử. Không block thread để chờ; dùng `Mono.delay(...)` hoặc retry operator có backoff.

### 12.3. 401: token hết hạn

Một response 401 có thể cho biết access token không còn hợp lệ. Nếu ứng dụng dùng Spring Security OAuth2 Client, để authorized client manager/filter quản lý việc lấy hoặc refresh token. Không viết vòng lặp gọi lại vô hạn mỗi khi nhận 401.

Nếu tự xử lý:
- Chỉ refresh theo một flow xác thực được hỗ trợ.
- Đảm bảo request chỉ retry một lần sau refresh.
- Không log token cũ/mới.
- Không retry request có side effect nếu chưa có idempotency guarantee.

### 12.4. 5xx: giữ nguyên status và cause

```java
return webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .onErrorMap(
                WebClientResponseException.class,
                error -> error.getStatusCode().is5xxServerError()
                        ? new InventoryServiceException(error)
                        : error);
```

Chỉ map 5xx sang exception của application. 4xx tiếp tục giữ nguyên để caller có thể xử lý input/authorization/not-found riêng.

## 13. Dự án Java 17+ chạy được: đọc error body và map lỗi WebClient

Dự án mẫu dùng Java 17, Spring Boot 3.3.5, Spring WebFlux, JUnit 5, Reactor Test và OkHttp MockWebServer. MockWebServer tạo HTTP server cục bộ trong test, cho phép chủ động trả 200, 404, 429 hoặc 500 mà không cần gọi Internet.

Ví dụ minh họa ba hành vi:

1. `find(...)` dùng `retrieve()` mặc định và nhận `WebClientResponseException`.
2. `findWithMapped4xx(...)` dùng `onStatus(...)` để chuyển 4xx thành exception ứng dụng, giữ cause/status/headers/body.
3. `findOrEmpty(...)` dùng `exchangeToMono(...)` để biến 404 thành `Mono.empty()` và tạo exception cho status còn lại.

### 13.1. Cấu trúc dự án

```text
webclient-error-response/
├── pom.xml
└── src/
    ├── main/java/edu/demo/catalog/
    │   ├── CatalogItem.java
    │   ├── ApiProblem.java
    │   ├── RemoteApiException.java
    │   └── CatalogClient.java
    └── test/java/edu/demo/catalog/
        └── CatalogClientTests.java
```

### 13.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-error-response</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <mockwebserver.version>4.12.0</mockwebserver.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>${mockwebserver.version}</version>
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

### 13.3. `CatalogItem.java`

```java
package edu.demo.catalog;

public record CatalogItem(String id, String name) {
}
```

### 13.4. `ApiProblem.java`

```java
package edu.demo.catalog;

public record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String code,
        String traceId) {
}
```

Record này biểu diễn một phần error contract của API mẫu. Trong hệ thống thực, hãy khớp DTO với schema của dịch vụ được gọi.

### 13.5. `RemoteApiException.java`

```java
package edu.demo.catalog;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClientResponseException;

public final class RemoteApiException extends RuntimeException {

    private final HttpStatusCode statusCode;
    private final HttpHeaders responseHeaders;
    private final String responseBody;

    public RemoteApiException(WebClientResponseException cause) {
        super(
                "Remote catalog returned HTTP "
                        + cause.getStatusCode().value(),
                cause);

        this.statusCode = cause.getStatusCode();
        this.responseHeaders =
                HttpHeaders.readOnlyHttpHeaders(cause.getHeaders());
        this.responseBody = cause.getResponseBodyAsString();
    }

    public HttpStatusCode getStatusCode() {
        return statusCode;
    }

    public HttpHeaders getResponseHeaders() {
        return responseHeaders;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
```

Exception ứng dụng giữ status, headers và raw body để adapter/caller phân loại tiếp. Trong production, có thể chỉ giữ error code và trace ID đã lọc thay vì giữ toàn bộ body.

### 13.6. `CatalogClient.java`

```java
package edu.demo.catalog;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CatalogItem> find(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }

    public Mono<CatalogItem> findWithMapped4xx(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        HttpStatusCode::is4xxClientError,
                        response -> response.createException()
                                .map(RemoteApiException::new))
                .bodyToMono(CatalogItem.class);
    }

    public Mono<CatalogItem> findOrEmpty(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(CatalogItem.class);
                    }

                    if (response.statusCode().value() == 404) {
                        return response.releaseBody()
                                .then(Mono.<CatalogItem>empty());
                    }

                    return response.createError();
                });
    }
}
```

Ba method thể hiện ba chính sách khác nhau:

- `find`: để `retrieve()` tạo `WebClientResponseException` mặc định.
- `findWithMapped4xx`: chuyển mọi 4xx thành `RemoteApiException`, còn 5xx tiếp tục theo mặc định của `retrieve()`.
- `findOrEmpty`: 404 là kết quả không có item; các status khác tạo error từ `ClientResponse`.

### 13.7. `CatalogClientTests.java`

```java
package edu.demo.catalog;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogClientTests {

    private MockWebServer server;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

        catalogClient = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void successfulResponseIsDecodedToItem() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"42","name":"Keyboard"}
                        """));

        StepVerifier.create(catalogClient.find("42"))
                .expectNext(new CatalogItem("42", "Keyboard"))
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/items/42", request.getPath());
        assertEquals(
                MediaType.APPLICATION_JSON_VALUE,
                request.getHeader("Accept"));
    }

    @Test
    void defaultRetrieveCreatesNotFoundExceptionWithReadableBody()
            throws Exception {

        String body = """
                {
                  "type": "https://api.example.test/problems/not-found",
                  "title": "Item not found",
                  "status": 404,
                  "detail": "Item 42 does not exist",
                  "code": "ITEM_NOT_FOUND",
                  "traceId": "remote-trace-123"
                }
                """;

        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", "application/problem+json")
                .addHeader("X-Request-Id", "request-404")
                .setBody(body));

        StepVerifier.create(catalogClient.find("42"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException exception =
                            assertInstanceOf(
                                    WebClientResponseException.class,
                                    error);

                    assertInstanceOf(
                            WebClientResponseException.NotFound.class,
                            error);

                    assertEquals(
                            404,
                            exception.getStatusCode().value());

                    assertEquals(
                            "request-404",
                            exception.getHeaders()
                                    .getFirst("X-Request-Id"));

                    assertEquals(
                            "GET",
                            exception.getRequest().getMethod().name());

                    assertTrue(
                            exception.getResponseBodyAsString()
                                    .contains("ITEM_NOT_FOUND"));

                    ApiProblem problem =
                            exception.getResponseBodyAs(ApiProblem.class);

                    assertEquals("ITEM_NOT_FOUND", problem.code());
                    assertEquals(404, problem.status());
                    assertEquals("remote-trace-123", problem.traceId());
                })
                .verify();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("/items/42", request.getPath());
    }

    @Test
    void customOnStatusMaps4xxAndPreservesOriginalResponse()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(429)
                .addHeader("Content-Type", "application/problem+json")
                .addHeader("Retry-After", "30")
                .setBody("""
                        {
                          "title": "Rate limited",
                          "status": 429,
                          "detail": "Try again later",
                          "code": "RATE_LIMITED"
                        }
                        """));

        StepVerifier.create(
                        catalogClient.findWithMapped4xx("42"))
                .expectErrorSatisfies(error -> {
                    RemoteApiException remote =
                            assertInstanceOf(
                                    RemoteApiException.class,
                                    error);

                    assertEquals(
                            429,
                            remote.getStatusCode().value());

                    assertEquals(
                            "30",
                            remote.getResponseHeaders()
                                    .getFirst("Retry-After"));

                    assertTrue(
                            remote.getResponseBody()
                                    .contains("RATE_LIMITED"));

                    assertInstanceOf(
                            WebClientResponseException.class,
                            remote.getCause());
                })
                .verify();
    }

    @Test
    void exchangeToMonoTurns404IntoEmptyAndReleasesBody()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", "application/problem+json")
                .setBody("""
                        {"title":"Not found","status":404}
                        """));

        StepVerifier.create(catalogClient.findOrEmpty("missing"))
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("/items/missing", request.getPath());
    }

    @Test
    void serverErrorRemainsWebClientResponseException()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(500)
                .addHeader("Content-Type", "text/plain; charset=UTF-8")
                .addHeader("X-Request-Id", "server-failure-500")
                .setBody("database temporarily unavailable"));

        StepVerifier.create(catalogClient.find("42"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException exception =
                            assertInstanceOf(
                                    WebClientResponseException.class,
                                    error);

                    assertInstanceOf(
                            WebClientResponseException.InternalServerError.class,
                            error);

                    assertEquals(
                            500,
                            exception.getStatusCode().value());

                    assertEquals(
                            "database temporarily unavailable",
                            exception.getResponseBodyAsString());

                    assertEquals(
                            "server-failure-500",
                            exception.getHeaders()
                                    .getFirst("X-Request-Id"));
                })
                .verify();
    }
}
```

### 13.8. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Bộ test có năm trường hợp:

1. Response 200 được decode thành `CatalogItem`.
2. Response 404 tạo `WebClientResponseException.NotFound`; test đọc status, header, request, body String và decode body thành `ApiProblem`.
3. `onStatus` map 429 thành `RemoteApiException`, vẫn giữ status, `Retry-After`, body và cause gốc.
4. `exchangeToMono` chuyển 404 thành `Mono.empty()` và release response body.
5. Response 500 giữ `WebClientResponseException.InternalServerError` cùng body và request ID.

Kết quả mong đợi sau khi chạy Maven:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả cần đối chiếu khi thực thi trong môi trường có thể tải dependencies. Nội dung bài không tuyên bố bộ test đã được chạy trong môi trường biên soạn.

## 14. Cách gọi API và đọc lỗi trong ứng dụng

Ví dụ sử dụng client trong service:

```java
@Service
public class ItemFacade {

    private final CatalogClient catalogClient;

    public ItemFacade(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    public Mono<ItemView> getItem(String id) {
        return catalogClient.find(id)
                .map(item -> new ItemView(item.id(), item.name()))
                .onErrorMap(
                        WebClientResponseException.NotFound.class,
                        error -> new ItemMissingException(id))
                .onErrorMap(
                        WebClientResponseException.class,
                        error -> error.getStatusCode().is5xxServerError()
                                ? new CatalogUnavailableException(error)
                                : error);
    }
}
```

Service biến 404 thành exception có ý nghĩa với ứng dụng. Lỗi 5xx được chuyển thành `CatalogUnavailableException` để tầng cao hơn quyết định fallback hoặc trả lỗi. Các 4xx còn lại tiếp tục truyền để có thể được xử lý riêng.

Nếu muốn endpoint của ứng dụng trả RFC 9457 `ProblemDetail`, hãy map `ItemMissingException`/`CatalogUnavailableException` tại HTTP boundary bằng `@RestControllerAdvice`. Đừng trả raw body của dịch vụ catalog cho client của ứng dụng nếu chưa lọc.

## 15. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ mọi lỗi WebClient đều là `WebClientResponseException` | Bỏ sót DNS, TLS, connect và timeout | Phân biệt response error, request/transport error và decode error |
| Chỉ đọc `getMessage()` | Không lấy được body/headers có cấu trúc | Dùng `getStatusCode()`, `getHeaders()`, `getResponseBodyAsString()` |
| Dùng `getRawStatusCode()` trong code mới | Dùng API đã deprecated | Dùng `getStatusCode()` |
| Giả định error body luôn có JSON | Body rỗng/text/HTML làm decode thất bại | Kiểm tra Content-Type và có fallback |
| Decode error body thành DTO mà không xử lý lỗi parse | `DecodingException` che status lỗi ban đầu | Đọc raw String trước hoặc dùng `createException()` |
| Dùng `onStatus` nhưng không consume body | Response body không được xử lý như dự kiến | Đọc body trong callback hoặc tạo exception bằng `createException()` |
| Trả `Mono.empty()` từ `onStatus` rồi nghĩ body tự biến thành empty | Downstream vẫn tiếp tục decode response body | Dùng `exchangeToMono()` và `releaseBody()` cho status-as-empty |
| Dùng `exchange()` cũ | Nguy cơ leak body/connection | Dùng `exchangeToMono()`/`exchangeToFlux()` |
| Đọc `ClientResponse` sau khi callback `exchangeToMono` đã kết thúc | Body có thể đã được release | Decode/consume/release ngay trong callback |
| Log toàn bộ error body | Lộ PII, token hoặc thông tin nội bộ | Log error code, status, trace ID; mask body |
| Retry mọi 4xx/5xx | Lặp request vô ích hoặc side effect | Phân loại status và chỉ retry theo semantics |
| Retry POST không có idempotency | Tạo resource hoặc giao dịch trùng lặp | Dùng idempotency key/contract deduplication |
| Chuyển nguyên lỗi upstream cho client bên ngoài | Rò rỉ cấu trúc và thông tin nội bộ | Map sang error contract của ứng dụng |
| Error body quá lớn | Có thể vượt `maxInMemorySize` khi buffering | Giữ error payload nhỏ, đặt giới hạn codec, dùng streaming nếu thực sự cần |
| Chỉ test status code | Không phát hiện sai header/body/error mapping | Test status, headers, raw body, typed body và request gốc |

## 16. Checklist khi xử lý error response

### Phân loại lỗi

- Có nhận được HTTP response không?
- Status là 4xx, 5xx hay response thành công nhưng body decode lỗi?
- Có phải lỗi transport như DNS, connect, TLS hoặc timeout không?
- Có nên xử lý riêng 404, 409, 429 hoặc 5xx không?

### Đọc response

- `getStatusCode()` có được dùng thay `getRawStatusCode()` không?
- Đã kiểm tra `Content-Type` trước khi decode body chưa?
- Body có thể rỗng hoặc không phải JSON không?
- Có cần `getResponseBodyAsString()`, byte array hay DTO?
- Có cần đọc `Retry-After` hoặc trace ID không?
- Có giữ request gốc khi cần điều tra không?

### Reactive và resource lifecycle

- `onStatus` callback có consume body hoặc tạo exception không?
- `exchangeToMono` callback có decode/release body trước khi kết thúc không?
- Có tránh `subscribe()` và `block()` trong reactive service không?
- Có tránh đọc lại body sau khi nó đã được consume/release không?
- Có giới hạn kích thước error payload không?

### Bảo mật và retry

- Log có che Authorization, cookie, API key và PII không?
- Raw upstream body có bị trả thẳng cho client không?
- Retry có giới hạn số lần, backoff, jitter và deadline không?
- Request có idempotent hoặc có idempotency key không?
- 401/403/404/409/429 có được phân biệt đúng không?

### Testing

- Có test 2xx, 404, 429 và 5xx?
- Có test body rỗng và body không phải JSON?
- Có test body JSON decode được thành error DTO?
- Có test custom `onStatus` và `exchangeToMono`?
- Có test request/response headers và body release behavior?
- Có test transport failure riêng nếu ứng dụng cần retry network error?

## 17. Bài tập tự kiểm tra

**Bài 1.** `retrieve().bodyToMono(Item.class)` nhận status 404. Exception mặc định thường là gì?

**Đáp án:** `WebClientResponseException.NotFound`, một subclass của `WebClientResponseException`.

**Bài 2.** Muốn đọc raw error body thành String, gọi API nào?

**Đáp án:** `getResponseBodyAsString()`. Charset được lấy từ media type nếu có, nếu không thì mặc định UTF-8.

**Bài 3.** Muốn lấy response body thành `ApiProblem` trong Spring Framework 6.x, dùng API nào?

**Đáp án:** `getResponseBodyAs(ApiProblem.class)`, nếu exception được tạo bởi WebClient có decoder function phù hợp và body đúng định dạng.

**Bài 4.** `WebClientResponseException` có xuất hiện khi DNS lookup thất bại không?

**Đáp án:** Không. Không có HTTP response; thường là `WebClientRequestException` hoặc lỗi transport tương ứng.

**Bài 5.** `onStatus` callback trả `Mono.empty()` có nghĩa gì?

**Đáp án:** Status đó không bị coi là error bởi `retrieve()`; response tiếp tục đi qua body extraction phía sau. Nó không tự động biến response thành `Mono.empty()`.

**Bài 6.** Khi nào nên dùng `exchangeToMono()`?

**Đáp án:** Khi status quyết định cách decode hoặc kết quả, ví dụ 2xx decode DTO, 404 release body và trả empty, status còn lại tạo error.

**Bài 7.** Vì sao không nên trả raw error body của upstream ra client của mình?

**Đáp án:** Body có thể chứa stack trace, hostname nội bộ, PII hoặc cấu trúc không thuộc public contract của ứng dụng.

**Bài 8.** Server trả 429 với `Retry-After: 30`. Có thể retry ngay không?

**Đáp án:** Không nên. Hãy tuân theo Retry-After, giới hạn retry, dùng backoff và deadline tổng; đồng thời bảo đảm request có thể retry an toàn.

**Bài 9.** Response 200 nhưng body JSON sai định dạng có phải `WebClientResponseException` không?

**Đáp án:** Không. Status là 2xx; lỗi xảy ra ở bước decode, thường là `DecodingException` hoặc lỗi codec tương ứng.

**Bài 10.** Vì sao cần consume hoặc release body trong `exchangeToMono()`?

**Đáp án:** WebClient tự release body chưa được consume khi publisher callback kết thúc. Nếu cần nội dung, phải decode/consume ngay trong callback; việc này giúp tránh giữ buffer và connection không cần thiết.

## 18. Ghi nhớ

- `WebClientResponseException` lưu thông tin của HTTP error response đã nhận được: status, headers, body và request.
- `retrieve()` mặc định chuyển 4xx/5xx thành `WebClientResponseException` và các subclass theo status phổ biến.
- Dùng `getStatusCode()`; `getRawStatusCode()` đã deprecated.
- `getResponseBodyAsString()` đọc body theo charset response hoặc UTF-8; `getResponseBodyAsByteArray()` lấy bytes thô.
- `getResponseBodyAs(Class<T>)` và `ParameterizedTypeReference<T>` decode error body thành DTO/generic type trong Spring Framework 6.x khi decoder phù hợp.
- `onStatus(...)` cho phép map HTTP status sang exception ứng dụng; trả `Mono.empty()` nghĩa là không coi status đó là lỗi mặc định.
- `exchangeToMono(...)` cho quyền quyết định cách decode/release theo status; consume hoặc release body trong callback.
- `WebClientRequestException`, timeout và `DecodingException` là các nhóm lỗi khác với HTTP response error.
- Không log hoặc trả raw body nhạy cảm; giữ status/error code/trace ID cần thiết.
- Retry phải dựa trên status, idempotency, `Retry-After`, backoff và deadline.
- Giữ error payload nhỏ để tránh buffering vượt giới hạn codec.

Khi debug một outbound request lỗi, hãy hỏi theo thứ tự: **có nhận được HTTP response không; status là gì; body có được đọc/giải mã đúng không; lỗi có được map đúng vào use case không; response body đã được consume hoặc release chưa?**

## Tài liệu chính thức

- Spring Framework 6.2, **`retrieve()` và `onStatus`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html
- Spring Framework 6.2, **`exchangeToMono()` và `exchangeToFlux()`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html
- Spring Framework 6.2.19, **`WebClientResponseException` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html
- Spring Framework 6.2.19, **`ClientResponse` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html
- Spring Framework 6.2, **WebClient Filters and response body lifecycle**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html
- Spring Framework 6.2, **WebClient testing**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-testing.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html