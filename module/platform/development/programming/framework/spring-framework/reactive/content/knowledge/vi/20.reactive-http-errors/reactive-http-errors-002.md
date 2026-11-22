# `ResponseStatusException` và `@ResponseStatus` trong Spring WebFlux

## 1. Mục tiêu: ánh xạ lỗi ứng dụng thành HTTP status đúng

Một reactive controller thường trả về `Mono<T>` hoặc `Flux<T>`. Khi xử lý bình thường, Spring ghi giá trị thành HTTP response. Khi publisher phát `onError`, WebFlux cần xác định lỗi đó tương ứng với status nào và response body có cần chứa thông tin lỗi hay không.

Hai cách phổ biến để gắn HTTP status với exception là:

- **`ResponseStatusException`**: ném một exception có status cụ thể tại thời điểm chạy. Thích hợp khi status hoặc lý do phụ thuộc request, ví dụ không tìm thấy item có ID đang được yêu cầu.
- **`@ResponseStatus`**: khai báo status cố định trên exception class hoặc controller method. Thích hợp khi một loại exception luôn mang cùng status, hoặc một endpoint luôn trả status thành công cố định như 201/204.

Cả hai được WebFlux hỗ trợ. Tuy nhiên, việc đặt status và việc tạo một error body JSON là hai việc khác nhau. Trong Spring Framework 6.x, `ResponseStatusException` còn triển khai `ErrorResponse` và cung cấp `ProblemDetail`; muốn bảo đảm body RFC 9457 được ghi ra, hãy dùng `@ExceptionHandler`/`@ControllerAdvice` hoặc cơ chế `ResponseEntityExceptionHandler` phù hợp.

Sau bài này, bạn có thể:

1. Phân biệt `ResponseStatusException` với `@ResponseStatus` trên exception class và trên controller method.
2. Phát exception đúng cách trong `Mono`/`Flux` mà không gọi `subscribe()` hay `block()`.
3. Hiểu vai trò của `WebFluxResponseStatusExceptionHandler`.
4. Trả lỗi có cấu trúc bằng `ProblemDetail` và `ResponseEntity`.
5. Chọn đúng status, giữ nguyên cause/headers và tránh làm lộ thông tin nội bộ.
6. Kiểm thử status, headers và error body bằng `WebTestClient`.

## 2. Luồng xử lý exception trong WebFlux

WebFlux có lớp xử lý exception ở hai phạm vi:

- **Exception trong annotated controller**: `@ExceptionHandler` ở controller hoặc `@ControllerAdvice` có thể xử lý lỗi phát sinh khi gọi handler method hoặc khi reactive return value hoàn tất bằng lỗi.
- **Exception ở WebHandler chain**: `WebExceptionHandler` bao quanh các `WebFilter` và target `WebHandler`, nên có thể xử lý exception phát sinh ở filter hoặc phần còn lại của web pipeline.

WebFlux Config khai báo `WebFluxResponseStatusExceptionHandler`. Handler này:

- Xử lý `ResponseStatusException` bằng cách đặt HTTP status từ exception.
- Là lớp mở rộng có thể tìm `@ResponseStatus` trên exception class và đặt status tương ứng.
- Không thể đổi status theo cách thông thường nếu response đã được commit; lỗi khi đó tiếp tục được truyền đi.

Mô hình khái niệm:

```text
HTTP request
    |
    v
WebFilter chain
    |
    v
Controller / functional handler
    |
    v
Mono / Flux
    |
    +---- onComplete -----------------> response success
    |
    +---- onError
             |
             v
       @ExceptionHandler / @ControllerAdvice
             |
             +---- handled ----------> error response
             |
             +---- not handled
                       |
                       v
             WebExceptionHandler chain
                       |
                       v
       WebFluxResponseStatusExceptionHandler
                       |
             set HTTP status if recognized
```

Thứ tự thực tế phụ thuộc nơi exception phát sinh và cơ chế xử lý đang được cấu hình. Một lỗi được `@ExceptionHandler` xử lý sẽ không cần đi tiếp tới handler status ở ngoài. Nếu response body đã bắt đầu được gửi, không thể quay lại thay status thành 404 hoặc 500.

## 3. `ResponseStatusException`: status động tại thời điểm chạy

`ResponseStatusException` thuộc package:

```java
org.springframework.web.server.ResponseStatusException
```

Nó là subclass của `ErrorResponseException`, triển khai `ErrorResponse` và mang thông tin HTTP error response. Các constructor thường dùng:

```java
new ResponseStatusException(HttpStatus.NOT_FOUND);

new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Item was not found");

new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "Inventory service failed",
        cause);
```

