# @RequestBody với Mono/Flux và phản hồi reactive qua ResponseEntity trong Spring WebFlux

## 1. Bài toán thực tế và mục tiêu

Một HTTP API Spring WebFlux thường cần nhận JSON từ client, xử lý bất đồng bộ, rồi quyết định HTTP status, headers và body. Ba câu hỏi dễ bị lẫn là:

1. `@RequestBody Mono<NewOrder>` khác `@RequestBody NewOrder` ở cách đọc và xử lý body như thế nào?
2. `@RequestBody Flux<Event>` có nghĩa "đọc cả một JSON array" hay "xử lý từng bản ghi trong stream"?
3. `ResponseEntity<Mono<Order>>`, `Mono<ResponseEntity<Order>>` và `ResponseEntity<Flux<Order>>` khác nhau thế nào về **thời điểm biết HTTP status/headers**, việc ghi body, streaming và lỗi?

Nếu chỉ nhìn thấy chữ `Mono` hoặc `Flux` rồi kết luận mọi thao tác là non-blocking, API rất dễ gặp lỗi: block event loop, trả HTTP 200 trước khi biết resource có tồn tại, decode sai Content-Type, ghi response khi headers đã commit, hoặc giữ quá nhiều dữ liệu trong RAM.

**Phạm vi:** Controller annotation của **Spring WebFlux 6.1.x**, **Java 17** và **Spring Boot 3.3.5**. Đây là bài thuộc nhóm **Controller WebFlux**, không phải Spring MVC Servlet. Ta dùng package `org.springframework.web.bind.annotation` cho `@RequestBody`, Reactor `reactor.core.publisher.Mono`/`Flux`, `ResponseEntity` từ Spring HTTP, HTTP codecs của WebFlux và `WebTestClient`.

### Kết quả học tập

Sau bài, bạn có thể:

- Đọc body reactive bằng `@RequestBody Mono<T>`/`Flux<T>` và biết khi nào dùng DTO trực tiếp.
- Hiểu role `HttpMessageReader`, Jackson decoder, `DataBuffer`, backpressure và request body one-shot.
- Phân biệt `application/json`, `application/x-ndjson` và các chuẩn streaming JSON.
- Chọn đúng một trong các kiểu response `ResponseEntity<T>`, `Mono<T>`, `ResponseEntity<Mono<T>>`, `ResponseEntity<Flux<T>>`, `Mono<ResponseEntity<T>>` và `Mono<ResponseEntity<Flux<T>>>`.
- Tạo HTTP 201 + `Location` sau khi lưu thành công, hoặc trả 404 đúng khi không tìm thấy.
- Dùng `@Valid` với body reactive và nhận biết `WebExchangeBindException`.
- Không vô tình nuốt lỗi bằng `onErrorResume`, không làm sai HTTP 4xx/5xx và không rò rỉ dữ liệu.
- Xây ứng dụng Boot WebFlux với JSON POST, NDJSON batch input, dynamic status và output reactive, kèm WebTestClient tests.
- Xác định ranh giới về cancellation, buffering, timeout, streaming response commit, Spring Security và persistence.

## 2. Hai hướng dữ liệu của một HTTP exchange

Một endpoint có hai pipelines độc lập nhưng phối hợp:

```text
HTTP request bytes
       |
       v
Reactive HTTP server adapter (Reactor Netty...)
       |
       v
ServerHttpRequest.getBody() : Flux<DataBuffer>
       |
       v
HttpMessageReader + Decoder (ví dụ Jackson JSON)
       |
       +--> @RequestBody Mono<DTO> (0..1 DTO)
       |
       +--> @RequestBody Flux<DTO> (0..N DTOs)
       |
       v
Controller -> service -> Mono/Flux result
       |
       v
HandlerResultHandler / HttpMessageWriter + Encoder
       |
       v
ServerHttpResponse headers/status + body publisher
       |
       v
HTTP client
```

`@RequestBody` không tự đọc bytes bằng `InputStream`/`HttpServletRequest` như trong Servlet MVC. WebFlux nhận body bằng `Publisher<DataBuffer>` và decode thông qua `HttpMessageReader` phù hợp với Content-Type.

Điểm quan trọng:

- **Request body** thuộc HTTP exchange, thông thường được consume **một lần**. Không tự subscribe `exchange.getRequest().getBody()` ở filter rồi để controller đọc tiếp.
- **Mono<T>** có tối đa một phần tử, có thể complete empty hoặc error.
- **Flux<T>** có từ 0 đến nhiều phần tử, có thể complete hoặc chạy lâu tùy source.
- **Reactive I/O** nghĩa kết hợp publisher/demand/cancellation đúng; không phải chỉ thay tên kiểu Java.
- Khi trả response, status/headers và publisher body có những thời điểm quyết định khác nhau. Đây là lý do có nhiều dạng `ResponseEntity` chứa publisher.

## 3. @RequestBody DTO trực tiếp, Mono<T>, Flux<T>

### 3.1. DTO trực tiếp

```java
@PostMapping("/items")
public Mono<Item> create(@RequestBody NewItem input) {
    return store.create(input);
}
```

Đoạn này là snippet, `Item`/`NewItem`/`store` sẽ được định nghĩa đầy đủ trong project bên dưới. Với tham số `NewItem` trực tiếp, WebFlux phải decode body trước khi gọi method controller. Kiểu trả về reactive vẫn có thể áp dụng cho phần xử lý sau đó.

Cách viết này tiện cho request nhỏ có một object và cần binding/validation theo annotated controller. Nó **không** tự biến toàn bộ hoạt động đọc body sang "blocking". WebFlux codec vẫn đọc request theo cơ chế reactive; method argument resolution cung cấp DTO sau khi decode.

### 3.2. @RequestBody Mono<T>

```java
@PostMapping("/items")
public Mono<Item> create(
        @RequestBody Mono<NewItem> incoming) {
    return incoming.flatMap(store::create);
}
```

Lúc controller method nhận `incoming`, đó là một `Mono<NewItem>` mô tả việc decode body. Method chủ động ghép các bước bằng `map`/`flatMap` và **trả publisher cho framework subscribe**.

- `flatMap` là phù hợp khi `store.create` trả `Mono<Item>`.
- Nếu `store.create` là method đồng bộ trả `Item`, `map(store::createSync)` có thể dùng, nhưng blocking call trong `map` vẫn có thể block event loop.
- Không gọi `incoming.block()` để lấy `NewItem` rồi mới xử lý.
- Không gọi `incoming.subscribe()` rồi trả một Mono khác, vì có thể làm body được consume ngoài lifecycle của HTTP request.

`Mono<NewItem>` không có nghĩa có một extra HTTP request hay một thread riêng đang chờ. Nó chỉ là cách biểu diễn result của quá trình decode.

### 3.3. @RequestBody Flux<T>

```java
@PostMapping(path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Long> accept(@RequestBody Flux<Event> events) {
    return events
            .flatMap(eventStore::save)
            .count();
}
```

Đây là snippet có `Event`, `eventStore` giả định. NDJSON (`application/x-ndjson`) đưa **một JSON value trên một dòng**, cho phép decoder tạo từng phần tử trong Flux từ request body stream khi hỗ trợ media type.

`Flux<Event>` không phải là yêu cầu framework lưu toàn bộ dữ liệu vào một `List<Event>` rồi mới gọi handler. Với Content-Type streaming phù hợp, decoder có thể phát nhiều `Event` qua thời gian theo dữ liệu đến. Tuy vậy, các buffers, codecs, `flatMap` concurrency, client/proxy và serialization có thể ảnh hưởng mức streaming/backpressure thực tế.

**Không dùng `Flux<T>` như bảo đảm rằng mọi dạng JSON đều phát từng object ngay lập tức.** Một JSON array `[{"x":1},{"x":2}]` với `application/json` có semantics khác NDJSON lines; decoder/content negotiation quyết định cách phát elements và flush. Nếu contract là NDJSON, khai báo Content-Type NDJSON và test bytes/wire format thật.

## 4. application/json vs application/x-ndjson

### JSON object

```http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":"Sách Spring"}
```

Đây là một document JSON duy nhất. `@RequestBody Mono<NewItem>` thường là lựa chọn tự nhiên.

