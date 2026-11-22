# retrieve và giải mã bằng bodyToMono, bodyToFlux

**Ngữ cảnh:** Spring Framework Reactive → **Đọc phản hồi WebClient**.

Sau khi gửi request bằng `WebClient`, ứng dụng cần quyết định cách nhận response body. Với luồng thông thường, `retrieve()` tạo một `ResponseSpec` để khai báo cách trích xuất response. Hai API quan trọng nhất là:

- `bodyToMono(T.class)`: giải mã body thành tối đa một giá trị kiểu `T` và trả `Mono<T>`.
- `bodyToFlux(T.class)`: giải mã body thành một luồng gồm không, một hoặc nhiều phần tử kiểu `T` và trả `Flux<T>`.

Cả hai đều dùng codec của Spring WebFlux để chuyển bytes thành Java object. Kiểu Java đích, `Content-Type` của response và codec được cấu hình phải tương thích. Mặc định, response có status 4xx hoặc 5xx trở thành `WebClientResponseException`; có thể thay đổi bằng `onStatus`.

Bài này tập trung vào **đọc response**. Hãy phân biệt request header `Accept` (client mong muốn nhận representation nào) với response header `Content-Type` (server thực sự gửi representation nào).

## 1. retrieve() nằm ở đâu trong request chain?

Một lời gọi WebClient thường gồm bốn giai đoạn:

```text
WebClient
   |
   v
get() / post() / method(...)
   |
   v
uri(...) + headers(...) + body(...)
   |
   v
retrieve()
   |
   v
ResponseSpec
   |
   +---- onStatus(...)       map HTTP error
   |
   +---- bodyToMono(T)       decode 0..1 value
   |
   +---- bodyToFlux(T)       decode 0..N values
   |
   +---- toEntity(T)         status + headers + body
   |
   v
Mono / Flux
   |
   v
subscribe / compose with caller
```

Ví dụ lấy một quyển sách:

```java
Mono<Book> book = webClient.get()
        .uri("/books/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Book.class);
```

`retrieve()` chưa trả về `Book`. Nó trả về `ResponseSpec` để bạn tiếp tục chọn cách giải mã. `bodyToMono` trả publisher; request thường chỉ thực thi khi publisher được subscribe bởi framework hoặc caller.

Ví dụ đọc danh sách:

```java
Flux<Book> books = webClient.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

Nếu muốn lấy metadata HTTP cùng body, dùng `toEntity` hoặc các biến thể tương ứng thay vì chỉ lấy body.

## 2. bodyToMono: giải mã tối đa một object

`bodyToMono(Class<T>)` yêu cầu codec giải mã response body thành một giá trị kiểu `T`:

```java
Mono<Book> bookMono = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class);
```

`Mono<T>` có ba khả năng quan trọng:

- Phát đúng một object rồi complete.
- Complete mà không phát object nếu response không có body.
- Phát error nếu status bị xem là lỗi, transport lỗi hoặc giải mã thất bại.

`Mono` không đồng nghĩa “luôn có một giá trị”. Nếu endpoint có thể trả 204 hoặc body rỗng, hãy xử lý nhánh empty rõ ràng.

### 2.1. Dùng khi nào?

`bodyToMono` phù hợp với:

- GET một resource theo ID.
- POST tạo mới và nhận object đã tạo.
- Endpoint trả một JSON object.
- Response text hoặc bytes cần đọc thành một giá trị.
- Một API chỉ xác nhận thành công bằng status và không cần nội dung (có thể dùng `Void.class` hoặc `toBodilessEntity()`).

Ví dụ:

```java
Mono<Book> book = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class);

Mono<String> text = webClient.get()
        .uri("/health/message")
        .retrieve()
        .bodyToMono(String.class);

Mono<byte[]> bytes = webClient.get()
        .uri("/files/cover")
        .retrieve()
        .bodyToMono(byte[].class);
```

Codec phù hợp sẽ được chọn theo kiểu đích và response media type. Ví dụ `String` thường dùng text decoder, `byte[]` dùng byte-array decoder, còn DTO JSON dùng Jackson codec nếu dependency và cấu hình đã cung cấp codec đó.

### 2.2. Body rỗng và Mono.empty()

Với response 204 hoặc body không có nội dung, `bodyToMono(Book.class)` có thể complete empty. Không nên giả định nó tạo một `Book` rỗng.

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Book response is empty")));
```

Nếu empty là hợp lệ, dùng fallback hoặc biểu diễn optional:

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Book.class)
        .defaultIfEmpty(Book.notAvailable());