`HttpStatus` triển khai `HttpStatusCode`, vì vậy có thể dùng trực tiếp. API cũng nhận `HttpStatusCode` để hỗ trợ status code không nhất thiết được biểu diễn bằng một hằng `HttpStatus`.

Thông tin quan trọng có thể đọc từ exception:

| API | Ý nghĩa |
|---|---|
| `getStatusCode()` | HTTP status cần trả |
| `getReason()` | Lý do được truyền vào constructor, có thể null |
| `getHeaders()` | Response headers bổ sung |
| `getBody()` | `ProblemDetail` được cung cấp qua `ErrorResponse` |
| `getCause()` | Nguyên nhân gốc nếu được truyền vào constructor |

Trong Spring Framework 6.x, `reason` được dùng làm nội dung `detail` mặc định của `ProblemDetail` do exception cung cấp. Tuy vậy, việc exception có `ProblemDetail` không đồng nghĩa mọi đường xử lý mặc định đều tự ghi body đó ra HTTP response. Phần render được trình bày ở mục 8.

### 3.1. Ví dụ tìm resource không tồn tại

```java
@GetMapping("/items/{id}")
public Mono<Item> getItem(@PathVariable String id) {
    return itemService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.NOT_FOUND,
                            "Item " + id + " was not found")));
}
```

`findById` trả `Mono.empty()` nếu không có item. `switchIfEmpty` chuyển trường hợp rỗng thành `onError` mang `ResponseStatusException`. WebFlux có thể nhận biết exception và ánh xạ thành HTTP 404.

Điểm quan trọng là exception được phát trong reactive pipeline. Không cần và không nên gọi:

```java
// Không làm như thế này:
itemService.findById(id).subscribe();
```

Tự subscribe sẽ tách công việc khỏi request lifecycle. Hãy trả publisher từ controller và để WebFlux quản lý subscription, lỗi và cancellation.

### 3.2. Truyền cause khi chuyển lỗi tầng dưới

```java
return inventoryClient.lookup(sku)
        .onErrorMap(
                TimeoutException.class,
                error -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Inventory lookup timed out",
                        error));
```

Ví dụ chuyển timeout của một dependency thành 504. Cause gốc vẫn được giữ để log và chẩn đoán. Không đưa thông điệp kỹ thuật như hostname, SQL, token hoặc stack trace vào `reason` gửi cho client.

Chỉ chuyển loại lỗi mà API thực sự muốn biểu diễn. Nếu mọi lỗi mạng, lỗi cấu hình và bug đều bị đổi thành 504, hệ thống sẽ mất khả năng phân biệt lỗi gateway với lỗi nội bộ.

### 3.3. Chọn status theo ý nghĩa HTTP

Một số status thường dùng:

| Status | Trường hợp thường phù hợp |
|---|---|
| 400 Bad Request | Request không hợp lệ hoặc không thể parse |
| 401 Unauthorized | Chưa xác thực hoặc credential không hợp lệ |
| 403 Forbidden | Đã xác thực nhưng không có quyền |
| 404 Not Found | Resource được yêu cầu không tồn tại |
| 409 Conflict | Xung đột với trạng thái hiện tại |
| 410 Gone | Resource đã bị loại bỏ vĩnh viễn theo contract |
| 422 Unprocessable Content | Nội dung hiểu được nhưng không đáp ứng quy tắc xử lý của API |
| 429 Too Many Requests | Vượt giới hạn request |
| 502 Bad Gateway | Gateway nhận phản hồi không hợp lệ từ upstream |
| 503 Service Unavailable | Dịch vụ tạm thời không thể xử lý |
| 504 Gateway Timeout | Gateway chờ upstream quá lâu |

Đây là hướng dẫn semantics, không phải quy tắc tự động của Spring. API cần giữ cách sử dụng status nhất quán.

## 4. `@ResponseStatus` trên exception class: status cố định cho một loại lỗi