### JSON array

```http
POST /api/items/batch HTTP/1.1
Content-Type: application/json

[{"name":"A"},{"name":"B"}]
```

Nếu business operation cần toàn bộ list/transactional validation, có thể dùng `@RequestBody Mono<List<NewItem>>` hoặc một DTO wrapper, với giới hạn max size. Dùng Flux với JSON array tùy codec semantics nhưng **đừng đồng nhất** với line-delimited streaming.

### NDJSON

```http
POST /api/items/batch HTTP/1.1
Content-Type: application/x-ndjson

{"name":"A"}
{"name":"B"}
```

NDJSON có mỗi dòng một JSON object, thường thuận lợi cho streaming và backpressure. Đường response `application/x-ndjson` cũng cho phép server ghi các JSON objects thành từng dòng; khác với `application/json` thường là một JSON array/document hợp lệ.

Trong Spring, `MediaType.APPLICATION_NDJSON` và `MediaType.APPLICATION_NDJSON_VALUE` đại diện media type NDJSON. `application/stream+json` là media type từng được dùng trong hệ sinh thái Spring, nhưng với API mới nên ưu tiên NDJSON khi client/server đồng ý.

### Khi nào không nên stream?

- Cần transaction "tất cả thành công hoặc không gì cả".
- Cần validate toàn batch trước khi ghi dữ liệu.
- Cần biết tổng record count và trả status cuối.
- Client/proxy phải có response JSON document duy nhất.
- Có giới hạn bộ nhớ và độ phức tạp thích hợp cho dữ liệu nhỏ.

Khi batch có vài chục items, decode thành list giới hạn có thể đơn giản hơn streaming. Streaming có giá trị khi tránh giữ toàn bộ payload, xử lý incremental/cancellation và client cần nhận phần tử sớm.

## 5. HttpMessageReader, Decoder và lỗi body

WebFlux `@RequestBody` dùng `HttpMessageReader` và `Decoder` từ cấu hình codecs; mặc định Boot WebFlux với Jackson đọc JSON thành record/DTO. Dựa vào `Content-Type`, framework chọn reader hỗ trợ type và media type.

Các lỗi cần phân biệt:

| Tình huống | Ý nghĩa |
| --- | --- |
| JSON malformed | Không decode được body; thông thường 400 |
| `Content-Type: text/plain` nhưng handler đợi JSON | Có thể bị 415 Unsupported Media Type |
| Body required nhưng empty | Có thể 400 khi `@RequestBody(required=true)` áp dụng |
| DTO thiếu field bắt buộc theo Bean Validation | 400 nếu có `@Valid`/validation phù hợp |
| DTO đọc được nhưng business resource không tồn tại | 404 theo business/response mapping |
| Body quá lớn | Có thể gặp codec buffer limit hoặc 413 policy |
| Client disconnect | Cancellation/network errors; không nhất thiết tạo JSON response |
| Decoder gặp lỗi giữa NDJSON stream | Publisher phát error, có thể ngừng đọc các phần còn lại |

Không mặc định exact exception class cho mọi lỗi decode; `ServerWebInputException` và các subclasses/converter exceptions có thể xuất hiện tùy Spring configuration. Bean Validation cho annotated `@RequestBody` thường báo `WebExchangeBindException`. Nếu có method-level validation do constraints trực tiếp trên parameters, có thể gặp `HandlerMethodValidationException`.

## 6. Bean Validation với Mono<T>/Flux<T>

Giả sử:

```java
public record NewItem(
        @NotBlank
        @Size(max = 80)
        String name) {}
```

Trên controller WebFlux, có thể dùng:

```java
@PostMapping
public Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<NewItem> request) {
    return request
            .flatMap(store::create)
            .map(item -> ResponseEntity
                    .created(URI.create("/api/items/" + item.id()))
                    .body(item));
}
```

Đây là snippet cần Java record, store và imports, được viết đầy đủ ở mục 13.

- `@Valid` chỉ yêu cầu kiểm tra constraints nested object; nó **không** là một constraint như `@NotBlank`.
- Với `Mono<NewItem>`, validation có thể phát error **trong Mono** khi giá trị được decode. Spring MVC/WebFlux argument-resolution khác nhau nên đừng dùng tên exception của Servlet MVC thay vì WebFlux.
- Lỗi validation thường được chuyển thành **HTTP 400 Bad Request**, trừ khi bạn thay mapping.
- Nếu bạn thêm constraints trực tiếp trên method parameters (ví dụ `@Min` cho numeric query argument) trong Spring 6.1, method validation có thể phát `HandlerMethodValidationException`.
- Với `Flux<NewItem>`, chú ý từng phần tử của streaming body và khả năng lỗi xảy ra **sau khi response bắt đầu**. Với streaming output, không bảo đảm có thể sửa status thành 400 khi đã commit một phần.

**Không xử lý validation bằng cách gọi `block()`.** Nếu muốn phản hồi error schema tùy chỉnh, sử dụng `@RestControllerAdvice`/`@ExceptionHandler` hoặc error operators **bên trong reactive chain** với scope và exception class chính xác.

### @Valid không thay thế business validation

Tên không rỗng chưa chứng minh người dùng được quyền tạo resource, không bị spam và không chứa domain value ngoài policy. Xác thực quyền, idempotency, rate limit, uniqueness, input length và SQL injection defense cần triển khai riêng tại service/persistence/security boundaries.

## 7. ResponseEntity<T> nghĩa là gì trong WebFlux?

`ResponseEntity<T>` chứa:
- HTTP status code.
- Headers như `Location`, `ETag`, `Cache-Control`, `Content-Type`, `X-Request-ID`.
- Body `T` (có thể là publisher).

`@RestController` trả DTO trực tiếp thường ngụ ý status 200. Khi cần 201, 202, 204, 404 hoặc header cụ thể, dùng `ResponseEntity`.

```java
return ResponseEntity
        .status(HttpStatus.CREATED)
        .location(URI.create("/api/items/42"))
        .body(new Item(42, "Java"));
```

Đây là snippet có record `Item` đã định nghĩa. Nó đặt status/headers trước khi body được serialize.

Trong WebFlux, `ResponseEntity` có thể bao publishers; **vị trí của Mono/Flux bên trong hay bên ngoài ResponseEntity quyết định thời điểm status/headers được biết**.

## 8. Bốn mẫu ResponseEntity reactive quan trọng nhất

### 8.1. ResponseEntity<Mono<T>>

```java
public ResponseEntity<Mono<Item>> accepted() {
    Mono<Item> body = service.computeLater();
    return ResponseEntity.accepted()
            .header("X-Mode", "body-later")
            .body(body);
}
```

Snippet này chưa runnable vì `service` giả định. Tại lúc method return, **status 202 và X-Mode đã được xác định**. `body` vẫn là publisher có thể phát item hoặc error sau.

Phù hợp khi:
- HTTP status/header chắc chắn ngay khi tạo response.
- Kết quả body có thể sẵn sàng sau.
- Body có tối đa một phần tử.

**Bẫy quan trọng:** Nếu `body` complete empty, status ban đầu vẫn là 202; không tự biến thành 404. Nếu bạn cần status 404 khi resource không có, nên chờ lookup rồi trả `Mono<ResponseEntity<Item>>`.

### 8.2. ResponseEntity<Flux<T>>

```java
public ResponseEntity<Flux<Item>> stream() {
    Flux<Item> body = service.streamItems();
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(body);
}
```

Status 200 và Content-Type được chọn **trước**, body phát nhiều items sau. Với NDJSON, client có thể nhận từng JSON line theo nhịp body publisher, tùy buffering/transport.

Khi cần JSON array thông thường, `ResponseEntity<Flux<Item>>` + `application/json` vẫn có thể là lựa chọn. Codec có thể serialize Flux thành một array và flush khác NDJSON. Đừng giả định cứ là `Flux` sẽ có mỗi item là một HTTP chunk; chunk boundaries không phải record boundaries.

### 8.3. Mono<ResponseEntity<T>>