```

`Book.notAvailable()` là factory method minh họa của DTO. Có thể dùng `blockOptional()` ở ranh giới imperative để phân biệt có/không có giá trị, nhưng trong reactive service hãy compose bằng `switchIfEmpty`, `defaultIfEmpty` hoặc `hasElement`.

Không dùng `defaultIfEmpty` để che một response lỗi hoặc lỗi decode. Empty và error là hai tín hiệu khác nhau.

### 2.3. Đọc response không có body

Nếu chỉ cần chờ thao tác HTTP hoàn tất và không cần body:

```java
Mono<Void> deleted = webClient.delete()
        .uri("/books/42")
        .retrieve()
        .bodyToMono(Void.class);
```

Nếu cần cả status và headers nhưng không cần body:

```java
Mono<ResponseEntity<Void>> deleted = webClient.delete()
        .uri("/books/42")
        .retrieve()
        .toBodilessEntity();
```

`Void.class` không phải kiểu DTO để deserialize. Nó biểu thị caller không cần nhận body.

## 3. bodyToFlux: giải mã nhiều phần tử

`bodyToFlux(Class<T>)` trả về `Flux<T>`. Publisher có thể phát 0..N phần tử, phù hợp với danh sách, stream event hoặc nguồn dữ liệu dài:

```java
Flux<Book> books = webClient.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

Có thể xử lý từng phần tử mà không cần gom toàn bộ danh sách:

```java
return webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToFlux(Book.class)
        .filter(book -> book.active())
        .map(Book::toSummary);
```

Mỗi item được phát khi decoder có thể giải mã item đó. Downstream có thể áp dụng backpressure, hủy subscription hoặc kết hợp với các publisher khác.

### 3.1. JSON array và NDJSON

Một response JSON array có thể được giải mã thành các item:

```json
[
  {"id": 1, "title": "Reactive"},
  {"id": 2, "title": "WebFlux"}
]
```

`bodyToFlux(Book.class)` có thể phát hai `Book` khi codec hỗ trợ cách representation đó.