Khi một exception class luôn biểu diễn cùng một lỗi HTTP, có thể gắn `@ResponseStatus` lên class:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ItemNotFoundException extends RuntimeException {

    public ItemNotFoundException(String id) {
        super("Item " + id + " was not found");
    }
}
```

Khi exception được ném ra trong WebFlux, `WebFluxResponseStatusExceptionHandler` có thể đọc annotation và đặt status 404.

Dùng trong reactive pipeline:

```java
@GetMapping("/legacy-items/{id}")
public Mono<Item> getLegacyItem(@PathVariable String id) {
    return itemService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ItemNotFoundException(id)));
}
```

Cách này phù hợp với ứng dụng nhỏ hoặc exception chỉ được dùng tại web layer. Nhưng có một quyết định kiến trúc cần cân nhắc: annotation đặt HTTP semantics trực tiếp lên exception class. Nếu exception thuộc domain/application layer và được tái sử dụng bởi batch job, message consumer hoặc một adapter khác, việc gắn `@ResponseStatus` làm tầng nghiệp vụ phụ thuộc HTTP.

Với hệ thống có nhiều adapter, thường nên giữ domain exception độc lập rồi ánh xạ ở `@ControllerAdvice` hoặc HTTP adapter.

### 4.1. `@ResponseStatus` trên exception có tự tạo JSON body không?

Không nên coi annotation này là một định nghĩa error-body contract. Trong WebFlux, `WebFluxResponseStatusExceptionHandler` có nhiệm vụ xác định và đặt status cho exception được nhận diện. Nếu API cần một body JSON có `type`, `title`, `status`, `detail` và field bổ sung, hãy dùng `@ExceptionHandler` trả `ProblemDetail` hoặc `ResponseEntity<ProblemDetail>`.

Không nên dựa vào `reason` của `@ResponseStatus` để thay thế error response JSON. Hãy kiểm soát body rõ ràng ở exception handler.

## 5. `@ResponseStatus` trên controller method: status cố định cho response bình thường

Annotation cũng có thể đặt trên method được ánh xạ HTTP. Trường hợp phổ biến là status thành công cố định:

```java
@PostMapping("/items")
@ResponseStatus(HttpStatus.CREATED)
public Mono<Item> create(@RequestBody CreateItem request) {
    return itemService.create(request);
}
```

Method trả item và Spring ghi body bình thường với status 201 Created.

Một ví dụ khác:

```java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> delete(@PathVariable String id) {
    return itemService.deleteById(id);
}
```

Khi publisher hoàn tất thành công, response có status 204 No Content.

Các trường hợp này thể hiện ý nghĩa của annotation trên handler method: đặt status mặc định/cố định cho response do handler tạo ra. Nếu cần status hoặc headers thay đổi theo kết quả chạy, `ResponseEntity` thường rõ ràng hơn.

### 5.1. Không nhầm status method với status exception

| Vị trí annotation | Ý nghĩa |
|---|---|
| Trên controller method | Status cố định cho response của method khi xử lý thành công |
| Trên exception class | Status được dùng khi exception đó được ném ra và WebFlux xử lý |
| Trên controller class | Có thể được kế thừa bởi các request-mapping và exception-handler methods; cần thận trọng vì phạm vi ảnh hưởng rộng |

Không đặt `@ResponseStatus(HttpStatus.CREATED)` ở cấp controller class nếu controller có cả GET, POST và DELETE với các status khác nhau.

### 5.2. Thuộc tính `reason`

`@ResponseStatus` có thuộc tính `reason`, nhưng nó không phải cơ chế thiết kế response body JSON cho REST API. Nếu cần thông điệp lỗi có cấu trúc hoặc nhiều field, hãy dùng `ProblemDetail`. Nếu cần điều khiển status, header và body theo từng kết quả, hãy trả `ResponseEntity`.

## 6. So sánh hai cách

| Tiêu chí | `ResponseStatusException` | `@ResponseStatus` |
|---|---|---|
| Cách khai báo | Tạo/emit exception lúc chạy | Annotation tĩnh |
| Status | Có thể chọn theo request hoặc kết quả | Cố định theo method hoặc exception class |
| Reason | Constructor nhận reason động | Giá trị annotation cố định |
| Cause | Constructor hỗ trợ truyền cause | Không có thuộc tính cause |
| Response headers | Có API `getHeaders()`; subclass có thể tùy biến | Không khai báo response headers |
| ProblemDetail | Có `getBody()` qua `ErrorResponse` | Không tự cung cấp `ProblemDetail` |
| Phù hợp | Resource không tồn tại theo ID, dependency timeout, lỗi có status động | Exception class có status ổn định, method luôn trả 201/204 |
| Tính linh hoạt | Cao hơn | Đơn giản, khai báo tĩnh |

Quy tắc chọn nhanh:

- Kết quả chỉ biết khi chạy và status thay đổi theo request: dùng `ResponseStatusException`.
- Một exception class luôn có cùng status: có thể dùng `@ResponseStatus` trên class.
- Một endpoint luôn trả status thành công cố định: dùng `@ResponseStatus` trên method.
- Cần body lỗi, headers hoặc status động theo nhiều nhánh: dùng `ProblemDetail`/`ResponseEntity` hoặc `@ExceptionHandler`.

## 7. Phát exception trong `Mono` và `Flux`

Trong reactive programming, exception cần trở thành tín hiệu `onError` của publisher để WebFlux xử lý theo request lifecycle.

### 7.1. Chuyển `Mono.empty()` thành 404

```java
Mono<Item> result = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Item not found")));
```

Đây là cách tự nhiên khi resource không tồn tại được biểu diễn bằng empty publisher.

### 7.2. Dùng `Mono.defer` khi lỗi phụ thuộc việc thực thi

```java
Mono<Item> result = Mono.defer(() -> {
    if (id == null || id.isBlank()) {
        return Mono.error(
                new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Item id is required"));
    }

    return repository.findById(id);
});
```

`defer` trì hoãn việc kiểm tra và tạo publisher đến lúc subscribe. Với một controller request thông thường, có thể kiểm tra dữ liệu ngay trong method; `defer` hữu ích khi muốn side effect hoặc logic tạo publisher nằm đúng trong subscription.

### 7.3. `onErrorMap` và `onErrorResume` khác nhau

`onErrorMap` biến một lỗi thành exception khác:

```java
return service.load(id)
        .onErrorMap(
                StorageTimeoutException.class,
                error -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Storage timed out",
                        error));