```java
public Mono<ResponseEntity<Item>> find(long id) {
    return repository.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Đây là snippet, `repository.find(id)` trả `Mono<Item>`. **ResponseEntity được tạo sau kết quả lookup**:

- Có item → HTTP 200 và JSON body.
- Empty → HTTP 404 không body.

Ở đây HTTP status **phụ thuộc** vào kết quả asynchronous. Đây thường là lựa chọn đúng cho GET resource đơn lẻ, lookup/permission decisions, tạo resource có thể thất bại, conditional response và business conflict.

### 8.4. Mono<ResponseEntity<Flux<T>>>

```java
public Mono<ResponseEntity<Flux<Item>>> export() {
    return permissionService.check()
            .map(allowed -> {
                if (!allowed) {
                    return ResponseEntity
                            .status(HttpStatus.FORBIDDEN)
                            .<Flux<Item>>build();
                }
                return ResponseEntity.ok()
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(service.streamItems());
            });
}
```

Snippet với `permissionService`/`service` giả định. **Hai giai đoạn bất đồng bộ:**
1. Mono ngoài quyết định status/headers sau một check async.
2. Flux bên trong cung cấp body sau khi response được chọn.

Phù hợp khi **quyền/status/header phụ thuộc I/O async**, nhưng payload có nhiều phần tử streaming. Không tự thay thế Spring Security/service authorization thật chỉ bằng một check minh họa.

### Bảng tóm tắt

| Kiểu return | Biết status/headers khi nào? | Body | Dùng khi |
| --- | --- | --- | --- |
| `ResponseEntity<T>` | Ngay khi return | Một object/value | Kết quả/status đã sẵn |
| `Mono<T>` | Thường response 200 mặc định, có handling khác | 0..1 value | Không cần status/header tùy điều kiện |
| `Flux<T>` | Thường response 200 mặc định, có handling khác | 0..N values | Danh sách/stream |
| `ResponseEntity<Mono<T>>` | **Trước khi Mono body phát** | 0..1 reactive | Status/header xác định sớm |
| `ResponseEntity<Flux<T>>` | **Trước Flux body phát** | 0..N reactive | Status/header xác định sớm, stream/list |
| `Mono<ResponseEntity<T>>` | **Sau khi Mono ngoài phát** | Một DTO hoặc empty | Status phụ thuộc lookup/async result |
| `Mono<ResponseEntity<Flux<T>>>` | **Sau Mono ngoài, trước Flux body** | Stream sau khi xác thực/chọn status | Quyết định envelope async, body streaming |

**Lưu ý:** "biết status sớm" nói về thời điểm phần mềm đã **chọn status/header**, không khẳng định bytes header đã được gửi qua socket ngay lúc Java method return. HTTP response thường chỉ commit khi body write/complete; thời điểm thực phụ thuộc server, codec và flow.

## 9. Mono.empty(), Flux.empty() và HTTP status

Một lỗi contract thường gặp:

```java
@GetMapping("/{id}")
public ResponseEntity<Mono<Item>> wrong(@PathVariable long id) {
    return ResponseEntity.ok().body(repository.find(id));
}
```

Nếu repository không tìm được item, `Mono.empty()` không tự sinh 404. Response được chọn 200 ngay.

Đúng hơn:

```java
@GetMapping("/{id}")
public Mono<ResponseEntity<Item>> correct(@PathVariable long id) {
    return repository.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Tương tự:
- `Flux.empty()` + 200 là response danh sách rỗng, thường hợp lệ.
- `Mono.empty()` + 204 có thể phù hợp hành động không có body, nhưng phải **chủ động** chọn 204 nếu contract cần.
- `Mono.error(ex)` đi vào reactive error handling; HTTP status phụ thuộc exception resolvers và response commit.
- `onErrorReturn(defaultValue)` có thể che business error, chuyển 5xx thành 200 vô ý nếu không thiết kế.

Không lẫn "Publisher không có phần tử" với "resource không tồn tại" hoặc "user không có quyền".

## 10. HTTP status, Location, Cache-Control và ETag

### 201 Created

Khi POST tạo item thành công, REST contract thường trả:
- `201 Created`.
- `Location: /api/items/42` trỏ tới item mới.
- Body DTO được server tạo, chứa server-owned ID.

Với body reactive:

```java
return body.flatMap(store::create)
        .map(created -> ResponseEntity
                .created(URI.create("/api/items/" + created.id()))
                .body(created));
```

Ở đây Status và Location chỉ được chọn **sau khi create Mono phát thành công**. Nếu create thất bại, không gửi 201 sai.

### 202 Accepted

`202 Accepted` cho biết request được chấp nhận để xử lý nhưng chưa hoàn tất; nếu thực sự có background job thì nên trả job ID/status URL phù hợp. **Đừng** chỉ đặt 202 vì body là Mono và mất vài milliseconds. Một `Mono` hoàn thành trong cùng HTTP request vẫn có thể trả 200/201 bình thường.

### 204 No Content

`ResponseEntity.noContent().build()` tạo 204. Theo HTTP semantics, không gửi body. Đừng gắn `Flux<Item>` body vào 204 rồi kỳ vọng client đọc được stream.

### Cache headers

`ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(...)` hữu ích khi body nhạy cảm; cache policy áp cho response độc lập với Mono/Flux. Nếu danh sách là user-specific, tránh public shared cache làm leak dữ liệu. ETag/conditional GET cần value ổn định và status 304 đúng trước khi body commit; không tạo ETag từ một stream chưa hoàn thành mà không tính chi phí/bộ đệm.

### Response already committed

Với NDJSON:
- Status/header được commit khi bắt đầu response.
- Item thứ ba mới lỗi, trong khi hai dòng đã tới client.
- Server **không bảo đảm** có thể đổi 200 thành 500 ProblemDetail hoặc 400 validation body.
- Client phải biết chính sách incomplete stream/retry/idempotency và giới hạn tác dụng phụ.

Vì vậy nếu cần atomic batch validation và error status cuối, thường phải **hoàn tất kiểm tra trước khi commit** thay vì trả một Flux output ngay.

## 11. Reactive streams, backpressure và serialization

WebFlux dùng Reactive Streams để điều khiển demand từ consumer, không phải bắt mỗi request thread ngủ đợi network.

- `Mono.just(dto)` phát một item khi subscribed.
- `Flux.fromIterable(items)` phát nhiều items.
- `flatMap` có thể cho concurrency và thay đổi ordering; `concatMap` giữ thứ tự tuần tự.
- `collectList()` gom toàn bộ Flux vào bộ nhớ; không phù hợp với input vô hạn hoặc body không giới hạn.
- `buffer(n)` tạo nhóm, cũng tăng memory usage.
- `take(n)` lấy tối đa n items và hủy upstream khi đủ, nhưng nếu dùng sai có thể lặng lẽ bỏ phần còn lại.
- `doOnCancel`/`doFinally` hỗ trợ cleanup khi client disconnect/response cancel.

**Backpressure chỉ hữu ích end-to-end** khi source, decoder, persistence client và HTTP writer cùng tôn trọng demand. Nếu trong controller gọi JDBC đồng bộ hoặc tạo `Flux.create` đẩy vô hạn không bound, việc dùng Flux không cứu hệ thống khỏi nghẽn thread/bộ nhớ.

### Blocking code trong map/flatMap

```java
// PHẢN VÍ DỤ: JDBC blocking trên event loop.
return incoming.map(dto ->
        jdbcRepository.save(dto));
```

Trong WebFlux Netty, operator có thể chạy trên event loop. JDBC đồng bộ có thể block event-loop, kéo chậm nhiều connections khác.

Phương án tạm khi phải dùng blocking dependency:

```java
return incoming.flatMap(dto ->
        Mono.fromCallable(() -> jdbcRepository.save(dto))
                .subscribeOn(Schedulers.boundedElastic()));
```

Đây là snippet với `jdbcRepository` và `Schedulers` imports giả định. `boundedElastic` **chuyển blocking sang bounded workers**, không biến JDBC thành non-blocking driver. Với database thật, cân nhắc R2DBC/non-blocking client phù hợp, quản lý transaction, pool, timeout và backpressure.

## 12. Thiết kế batch NDJSON an toàn

Một `@RequestBody Flux<NewItem>` có thể nhận hàng nghìn JSON lines. Nếu dùng:

```java
return requests.collectList()
        .flatMap(store::saveBatch);
```

không giới hạn kích thước, client có thể đẩy vô hạn làm server tích tụ RAM.

Với một API hỗ trợ tối đa 100 items/batch:
- Chỉ nhận tối đa **101** entries để phát hiện batch quá lớn, sau đó báo lỗi.
- Kiểm tra constraints từng entry trước khi ghi.
- Tạo danh sách kết quả khi tất cả hợp lệ.
- Trả `Mono<ResponseEntity<List<Item>>>` **sau khi** hoàn tất batch.
- Triển khai DB transaction nếu contract yêu cầu all-or-nothing.
- Giới hạn request bytes và connection timeouts ở proxy/runtime vì giới hạn record count không bảo vệ khỏi **một record rất lớn**.

Ví dụ:

```java
return items.take(101)
        .collectList()
        .flatMap(list -> {
            if (list.size() > 100) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "At most 100 items"));
            }
            return store.saveBatch(list);
        });
```

Snippet này trả kiểu do `store.saveBatch` xác định; project đầy đủ ở mục 13 sẽ trả `Mono<ResponseEntity<List<Item>>>`. Khi nguồn có 101 items, `take(101)` đã đủ để phát hiện quá giới hạn, không **âm thầm chấp nhận** 100 đầu. Khi nguồn có nhiều hơn 101, subscription cancel phần sau theo reactive contract. Với HTTP keep-alive/upload streaming, kiểm tra policy drain/cancel connection của server/client khi request bị từ chối sớm.

**Atomicity:** `collectList()` không tạo DB transaction. Nếu code lưu từng item rồi lỗi ở item cuối, các items trước có thể đã được ghi. Demo sẽ có validation trước khi gọi service, và production phải chọn transactional database service nếu cần atomic batch.

## 13. Dự án Maven chạy được: JSON Mono, Flux NDJSON, ResponseEntity

Ứng dụng minh họa:

- `POST /api/items` nhận `@Valid @RequestBody Mono<NewItem>` và trả `Mono<ResponseEntity<Item>>` với 201 + Location sau khi lưu.
- `GET /api/items/{id}` trả `Mono<ResponseEntity<Item>>` chọn 200/404 theo lookup.
- `GET /api/items/accepted` trả `ResponseEntity<Mono<StatusMessage>>` với status/header biết sớm, body phát sau.
- `GET /api/items` trả `ResponseEntity<Flux<Item>>` với `application/json` để tạo một JSON array.
- `GET /api/items/stream` trả `ResponseEntity<Flux<Item>>` với `application/x-ndjson` để stream từng item.
- `POST /api/items/batch` nhận `@Valid @RequestBody Flux<NewItem>` dạng NDJSON, giới hạn 100 items, trả `Mono<ResponseEntity<List<Item>>>`.
- `@RestControllerAdvice` dùng một error body cố định cho `WebExchangeBindException`.
- Tests `WebTestClient` xác minh headers/status/JSON/NDJSON/validation và batch limit.

Dữ liệu nằm trong RAM. Không có database, Spring Security hoặc transaction thực; dùng store để tập trung vào HTTP reactive semantics.

### 13.1. Cây tệp

```text
webflux-body-response-demo/
├── pom.xml
└── src/
    ├── main/java/example/bodyresponse/
    │   ├── BodyResponseApplication.java
    │   ├── NewItem.java
    │   ├── Item.java
    │   ├── StatusMessage.java
    │   ├── ApiError.java
    │   ├── ItemStore.java
    │   ├── ItemController.java
    │   └── ApiErrors.java
    └── test/java/example/bodyresponse/
        └── ItemControllerTest.java
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
    <artifactId>webflux-body-response-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

Chỉ thêm `spring-boot-starter-webflux` (không `spring-boot-starter-web`) để ứng dụng dùng WebFlux reactor stack như bài học. Có Jackson qua WebFlux starter và Jakarta Bean Validation qua validation starter. WebTestClient có trong starter-test.

### 13.3. Spring Boot application

**`src/main/java/example/bodyresponse/BodyResponseApplication.java`**

```java
package example.bodyresponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyResponseApplication.class, args);
    }
}
```

### 13.4. DTOs và response record

**`src/main/java/example/bodyresponse/NewItem.java`**

```java
package example.bodyresponse;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewItem(
        @NotBlank
        @Size(max = 80)
        String name) {}