Với dữ liệu phát theo từng dòng, NDJSON (newline-delimited JSON) là lựa chọn phù hợp:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"title":"Reactive"}
{"id":2,"title":"WebFlux"}
```

Client:

```java
Flux<Book> books = webClient.get()
        .uri("/books/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

NDJSON biểu diễn mỗi JSON object trên một dòng. Server có thể gửi các dòng theo thời gian, và client nhận các object tương ứng khi dữ liệu đến. Hãy dùng media type đúng với giao thức server thực sự phát.

### 3.2. Flux không tự biến response thành streaming protocol

Kiểu trả về `Flux<T>` không tự quyết định framing trên dây. Việc decode và khả năng phát từng phần phụ thuộc:

- `Content-Type` và format body.
- Codec/decoder được cấu hình.
- Server có flush từng phần hay buffer toàn bộ.
- HTTP connector, proxy và network buffering.
- Operator phía client có aggregate dữ liệu hay không.

Với stream dài, dùng media type streaming phù hợp như NDJSON hoặc SSE. Đừng cho rằng JSON array lớn luôn có cùng hành vi bộ nhớ và latency như NDJSON.

### 3.3. Không collectList() nguồn vô hạn

`collectList()` biến Flux thành `Mono<List<T>>` và phải giữ toàn bộ phần tử trước khi phát list:

```java
Mono<List<Book>> allBooks = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToFlux(Book.class)
        .collectList();
```

Cách này phù hợp với danh sách hữu hạn, có giới hạn và thực sự cần xử lý toàn bộ cùng lúc. Không dùng cho SSE, event stream vô hạn hoặc response rất lớn; bộ nhớ sẽ tăng theo số item.

Nếu cần tổng hợp, hãy cân nhắc `take(n)`, `bufferTimeout`, pagination, giới hạn kết quả hoặc xử lý từng item.

## 4. Codec quyết định cách bytes trở thành object

`retrieve()` không tự parse JSON bằng một bộ chuyển đổi riêng. WebClient sử dụng `HttpMessageReader` và codec được đăng ký trong `ExchangeStrategies` để decode body.

Một số kiểu thường gặp:

| Response body | Kiểu đích | Ví dụ |
|---|---|---|
| JSON object | DTO | `bodyToMono(Book.class)` |
| JSON array | từng DTO | `bodyToFlux(Book.class)` |
| JSON object có generic | `ParameterizedTypeReference` | `bodyToMono(typeRef)` |
| NDJSON | từng DTO | `bodyToFlux(Book.class)` |
| Text | `String` | `bodyToMono(String.class)` |
| Binary | `byte[]` hoặc `DataBuffer` | `bodyToMono(byte[].class)` |
| Không cần body | `Void` | `bodyToMono(Void.class)` |

Request header `Accept` giúp server chọn representation. Response `Content-Type` cho biết định dạng thực tế để codec chọn decoder. Nếu server trả XML nhưng client chỉ có JSON codec, việc giải mã có thể thất bại dù Java class đúng.

Ví dụ khai báo rõ Accept:

```java
Mono<Book> result = webClient.get()
        .uri("/books/42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Book.class);
```

`Accept` không ép server phải tuân theo; server có thể trả 406 nếu không thể cung cấp representation được yêu cầu, hoặc trả một kiểu không mong đợi do API/proxy cấu hình sai.

## 5. Giải mã kiểu generic với ParameterizedTypeReference

Java type erasure khiến `List<Book>.class` không tồn tại. Nếu response là một object generic như:

```json
{
  "data": [
    {"id": 1, "title": "Reactive"},
    {"id": 2, "title": "WebFlux"}
  ],
  "nextCursor": "page-2"
}
```

Tạo type reference để giữ đầy đủ thông tin kiểu:

```java
record Page<T>(List<T> data, String nextCursor) {}

ParameterizedTypeReference<Page<Book>> type =
        new ParameterizedTypeReference<>() {};

Mono<Page<Book>> page = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToMono(type);
```

Hoặc khai báo trực tiếp:

```java
Mono<Page<Book>> page = webClient.get()
        .uri("/books")
        .retrieve()
        .bodyToMono(
                new ParameterizedTypeReference<Page<Book>>() {});
```

Với Flux phát từng generic element:

```java
ParameterizedTypeReference<Map<String, Object>> rowType =
        new ParameterizedTypeReference<>() {};

Flux<Map<String, Object>> rows = webClient.get()
        .uri("/reports/rows")
        .retrieve()
        .bodyToFlux(rowType);
```

Type reference mô tả **kiểu của body hoặc từng phần tử**, tùy method:

- `bodyToMono(Page<Book>)` mô tả một Page chứa Book.
- `bodyToFlux(Map<String,Object>)` mô tả mỗi item được phát là một Map.

Không dùng `List.class` rồi cast các phần tử sang DTO. Decoder sẽ không có đủ generic type để deserialize chính xác và lỗi có thể chỉ xuất hiện ở bước cast sau đó.

## 6. Lấy status và headers bằng toEntity

`bodyToMono` và `bodyToFlux` chỉ trả body. Nếu cần status, headers hoặc `Location`, dùng `toEntity`:

```java
Mono<ResponseEntity<Book>> response = webClient.get()
        .uri("/books/42")
        .retrieve()
        .toEntity(Book.class);
```

Sau khi nhận entity:

```java
return response.map(entity -> {
    HttpStatusCode status = entity.getStatusCode();
    HttpHeaders headers = entity.getHeaders();
    Book book = entity.getBody();

    return new BookResult(status, headers.getETag(), book);
});
```

`toEntity` vẫn decode body theo codec và status error mặc định vẫn được xử lý. Dùng nó khi caller cần metadata HTTP cùng DTO.

Các lựa chọn liên quan:

| Method | Kết quả | Dùng khi |
|---|---|---|
| `bodyToMono(T.class)` | `Mono<T>` | Chỉ cần một body object |
| `bodyToFlux(T.class)` | `Flux<T>` | Chỉ cần stream item |
| `toEntity(T.class)` | `Mono<ResponseEntity<T>>` | Cần status, headers và body |
| `toEntityList(T.class)` | `Mono<ResponseEntity<List<T>>>` | Cần metadata và list đã aggregate |
| `toEntityFlux(T.class)` | `Mono<ResponseEntity<Flux<T>>>` | Cần metadata và body stream |
| `toBodilessEntity()` | `Mono<ResponseEntity<Void>>` | Cần status/headers, không cần body |

### 6.1. toEntityFlux và lifecycle body

`toEntityFlux` trả metadata response trong `Mono<ResponseEntity<Flux<T>>>`. Body vẫn là publisher; caller phải tiêu thụ nó:

```java
Mono<List<Book>> books = webClient.get()
        .uri("/books/stream")
        .retrieve()
        .toEntityFlux(Book.class)
        .flatMap(entity -> entity.getBody().collectList());
```

Nếu giữ `ResponseEntity<Flux<T>>` để trả về nơi khác, hãy bảo đảm stream được subscribe/consume đúng lifecycle. Không lấy headers rồi bỏ quên body; response content chưa tiêu thụ có thể giữ connection/resource cho tới khi được release theo contract của client.

## 7. Mặc định xử lý status 4xx và 5xx

Khi dùng `retrieve()`, Spring mặc định coi status từ 400 trở lên là lỗi. Publisher body sẽ phát `WebClientResponseException` hoặc subclass theo status, ví dụ `WebClientResponseException.NotFound`.

Ví dụ:

```java
Mono<Book> book = webClient.get()
        .uri("/books/999")
        .retrieve()
        .bodyToMono(Book.class);
```

Nếu server trả 404, `Mono<Book>` không complete empty theo mặc định. Nó phát lỗi `WebClientResponseException.NotFound`.

Có thể xử lý ở downstream:

```java
return webClient.get()
        .uri("/books/{id}", id)
        .retrieve()
        .bodyToMono(Book.class)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.empty());
```

Chỉ làm vậy nếu API contract thực sự coi 404 là “không có kết quả”. Không biến mọi lỗi 4xx/5xx thành empty vì có thể che authentication failure, rate limit, server outage hoặc lỗi contract.

### 7.1. Phân biệt HTTP error, transport error và decode error

| Nhóm | Ví dụ | Cách quan sát |
|---|---|---|
| HTTP status error | 404, 429, 500 | `WebClientResponseException` |
| Transport/request error | DNS, connect reset, TLS, timeout | Thường là `WebClientRequestException` hoặc lỗi connector |
| Decode error | JSON malformed, kiểu dữ liệu không tương thích | Codec/decoder exception, thường là `DecodingException` |
| Cancellation | Caller không còn cần response | Cancel signal; không phải HTTP status exception |

Phân loại đúng giúp retry và error mapping không bị sai. Ví dụ retry 500 có thể hợp lý theo policy, nhưng retry một JSON sai schema thường không giải quyết được vấn đề. Một request bị cancel cũng không phải lỗi để tự động retry.

## 8. Tùy biến lỗi bằng onStatus

`onStatus(predicate, exceptionFunction)` cho phép ánh xạ status response thành exception domain. Callback nhận `ClientResponse` và phải trả `Mono<? extends Throwable>`.

Ví dụ ánh xạ 404:

```java
Mono<Book> book = webClient.get()
        .uri("/books/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(ApiError.class)
                        .defaultIfEmpty(
                                new ApiError("NOT_FOUND", "Book not found"))
                        .map(BookNotFoundException::new))
        .bodyToMono(Book.class);
```

Đây là snippet cần các record/exception `ApiError` và `BookNotFoundException`. Luồng xử lý:

1. Nếu status không phải 404, xử lý tiếp theo mặc định.
2. Nếu status là 404, callback đọc error body thành `ApiError`.
3. Nếu server không gửi error body, `defaultIfEmpty` tạo một error object dự phòng.
4. `map` tạo exception domain.
5. `bodyToMono(Book.class)` không được thực hiện như một response thành công; publisher kết thúc bằng exception domain.

Ví dụ mapping mọi lỗi 5xx:

```java
.onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(body -> new RemoteServiceException(
                        response.statusCode(), body)))
```

Không đưa toàn bộ error body vào log hoặc response public nếu body có thể chứa dữ liệu nhạy cảm. Giới hạn độ dài, mask dữ liệu và ưu tiên mã lỗi ổn định.

### 8.1. Callback onStatus phải tiêu thụ error body khi cần

`ClientResponse` body là stream. Nếu cần dùng payload để tạo exception, hãy decode nó trong callback như ví dụ. Đừng đọc body nhiều lần hoặc mong downstream còn có thể decode lại cùng response body sau khi đã tiêu thụ.

Nếu error body có thể rỗng, dùng `defaultIfEmpty` khi vẫn muốn tạo exception. Nếu callback trả `Mono.empty()`, Spring không coi status đó là error và response được tiếp tục xử lý như response bình thường. Đây là cách bỏ qua status handler cho một trường hợp có chủ đích, không phải cách bỏ qua toàn bộ response.

### 8.2. Error body không phải lúc nào cũng JSON

Một upstream có thể trả JSON Problem Details, text hoặc body rỗng. Nếu callback luôn dùng `bodyToMono(ApiError.class)` nhưng server trả HTML/text, decode có thể thất bại và che mất status ban đầu.

Có thể đọc raw text khi format không ổn định:

```java
.onStatus(
        HttpStatusCode::isError,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(body -> new RemoteApiException(
                        response.statusCode(), body)))
```

Nếu API có contract Problem Details, dùng DTO phù hợp hoặc `ProblemDetail.class`. Không tự giả định mọi hệ thống 4xx/5xx đều có cùng schema.

## 9. Khi nào retrieve() không đủ?

`retrieve()` phù hợp khi cách xử lý response tương đối thống nhất: status lỗi được ánh xạ, rồi body được decode thành một kiểu.

Nếu cần quyết định kiểu body theo status, cần xem headers trước khi decode, hoặc cần nhiều nhánh response khác nhau, dùng `exchangeToMono` hoặc `exchangeToFlux`:

```java
Mono<Book> result = webClient.get()
        .uri("/books/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Book.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createError();
        });
```

Ví dụ này cố ý ánh xạ 404 thành empty và dùng `createError()` cho status còn lại. Hãy chọn semantics theo API contract.

Khác biệt lifecycle cần nhớ: với `exchangeToMono`/`exchangeToFlux`, callback phải khai báo cách xử lý body. Sau khi publisher callback hoàn tất, Spring tự release response body nếu callback chưa tiêu thụ nó. Nếu cần body, decode hoặc consume trong callback; đừng trả một response publisher tách rời mà bỏ qua ownership.

Không dùng `exchangeToMono` chỉ vì nó trông thấp tầng hơn. Với phần lớn trường hợp body đơn giản, `retrieve()` ngắn và dễ đọc hơn.

## 10. Media type và content negotiation

Client có thể yêu cầu representation bằng `Accept`:

```java
webClient.get()
        .uri("/books/stream")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Book.class);
```

Server trả `Content-Type` để xác định representation thực tế. Một số media type thường gặp:

| Media type | Ý nghĩa | Kiểu đọc thường dùng |
|---|---|---|
| `application/json` | JSON object hoặc array | `bodyToMono` / `bodyToFlux` |
| `application/x-ndjson` | Một JSON object trên mỗi dòng | `bodyToFlux` |
| `text/event-stream` | Server-Sent Events | `bodyToFlux(ServerSentEvent<T>)` |
| `text/plain` | Text | `bodyToMono(String.class)` |
| `application/octet-stream` | Binary | `byte[]` hoặc `DataBuffer` |
| `application/problem+json` | HTTP Problem Details | DTO lỗi hoặc `ProblemDetail` |

Ví dụ đọc SSE:

```java
ParameterizedTypeReference<ServerSentEvent<Book>> eventType =
        new ParameterizedTypeReference<>() {};

Flux<ServerSentEvent<Book>> events = webClient.get()
        .uri("/books/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(eventType);
```

Nếu chỉ cần data của event, có thể map `ServerSentEvent<Book>::data` sau khi decode. Tuy nhiên, nếu cần event ID, event name hoặc retry metadata, giữ nguyên `ServerSentEvent`.

Nếu `Accept` và khả năng server không giao nhau, server có thể trả 406. Nếu response `Content-Type` không có decoder phù hợp, client có thể gặp lỗi decode. Đừng sửa lỗi codec bằng cách ép mọi response thành String rồi parse thủ công nếu codec chuẩn có thể xử lý đúng.

## 11. Bộ nhớ, streaming và backpressure

`bodyToMono` thường phù hợp với body hữu hạn, đơn lẻ. `bodyToFlux` phù hợp với nhiều phần tử, nhưng không tự bảo đảm bộ nhớ luôn ổn định.

Các nguyên tắc:

- Dùng media type streaming và decoder phù hợp cho stream lớn hoặc dài.
- Tránh `collectList()` nếu số item không bị giới hạn.
- Cấu hình giới hạn bộ nhớ codec phù hợp với payload; không tăng vô hạn để che lỗi.
- Tránh `bodyToMono(String.class)` cho file lớn.
- Khi xử lý `DataBuffer` trực tiếp, tuân thủ ownership và release contract của buffer.
- Hạn chế concurrency downstream nếu mỗi item kích hoạt một request khác.
- Dùng `limitRate` hoặc operator phù hợp khi cần điều tiết demand; hiểu prefetch của operator đang dùng.
- Để cancellation truyền qua publisher; đừng gọi `subscribe()` tách rời trong service.

Ví dụ xử lý từng item:

```java
return webClient.get()
        .uri("/events")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Event.class)
        .concatMap(event ->
                eventService.process(event));
```

`concatMap` xử lý tuần tự và giữ thứ tự; nếu cần concurrency, chọn `flatMap` với giới hạn phù hợp. Đừng dùng `collectList()` chỉ để có thể gọi một vòng lặp imperative nếu nguồn có thể phát rất nhiều item.

## 12. Lỗi decode thường gặp

### 12.1. DTO không khớp JSON

Nếu JSON có field không tương thích với kiểu Java, decoder có thể phát lỗi. Kiểm tra:

- Tên field và cấu trúc nested object.
- Kiểu số, boolean, enum, timestamp.
- Constructor/record và Jackson configuration.
- Nullability và field bắt buộc.
- Version/schema của upstream.

Không map một payload lỗi thành DTO mặc định bằng cách nuốt mọi exception. Điều đó có thể khiến dữ liệu sai đi sâu vào domain.

### 12.2. Content-Type sai

Server có thể trả JSON nhưng khai báo `text/plain`, hoặc trả HTML proxy error trong khi khai báo JSON. Codec chọn decoder dựa trên media type; lỗi có thể xảy ra dù bytes trông giống JSON.

Hãy sửa contract server nếu có thể. Nếu phải tương thích upstream sai chuẩn, cô lập workaround tại adapter riêng và test nó rõ ràng.

### 12.3. Body đã bị consume

Response body là stream có thể tiêu thụ một lần. Nếu filter hoặc callback đã đọc body, downstream không thể mặc định đọc lại. Khi cần log và decode cùng body, phải thiết kế buffering/rebuild có giới hạn và quản lý memory; tốt hơn là log metadata hoặc error code đã chuẩn hóa.

## 13. Chương trình Java 17+ chạy được: retrieve, Mono, Flux và onStatus

Ví dụ dưới đây dựng một HTTP server local bằng Reactor Netty. WebClient gọi server đó để đọc một JSON object, một NDJSON stream, một response rỗng, và một response 404. Nó minh họa cả xử lý lỗi mặc định lẫn mapping lỗi thành exception riêng.

Cấu trúc:

```text
webclient-response-decode-demo/
├── pom.xml
└── src/main/java/demo/WebClientResponseDecodeDemo.java
```

### 13.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webclient-response-decode-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.2. WebClientResponseDecodeDemo.java

```java
package demo;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

import io.netty.handler.codec.http.HttpResponseStatus;

import java.util.List;

public class WebClientResponseDecodeDemo {

    public record Book(int id, String title) { }

    public record ApiError(String code, String message) { }

    public static final class RemoteApiException
            extends RuntimeException {

        private final ApiError error;

        public RemoteApiException(ApiError error) {
            super(error.code() + ": " + error.message());
            this.error = error;
        }

        public ApiError error() {
            return error;
        }
    }

    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes
                        .get("/book", (request, response) ->
                                response.header(
                                                "Content-Type",
                                                "application/json")
                                        .sendString(Mono.just(
                                                "{\"id\":42,"
                                                + "\"title\":\"Reactive WebClient\"}")))
                        .get("/books", (request, response) ->
                                response.header(
                                                "Content-Type",
                                                "application/x-ndjson")
                                        .sendString(Flux.just(
                                                "{\"id\":1,\"title\":\"Reactive\"}\n",
                                                "{\"id\":2,\"title\":\"WebFlux\"}\n")))
                        .get("/empty", (request, response) ->
                                response.status(
                                                HttpResponseStatus.NO_CONTENT)
                                        .send())
                        .get("/missing", (request, response) ->
                                response.status(
                                                HttpResponseStatus.NOT_FOUND)
                                        .header(
                                                "Content-Type",
                                                "application/json")
                                        .sendString(Mono.just(
                                                "{\"code\":\"BOOK_NOT_FOUND\","
                                                + "\"message\":\"Book not found\"}")))
                )
                .bindNow();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            Book book = client.get()
                    .uri("/book")
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .bodyToMono(Book.class)
                    .block();

            List<Book> books = client.get()
                    .uri("/books")
                    .accept(MediaType.APPLICATION_NDJSON)
                    .retrieve()
                    .bodyToFlux(Book.class)
                    .collectList()
                    .block();

            boolean emptyBody = client.get()
                    .uri("/empty")
                    .retrieve()
                    .bodyToMono(Book.class)
                    .blockOptional()
                    .isEmpty();

            try {
                client.get()
                        .uri("/missing")
                        .retrieve()
                        .bodyToMono(Book.class)
                        .block();
            }
            catch (WebClientResponseException ex) {
                System.out.println(
                        "default error status="
                        + ex.getStatusCode().value());
            }

            try {
                client.get()
                        .uri("/missing")
                        .retrieve()
                        .onStatus(
                                HttpStatusCode::is4xxClientError,
                                response -> response
                                        .bodyToMono(ApiError.class)
                                        .defaultIfEmpty(new ApiError(
                                                "UNKNOWN",
                                                "No error body"))
                                        .map(RemoteApiException::new))
                        .bodyToMono(Book.class)
                        .block();
            }
            catch (RemoteApiException ex) {
                System.out.println(
                        "mapped error=" + ex.error().code());
            }

            System.out.println(
                    "book: " + book.id() + " / " + book.title());
            System.out.println("books count=" + books.size());
            System.out.println("empty body=" + emptyBody);
        }
        finally {
            server.disposeNow();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebClientResponseDecodeDemo
```

**Standard output dự kiến:**

```text
default error status=404
mapped error=BOOK_NOT_FOUND
book: 42 / Reactive WebClient
books count=2
empty body=true
```

Giải thích:

1. Server bind port 0 để hệ điều hành chọn port trống; WebClient dùng port thực tế.
2. `/book` trả JSON object; `bodyToMono(Book.class)` giải mã thành một record.
3. `/books` trả NDJSON với hai dòng; `bodyToFlux(Book.class)` giải mã thành hai item.
4. `collectList()` chỉ được dùng trong demo vì response có đúng hai item hữu hạn; stream production lớn nên xử lý từng item.
5. `/empty` trả 204; `bodyToMono(Book.class)` complete empty nên `blockOptional()` trả Optional rỗng.
6. Lần gọi đầu tới `/missing` dùng mặc định và nhận `WebClientResponseException` với status 404.
7. Lần gọi sau dùng `onStatus`, decode error body thành `ApiError` và phát `RemoteApiException`.
8. `block()` chỉ dùng trong `main` để chương trình demo chờ kết quả. Không dùng block trong controller hoặc reactive service.

Chương trình này chạy HTTP local và dùng codec WebClient thật. Nó minh họa cách decode body và status handling; không thay thế integration test với upstream production, TLS hoặc proxy.

## 14. Kiểm thử WebClient response decoding

Nên kiểm thử cả payload lẫn tín hiệu reactive:

- JSON object được decode thành đúng DTO.
- JSON array hoặc NDJSON phát đúng số item và đúng thứ tự.
- Generic envelope giữ đúng kiểu phần tử.
- Body rỗng tạo empty publisher theo contract.
- 4xx/5xx mặc định phát WebClientResponseException.
- onStatus tạo đúng exception domain và tiêu thụ error body.
- Body sai schema phát decode error.
- Accept và Content-Type phù hợp.
- Cancellation dừng việc đọc stream khi caller không còn cần.
- Body lớn không bị aggregate ngoài dự kiến.

Ví dụ dùng StepVerifier:

```java
StepVerifier.create(
        client.get()
                .uri("/books")
                .retrieve()
                .bodyToFlux(Book.class))
        .expectNextMatches(book ->
                book.id() == 1 && book.title().equals("Reactive"))
        .expectNextMatches(book ->
                book.id() == 2 && book.title().equals("WebFlux"))
        .verifyComplete();
```

Đây là snippet cần dependency `reactor-test` và test fixture server. `StepVerifier` kiểm tra tín hiệu mà không cần `block()`.

Với HTTP client test, MockWebServer hoặc WireMock giúp kiểm tra request thực tế, header, status, body, delay và connection behavior. Fake `ExchangeFunction` phù hợp cho unit test logic nhỏ nhưng không kiểm tra socket, TLS hoặc codec/connector thật nếu bạn bỏ qua các thành phần đó.

## 15. Những lỗi thường gặp

1. **Dùng bodyToMono cho response có nhiều item.** Chọn `bodyToFlux` nếu endpoint phát nhiều object.
2. **Nghĩ Mono luôn có một giá trị.** Mono có thể complete empty; xử lý `switchIfEmpty` hoặc `defaultIfEmpty`.
3. **Nghĩ 404 tự trở thành Mono.empty().** retrieve mặc định phát `WebClientResponseException` cho status 4xx/5xx.
4. **Dùng bodyToFlux rồi collectList với stream vô hạn.** Publisher sẽ không hoàn tất và list tiếp tục tăng; xử lý từng item.
5. **Dùng List.class cho generic DTO.** Type erasure làm mất kiểu phần tử; dùng `ParameterizedTypeReference`.
6. **Nhầm Accept và Content-Type.** Accept là mong muốn của client; Content-Type mô tả response thực tế.
7. **Cho rằng Flux luôn streaming trên wire.** Codec, media type, server flush và proxy buffering đều ảnh hưởng.
8. **Không đọc error body trong onStatus.** Nếu cần error payload, decode nó trong callback trước khi response body bị giải phóng.
9. **Đọc body lỗi hai lần.** Response body là stream; thiết kế một lần tiêu thụ và chuyển dữ liệu đã decode vào exception.
10. **Trả Mono.empty từ onStatus mà tưởng bỏ response.** Điều đó bỏ xử lý error cho status ấy; body tiếp tục được xử lý như response bình thường.
11. **Bắt mọi Exception rồi trả empty.** Có thể che lỗi transport, schema và server outage.
12. **Dùng toEntity khi chỉ cần body.** Không sai nhưng tạo thêm metadata không cần thiết; chọn API theo nhu cầu.
13. **Dùng bodyToMono(String.class) cho file lớn.** Toàn bộ body có thể được aggregate; cân nhắc streaming/binary API.
14. **Không kiểm tra Content-Type.** Codec có thể không tìm thấy decoder tương thích hoặc decode sai representation.
15. **Retry tất cả decode error.** Payload sai schema thường không tự sửa được bằng retry.
16. **Block trong reactive service.** Chặn thread và phá composition/cancellation; trả Mono/Flux cho caller.
17. **Subscribe thủ công trong service.** Caller mất quyền quản lý lỗi, cancellation và lifecycle.
18. **Giữ Flux body mà không tiêu thụ.** Có thể giữ connection/resource; tiêu thụ hoặc để framework quản lý đúng lifecycle.
19. **Log nguyên error body.** Có thể lộ token, PII hoặc thông tin nội bộ; mask và giới hạn nội dung.
20. **Dùng WebTestClient để giả định đã test outbound WebClient.** WebTestClient chủ yếu kiểm thử server-side; dùng mock HTTP server hoặc ExchangeFunction cho outbound client.
21. **Coi lỗi HTTP và lỗi kết nối giống nhau.** 404 là status response; DNS/TLS/timeout là transport failure.
22. **Coi body JSON null, body rỗng và 404 là một trạng thái.** Chúng có semantics khác nhau; thiết kế mapping rõ ràng.
23. **Dùng bodyToFlux cho một object JSON duy nhất.** Nếu server chỉ phát một object, bodyToMono thường thể hiện contract rõ hơn.
24. **Không test cancellation của stream.** Client có thể ngừng tiêu thụ; kiểm tra upstream có nhận cancel và release resource đúng cách.

## 16. Checklist chọn API

Trước khi hoàn tất một lời gọi WebClient, hãy xác định:

- Response là một object, một stream hay không có body?
- Chỉ cần body hay cần cả status và headers?
- Content-Type của server có tương thích codec và kiểu Java không?
- Có generic type cần `ParameterizedTypeReference` không?
- Body có thể empty không? Empty có nghĩa hợp lệ, không tìm thấy hay vi phạm contract?
- 4xx/5xx cần dùng exception mặc định hay `onStatus`?
- Error body là JSON, Problem Details, text hay có thể rỗng?
- Có cần status-dependent decoding để dùng `exchangeToMono`/`exchangeToFlux`?
- Stream có hữu hạn không? Có vô tình aggregate bằng `collectList()`?
- Caller có thể cancel không? Response body và transport resource có được release?
- Có tránh block/subscribe trong reactive application code?
- Test có xác nhận payload, status, headers, decode error, empty và cancellation?

**Ghi nhớ:** `retrieve()` khai báo cách lấy response. `bodyToMono` giải mã tối đa một object và có thể complete empty; `bodyToFlux` giải mã một luồng phần tử. Codec dựa trên kiểu đích và media type. Status 4xx/5xx mặc định phát `WebClientResponseException`; dùng `onStatus` để ánh xạ lỗi upstream sang exception domain. Dùng `toEntity` khi cần metadata, `ParameterizedTypeReference` cho generic type, và `exchangeToMono` khi cần kiểm soát response theo status. Luôn giữ body trong reactive lifecycle và tránh aggregate stream không giới hạn.

## Tài liệu tham khảo

- Spring Framework — [retrieve(): decode response with bodyToMono and bodyToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
- Spring Framework — [WebClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Framework — [WebClient exchange and response handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html).
- Spring Framework — [WebClient request and response body codecs](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html).
- Spring Framework — [WebClient synchronous use and blocking boundaries](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html).
- Project Reactor — [Mono and Flux reference](https://projectreactor.io/docs/core/release/reference/).