```

`onErrorResume` phục hồi bằng publisher khác:

```java
return service.load(id)
        .onErrorResume(CacheUnavailableException.class,
                error -> service.loadFromDatabase(id));
```

Nếu `onErrorResume` trả về giá trị thay thế và complete thành công, response có thể là 2xx; exception ban đầu không còn được dùng để tạo status. Chỉ phục hồi khi fallback thực sự là hành vi mong muốn.

Không bắt mọi exception rồi trả `Mono.just(defaultValue)`. Cách đó có thể che lỗi và tạo phản hồi thành công giả.

### 7.4. Đừng bọc mất exception mang status

Nếu một `ResponseStatusException` bị bọc thành một exception chung không giữ quan hệ cause hoặc không được handler nhận diện, status dự kiến có thể không còn được ánh xạ như mong muốn. Giữ nguyên exception hoặc chuyển đổi có chủ đích và kiểm thử status cuối cùng.

## 8. Trả error body có cấu trúc bằng `ProblemDetail`

Spring Framework 6 hỗ trợ RFC 9457 Problem Details qua các abstraction:

- `ProblemDetail`: body lỗi chuẩn với `type`, `title`, `status`, `detail`, `instance` và properties mở rộng.
- `ErrorResponse`: contract cung cấp HTTP status, headers và ProblemDetail.
- `ErrorResponseException`: exception cơ sở có thể mang `ErrorResponse`.
- `ResponseEntityExceptionHandler`: base class dành cho `@ControllerAdvice`, xử lý exception WebFlux và render Problem Details.

`ResponseStatusException` kế thừa `ErrorResponseException`, do đó có `getBody()` để truy cập ProblemDetail. Một cách rõ ràng để trả body là dùng advice:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ProblemDetail> handle(
            ResponseStatusException exception) {

        ProblemDetail problem = exception.getBody();

        return ResponseEntity
                .status(exception.getStatusCode())
                .headers(headers ->
                        headers.addAll(exception.getHeaders()))
                .body(problem);
    }
}
```

Advice trên:

1. Nhận exception có status.
2. Lấy ProblemDetail do exception cung cấp.
3. Giữ status và response headers.
4. Trả body theo định dạng Problem Details.

Khi Jackson được cấu hình theo Spring WebFlux mặc định, `ProblemDetail` được ghi với media type `application/problem+json` (hoặc XML khi phù hợp). Thuộc tính `instance` có thể được Spring điền từ URL path hiện tại nếu chưa được đặt.

### 8.1. Thêm error code riêng

Có thể thêm thuộc tính tùy chỉnh:

```java
ProblemDetail problem = exception.getBody();
problem.setProperty("code", "ITEM_NOT_FOUND");
problem.setProperty("retryable", false);
```

Khi dùng Jackson tích hợp của Spring, map `properties` được ghi thành các field cấp cao nhất trong JSON Problem Detail.

Ví dụ body:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item 42 was not found",
  "instance": "/api/items/42",
  "code": "ITEM_NOT_FOUND",
  "retryable": false
}
```

Giữ error code ổn định để client xử lý theo máy. `detail` có thể thay đổi hoặc được quốc tế hóa, vì vậy không nên để client phụ thuộc vào việc parse câu văn.

### 8.2. Dùng `ResponseEntityExceptionHandler` cho lỗi WebFlux chuẩn

Nếu muốn chuẩn hóa cả lỗi do framework phát sinh như body không đọc được, method không hỗ trợ, validation hoặc media type, có thể mở rộng `ResponseEntityExceptionHandler`:

```java
@RestControllerAdvice
public class GlobalWebFluxExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

Base class này cung cấp một `@ExceptionHandler` cho các exception WebFlux và `ErrorResponseException`, trả response theo RFC 9457. Có thể override các method xử lý cụ thể hoặc thêm handler cho exception nghiệp vụ của ứng dụng.