```

**`src/main/java/example/bodyresponse/Item.java`**

```java
package example.bodyresponse;

public record Item(long id, String name) {}
```

**`src/main/java/example/bodyresponse/StatusMessage.java`**

```java
package example.bodyresponse;

public record StatusMessage(String state) {}
```

**`src/main/java/example/bodyresponse/ApiError.java`**

```java
package example.bodyresponse;

public record ApiError(String code) {}
```

Các record dùng Java 17, được Jackson serialize/deserialize. `@NotBlank` kiểm tra null/empty/whitespace; `@Size(max=80)` chỉ kiểm tra độ dài string. Đó là **DTO validation**, chưa phải authorization hoặc SQL/input safety.

### 13.5. Store dùng RAM, API trả Mono/Flux

**`src/main/java/example/bodyresponse/ItemStore.java`**

```java
package example.bodyresponse;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ItemStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentHashMap<Long, Item> data =
            new ConcurrentHashMap<>();

    private Item save(NewItem input) {
        long id = sequence.incrementAndGet();
        Item item = new Item(id, input.name().strip());
        data.put(id, item);
        return item;
    }

    public Mono<Item> create(NewItem input) {
        return Mono.fromSupplier(() -> save(input));
    }

    public Mono<Item> find(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(data.get(id)));
    }

    public Flux<Item> all() {
        return Flux.defer(() -> {
            List<Item> snapshot =
                    new ArrayList<>(data.values());
            snapshot.sort(Comparator.comparingLong(Item::id));
            return Flux.fromIterable(snapshot);
        });
    }

    public Mono<List<Item>> saveBatch(List<NewItem> input) {
        return Mono.fromSupplier(() -> {
            List<Item> saved = new ArrayList<>();
            for (NewItem draft : input) {
                saved.add(save(draft));
            }
            return List.copyOf(saved);
        });
    }
}
```

**Điều cần hiểu:**

1. `Mono.fromSupplier` thực hiện `save` khi Publisher được subscribe, không phải lúc controller tạo Mono.
2. `Mono.defer` chỉ tra Map khi subscribe, hữu ích để quan sát trạng thái mới trong tests.
3. `Flux.defer` tạo snapshot list lúc subscribe và phát items theo thứ tự ID.
4. Không có JDBC/file/network blocking nên các thao tác ngắn trong memory chạy trên event loop không gây wait I/O; nhưng trong app thật dùng blocking DB driver phải offload hoặc chọn reactive data client.
5. `ConcurrentHashMap` và `AtomicLong` giúp demo không hỏng do đồng thời cơ bản, **không thay DB transaction**.
6. `saveBatch` có thể để lại partial writes nếu giữa chừng gặp unexpected runtime failure; production cần transaction/idempotency nếu contract đòi atomicity.
7. Store là Spring `@Service`, tách khỏi HTTP controller để dễ test/business reuse.
8. Không dùng `Thread.sleep` để giả lập non-blocking latency.

### 13.6. REST controller: sáu endpoints minh họa

**`src/main/java/example/bodyresponse/ItemController.java`**

```java
package example.bodyresponse;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemStore store;

    public ItemController(ItemStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Item>> create(
            @Valid @RequestBody Mono<NewItem> request) {

        return request.flatMap(store::create)
                .map(item -> ResponseEntity
                        .created(URI.create(
                                "/api/items/" + item.id()))
                        .body(item));
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Item>> find(
            @PathVariable long id) {

        return store.find(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.notFound().build());
    }

    @GetMapping("/accepted")
    public ResponseEntity<Mono<StatusMessage>> accepted() {
        Mono<StatusMessage> body =
                Mono.just(new StatusMessage("queued"))
                        .delayElement(Duration.ofMillis(10));

        return ResponseEntity.accepted()
                .header("X-Body-Mode", "mono")
                .body(body);
    }

    @GetMapping
    public ResponseEntity<Flux<Item>> list() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    @GetMapping(
            path = "/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<Item>> stream() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(store.all());
    }

    @PostMapping(
            path = "/batch",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<List<Item>>> batch(
            @Valid @RequestBody Flux<NewItem> incoming) {

        return incoming.take(101)
                .collectList()
                .flatMap(drafts -> {
                    if (drafts.size() > 100) {
                        return Mono.error(
                                new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "At most 100 items"));
                    }
                    return store.saveBatch(drafts);
                })
                .map(saved -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(saved));
    }
}
```

### Tại sao mỗi method return kiểu khác nhau?

- **`create`**: chưa biết được `201 Location` cho tới khi item đã được tạo, nên return `Mono<ResponseEntity<Item>>`.
- **`find`**: phải quyết định giữa 200/404 theo `Mono<Item>`, nên cũng return `Mono<ResponseEntity<Item>>`.
- **`accepted`**: status 202 và `X-Body-Mode` đã cố định; body là `Mono<StatusMessage>` có thể phát trễ.
- **`list`**: status/header biết ngay, `Flux<Item>` được serialize thành JSON response thông thường.
- **`stream`**: status/header biết ngay, nhưng Flux được encode theo NDJSON media type, cho phép nhiều JSON lines.
- **`batch`**: NDJSON là input Flux, nhưng ta muốn **biết batch hợp lệ và lưu xong** mới chọn 201, nên return `Mono<ResponseEntity<List<Item>>>`.

**Sáu endpoints này đủ để thấy** vị trí Mono/Flux trong type signature phản ánh business response semantics chứ không chỉ phong cách lập trình.

### Vì sao batch giới hạn 101?

Nếu dùng `incoming.take(100)` rồi lưu, một request có 101 lines có thể bị lặng lẽ bỏ phần tử 101 nhưng vẫn báo thành công. `take(101)` cho phép nhìn thấy phần tử thứ 101 và **từ chối** toàn batch (trước khi gọi `saveBatch`) khi quá giới hạn 100.

Bản demo giới hạn số records; production còn phải đặt max body bytes, max JSON nesting, per-record size, connection timeouts, rate limits và cancellation cleanup. Không giả định `collectList()` an toàn cho input vô hạn.

### Validation trong batch

`@Valid @RequestBody Flux<NewItem>` cho phép validation của từng DTO phát hiện constraint violations qua reactive body handling. Với batch đang gom trước khi ghi, lỗi validation sẽ khiến Publisher fail và `store.saveBatch` không được gọi. Nhưng với một hệ thống streaming handler thực sự lưu từng item ngay khi đọc, các items trước lỗi có thể đã tồn tại; khi cần atomicity phải định nghĩa transaction/compensation policy.

## 14. Error handler riêng cho validation

**`src/main/java/example/bodyresponse/ApiErrors.java`**

```java
package example.bodyresponse;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> invalidBody(
            WebExchangeBindException error) {
        return ResponseEntity.badRequest()
                .body(new ApiError("invalid_item"));
    }
}
```

Điểm cần phân biệt:

- `WebExchangeBindException` là lỗi binding/validation trong **WebFlux**, khác `MethodArgumentNotValidException` ở Servlet MVC.
- Body trả client chỉ chứa code ổn định, không leak rejected values, exception stack hoặc internal validation messages.
- Đây chỉ xử lý `WebExchangeBindException`; JSON malformed, `HandlerMethodValidationException`, request size, authorization hay downstream exception còn cần error policy riêng.
- `@RestControllerAdvice` xử lý lỗi trong annotated controller pipeline; `WebExceptionHandler` là abstraction ở outer WebHandler chain, có scope/ordering khác. Không cần tự viết low-level WebExceptionHandler chỉ để map một lỗi validation thông thường.
- Không bắt `Throwable` rồi trả 400 cho mọi thứ; có thể che 500, bỏ qua cancellation hoặc rò rỉ thông tin.

## 15. Chạy Maven và gửi request thật

Cài **JDK 17+** và Maven. Từ thư mục `webflux-body-response-demo` chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Đây là hai lệnh **chạy tuần tự**. Với Boot default, app nghe tại `http://localhost:8080`; server khác/proxy khác có thể thay URL/port.

### 15.1. POST một JSON object, nhận 201 + Location

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Spring WebFlux"}'
```

Dự kiến (JVM vừa khởi động, chưa có dữ liệu):

```http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json

{"id":1,"name":"Spring WebFlux"}
```

`Location` là URI reference tương đối trỏ tới GET endpoint trên cùng origin. Nó không phụ thuộc request Host header chưa được kiểm chứng. Nếu public client cần absolute URL, cấu hình trusted external base/forwarded-header policy đúng; đừng nối raw Host thành redirect.

### 15.2. GET có hoặc không tồn tại

```bash
curl -i 'http://localhost:8080/api/items/1'
curl -i 'http://localhost:8080/api/items/999999'
```

Lần đầu sau POST trả 200 và JSON Item; lần thứ hai trả **404 Not Found** không có item. Status 404 đến từ `Mono<ResponseEntity<Item>>` sau khi `store.find(id)` complete empty, không phải vì body Mono tự sinh 404.

### 15.3. ResponseEntity chứa Mono với status biết sớm

```bash
curl -i 'http://localhost:8080/api/items/accepted'
```

Dự kiến:

```http
HTTP/1.1 202 Accepted
X-Body-Mode: mono
Content-Type: application/json

{"state":"queued"}
```

Status/header đã được controller chọn trước khi delayed Mono phát object. **Không đồng nghĩa một job nền thật đang chạy**; endpoint demo dùng 202 để minh họa HTTP envelope. Nếu triển khai production 202, cần job tracking/processing semantics rõ.

### 15.4. JSON array với ResponseEntity<Flux<Item>>

```bash
curl -i 'http://localhost:8080/api/items'
```

Sau khi tạo item đầu, body JSON dạng:

```json
[{"id":1,"name":"Spring WebFlux"}]
```

Một Flux có nhiều DTO nhưng Content-Type `application/json` ở đây là danh sách theo một JSON document/array. Đừng dựa vào network chunk boundaries để phân tách items.

### 15.5. NDJSON output streaming

```bash
curl -i -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items/stream'
```

Nếu có hai items ID 1,2, body gồm những dòng JSON riêng:

```text
{"id":1,"name":"Spring WebFlux"}
{"id":2,"name":"Reactor"}
```

`-N` của curl tắt một số output buffering của curl; server/proxy có thể vẫn buffer tùy configuration. Nếu không có item, response 200 NDJSON có thể có body rỗng. Với transport streaming, flushing và khả năng quan sát từng item phụ thuộc nguồn phát, decoder/encoder và intermediary proxies.

### 15.6. NDJSON input batch

```bash
curl -i -X POST \
  'http://localhost:8080/api/items/batch' \
  -H 'Content-Type: application/x-ndjson' \
  -H 'Accept: application/json' \
  --data-binary $'{"name":"Alpha"}\n{"name":"Beta"}\n'
```

Trong Bash, ký hiệu `$'...'` tạo các newline thật. Windows PowerShell có cú pháp quote/newline khác; tạo một file NDJSON rồi dùng `--data-binary @batch.ndjson` khi cần portability.

Dự kiến HTTP 201 và JSON array chứa hai Item mới có server-owned IDs:

```json
[{"id":3,"name":"Alpha"},{"id":4,"name":"Beta"}]
```

IDs ví dụ giả sử trước đó chỉ tạo hai items. Nếu đã gọi thêm requests/tests hoặc restart server, IDs khác. Không viết client code phụ thuộc vào ID tuyệt đối trong body.

### 15.7. Validation lỗi

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"   "}'
```

Dự kiến `400 Bad Request` và error body:

```json
{"code":"invalid_item"}
```

Điều này xảy ra vì record `NewItem` có `@NotBlank` và controller `@Valid @RequestBody Mono<NewItem>`. Nếu chuyển sang plain `@RequestBody Mono<NewItem>` mà không có validation nơi khác, body có thể qua được dù name không hợp lệ, dẫn tới business data sai.

## 16. WebTestClient integration tests