Không tạo một `@ExceptionHandler(Exception.class)` trả 400 cho mọi lỗi. Lỗi không mong đợi, bug và hạ tầng cần được giữ là 5xx để có thể điều tra.

## 9. `@ExceptionHandler` và `WebExceptionHandler` khác nhau thế nào?

Hai abstraction đều xử lý lỗi nhưng có phạm vi khác nhau:

| Abstraction | Phạm vi | Trường hợp phù hợp |
|---|---|---|
| `@ExceptionHandler` | Lỗi từ controller method trong annotated controller | Map domain exception thành ProblemDetail |
| `@ControllerAdvice` / `@RestControllerAdvice` | Áp dụng `@ExceptionHandler` cho nhiều controller | Error schema dùng chung cho REST API |
| `ResponseEntityExceptionHandler` | Base class của advice xử lý lỗi WebFlux chuẩn | Chuẩn hóa lỗi framework theo RFC 9457 |
| `WebExceptionHandler` | Toàn bộ WebHandler chain, gồm WebFilter và handler đích | Lỗi phát sinh trước/sau controller hoặc trong filter |
| `WebFluxResponseStatusExceptionHandler` | `WebExceptionHandler` chuyên xử lý status exception/annotation | Ánh xạ status từ `ResponseStatusException` và `@ResponseStatus` trên exception class |

`@ControllerAdvice` không phải một global interceptor cho mọi lỗi ở mọi tầng của server. Nếu lỗi phát sinh trong `WebFilter` trước khi request tới annotated controller, cơ chế `WebExceptionHandler` là tầng phù hợp hơn.

Functional endpoint (`WebFlux.fn`) có thể cấu hình exception handlers thông qua `HandlerStrategies`; đừng giả định `@ControllerAdvice` tự động bao phủ mọi functional route theo cùng cách với annotated controller.

## 10. Response đã commit: vì sao không thể đổi status sau đó?

HTTP status và headers phải được gửi trước hoặc cùng lúc response bắt đầu commit. Với một endpoint trả JSON đơn, lỗi thường phát sinh trước khi body được ghi xong và có thể được ánh xạ thành error response.

Với streaming response:

```java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Event>> events() {
    return eventService.stream();
}
```

Giả sử stream đã gửi một số event rồi mới phát `onError`. Lúc đó status/header có thể đã được gửi. WebFlux không thể quay lại đổi HTTP 200 thành 500 và thay thế body đã phát. Client có thể thấy stream kết thúc bất thường hoặc nhận lỗi ở tầng transport/protocol tùy tình huống.

Vì vậy:

- Xác định status trước khi bắt đầu streaming nếu có thể.
- Xử lý lỗi theo giao thức stream khi cần, ví dụ phát một event lỗi theo contract của ứng dụng.
- Không coi `ResponseStatusException` phát muộn là cách sửa status đã commit.
- Kiểm thử cả trường hợp lỗi trước event đầu tiên và lỗi sau khi stream bắt đầu.

## 11. Lỗi phổ biến khi dùng `ResponseStatusException` và `@ResponseStatus`

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `@ResponseStatus` trên controller class có nhiều endpoint | Áp cùng status lên nhiều method ngoài ý muốn | Đặt ở method cụ thể hoặc exception class |
| Dùng `@ResponseStatus` cho status phụ thuộc kết quả runtime | Annotation không biểu diễn được nhiều nhánh status | Dùng `ResponseStatusException` hoặc `ResponseEntity` |
| Nghĩ `@ResponseStatus` tự tạo JSON error body | Client nhận status nhưng không có schema lỗi mong muốn | Dùng `ProblemDetail`/`@ExceptionHandler` |
| Nghĩ `ResponseStatusException` luôn tự render body trong mọi đường xử lý | Có thể chỉ thấy status được đặt bởi WebExceptionHandler | Dùng advice trả `ProblemDetail` nếu body là contract |
| Dùng reason chứa SQL hoặc thông tin nội bộ | Lộ chi tiết hệ thống cho client | Dùng detail an toàn, giữ cause trong log |
| Ném exception đồng bộ ngoài reactive pipeline ở nơi không phù hợp | Khó kiểm soát thời điểm lỗi và subscription | Dùng `Mono.error`, `switchIfEmpty`, `defer` |
| Dùng `onErrorResume` trả fallback cho mọi lỗi | Lỗi thật bị biến thành response thành công | Chỉ phục hồi lỗi có fallback hợp lệ |
| Bọc `ResponseStatusException` thành exception chung | Status mapping có thể mất | Giữ exception hoặc map lại có chủ đích |
| Đổi status sau khi response commit | Không thể sửa status/header đã gửi | Quyết định status trước khi stream body |
| Dùng domain exception gắn annotation HTTP trong mọi tầng | Domain phụ thuộc transport | Map domain exception tại HTTP boundary |
| Dùng `ResponseStatusException` cho mọi lỗi bất ngờ | Che bug thành client error | Phân loại input, domain và infrastructure error |
| Ghi stack trace đầy đủ cho mọi 404 | Log noise lớn | Dùng log level phù hợp và giữ trace cho lỗi bất ngờ |