Để bảo đảm không chỉ có code snippets mà còn xác minh HTTP contract, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` với `WebTestClient`. Các tests không phụ thuộc ID cố định hoặc thứ tự thực thi.

**`src/test/java/example/bodyresponse/ItemControllerTest.java`**

```java
package example.bodyresponse;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void monoRequestBodyCreates201AndLocation() {
        String location = client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewItem("Spring"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .expectBody(Item.class)
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.matches("/api/items/[1-9][0-9]*"));

        client.get().uri(location).exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.name").isEqualTo("Spring");
    }

    @Test
    void validationForMonoBodyProduces400() {
        client.post()
              .uri("/api/items")
              .contentType(MediaType.APPLICATION_JSON)
              .bodyValue(new NewItem("   "))
              .exchange()
              .expectStatus().isBadRequest()
              .expectBody()
              .jsonPath("$.code").isEqualTo("invalid_item");
    }

    @Test
    void monoResponseEntityCanChoose404() {
        client.get()
              .uri("/api/items/999999999")
              .exchange()
              .expectStatus().isNotFound();
    }

    @Test
    void entityWithMonoHasEarlyStatusAndHeaders() {
        client.get().uri("/api/items/accepted")
              .exchange()
              .expectStatus().isAccepted()
              .expectHeader().valueEquals(
                      "X-Body-Mode", "mono")
              .expectBody()
              .jsonPath("$.state").isEqualTo("queued");
    }

    @Test
    void entityWithFluxCanProduceJsonArray() {
        client.get().uri("/api/items")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_JSON)
              .expectBody()
              .jsonPath("$").isArray();
    }

    @Test
    void fluxInputSupportsNdjsonBatch() {
        String ndjson =
                "{\"name\":\"Kotlin\"}\n"
                + "{\"name\":\"Reactor\"}\n";

        client.post()
              .uri("/api/items/batch")
              .contentType(MediaType.APPLICATION_NDJSON)
              .bodyValue(ndjson)
              .exchange()
              .expectStatus().isCreated()
              .expectBody()
              .jsonPath("$").isArray()
              .jsonPath("$.length()").isEqualTo(2);
    }

    @Test
    void ndjsonOutputHasDeclaredStreamingMediaType() {
        client.get().uri("/api/items/stream")
              .accept(MediaType.APPLICATION_NDJSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_NDJSON);
    }
}
```

Bộ test có **7 test methods**.

**Đặc biệt:** Test đầu gọi POST, lấy header Location thực rồi GET lại, không hardcode ID 1. Những tests khác chỉ kiểm tra cấu trúc JSON array, nên không phụ thuộc số lượng items do các tests khác tạo. Test NDJSON input dùng raw body text chứa hai JSON lines; không nhầm nó với JSON string literal encoded thành `"..."`.

**Lưu ý static QA:** Bộ tests được soạn để dùng APIs Spring WebFlux/Spring Boot 3.3.5. `@AutoConfigureWebTestClient` có thể dùng với `RANDOM_PORT` để test reactive server. Mã này chưa được chạy Maven trong phạm vi Google Sheets; trước khi dùng production, chạy đầy đủ `mvn test`/integration tests với đúng toolchain.

### Mở rộng tests hữu ích

Bổ sung:
- Body rỗng với `@RequestBody(required=true)`.
- Bad Content-Type / unsupported media.
- JSON malformed và field type mismatch.
- 100 vs 101 NDJSON records.
- Validation lỗi ở element thứ hai khi batch đã đọc phần tử đầu.
- Client cancel giữa NDJSON stream.
- Slow consumer/response buffer/backpressure.
- Reactor Context/trace ID propagation.
- Spring Security auth/authorization/CSRF/CORS.
- Large body, max in-memory size, response timeout.
- R2DBC or other truly non-blocking database client behavior.

## 17. Một vấn đề nhỏ về WebTestClient và BodyExtractors

`WebTestClient` có nhiều cách assert response body:

- `expectBody(Item.class)` cho một object.
- `expectBodyList(Item.class)` cho list/array JSON.
- `expectBody().jsonPath(...)` cho JSON tree.
- `returnResult(Item.class).getResponseBody()` để consume streamed Flux items với Reactor operators/StepVerifier.
- `exchange()` bắt đầu HTTP request/response exchange.

Với NDJSON streaming dài, test `expectBodyList` có thể **chờ stream complete**; nếu SSE/Flux vô hạn, test không nên đợi toàn bộ publisher. Dùng `returnResult(Item.class)` và `StepVerifier`/`take(n)`/timeouts, bảo đảm cancellation và dọn subscription sau test.

### Không dùng HTTP status để đo từ số lượng body items

`Flux.empty()` có thể là kết quả hợp lệ với 200. Với resource không tồn tại, status nên được quyết định dựa vào lookup/metadata trước khi trả response (thường `Mono<ResponseEntity<...>>`). Với stream đang chạy, status không thể thay đổi cho mỗi element sau khi đã commit.

## 18. Chọn Mono hay Flux ở request body

| Đầu vào | Chọn loại nào? | Lý do |
| --- | --- | --- |
| Một JSON object nhỏ | `Mono<DTO>` hoặc DTO trực tiếp | Tối đa một object |
| Một JSON array nhỏ, atomic batch | `Mono<List<DTO>>`/wrapper DTO | Validate toàn bộ trước khi ghi |
| NDJSON nhiều records | `Flux<DTO>` | Phát từng object, hỗ trợ backpressure |
| SSE input | Không phổ biến cho POST; chọn protocol rõ | SSE thường là server→client |
| Binary upload lớn | `Flux<DataBuffer>`/file upload APIs | Quản lý pooled buffers, size, cancel |
| Multipart | WebFlux `@RequestPart`/`FilePart`/`Part` | Có API riêng, không coi là JSON DTO |
| Form URL encoded | WebFlux form data APIs | Media type/decoder khác JSON |
| Client gửi 0 bytes | Policy `required`/optional rõ | Mono empty khác validation lỗi |
| Client gửi malformed JSON | Error handling, 400 | Không biến thành default DTO âm thầm |

Với media type `application/json` truyền một object, không cần dùng `Flux<T>` chỉ vì ứng dụng đã reactive. Dùng đúng **cardinality contract** thường quan trọng hơn việc "càng nhiều Flux càng tốt".

## 19. Chọn ResponseEntity reactive dựa trên quyết định status

Một cách hỏi ngắn:

**Status/headers phụ thuộc vào kết quả bất đồng bộ không?**

- **Không** → `ResponseEntity<Mono<T>>` hoặc `ResponseEntity<Flux<T>>`. Nếu body sẵn thì `ResponseEntity<T>`.
- **Có** → `Mono<ResponseEntity<T>>`.
- **Có, và body tiếp tục streaming sau khi envelope đã chọn** → `Mono<ResponseEntity<Flux<T>>>`.

Ví dụ:
- `GET /items/{id}` phải 404 nếu không có: `Mono<ResponseEntity<Item>>`.
- `GET /stream` luôn 200 NDJSON: `ResponseEntity<Flux<Item>>`.
- `POST /items` cần ID/Location sau khi tạo: `Mono<ResponseEntity<Item>>`.
- `GET /long-operation` luôn 202, body trạng thái phát muộn: `ResponseEntity<Mono<StatusMessage>>` (nhưng cần job semantics nếu thực sự async background).
- `GET /export` cần check permissions/quota trước rồi mới stream: `Mono<ResponseEntity<Flux<byte[]>>>` hoặc phù hợp hơn stream DataBuffer/Resource theo codec, kèm cancellation/backpressure tests.

### Vì sao ResponseEntity<Mono<T>> không tự thay 200 bằng 404?

Lúc `ResponseEntity.ok().body(sourceMono)` được tạo, HTTP 200 đã được quyết định. Khi `sourceMono` complete empty, framework không thể "tự hiểu" đây là missing resource. Nếu source phát `ResponseStatusException` trước commit, framework có thể đổi status tùy resolver, nhưng dựa vào error như phép thay thế cho conditional success/absence là cách thiết kế API khó đoán. Với missing bình thường, chọn `Mono<ResponseEntity<T>>`.

## 20. Error operators: đâu là chỗ xử lý lỗi đúng?

Trong một pipeline:

```java
return incoming.flatMap(store::create)
        .onErrorResume(DuplicateItemException.class, e ->
                Mono.error(new ResponseStatusException(
                        HttpStatus.CONFLICT, "Duplicate item")));