## 12. Dự án Java 17+ chạy được: ResponseStatusException và @ResponseStatus

Dự án Maven dưới đây dùng Spring Boot 3.3.5, Spring WebFlux và `WebTestClient`. Nó minh họa ba cách:

1. `ResponseStatusException` tạo 404 động khi item không tồn tại.
2. `@ResponseStatus` trên exception class tạo 404 cố định.
3. `@ResponseStatus` trên controller method tạo status 201 và 204 khi xử lý thành công.

Một `@RestControllerAdvice` render `ProblemDetail` từ `ResponseStatusException` để error body có contract rõ ràng.

### 12.1. Cấu trúc dự án

```text
webflux-response-status/
├── pom.xml
└── src/
    ├── main/java/edu/demo/status/
    │   ├── StatusApplication.java
    │   ├── Item.java
    │   ├── CreateItem.java
    │   ├── ItemService.java
    │   ├── ItemController.java
    │   ├── LegacyItemNotFoundException.java
    │   └── ApiExceptionHandler.java
    └── test/java/edu/demo/status/
        └── ItemStatusTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-response-status</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 12.3. `StatusApplication.java`

```java
package edu.demo.status;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(StatusApplication.class, args);
    }
}
```

### 12.4. `Item.java` và `CreateItem.java`

```java
package edu.demo.status;

public record Item(String id, String name) {
}
```

```java
package edu.demo.status;

public record CreateItem(String name) {
}
```

### 12.5. `ItemService.java`

```java
package edu.demo.status;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ItemService {

    private final ConcurrentMap<String, Item> items =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong();

    public Mono<Item> create(CreateItem request) {
        return Mono.fromSupplier(() -> {
            String id = Long.toString(sequence.incrementAndGet());
            Item item = new Item(id, request.name());
            items.put(id, item);
            return item;
        });
    }

    public Mono<Item> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)));
    }

    public Mono<Boolean> deleteById(String id) {
        return Mono.fromSupplier(() -> items.remove(id) != null);
    }
}
```

Service chỉ cung cấp kết quả nghiệp vụ: có item, không có item, hoặc đã xóa được hay chưa. Nó không tự quyết định HTTP status. HTTP adapter ánh xạ kết quả empty/false thành exception hoặc response phù hợp.

### 12.6. `LegacyItemNotFoundException.java`

```java
package edu.demo.status;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class LegacyItemNotFoundException extends RuntimeException {

    public LegacyItemNotFoundException(String id) {
        super("Item " + id + " was not found");
    }
}
```

Đây là exception minh họa cách gắn status cố định lên exception class. Vì class này dùng `@ResponseStatus`, WebFlux có thể đặt status 404 khi exception thoát ra ngoài. Ví dụ không dùng `reason` để tạo error body; phần error body sẽ do advice quản lý nếu cần.

### 12.7. `ItemController.java`

```java
package edu.demo.status;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Item> get(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Item " + id + " was not found")));
    }

    @GetMapping("/legacy/{id}")
    public Mono<Item> getLegacy(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new LegacyItemNotFoundException(id)));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Item> create(@RequestBody CreateItem request) {
        return service.create(request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> delete(@PathVariable String id) {
        return service.deleteById(id)
                .flatMap(deleted -> {
                    if (deleted) {
                        return Mono.empty();
                    }

                    return Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.NOT_FOUND,
                                    "Item " + id + " was not found"));
                });
    }
}
```

Hai đường tìm item minh họa hai kiểu exception:

- `/api/items/{id}` phát `ResponseStatusException` với status và detail được quyết định tại runtime.
- `/api/items/legacy/{id}` phát exception class có `@ResponseStatus`.

POST và DELETE minh họa status cố định trên method: 201 và 204.

### 12.8. `ApiExceptionHandler.java`

```java
package edu.demo.status;