```

Đây là snippet với `DuplicateItemException` và `store` giả định. Nó chuyển **một lỗi domain đã biết** thành HTTP 409, không biến mọi Exception thành 409.

Sai:

```java
return incoming
        .onErrorReturn(new NewItem("default"))
        .flatMap(store::create);
```

Nếu JSON malformed, validation fail hoặc body thiếu, đoạn trên có thể âm thầm tạo item mặc định và trả 201 — thay đổi ý nghĩa HTTP request, nguy hiểm cho dữ liệu. Không dùng `onErrorReturn` để che invalid input.

### Khi HTTP response đã commit

`ResponseEntity<Flux<T>>` cho stream dài có thể đã gửi response 200 và vài items. Nếu item tiếp theo báo error:
- App không thể bảo đảm trả JSON 500 sạch.
- HTTP connection có thể kết thúc sớm hoặc client thấy stream bị gián đoạn.
- Cần retry/resume semantics ở protocol level nếu cần.
- Logging và tracing cần phân biệt partial response từ full success.
- Không retry tự động POST non-idempotent ở reactive operator nếu có side effects.

### Exceptions trong WebFlux

`@RestControllerAdvice`/`@ExceptionHandler` xử lý exception trong annotated endpoint flow; `WebExceptionHandler` ở outer WebHandler chain xử lý errors còn propagate. `ResponseStatusException` có thể được framework map thành status. Các thành phần có thể được cấu hình theo order; không tự khai một WebExceptionHandler "catch-all" rồi ẩn mọi lỗi thành 400.

## 21. Content negotiation, 406/415 và streaming codecs

- `Content-Type` của request chỉ **format dữ liệu gửi tới server**.
- `Accept` của request cho biết **format client muốn nhận**.
- `consumes` trong `@PostMapping` giới hạn request media type.
- `produces` trong `@GetMapping` giới hạn response media type.
- `ResponseEntity.contentType(...)` đặt response Content-Type.

Ví dụ:

```java
@GetMapping(path="/stream",
            produces=MediaType.APPLICATION_NDJSON_VALUE)
public ResponseEntity<Flux<Item>> stream() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(store.all());
}
```

Nếu client gửi `Accept: text/plain` và endpoint chỉ `produces=application/x-ndjson`, có thể gặp 406 (Not Acceptable) theo content negotiation. Nếu client POST `Content-Type: text/plain` tới handler chỉ consumes JSON, có thể gặp 415. Các status chính xác còn phụ thuộc mapping, codecs, exception handling và framework configuration; kiểm thử thực tế thay vì chỉ suy đoán.

## 22. Request body one-shot, filter logging và DataBuffer

`ServerHttpRequest.getBody()` trả `Flux<DataBuffer>`. Một WebFilter muốn log raw request body bằng cách gọi `subscribe()` có thể tiêu thụ body trước khi `@RequestBody Mono<T>` đọc, gây lỗi.

Phản ví dụ:

```java
exchange.getRequest().getBody().subscribe(buffer ->
        unsafeLog(buffer));