import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ProblemDetail> handle(
            ResponseStatusException exception) {

        ProblemDetail problem = exception.getBody();

        return ResponseEntity
                .status(exception.getStatusCode())
                .headers(headers ->
                        headers.addAll(exception.getHeaders()))
                .body(problem);
    }
}
```

Advice này bảo đảm những `ResponseStatusException` từ annotated controllers được trả với status, headers và ProblemDetail tương ứng. Trong ứng dụng lớn, nên xử lý riêng từng nhóm exception hoặc mở rộng `ResponseEntityExceptionHandler` để chuẩn hóa cả exception framework.

### 12.9. `ItemStatusTests.java`

```java
package edu.demo.status;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemStatusTests {

    @Autowired
    WebTestClient client;

    @Test
    void postUsesResponseStatusCreated() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItem("Keyboard"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").exists()
                .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void responseStatusExceptionMapsTo404AndProblemDetail() {
        client.get()
                .uri("/api/items/not-found")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.detail")
                .isEqualTo("Item not-found was not found");
    }

    @Test
    void responseStatusOnExceptionClassMapsTo404() {
        client.get()
                .uri("/api/items/legacy/not-found")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void deleteUsesResponseStatusNoContent() {
        Item created = client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItem("Mouse"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(Item.class)
                .returnResult()
                .getResponseBody();

        org.junit.jupiter.api.Assertions.assertNotNull(created);

        client.delete()
                .uri("/api/items/{id}", created.id())
                .exchange()
                .expectStatus().isNoContent()
                .expectBody().isEmpty();
    }

    @Test
    void deleteMissingItemUsesDynamic404() {
        client.delete()
                .uri("/api/items/missing-delete")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404);
    }
}
```

### 12.10. Chạy chương trình

Trong thư mục có `pom.xml`:

```bash
mvn test
```

Khi dependency tải được và assertion đúng, Maven Surefire sẽ báo năm test chạy, không có failure/error:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả mong đợi để đối chiếu sau khi thực thi; tài liệu không tuyên bố Maven đã được chạy trong môi trường biên soạn.

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

Tạo item:

```bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard"}'
```

Response có status `201 Created` và JSON chứa `id`, `name`.

Tra cứu một ID không tồn tại:

```bash
curl -i "http://localhost:8080/api/items/unknown"
```

Response có status `404 Not Found`; với advice trong ví dụ, body được render dưới dạng `application/problem+json`.

## 13. Kiểm thử và chẩn đoán

Khi test status mapping, không chỉ kiểm tra code status. Với API có error contract, nên xác nhận:

- HTTP status đúng.
- Content-Type đúng, thường là `application/problem+json`.
- `ProblemDetail.status` khớp status HTTP.
- `detail` không chứa thông tin nội bộ.
- Error code hoặc field bổ sung ổn định nếu client phụ thuộc.
- Headers bắt buộc được giữ lại.
- Không có response body khi status yêu cầu body rỗng như 204.

Các trường hợp nên test:

| Trường hợp | Assertion |
|---|---|
| `ResponseStatusException` 404 | Status 404; ProblemDetail body nếu có advice |
| Exception class có `@ResponseStatus(404)` | Status 404 |
| Method có `@ResponseStatus(201)` | Status 201 và body vẫn được ghi |
| Method có `@ResponseStatus(204)` | Status 204, body rỗng |
| Response đã commit rồi stream phát lỗi | Không kỳ vọng status có thể đổi thành 4xx/5xx |
| Unexpected exception | Status 5xx, không bị biến thành 400 |

Nếu status không như mong đợi, lần theo:

1. Exception có thực sự được phát thành `onError` không?
2. Exception có bị `onErrorResume` chuyển thành giá trị thành công không?
3. `@ExceptionHandler` nào đã bắt exception?
4. `WebFluxResponseStatusExceptionHandler` có nhận được exception không?
5. Response đã commit trước khi exception xuất hiện chưa?
6. Có filter hoặc custom `WebExceptionHandler` nào xử lý trước và thay đổi kết quả không?

## 14. Checklist chọn cách ánh xạ status

- Status có cố định cho một endpoint thành công không? Cân nhắc `@ResponseStatus` trên method.
- Một loại exception luôn có cùng status và chỉ dùng ở web layer không? Cân nhắc `@ResponseStatus` trên exception class.
- Status phụ thuộc kết quả hoặc dữ liệu request không? Dùng `ResponseStatusException` hoặc `ResponseEntity`.
- Có cần error body chuẩn RFC 9457 không? Dùng `ProblemDetail`, `@ExceptionHandler` hoặc `ResponseEntityExceptionHandler`.
- Có cần response headers riêng không? Dùng `ResponseEntity` hoặc giữ headers từ `ResponseStatusException`.
- Exception có chứa thông tin nhạy cảm không? Dùng detail an toàn, không gửi cause/stack trace cho client.
- Domain/application layer có bị buộc phụ thuộc HTTP annotation không? Nếu có, chuyển mapping ra adapter/advice.
- Error có thể phát sau khi streaming body bắt đầu không? Thiết kế giao thức stream riêng.
- Có test cho status, body, content type và trường hợp response committed không?
- Có giữ lỗi không mong đợi ở 5xx để điều tra không?

## 15. Bài tập tự kiểm tra

**Bài 1.** Một repository trả `Mono.empty()` khi không tìm thấy item. Muốn trả 404 theo request ID, nên dùng gì?

**Đáp án:** `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND, ...)))`, hoặc map empty sang một exception class có `@ResponseStatus` nếu status cố định và phù hợp kiến trúc.

**Bài 2.** `@ResponseStatus(HttpStatus.CREATED)` đặt trên POST method có ngăn Spring ghi response body không?

**Đáp án:** Không, khi không dùng `reason`, method vẫn có thể trả object/`Mono<T>` để Spring ghi body với status 201.

**Bài 3.** `@ResponseStatus(HttpStatus.NOT_FOUND)` trên exception class có tự tạo JSON `ProblemDetail` không?

**Đáp án:** Không nên giả định như vậy. WebFlux status handler xác định và đặt status; muốn error body có schema rõ ràng thì dùng `@ExceptionHandler` trả `ProblemDetail` hoặc `ResponseEntity`.

**Bài 4.** Vì sao `ResponseStatusException` phù hợp hơn annotation tĩnh khi status phụ thuộc runtime?

**Đáp án:** Constructor cho phép chọn `HttpStatusCode`, reason và cause tại thời điểm exception được tạo.

**Bài 5.** `ResponseStatusException` có body `ProblemDetail` nhưng response thực tế không có JSON body. Cần kiểm tra gì?

**Đáp án:** Kiểm tra đường xử lý exception. Nếu chỉ có `WebFluxResponseStatusExceptionHandler`, nó đặt status; thêm `@ExceptionHandler`/`ResponseEntityExceptionHandler` để render body.

**Bài 6.** Một SSE stream đã phát 10 event rồi mới ném `ResponseStatusException(500)`. WebFlux có thể đổi status thành 500 không?

**Đáp án:** Thông thường không, vì response đã commit. Cần xử lý lỗi theo protocol của stream hoặc thiết kế status trước khi bắt đầu gửi body.

**Bài 7.** Một lỗi database bất ngờ bị đổi thành `ResponseStatusException(BAD_REQUEST)`. Vì sao không tốt?

**Đáp án:** Nó báo sai rằng client gửi request không hợp lệ, che lỗi hạ tầng và làm metric/status mất ý nghĩa. Chỉ map lỗi theo nguyên nhân và contract thực sự.

**Bài 8.** Vì sao domain exception không nên luôn mang `@ResponseStatus`?

**Đáp án:** Domain có thể được dùng bởi nhiều adapter không phải HTTP. Đặt annotation HTTP lên exception khiến domain phụ thuộc transport; ánh xạ ở HTTP boundary thường linh hoạt hơn.

## 16. Ghi nhớ

- `ResponseStatusException` là cách phát exception có status động trong reactive pipeline.
- `@ResponseStatus` trên exception class gắn status cố định với một loại lỗi; WebFlux có `WebFluxResponseStatusExceptionHandler` để nhận diện.
- `@ResponseStatus` trên controller method phù hợp status cố định cho response thành công như 201 hoặc 204.
- `ResponseStatusException` triển khai `ErrorResponse` và có `ProblemDetail`; muốn body JSON được render rõ ràng, dùng `@ExceptionHandler`, `@ControllerAdvice` hoặc `ResponseEntityExceptionHandler`.
- `WebExceptionHandler` bao phạm vi WebHandler chain; `@ExceptionHandler`/`@ControllerAdvice` xử lý lỗi controller theo cơ chế annotated controller.
- Không đổi status sau khi response đã commit, đặc biệt với SSE/NDJSON streaming.
- Giữ cause để điều tra, nhưng chỉ gửi detail an toàn cho client.
- Không biến mọi exception thành 400; phân loại lỗi input, domain và infrastructure.

Khi xử lý lỗi trong WebFlux, hãy xác định ba điều: **exception được phát ở đâu, handler nào nhận nó, và response đã commit hay chưa**. Từ đó chọn đúng giữa status exception, annotation, advice và ProblemDetail.

## Tài liệu chính thức

- Spring Framework 6.2, **WebFlux Reactive Core – Exception Handling**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **`ResponseStatusException` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/ResponseStatusException.html
- Spring Framework 6.2, **`WebFluxResponseStatusExceptionHandler` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/handler/WebFluxResponseStatusExceptionHandler.html
- Spring Framework 6.2, **`@ResponseStatus` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html
- Spring Framework 6.2, **WebFlux Controller Exceptions**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html
- Spring Framework 6.2, **WebFlux Error Responses and Problem Details**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html