return chain.filter(exchange);
```

Đây là pseudocode; `unsafeLog` không định nghĩa vì bản thân pattern là sai. Hậu quả:
- Hai subscribers tranh cùng network stream.
- Body reader sau có thể nhận empty/malformed data.
- Passwords, tokens, PII bị ghi logs.
- Pooled DataBuffers có thể leak nếu không release đúng.
- Reactive cancellation/backpressure không đồng bộ.

Nếu cần request body instrumentation, dùng API/tooling chuyên dụng với redaction, byte limits, `ServerHttpRequestDecorator` và ownership của `DataBufferUtils` rõ ràng; ưu tiên không log body nhạy cảm.

**Không lưu toàn bộ request body vào memory để debug production** mà thiếu size cap và privacy policy.

## 23. Bảo mật, concurrency và vận hành

### 23.1. Input size và codec limits

- Giới hạn max in-memory codec buffer (`spring.codec.max-in-memory-size` tùy Spring Boot config).
- Giới hạn HTTP body size/JSON depth ở proxy/server khi cần.
- Giới hạn items per batch và max name length.
- Đặt request/idle timeouts, connection and concurrency limits.
- Giới hạn tốc độ và body chunk sizes với slow clients.
- Không để client gửi Flux vô hạn rồi `collectList()` vô hạn.

### 23.2. Authentication và authorization

`@Valid` kiểm tra cú pháp DTO, không có nghĩa principal được tạo/đọc Item. Với WebFlux, dùng Spring Security `SecurityWebFilterChain` cùng reactive SecurityContext, sau đó kiểm tra ownership/tenant trong service. Không lấy client-provided `userId`/`X-Role` làm danh tính đã xác thực. Với browser cookie/session auth, POST còn chịu CSRF policy.

### 23.3. Thao tác idempotent và retry

POST create thường không idempotent. Nếu client timeout sau khi server đã lưu item, retry có thể tạo duplicate. Với hệ thống thật, cân nhắc `Idempotency-Key` do server validate, transaction/unique constraints, trace IDs và retry policy rõ. Reactor `retry()` không tự phân biệt side-effecting operations với read-only operations.

### 23.4. Backpressure và slow clients

Với Flux NDJSON, nếu client đọc chậm, upstream demand/cancellation có thể ảnh hưởng nguồn phát. Nhưng nếu code tự cache quá nhiều item, buffer vô hạn hoặc remote producer phớt lờ demand, RAM vẫn tăng. Phải đo active connections, pending buffers, response write latency, cancellations, DB connections và scheduler saturation.

### 23.5. Logging, context propagation và metrics

Reactive execution có thể chuyển scheduler; đừng dựa vào custom ThreadLocal cho request ID hoặc SecurityContext. Dùng Reactor Context/tracing integration và metrics theo route template để tránh cardinality cao. Không log raw query/body chứa secrets.

### 23.6. Reverse proxy và HTTP framing

Server có thể stream NDJSON qua chunked transfer hoặc HTTP/2 frames; **TCP/HTTP chunk boundaries không trùng JSON line boundaries**. Client parser phải dựa trên newline/codec framing, không giả sử một network read bằng một record. Reverse proxy có thể buffer/compress response, ảnh hưởng latency streaming. Test qua deployment topology thực khi việc nhận từng item sớm là yêu cầu nghiệp vụ.

## 24. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| GET không có Item nhưng trả 200 body rỗng | `ResponseEntity.ok().body(Mono.empty())` | `Mono<ResponseEntity<Item>>` để chọn 404 |
| POST trả 200 thay vì 201 | Return DTO/Mono không có status override | `Mono<ResponseEntity<Item>>` + `created(Location)` |
| `Mono<NewItem>` không được xử lý | Tạo Mono nhưng không return/subscribe đúng lifecycle | Return reactive composition, không subscribe thủ công |
| Event loop bị block | Gọi JDBC/file/network sync trong `map/flatMap` | Non-blocking driver hoặc bounded scheduler offload |
| Invalid DTO được lưu | Quên `@Valid`/business validation | `@Valid @RequestBody Mono<DTO>` và service checks |
| JSON malformed ra status/body không đúng | Error policy không cover WebFlux decoder errors | Test malformed JSON và exception mappings |
| Flux input không stream | Dùng JSON document/array không phải NDJSON hoặc decoder buffering | Dùng đúng Content-Type và wire format |
| Mỗi output item không nhận được ngay | `application/json` encode thành array, proxy buffering | NDJSON/SSE và streaming tests |
| NDJSON response client parse lỗi | Parser dựa vào HTTP chunks thay vì newline | Dùng NDJSON framing |
| Batching gây OOM | `Flux.collectList()` không bound | Giới hạn items/bytes, streaming processing |
| Batch 101 items vẫn 201 cho 100 đầu | `take(100)` truncates silently | `take(101)` rồi reject nếu size>100 |
| Stream lỗi giữa chừng nhưng status vẫn 200 | Response đã commit | Protocol resume/retry, không hứa JSON 500 |
| Spring MVC classes xuất hiện trong WebFlux | Import hoặc starter-web nhầm | Dùng WebFlux stack đúng dependencies |
| `Mono.empty()` gây API "not found" không rõ | Thiếu distinction absent vs success empty | Chọn status/DTO contract |
| Too many publisher subscriptions | Manual `subscribe()` hoặc share one-shot body | Để framework subscribe, không dùng duplicate |
| Header/Location sai sau proxy | Host/Forwarded trust sai | Canonical base/trusted proxy policy |
| CORS 403 khi browser POST | Preflight/security ordering | WebFlux CORS/Spring Security integration |
| 401/403 xử lý bởi controller thay vì Security | Không có auth policy ở HTTP filter chain | SecurityWebFilterChain + service ACL |
| `@Valid` exception class khác MVC | WebFlux validation flow khác Servlet | Handle `WebExchangeBindException` và method validation appropriately |
| Mất tracing principal khi scheduler đổi | Dùng ThreadLocal custom | Reactor Context/official context propagation |
| Reactive code retry tạo duplicate | Retry POST không có idempotency | Idempotency key và transaction |
| ResponseEntity bên ngoài Flux đổi status sai | Chọn 200 trước khi biết kết quả | Mono<ResponseEntity<...>> |
| Body JSON array bị coi là NDJSON | Nhầm media type | Content-Type/Accept matching and tests |
| Body quá lớn dù chỉ một record | Giới hạn số records nhưng không giới hạn bytes | Codec byte/size limits |
| DataBuffer leak trong WebFilter | Cache/retain mà không release | Dùng DataBufferUtils và test cancellation |

## 25. Checklist để code review

- [ ] Controller là WebFlux, không lẫn Servlet MVC.
- [ ] `@RequestBody Mono<T>` dùng cho một object, `Flux<T>` cho nhiều elements/streaming contract đúng media type.
- [ ] `@Valid` được đặt ở input reactive khi cần Bean Validation.
- [ ] Không `block()`/`subscribe()` trên request thread/event loop.
- [ ] Không dùng body publisher hai lần hoặc log raw secrets.
- [ ] Status/headers phải được quyết định trước commit và dựa vào đúng async result.
- [ ] `Mono<ResponseEntity<T>>` cho 200/404, 201/409 hay điều kiện business động.
- [ ] `ResponseEntity<Flux<T>>` cho status biết sớm cùng stream nhiều items.
- [ ] JSON array khác NDJSON line-delimited; client parser không dựa network chunks.
- [ ] Giới hạn số items, bytes, nesting, timeout, concurrency và queue.
- [ ] Với streaming lỗi sau commit, có policy retry/resume/cancellation riêng.
- [ ] Validation, auth, ownership, CSRF, idempotency và transactions không lẫn nhau.
- [ ] Đặt Location đúng server resource, không tin Host/Forwarded client tùy ý.
- [ ] Tests cover body empty/invalid/malformed/unsupported content type.
- [ ] WebTestClient covers 200, 201, 202, 204 nếu có, 400, 404, 413 nếu có, Content-Type, headers, array, NDJSON.
- [ ] Mọi external blocking dependency được xử lý đúng; không chỉ "bọc Mono" rồi coi non-blocking.
- [ ] Không dùng `Flux.collectList()` với input không giới hạn.
- [ ] Đo metrics latency, downstream errors, slow clients và cancelled streams.
- [ ] Dùng route template metrics để tránh high-cardinality tags.
- [ ] Mỗi API có error schema và content negotiation contract rõ.

## 26. Bài tập tự kiểm tra

1. `@RequestBody NewItem` khác `@RequestBody Mono<NewItem>` thế nào?
2. `@RequestBody Flux<NewItem>` có bắt buộc nhận mỗi object ngay khi đến nếu Content-Type là `application/json` array không?
3. Vì sao NDJSON thuận tiện cho stream nhiều JSON objects?
4. `Mono<ResponseEntity<Item>>` khác `ResponseEntity<Mono<Item>>` ở thời điểm quyết định 404 ra sao?
5. Vì sao `Flux.empty()` thường có thể trả 200 danh sách rỗng, còn missing resource cần 404?
6. Khi nào chọn `Mono<ResponseEntity<Flux<T>>>` thay `ResponseEntity<Flux<T>>`?
7. `@Valid` trên reactive body có thể gây exception WebFlux nào?
8. Có nên bắt `WebExchangeBindException` rồi trả raw `error.getMessage()` cho public client không?
9. `Location` cho POST resource nên tạo trước hay sau khi server xác định ID?
10. `ResponseEntity<Flux<Item>>` với `application/json` và `application/x-ndjson` khác nhau gì về format?
11. Vì sao `collectList()` trên NDJSON input vô hạn có thể dẫn đến OOM?
12. Batching tối đa 100 cần đọc tới phần tử thứ bao nhiêu để biết "too many"?
13. Khi response NDJSON đã gửi ba dòng và dòng thứ tư lỗi, status có thể đổi từ 200 sang 500 sạch không?
14. Vì sao không gọi `incoming.block()` trong controller WebFlux trên event loop?
15. `Mono.fromCallable(() -> jdbc.save(...)).subscribeOn(boundedElastic())` có làm JDBC non-blocking không?
16. `@RequestBody Flux<T>` và `Flux<DataBuffer>` khác nhau ở mức trừu tượng nào?
17. Khi nào server dùng `413 Payload Too Large`?
18. Vì sao 202 Accepted không đồng nghĩa mọi `Mono` delayed?
19. Tại sao không nên dùng `onErrorReturn(new DefaultItem(...))` cho JSON malformed/validation errors?
20. Client muốn parsing NDJSON theo đâu: HTTP chunks hay newline framing?
21. CORS có thay authorization không?
22. Retry POST gây dữ liệu duplicate ra sao?
23. Vì sao response headers nên xác định trước body write?
24. Khi no resource mà body Publisher empty, làm sao trả 404 đúng?
25. Những gì `WebTestClient` xác minh được và không thể thay benchmark/production proxy test?

**Gợi ý:** (1) Direct DTO decode trước handler, Mono là reactive value của decode. (2) Không, tùy codecs/media type. (3) Mỗi JSON line là record độc lập. (4) Mono<ResponseEntity> chờ lookup rồi chọn 200/404; ResponseEntity<Mono> status đã chọn. (5) Khác collection rỗng với resource absent. (6) Khi envelope/status phụ thuộc async decision nhưng body là Flux. (7) WebExchangeBindException; method constraints còn có HandlerMethodValidationException. (8) Không. (9) Sau khi server xác định ID. (10) JSON array vs newline-delimited objects. (11) Không bound memory. (12) 101. (13) Không bảo đảm. (14) Block event loop. (15) Không, chỉ offload blocking. (16) Decoded DTOs vs raw pooled buffers. (17) Request vượt giới hạn theo HTTP policy. (18) 202 là business semantics. (19) Che invalid input, có thể ghi dữ liệu sai. (20) NDJSON delimiters. (21) Không. (22) Side effect lặp. (23) Response commit. (24) Mono<ResponseEntity>. (25) Contract/runtime behavior cơ bản, không tự chứng minh throughput/backpressure/reverse proxy.

## 27. Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework — WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
- [Spring Framework — WebFlux HTTP Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework 6.1 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.html)
- [Project Reactor — Mono/Flux Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)

**Tổng kết:** `@RequestBody Mono<T>` biểu diễn request body một object dưới dạng reactive publisher; `@RequestBody Flux<T>` thích hợp khi nhận nhiều objects, đặc biệt NDJSON/streaming. Với response, hãy chọn kiểu theo **thời điểm cần quyết định status/headers**: `ResponseEntity<Mono<T>>` và `ResponseEntity<Flux<T>>` biết envelope sớm; `Mono<ResponseEntity<T>>` chờ kết quả async để chọn status như 201/404; `Mono<ResponseEntity<Flux<T>>>` cho phép quyết định envelope async rồi mới phát stream. Tất cả phải đi kèm media type đúng, validation, bounds, error policy, cancellation và không blocking event loop.
