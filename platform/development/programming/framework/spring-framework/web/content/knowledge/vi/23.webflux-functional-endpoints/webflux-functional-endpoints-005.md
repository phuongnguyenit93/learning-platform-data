# Đọc body bằng bodyToMono/bodyToFlux và kiểm tra dữ liệu trong Functional WebFlux

## 1. Vấn đề: HTTP body là luồng bytes, không phải đối tượng Java đáng tin

Khi client gửi request đến API:

```http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "title": "WebFlux thực hành",
  "contact": {"email": "reader@example.org"}
}
```

Server trước hết chỉ nhận **bytes**. Để xử lý nghiệp vụ, ứng dụng cần giải mã JSON, tạo DTO, kiểm tra dữ liệu, rồi mới gọi service hoặc lưu database. Spring WebFlux functional endpoints (thường gọi **WebFlux.fn**) cung cấp hai phương thức quan trọng trong `ServerRequest`:

- **`bodyToMono(Class<T>)`:** đọc/giải mã request body để tạo `Mono<T>`, phù hợp khi hợp đồng mong **một đối tượng** hoặc một giá trị.
- **`bodyToFlux(Class<T>)`:** tạo `Flux<T>` gồm **nhiều giá trị** được giải mã từ body, phù hợp các representation có framing cho nhiều phần tử, chẳng hạn NDJSON.

Cả hai dùng hệ thống `HttpMessageReader`/`Decoder` của WebFlux; chúng **không** tự xác nhận rằng dữ liệu đạt Bean Validation hoặc domain rules.

Đặc biệt, trong **functional handler** bạn thường phải gọi validator **tường minh**, khác cơ chế `@Valid @RequestBody` được hạ tầng Spring áp vào tham số của annotated controller. Nếu bỏ qua bước này, JSON có trường trống vẫn có thể được deserialize thành DTO và đi vào kho dữ liệu.

Bài thuộc nhóm **Functional WebFlux**, áp dụng cho **Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, Reactor 3.7.x**, chạy WebFlux trên Reactor Netty. Các ví dụ không dùng Servlet MVC và không trộn packages `org.springframework.web.servlet.function` với `org.springframework.web.reactive.function.server`.

### Sau bài này, bạn sẽ làm được

1. Chọn `bodyToMono` hay `bodyToFlux` theo đúng HTTP content representation.
2. Biết `ServerRequest.body(BodyExtractors.toMono/toFlux)` tương đương phương thức tiện ích.
3. Dùng `jakarta.validation.Validator` hoặc Spring `Validator` để validate trước side effect.
4. Phân biệt **body rỗng**, **JSON hỏng**, **đúng JSON nhưng vi phạm constraint**, **sai Content-Type**, **request quá lớn**, **sai business rule**.
5. Xử lý lỗi reactive với `onErrorResume` theo loại, không bắt mọi lỗi rồi đổi thành 400.
6. Biết streaming theo từng record NDJSON, backpressure và xử lý lỗi giữa stream.
7. Thiết lập testing cho request hợp lệ và không hợp lệ với `WebTestClient`.
8. Kiểm soát memory/cancellation, tránh `collectList()` hay `block()` trên luồng dài.

## 2. Kiến trúc request body trong WebFlux.fn

```text
HTTP request
  |
  v
Reactor Netty -> ServerHttpRequest
  |
  v
Flux<DataBuffer>       (bytes / buffers)
  |
  v
ServerRequest
  |
  | bodyToMono(CreateBook.class)
  | bodyToFlux(ImportLine.class)
  | body(BodyExtractors.toMono(...))
  |
  v
HttpMessageReader + Decoder (chọn theo type và Content-Type)
  |
  +--> onError(DecodingException / WebFlux input errors)
  |
  v
Mono<DTO> hoặc Flux<DTO>
  |
  v
Validator / business rules (phải được gọi đúng chỗ)
  |
  +--> onError(input validation)
  |
  v
Reactive service / repository
  |
  v
Mono<ServerResponse>
  |
  v
HttpMessageWriter -> HTTP status + headers + body
```

Các thành phần:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `RouterFunction<ServerResponse>` | Chọn route theo method, path và predicates |
| `HandlerFunction<ServerResponse>` | Nhận `ServerRequest` và trả `Mono<ServerResponse>` |
| `ServerRequest` | Truy cập headers, URI, query, path variables, body |
| `HttpMessageReader` | Đọc HTTP body thành một hay nhiều giá trị Java |
| `Decoder<T>` | Giải mã từ `DataBuffer`/bytes thành kiểu `T` |
| `Mono<T>` | Publisher có 0 hoặc 1 giá trị |
| `Flux<T>` | Publisher có 0 đến nhiều giá trị |
| `jakarta.validation.Validator` | Đánh giá ràng buộc Bean Validation trên object |
| `ServerResponse` | Khai báo status, headers, body, được ghi khi Mono response được subscribe |

Khác Spring MVC.fn, handler WebFlux.fn **trả `Mono<ServerResponse>`**:

```java
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

Mono<ServerResponse> handle(ServerRequest request) {
    return ServerResponse.ok().bodyValue("Hello");
}
```

Đoạn trên là **method fragment** cho một handler; `ServerResponse.ok().bodyValue(...)` tạo **Mono của ServerResponse**, không phải synchronous `ServerResponse` như MVC Servlet functional handlers.

## 3. `bodyToMono(Class<T>)`: một đối tượng trong request

Cú pháp cơ bản:

```java
Mono<CreateBook> body =
        request.bodyToMono(CreateBook.class);
```

Phù hợp với:

- JSON object cho create/update command.
- Một JSON scalar hoặc một string tùy media type/decoder.
- Metadata object cần kiểm tra trước khi ghi dữ liệu.
- Một body được client gửi đúng một lần, không phải vô hạn records.

Ví dụ:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateBook.class)
            .flatMap(command ->
                    ServerResponse.ok().bodyValue(command));
}
```

**Đây chỉ là fragment minh họa deserialize**, chưa có validation, authorization hoặc persistence.

### 3.1. `Mono` là một publisher, không phải DTO đã có sẵn

Ngay sau `request.bodyToMono(CreateBook.class)`, bạn có một mô tả computation bất đồng bộ. Decoder/body data được tiêu thụ khi pipeline được subscribe bởi hạ tầng WebFlux. **Không** được:

```java
// Sai trong WebFlux request handling:
CreateBook command =
        request.bodyToMono(CreateBook.class).block();
```

`block()` trên Reactor Netty event loop có thể chặn processing, dẫn đến throughput thấp hoặc lỗi blocking operation not supported.

Cũng không tự subscribe rồi trả response thành công trước khi work kết thúc:

```java
// Sai: side effect rời khỏi HTTP response lifecycle:
request.bodyToMono(CreateBook.class)
        .subscribe(this::save);

return ServerResponse.accepted().build();
```

Nếu `save` thất bại, HTTP response không còn phản ánh kết quả; lỗi/cancel có thể bị xử lý sai. **Compose publisher và trả nguyên Mono tới WebFlux**.

### 3.2. Body rỗng khác JSON chứa null

Với `bodyToMono(T.class)`, **không có giá trị** có thể dẫn đến `Mono.empty()`. Một body thực sự rỗng và JSON literal `null` có thể dẫn đến behavior phụ thuộc decoder; không giả định mọi trường hợp có object non-null.

Một API yêu cầu body nên quy định riêng:

```java
Mono<CreateBook> required = request
        .bodyToMono(CreateBook.class)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException(
                        "Request body required")));
```

Fragment này minh họa `switchIfEmpty`; code production cần map exception thành **400 với error code ổn định** thay vì trả raw message. Dùng `defaultIfEmpty(...)` khi domain thật sự có giá trị mặc định hợp lệ; **không** tạo DTO giả để bỏ qua input bắt buộc.

### 3.3. Nếu body là JSON array?

```http
Content-Type: application/json

[
  {"sku":"A-1","quantity":2},
  {"sku":"B-2","quantity":3}
]
```

Có ít nhất hai hướng:

- Muốn **một aggregate object**: `bodyToMono(new ParameterizedTypeReference<List<ImportLine>>() {})`. Cần tích lũy list; giới hạn bộ nhớ theo tổng array.
- Muốn processing nhiều items: dùng `bodyToFlux(ImportLine.class)` khi reader hỗ trợ streaming/decode representation phù hợp; với một JSON array, mức độ decode incremental và buffering tùy codec.

**Ưu tiên NDJSON** nếu hợp đồng truyền vô số records riêng, mỗi dòng là một JSON object. Không giả định `Flux<T>` tự biến mọi body thành streaming tối ưu.

## 4. `bodyToFlux(Class<T>)`: nhiều phần tử nối tiếp

```java
Flux<ImportLine> items =
        request.bodyToFlux(ImportLine.class);
```

Phù hợp với **stream các record** trong content representation có framing rõ ràng, ví dụ:

```http
POST /api/books/import HTTP/1.1
Content-Type: application/x-ndjson

{"sku":"B-101","quantity":3}
{"sku":"B-102","quantity":5}
{"sku":"B-103","quantity":2}
```

`application/x-ndjson` (Newline Delimited JSON) diễn đạt: **mỗi dòng riêng là một JSON value**, khác một JSON array chung.

Một handler có thể dùng:

```java
Mono<ServerResponse> importLines(ServerRequest request) {
    return request.bodyToFlux(ImportLine.class)
            .map(this::validateAndNormalize)
            .reduce(
                new ImportSummary(0, 0),
                (summary, line) ->
                    new ImportSummary(
                        summary.rows() + 1,
                        summary.quantity() + line.quantity()))
            .flatMap(total ->
                ServerResponse.ok().bodyValue(total));
}
```

Đây là **fragment**, cần khai báo records, validator và method `validateAndNormalize`. Dùng `reduce` giữ hai số liệu, không `collectList()` mọi record trong RAM.

### 4.1. Flux có backpressure nhưng không có nghĩa tổng memory tự bị giới hạn

- `Flux<T>` dùng `request(n)` để phối hợp **nhu cầu phần tử** giữa publisher/subscriber.
- Decoder có thể phải buffer đến khi một JSON record hoàn chỉnh.
- `flatMap` có concurrency/prefetch và queues riêng.
- `collectList()` tích lũy **mọi item** trước khi xuất response.
- Một item rất lớn vẫn có thể vượt `maxInMemorySize`.
- Một NDJSON stream hàng GB có thể chứa records nhỏ hơn codec limit mà vẫn vượt **total upload quota**.

Do đó với public import API phải có **giới hạn tổng bytes, số records, thời lượng, rate limit, concurrency và quota**, không chỉ quan sát memory per-record.

### 4.2. Thứ tự khi validate và ghi dữ liệu

Nếu các dòng cần xử lý theo thứ tự:

```java
return request.bodyToFlux(ImportLine.class)
        .concatMap(line ->
                validate(line)
                    .then(repository.save(line)))
        .then(ServerResponse.noContent().build());
```

Đây là **fragment**; `validate` được giả định trả `Mono<Void>` và repository.save là reactive. `concatMap` giữ thứ tự các source elements. **Không hứa transactional all-or-nothing**: nếu dòng 100 lỗi sau khi 99 dòng đã lưu, side effects 1–99 có thể đã commit. Nếu muốn toàn bộ batch atomic, cần staging, transaction logic phù hợp, idempotency hoặc job import độc lập.

`flatMap` có thể xử lý concurrent và thứ tự hoàn tất thay đổi; chọn dựa trên semantics nghiệp vụ, không chỉ tốc độ.

## 5. `body(...)` và `BodyExtractors`: phiên bản tổng quát

`bodyToMono` và `bodyToFlux` là shortcuts:

```java
Mono<CreateBook> a = request.bodyToMono(CreateBook.class);

Mono<CreateBook> b = request.body(
        BodyExtractors.toMono(CreateBook.class));

Flux<ImportLine> c = request.bodyToFlux(ImportLine.class);

Flux<ImportLine> d = request.body(
        BodyExtractors.toFlux(ImportLine.class));
```

Đây là fragment, cần:

```java
import org.springframework.web.reactive.function.BodyExtractors;
```

`BodyExtractors` có hỗ trợ các cách đọc **raw DataBuffer, Resource, parts, form/multipart** tùy media type. Dùng API chuyên dụng khi representation phức tạp, không lạm dụng `bodyToFlux(MyPojo.class)` cho file lớn.

### 5.1. Kiểu generic

`bodyToMono(Class<T>)` tiện khi `T` không chứa generic type. Với `List<Book>` hoặc `Map<String,List<Book>>`:

```java
Mono<List<ImportLine>> lines =
        request.bodyToMono(
            new ParameterizedTypeReference<
                List<ImportLine>>() {});
```

Đây là fragment; cần import `org.springframework.core.ParameterizedTypeReference` và `java.util.List`. Overload `ParameterizedTypeReference<T>` giữ được generic element type cho Jackson/codec; `List.class` làm mất generic type trong nhiều trường hợp.

**Không dùng `bodyToMono(List.class)` rồi cast toàn bộ items** sang DTO; dữ liệu thường được decode thành maps không phải record cụ thể nếu thiếu thông tin generic.

## 6. Bean Validation trong functional endpoint không tự chạy

Giả sử DTO:

```java
record Contact(
        @NotBlank @Email String email) {}

record CreateBook(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}
```

Nếu handler chỉ:

```java
return request.bodyToMono(CreateBook.class)
        .flatMap(book -> repository.save(book));
```

**Không tự động validate** chỉ vì có `@NotBlank` ở record. WebFlux.fn không có tham số method được đánh dấu `@Valid @RequestBody` như annotated controller. Cần gọi Spring Validator hoặc Jakarta Bean Validation **sau khi decode, trước save**.

### 6.1. Cách A: Spring `Validator` + `BeanPropertyBindingResult`

Đây là cách tài liệu chính thức Spring WebFlux.fn sử dụng:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;
import org.springframework.web.server.ServerWebInputException;

private final Validator springValidator;

private void validate(CreateBook book) {
    Errors errors =
            new BeanPropertyBindingResult(book, "createBook");
    springValidator.validate(book, errors);

    if (errors.hasErrors()) {
        // Thực tế hãy dùng error code và message an toàn.
        throw new ServerWebInputException(
                "Book input validation failed");
    }
}
```

**Đây là class fragment**, cần có field `springValidator` được khởi tạo/injected. Một global `LocalValidatorFactoryBean` có thể tích hợp Jakarta constraints; cũng có thể dùng Spring custom `Validator`.

- `BeanPropertyBindingResult` mang cả field errors và object errors.
- `@Valid` nested cascade được hỗ trợ khi provider và Spring adapter dùng đúng.
- Dùng `errors.getFieldErrors()` để lấy tên field, nhưng **không trả raw rejected value** ra client/log.
- `ServerWebInputException` thường có HTTP 400 semantics trên WebFlux, nhưng body JSON cụ thể phụ thuộc error handler của ứng dụng.

### 6.2. Cách B: Jakarta `Validator` trực tiếp

Trong project có `spring-boot-starter-validation`, inject `jakarta.validation.Validator`:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

private final Validator beanValidator;

private <T> T requireValid(T input) {
    Set<ConstraintViolation<T>> violations =
            beanValidator.validate(input);

    if (!violations.isEmpty()) {
        throw new InputProblem("INPUT_VALIDATION");
    }

    return input;
}
```

Đây là fragment, cần import `java.util.Set` và custom exception `InputProblem`. Cách này dùng Bean Validation API chuẩn, thích hợp DTO đã đặt `jakarta.validation.constraints.*`. Trong runnable demo sẽ dùng **Jakarta Validator** và tạo error field paths một cách an toàn.

**Điều cốt lõi:** cả hai cách đều phải được **gọi tường minh**:

```java
Mono<CreateBook> validated =
        request.bodyToMono(CreateBook.class)
                .map(this::requireValid);
```

`map` không chạy với `Mono.empty()` hoặc khi decoder đã báo lỗi; vì vậy cần `switchIfEmpty` cho body bắt buộc và đường xử lý decoder exception riêng.

### 6.3. Cascaded validation và null

| Annotation | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `@NotNull` | Không được null | Không cấm chuỗi whitespace |
| `@NotBlank` | Text có non-whitespace | Phù hợp title/email |
| `@Size(min,max)` | Giới hạn kích thước string/collection | Không tự cấm null |
| `@Email` | Hình thức email | Không chứng minh email thuộc người dùng |
| `@Positive` | Số phải lớn hơn 0 | Không tự cấm null |
| `@Valid` | Cascade vào nested object | Không tự báo lỗi nếu nested object null |
| `@Validated(...)` | Chọn validation group với Spring | Dùng có chủ đích; không tự áp chỉ vì functional body |

Ví dụ `@NotNull @Valid Contact contact` có **hai nhiệm vụ**: bắt buộc có contact và kiểm tra constraints bên trong. Nếu chỉ `@Valid Contact contact`, `contact=null` thường không gây violation.

### 6.4. Dùng validation cho cả `Flux`

```java
Flux<ImportLine> validLines =
        request.bodyToFlux(ImportLine.class)
                .index()
                .map(tuple -> {
                    long line = tuple.getT1() + 1;
                    return checkLine(
                            tuple.getT2(),
                            "lines[" + line + "].");
                });
```

`Flux#index()` trả index **bắt đầu ở 0**, nên cộng 1 nếu muốn báo lỗi theo số dòng người dùng. `checkLine` trong ví dụ đầy đủ trả object sau khi validate; nếu lỗi thì throw exception, gây `onError`, dừng xử lý tiếp. Với dữ liệu NDJSON, dòng trống/delimiter và parser behavior phải được test, không giả định index luôn bằng số dòng vật lý bao gồm dòng trống.

## 7. Phân biệt năm kiểu lỗi đầu vào

Một REST API nghiêm túc không được biến mọi exception thành “invalid body”:

| Tình huống | Nguyên nhân | Phản hồi thường hợp lý |
| --- | --- | --- |
| Body bắt buộc nhưng trống | `Mono.empty()` / `Flux.empty()` | 400, `BODY_REQUIRED` |
| Body JSON sai cú pháp/kiểu | Decoder/Jackson error | 400, `MALFORMED_BODY` |
| JSON hợp lệ nhưng vi phạm `@NotBlank`, `@Positive` | Bean Validation | 400, `INPUT_VALIDATION` |
| `Content-Type` không đúng route/reader | Route predicate hoặc unsupported media type | 415 hay 404/khác theo routing/config; không đoán |
| Business conflict sau validate | Domain service / database unique constraint | 409 hay 422 theo contract |

Một số lỗi khác phải để hệ thống riêng xử lý:

- **Body/record quá lớn:** `DataBufferLimitException` có thể từ codec; API nên có policy 413 nhưng không mặc định hứa mọi phiên bản trả 413.
- **Unacceptable response media type:** 406 khi không có writer phù hợp.
- **Too many requests:** 429 là quota/rate limiting, không phải Bean Validation.
- **Auth missing/forbidden:** 401/403 ở Spring Security layer.
- **DB/network outage:** 5xx hoặc retry policy, **không** trả 400.
- **Client disconnect:** cancellation/transport handling; không giả định luôn gửi được JSON lỗi.

### 7.1. Lỗi decoder và validation xảy ra ở giai đoạn khác nhau

Ví dụ JSON sai:

```json
{"title":
```

Không có `CreateBook` hợp lệ để validate. Error có thể là `DecodingException` hoặc được WebFlux bọc thành `ServerWebInputException`; cần kiểm tra chain của Spring Framework/codec version bạn dùng.

Ví dụ JSON đúng nhưng title rỗng:

```json
{
  "title": " ",
  "contact": {"email":"reader@example.org"}
}
```

Decoder tạo DTO, sau đó **validator do bạn gọi** phát violation. Bắt cả hai trong một `onErrorResume(Throwable.class, ...)` rồi trả 400 sẽ che mất error từ DB, programming bug hoặc OOM.

### 7.2. Phạm vi `onErrorResume`

```java
return request.bodyToMono(CreateBook.class)
        .map(this::requireValid)
        .flatMap(this::save)
        .onErrorResume(InputProblem.class, this::badInput);
```

Dạng này chỉ xử lý exception **InputProblem**. Nếu DB lỗi, lỗi được propagates tới WebFlux global error infrastructure, thay vì bị biến thành invalid request. Đây là nguyên tắc phân loại lỗi theo **exception type và layer**.

Nếu bạn dùng `onErrorResume(DecodingException.class,...)`, chỉ map lỗi decode sang MALFORMED_BODY. Nếu có `ServerWebInputException` từ reader, map input problem theo HTTP status/policy; giữ exception text riêng tư.

## 8. Ranh giới của Content-Type, Accept và route predicates

Với router:

```java
RouterFunctions.route()
        .POST(
            "/api/books",
            RequestPredicates.contentType(
                    MediaType.APPLICATION_JSON),
            handler::create)
        .build();
```

Request predicate chỉ match nếu `Content-Type` phù hợp. Client gửi XML có thể **không match route**, dẫn đến 404/415 tùy các handler mappings và error policies; không tự suy ra Bean Validation sẽ bắt.

- `Content-Type` mô tả **request representation**, ví dụ JSON, NDJSON, form.
- `Accept` mô tả **các representations client nhận được** ở response.
- `contentType(APPLICATION_JSON)` **không** chứng minh body thật sự là JSON hợp lệ.
- `accept(APPLICATION_JSON)` không thay nội dung được ghi thành JSON nếu writer/DTO không phù hợp.
- HTTP headers do client cung cấp, cần kiểm tra cả payload và business rules.
- Nếu cần trả chuẩn 415 thay vì “không có route”, thiết kế fallback/error handling ở application/gateway và viết tests.

**Với WebFlux.fn, route predicates được xét theo thứ tự khai báo.** Một route rộng khai trước có thể shadow route cụ thể hơn. Đặt `/api/books/import` trước route `/api/books/{id}` nếu cả hai dùng cùng HTTP method và có nguy cơ overlap.

## 9. Không đọc body hai lần nếu không chủ đích cache

HTTP request body là **một stream**, không phải Java object cache tùy ý.

Anti-pattern:

```java
// Không làm thế này:
request.bodyToMono(String.class)
        .doOnNext(System.out::println)
        .subscribe();

return request.bodyToMono(CreateBook.class)
        .flatMap(this::save);
```

Bạn vừa tự subscribe (rời lifecycle) rồi thử consume body lần hai. Body có thể đã tiêu thụ; pooled buffers có thể bị release, dẫn tới lỗi.

Để inspect/validate, dùng **một pipeline**:

```java
return request.bodyToMono(CreateBook.class)
        .doOnNext(dto ->
                metrics.markReceived())
        .map(this::requireValid)
        .flatMap(this::save);
```

Không log raw DTO nếu có password, token, email/PII. Với request logging body thật sự, cần buffer decorator được thiết kế đúng, cap bytes, lifecycle/retain/release, redaction và security review; đừng tái đọc request để log.

### 9.1. BodyExtractors và buffer ownership

- Standard `bodyToMono/bodyToFlux` để HTTP codec xử lý `DataBuffer` lifecycle.
- Khi tự đọc `Flux<DataBuffer>`, cần hiểu pooled buffer retention, `DataBufferUtils.release`/`retain`, cancellation và discard.
- Không `collectList()` toàn bộ raw DataBuffers rồi giữ vô hạn.
- `DataBufferUtils.join(...)` aggregate bytes và có overload maxByteCount, nhưng không phù hợp infinite/unbounded body.
- Không đưa raw `DataBuffer` vào downstream cache sau khi framework đã release; nếu phải handoff, có ownership contract rõ.
- Spring WebFlux codecs tôn trọng Reactive Streams demand trong khả năng của implementation, nhưng network/proxy vẫn có queues và buffers riêng.

## 10. Validation phải xảy ra trước side effects

Luồng đúng:

```text
decode body
  |
  v
validate DTO / field paths
  |
  +--- invalid ---> 400 JSON error, KHÔNG lưu
  |
  v
validate business rules / authorization
  |
  v
repository.save / publish event
  |
  v
201 / 200 response
```

Nếu gọi database trước rồi mới `validate`, một request có title rỗng có thể đã tạo record sai. Với stream nhiều records, phải phân biệt:

- **Per-record validation:** mỗi record được kiểm tra trước khi xử lý riêng.
- **Whole-batch validation:** kiểm tra cross-record duplicates, limits và invariant toàn batch. Có thể cần staging/transaction/snapshot.
- **Atomicity:** với stream lớn, không thể hứa rollback mọi side effects chỉ bằng `onErrorResume`. Phải thiết kế DB transaction hoặc job-based processing.
- **Ordering:** `concatMap` giữ thứ tự nguồn khi side effects cần tuần tự; `flatMap` xử lý concurrency có thể reorder.
- **Database uniqueness:** Bean Validation không thay DB unique constraint khi nhiều concurrent requests.
- **Authorization:** các ràng buộc field không thay quyền truy cập theo user/tenant.

### 10.1. Lấy thông tin user đáng tin

Không để input DTO chứa `ownerId`/`role` rồi mặc định tin. Lấy authenticated identity từ security context trong WebFlux và kiểm tra quyền dùng reactive services. Validation kiểm tra định dạng; authorization kiểm tra **ai được làm gì**.

## 11. Lỗi trả về: code và danh sách fields an toàn

Gợi ý error JSON:

```json
{
  "code": "INPUT_VALIDATION",
  "fields": ["title", "contact.email"]
}
```

Với NDJSON dòng thứ hai:

```json
{
  "code": "INPUT_VALIDATION",
  "fields": ["lines[2].quantity"]
}
```

Tên trường và mã lỗi thường đủ để frontend hiển thị hoặc i18n. Không trả:

```json
{
  "field": "password",
  "rejectedValue": "MySecret",
  "stackTrace": "java.lang.IllegalArgumentException..."
}
```

Exception messages/custom constraints có thể vô tình chứa user input. Hạn chế echo; nếu cần human-readable messages, chọn từ bảng thông báo an toàn, không trực tiếp trả `violation.getInvalidValue()`.

### 11.1. ProblemDetail là một lựa chọn

Spring 6.2 hỗ trợ `ProblemDetail`/RFC 9457 cho HTTP errors. Với functional endpoints, bạn có thể xây `ServerResponse` cho `application/problem+json`, hoặc sử dụng global exception infrastructure với error response. Nhưng **đừng trộn nhiều schema lỗi vô tổ chức**; chọn consistent error format theo API version.

## 12. Ví dụ chạy được: Spring Boot 3.5 + Java 17 WebFlux.fn

Demo minh họa đầy đủ cả hai kiểu body:

1. **`POST /api/books`**: nhận một JSON object bằng `bodyToMono(CreateBook.class)`, validate nested contact, lưu in-memory, trả **201 Created** + Location.
2. **`POST /api/books/import`**: nhận nhiều NDJSON records bằng `bodyToFlux(ImportLine.class)`; validate **từng item** cùng vị trí index, sau đó giảm thành thống kê count/quantity, trả 200.
3. **`GET /api/books/{id}`**: đọc resource đã lưu để chứng minh Location.
4. Định dạng lỗi an toàn cho BODY_REQUIRED, INPUT_VALIDATION, MALFORMED_BODY và INVALID_ID.
5. Không dùng `subscribe()`/`block()` trong handler. Không chạy blocking JDBC trên Netty event loop.

Đây là **demo in-memory, không phải ứng dụng production**: khi restart mất dữ liệu, scale nhiều nodes không chia sẻ map. Batch import chỉ tính tổng, không lưu rows; không có database, auth, global total-byte cap hay cross-record reconciliation.

### 12.1. Dependencies Gradle

Dùng Spring Initializr tạo project **Spring Boot 3.5.x, Java 17, Spring Reactive Web, Validation**. Trong `build.gradle` đã có Boot plugin, repositories và Java toolchain, dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment build.gradle**, không phải file Gradle hoàn chỉnh. Không thêm `spring-boot-starter-web` chỉ vì muốn dùng RouterFunction; Boot 3.x thường chọn Servlet MVC nếu cả MVC và WebFlux starters cùng có mặt.

### 12.2. Toàn bộ Java source

Tạo file **`src/main/java/demo/fnbody/FnBodyApplication.java`**:

```java
package demo.fnbody;

import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

@SpringBootApplication
public class FnBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(FnBodyApplication.class, args);
    }
}

record Contact(@NotBlank @Email String email) {}

record CreateBook(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}

record Book(long id, String title, String contactEmail) {}

record ImportLine(
        @NotBlank String sku,
        @Positive @Max(1000) int quantity) {}

record ImportSummary(long rows, long units) {}

record ApiError(String code, List<String> fields) {}

final class InputProblem extends RuntimeException {
    private final String code;
    private final List<String> fields;

    InputProblem(String code, List<String> fields) {
        super(code);
        this.code = code;
        this.fields = List.copyOf(fields);
    }

    String code() { return code; }
    List<String> fields() { return fields; }
}

@Component
class BookHandler {
    private final Validator validator;
    private final AtomicLong ids = new AtomicLong(2000);
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    BookHandler(Validator validator) {
        this.validator = validator;
    }

    private <T> T checked(T value, String prefix) {
        Set<ConstraintViolation<T>> violations =
                validator.validate(value);

        if (!violations.isEmpty()) {
            List<String> fields = violations.stream()
                    .map(v -> prefix + v.getPropertyPath())
                    .distinct()
                    .sorted()
                    .toList();

            throw new InputProblem(
                    "INPUT_VALIDATION", fields);
        }

        return value;
    }

    private Mono<ServerResponse> error(
            String code, List<String> fields) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(code, fields));
    }

    // Không catch Throwable hay database errors thành 400.
    private Mono<ServerResponse> handleInputErrors(
            Mono<ServerResponse> publisher) {
        return publisher
                .onErrorResume(InputProblem.class,
                    problem -> error(
                        problem.code(), problem.fields()))
                .onErrorResume(DecodingException.class,
                    problem -> error(
                        "MALFORMED_BODY", List.of("body")))
                .onErrorResume(ServerWebInputException.class,
                    problem -> error(
                        "MALFORMED_BODY", List.of("body")));
    }

    Mono<ServerResponse> create(ServerRequest request) {
        Mono<ServerResponse> result =
                request.bodyToMono(CreateBook.class)
                    .switchIfEmpty(Mono.error(
                        new InputProblem(
                            "BODY_REQUIRED", List.of("body"))))
                    .map(value -> checked(value, ""))
                    .flatMap(value -> {
                        long id = ids.incrementAndGet();
                        Book created = new Book(
                            id, value.title().trim(),
                            value.contact().email());
                        books.put(id, created);

                        // Relative Location: demo chạy tại context root.
                        URI uri = URI.create("/api/books/" + id);

                        return ServerResponse.created(uri)
                                .contentType(
                                    MediaType.APPLICATION_JSON)
                                .bodyValue(created);
                    });

        return handleInputErrors(result);
    }

    Mono<ServerResponse> importLines(ServerRequest request) {
        Mono<ImportSummary> count =
                request.bodyToFlux(ImportLine.class)
                    .index()
                    .map(tuple -> {
                        long lineNumber = tuple.getT1() + 1;
                        return checked(
                                tuple.getT2(),
                                "lines[" + lineNumber + "].");
                    })
                    .reduce(
                        new ImportSummary(0L, 0L),
                        (acc, line) ->
                            new ImportSummary(
                                acc.rows() + 1,
                                acc.units() + line.quantity()));

        Mono<ServerResponse> result =
                count.flatMap(summary -> {
                    if (summary.rows() == 0) {
                        return error(
                            "BODY_REQUIRED", List.of("body"));
                    }
                    return ServerResponse.ok()
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(summary);
                });

        return handleInputErrors(result);
    }

    Mono<ServerResponse> get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(
                    request.pathVariable("id"));
        } catch (NumberFormatException badId) {
            return error(
                "INVALID_ID", List.of("id"));
        }

        return Mono.justOrEmpty(books.get(id))
                .flatMap(book ->
                    ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(
                    ServerResponse.notFound().build());
    }
}

@Configuration
class BookRoutes {
    @Bean
    RouterFunction<ServerResponse> bookRouter(
            BookHandler handler) {
        return RouterFunctions.route()
                .POST(
                    "/api/books/import",
                    contentType(MediaType.APPLICATION_NDJSON),
                    handler::importLines)
                .POST(
                    "/api/books",
                    contentType(MediaType.APPLICATION_JSON),
                    handler::create)
                .GET("/api/books/{id}", handler::get)
                .build();
    }
}
```

**Kiểm tra cấu trúc:**

- Một `public class FnBodyApplication`; các records, `BookHandler` và `BookRoutes` package-private cùng package.
- `@Component BookHandler` được Spring Boot component scan, inject `jakarta.validation.Validator` do validation starter cấu hình.
- `@Configuration BookRoutes` cung cấp một `RouterFunction<ServerResponse>` bean WebFlux.fn.
- `BookHandler` nhận `ServerRequest` và trả `Mono<ServerResponse>` đúng WebFlux.fn.
- `checked` dùng typed `ConstraintViolation` nhưng chỉ đưa ra **field paths**, không echo input hay constraint message có thể chứa dữ liệu nhạy cảm.
- `create` chỉ sinh ID, lưu map **sau** khi decode và Bean Validation hoàn tất.
- `importLines` validate từng dòng trước khi cộng aggregate; không materialize cả batch.
- `handleInputErrors` chỉ bắt input/domain validation exception cụ thể và decoder-related exceptions; không bắt mọi bug thành 400.
- `GET /api/books/{id}` trả 404 nếu không tồn tại, INVALID_ID nếu ID không phải số.
- `@Positive @Max(1000)` giới hạn quantity mỗi dòng, nhưng **không** giới hạn tổng số dòng hoặc tổng quantity của toàn stream; production cần quota/overflow handling.

### 12.3. Chạy và kiểm tra bằng curl

```bash
./gradlew bootRun
```

**Tạo book hợp lệ:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Reactive Guide","contact":{"email":"reader@example.org"}}'
```

Nếu đây là request tạo đầu tiên, kết quả dự kiến:

```http
HTTP/1.1 201 Created
Location: /api/books/2001
Content-Type: application/json

{"id":2001,"title":"Reactive Guide","contactEmail":"reader@example.org"}
```

`Location` là relative path, phù hợp demo context root. Với production sau gateway/context prefix, cần generate links phù hợp public base/path và Host/Forwarded trust policy.

**Thiếu body:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary ''
```

Kỳ vọng 400:

```json
{"code":"BODY_REQUIRED","fields":["body"]}
```

**JSON hợp lệ nhưng sai constraints:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":" ","contact":{"email":"not-an-email"}}'
```

Kỳ vọng 400; fields thường là `title` và `contact.email` (do `@Valid` cascade):

```json
{"code":"INPUT_VALIDATION","fields":["contact.email","title"]}
```

Các field names được code sort alphabetic, nên thứ tự ổn định trong demo (nhưng thứ tự violations do provider trả trước sort không bảo đảm).

**Malformed JSON:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

Kỳ vọng lỗi decoder được mã hóa thành `MALFORMED_BODY` khi đi vào `DecodingException` hoặc `ServerWebInputException`:

```json
{"code":"MALFORMED_BODY","fields":["body"]}
```

Nếu hạ tầng báo lỗi theo class/adapter khác, phải kiểm chứng bằng integration tests và bổ sung handler có chọn lọc; không map `Throwable` sang 400.

**Import NDJSON hợp lệ:**

```bash
printf '%s\n' \
  '{"sku":"B-101","quantity":3}' \
  '{"sku":"B-102","quantity":5}' \
  '{"sku":"B-103","quantity":2}' \
  | curl -i -X POST 'http://localhost:8080/api/books/import' \
      -H 'Content-Type: application/x-ndjson' \
      --data-binary @-
```

Body dự kiến:

```json
{"rows":3,"units":10}
```

**Dòng thứ hai sai:**

```bash
printf '%s\n' \
  '{"sku":"B-101","quantity":3}' \
  '{"sku":"B-102","quantity":0}' \
  | curl -i -X POST 'http://localhost:8080/api/books/import' \
      -H 'Content-Type: application/x-ndjson' \
      --data-binary @-
```

Kỳ vọng 400:

```json
{"code":"INPUT_VALIDATION","fields":["lines[2].quantity"]}
```

Vì import chỉ tính aggregate và không lưu dữ liệu, invalid stream không tạo dữ liệu partial. **Đừng coi ví dụ này là transactional bulk import** khi chuyển sang DB.

## 13. Test WebTestClient qua HTTP trên RANDOM_PORT

Kiểm thử dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` để chạy WebFlux với HTTP codecs/Netty, thay vì chỉ gọi handler trực tiếp.

Tạo **`src/test/java/demo/fnbody/FnBodyApplicationTests.java`**:

```java
package demo.fnbody;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FnBodyApplicationTests {
    @Autowired
    WebTestClient client;

    @Test
    void createsBookFromOneJsonObject() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {
                      "title":"Reactive Guide",
                      "contact":{"email":"reader@example.org"}
                    }
                    """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Reactive Guide")
                .jsonPath("$.contactEmail")
                    .isEqualTo("reader@example.org");
    }

    @Test
    void emptyBodyIsRejectedBeforePersistence() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("BODY_REQUIRED");
    }

    @Test
    void invalidFieldsProduceValidationError() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {
                      "title":" ",
                      "contact":{"email":"invalid-email"}
                    }
                    """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("contact.email")
                .jsonPath("$.fields[1]")
                    .isEqualTo("title");
    }

    @Test
    void missingNestedContactIsInvalid() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {"title":"Valid title"}
                    """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("contact");
    }

    @Test
    void malformedJsonIsNotBeanValidationError() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("MALFORMED_BODY");
    }

    @Test
    void multiLineNdjsonIsReducedWithoutCollectList() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(Flux.just(
                    new ImportLine("B-101", 3),
                    new ImportLine("B-102", 5),
                    new ImportLine("B-103", 2)),
                    ImportLine.class)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.rows").isEqualTo(3)
                .jsonPath("$.units").isEqualTo(10);
    }

    @Test
    void invalidNdjsonItemIdentifiesIndex() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(Flux.just(
                    new ImportLine("B-101", 3),
                    new ImportLine("B-102", 0)),
                    ImportLine.class)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("lines[2].quantity");
    }

    @Test
    void emptyNdjsonIsRejected() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("BODY_REQUIRED");
    }

    @Test
    void malformedIdIsBadInput() {
        client.get()
                .uri("/api/books/not-a-number")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_ID");
    }

    @Test
    void missingBookReturns404() {
        client.get()
                .uri("/api/books/999999999")
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

Chạy:

```bash
./gradlew test
```

**Mười tests được thiết kế để pass** với Boot 3.5, Reactor Netty và Java 17 code ở trên. Đây là **kỳ vọng qua review source và API**, **không phải bằng chứng Gradle đã chạy**. Trong hệ thống thực, hãy thực thi tests và điều chỉnh chỗ behavior thực của codec/config phiên bản không đúng giả định.

Điểm đáng chú ý:

- Test `bodyToMono` qua JSON hợp lệ, trống, invalid/nested constraints và malformed syntax.
- Test `bodyToFlux` bằng **NDJSON publisher** từ WebTestClient và xác minh thống kê/invalid index.
- Test body rỗng không bị tự chấp nhận là batch 0 thành công.
- Test path variable do functional handler tự parse, phân biệt bad ID và missing resource.
- Các tests tạo book mới dùng id sequence nhưng không assert ID cố định để tránh phụ thuộc execution order.
- `@SpringBootTest(RANDOM_PORT)` bao gồm actual HTTP encoding/decoding, còn unit test Java Validator nên có riêng nếu ràng buộc domain phức tạp.

### 13.1. Test “không lưu input sai” nghiêm túc

Demo không trả số lượng stored books. Để xác minh invalid payload không ghi DB ở production, dùng reactive repository spy/mocks hoặc database integration tests:

1. Gửi invalid DTO.
2. Assert status 400.
3. Assert repository `save` **không được gọi**.
4. Nếu có transaction, assert rollback/DB rows unchanged.
5. Test concurrency/race, auth và idempotency.

Không chỉ assert code 400 rồi suy ra không side effect; test đúng layer repository.

## 14. Body rỗng, malformed, validation và lỗi domain: thiết kế exception flow

Thứ tự khuyến nghị:

```text
bodyToMono / bodyToFlux
  |
  +--- Flux/Mono empty --> explicit BODY_REQUIRED
  |
  +--- decode error --> MALFORMED_BODY
  |
  v
validate each DTO
  |
  +--- violations --> INPUT_VALIDATION (400)
  |
  v
business & security checks
  |
  +--- permission --> 403
  +--- conflict --> 409
  |
  v
repository
  |
  +--- infrastructure failure --> 5xx
  |
  v
ServerResponse success
```

**Không chuyển `DataBufferLimitException` thành MALFORMED_BODY mặc định** nếu error bị wrap trong ServerWebInputException; một số input decoding limit failures cần 413 theo product contract. Demo chọn hạn chế error handler để dễ học; production nên phân loại cause chain, có giới hạn payload tại ingress/codec, và test 413.

### 14.1. Vì sao tránh response body chứa raw exception?

`DecodingException#getMessage()` có thể chứa class names, parsing positions hoặc fragments từ payload. `ConstraintViolation#getInvalidValue()` có thể là secret. Thay bằng safe **field names/error codes**, và log internal error information có kiểm soát, redaction ở app/gateway/APM.

### 14.2. Khi response đã committed

Trong `bodyToFlux` request input, bạn có thể stream phản hồi song song hoặc theo từng item. Nếu đã gửi 200 + vài bytes rồi mới gặp dòng lỗi, HTTP status **không thể chắc chắn đổi sang 400**. Chọn giao thức explicit stream-error frames hoặc đợi hoàn tất validation trước khi trả success nếu batch nhỏ và business đòi atomic reply.

Trong demo `reduce` chờ hết input trước khi sinh response, nên lỗi invalid line thường có thể trả 400 trước khi response commit. Đây là **đánh đổi latency/aggregation**: memory nhỏ với reduce, nhưng response chỉ xuất sau khi stream kết thúc.

## 15. NDJSON, JSON array và những lựa chọn khác

| Input representation | Cách đọc thường phù hợp | Trade-off |
| --- | --- | --- |
| `application/json`, một object | `bodyToMono(MyDto.class)` | Dễ validate một command; decoder có thể aggregate object |
| `application/json`, một array | `bodyToMono(ParameterizedTypeReference<List<Dto>>)` | Giữ list trong RAM, dễ cross-item validation |
| `application/x-ndjson`, nhiều dòng | `bodyToFlux(Dto.class)` | Per-record processing, framing rõ |
| `text/plain`, một chuỗi | `bodyToMono(String.class)` | Kiểm tra charset và max bytes |
| `application/octet-stream`, file lớn | `body(BodyExtractors.toDataBuffers())` / `FilePart` | Raw bytes ownership/quota/storage phức tạp |
| `application/x-www-form-urlencoded` | `ServerRequest.formData()` | Bind form map, validation tự gọi |
| `multipart/form-data` | `ServerRequest.multipartData()` | Files/parts + disk/RAM/part limits riêng |

`bodyToFlux<T>` không thích hợp cho mọi file upload; việc decode bytes thành DTO cần representation thích hợp. `multipartData()` trả dữ liệu parts đã được đọc theo contract parser, có thể spool file ra disk; nếu file cực lớn hoặc cần streaming parts, xem `PartEvent` APIs của WebFlux 6.2 và quản lý buffers.

### 15.1. Form data

```java
Mono<MultiValueMap<String, String>> form =
        request.formData();
```

Đây là fragment; mỗi value do client cung cấp phải được parse/validate, ví dụ `Integer.parseInt` có thể ném `NumberFormatException`. Không nghĩ form map đã tự chạy `@NotBlank` trong functional handler.

### 15.2. Multipart

```java
Mono<MultiValueMap<String, Part>> parts =
        request.multipartData();
```

Đây là fragment; cần import `org.springframework.http.codec.multipart.Part`. Với file, `FilePart.filename()` không đáng tin làm filesystem path. Khi transfer file, dùng path **do server sinh**, kiểm soát authorization, size, storage, MIME validation và lifecycle; Bean Validation trên metadata không kiểm tra virus hay file content.

## 16. Giới hạn bộ nhớ và byte-size quan trọng hơn number of DTOs

Các giới hạn độc lập:

| Giới hạn | Lớp tác động | Nó không bảo đảm |
| --- | --- | --- |
| Codec `maxInMemorySize` | Bytes của một đơn vị decode/aggregate | Không phải tổng request quota |
| Body max bytes | Gateway/server/app | Không phải business field validation |
| NDJSON max record length | Decoder/endpoint contract | Không giới hạn tổng batch |
| `@Size(max=80)` | DTO field length (Java semantic) | Không giới hạn toàn bộ JSON bytes |
| `take(maxRecords)` | Số phần tử reactive được downstream nhận | Có thể cancel sớm; không luôn chặn transport bytes đã gửi |
| Database unique constraint | Trùng khóa persisted | Không thay client validation |
| Rate/concurrency limit | Request volume và resource usage | Không thay codec limit |
| Timeout | Thời gian request/stream | Không giới hạn số bytes |

Với **Spring Boot 3.5**, property cấu hình HTTP codecs:

```properties
spring.http.codecs.max-in-memory-size=256KB
```

Giá trị ở trên là một **giá trị cấu hình minh họa**: namespace `spring.http.codecs` thuộc Boot 3.5; kiểm tra bản dùng nếu bạn chuyển Boot major. Nhiều codecs có default khoảng 256 KiB cho một đơn vị tích lũy; property này không phải giới hạn tổng uploads. Khi dùng WebClient tự khởi tạo, client codec limits có thể khác server.

Đừng copy `spring.codec.max-in-memory-size` từ tutorial Boot cũ rồi tin nó vẫn có hiệu lực ở Boot 3.5.

### 16.1. Body đến chậm và cancellation

Client có thể gửi dữ liệu rất chậm (slow upload), hoặc disconnect giữa NDJSON stream. Reactor có `timeout`/`doFinally`/`doOnCancel` nhưng network request cancellation propagation không luôn tức thời và một upstream source có thể vẫn hoạt động. Trong production:

- Giới hạn upload duration/idle timeout ở gateway/netty.
- Có per-tenant request concurrency và rate quota.
- Nếu tạo external subscriptions/storage streams, cleanup ở `doFinally`/`usingWhen`.
- Không tạo unbounded replay/logging queue cho raw input.
- Hạn chế recursive/very deeply nested JSON, numeric overflow, CPU-heavy regex.
- Giới hạn trực tiếp **số dòng** và **số bytes** với contract rõ, không chỉ count đã decode.

## 17. Khi nào nên dùng annotated controller thay WebFlux.fn?

| Tình huống | Functional WebFlux | Annotated WebFlux |
| --- | --- | --- |
| Tổ chức route theo hàm/predicates | `RouterFunctions.route()` | `@RequestMapping` |
| Đọc một body | `request.bodyToMono(Dto.class)` | `@RequestBody Mono<Dto>` |
| Đọc stream body | `request.bodyToFlux(Dto.class)` | `@RequestBody Flux<Dto>` |
| Validate DTO từ JSON | Gọi Validator trong handler | `@Valid/@Validated` được framework hỗ trợ |
| Method constraints direct `@Min` | Parse/validate tường minh hoặc domain/service | Built-in handler method validation |
| Body field errors | Custom `InputProblem` + error response | `WebExchangeBindException` thường gặp |
| Middleware cục bộ | `HandlerFilterFunction` | `WebFilter`, advice, interceptors tùy stack |
| Error schema | `ServerResponse` hoặc WebExceptionHandler | `@RestControllerAdvice`/ErrorResponse |
| JSON codecs | Chung `HttpMessageReader/Writer` của WebFlux | Chung codecs |
| Backpressure | `Mono/Flux` | `Mono/Flux` |

**Quan trọng:** khi dùng `bodyToMono` trong functional handler, không tự kỳ vọng framework phát `WebExchangeBindException` chỉ vì DTO có `@NotBlank`. Nó cần validator được gọi tường minh. Ngược lại, trong annotated controller với `@Valid`, WebFlux hạ tầng hỗ trợ validation và exception path theo controller signatures.

Spring MVC.fn là một sản phẩm khác (`org.springframework.web.servlet.function.ServerRequest`), nơi `body(...)` thường trả synchronous object; không copy cách đó vào reactive handler.

## 18. Custom validation và nghiệp vụ bất đồng bộ

### 18.1. Cross-field constraints

Ví dụ DTO có `startDate`, `endDate`; ràng buộc start không sau end cần class-level Bean Validation constraint hoặc code domain:

```java
Mono<EventCommand> checkRange(EventCommand input) {
    if (input.start().isAfter(input.end())) {
        return Mono.error(
                new InputProblem(
                    "INVALID_TIME_RANGE",
                    List.of("start", "end")));
    }
    return Mono.just(input);
}
```

Đây là fragment; DTO và exception phải tồn tại. Không bọc tất cả lỗi thành `IllegalArgumentException` rồi generic 400 nếu có thể dùng typed business exceptions.

### 18.2. Kiểm tra uniqueness qua reactive repository

```java
Mono<Book> checkThenSave(CreateBook input) {
    return repository.existsByTitle(input.title())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(
                        new DuplicateBookException());
                }
                return repository.save(toEntity(input));
            });
}
```

Đây là fragment. **Có race** giữa `exists` và `save`, nên nếu business không cho trùng, phải dùng DB unique index/constraint và map conflict 409. Không đặt blocking database calls trong `ConstraintValidator` chạy trên Netty event loop.

### 18.3. Bean Validation groups

Có thể dùng `validator.validate(dto, CreateGroup.class)` để chọn group khi tự gọi Jakarta Validator. Nếu muốn create/update rules khác nhau:

```java
Set<ConstraintViolation<CreateBook>> errors =
        validator.validate(input, OnCreate.class);
```

Fragment giả định `OnCreate` marker interface tồn tại và constraints đã gắn group phù hợp. Khi chọn group riêng, các constraints thuộc `Default` không tự được kích hoạt nếu không chọn đúng; test `null`, empty, whitespace và nested cascade.

## 19. Test thêm: không có body, ID, serialization và memory

Một bộ test đủ tốt ngoài mười bài phía trên nên có:

1. Body JSON đúng, `Content-Type` sai: xác minh status thực của router/predicate policy.
2. Missing `Content-Type`: xác minh route behavior; không suy ra lỗi validation.
3. Generic JSON array: kiểm tra `ParameterizedTypeReference<List<...>>` decode đúng element type.
4. Một NDJSON record vượt `maxInMemorySize`: xác nhận codec limit và error policy riêng.
5. Nhiều records nhỏ tổng request lớn: xác nhận upload quota tầng proxy hoặc application.
6. Stream có lỗi tại dòng thứ N: xác nhận các side effects trước đó/transaction semantics.
7. Stream client cancel: xác minh publisher/external resource cleanup.
8. Nested Bean Validation errors với thứ tự field sort ổn định.
9. Producer không tự subscribe/block (có thể static analysis/review).
10. Test trên staging proxy với request chunked/HTTP2, slow upload và gateway timeouts.

### 19.1. Why WebTestClient?

`WebTestClient` hỗ trợ WebFlux HTTP tests. Có thể bind trực tiếp vào router functions hoặc chạy server thật. Demo dùng **RANDOM_PORT** để kiểm tra codec/network request/response, không chỉ logic handler.

Khi test external network, thời gian, connection pool và backpressure có nhiều yếu tố khiến assertions quá sát wall clock dễ flaky. Để test raw reactive demand, dùng `StepVerifier` trong unit tests; để kiểm tra HTTP body framing, dùng WebTestClient hoặc client streaming phù hợp.

## 20. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `bodyToMono` rồi `block()` | Block event loop | Compose `flatMap/map` và return Mono |
| Tự `subscribe()` trong handler | Mất HTTP error/cancellation lifecycle | Để WebFlux subscribe |
| DTO có `@NotBlank` nên “tự valid” trong fn | Input sai lọt service | Inject Validator và gọi tường minh |
| Chỉ validate record đầu | Các record sau không an toàn | Validate từng phần tử Flux |
| `collectList()` với infinite NDJSON | Tăng heap/vô hạn | Stream/reduce bounded |
| Không xử lý `Mono.empty` | Request thiếu body bị chấp nhận/response treo tùy code | `switchIfEmpty` hoặc policy rõ |
| Catch mọi Exception thành 400 | DB failure/programming bug bị che | Typed errors theo layer |
| Log `violation.getInvalidValue()` | Lộ credentials/PII | Field paths + safe error code |
| JSON syntax lỗi mà trả INPUT_VALIDATION | Sai phân loại | Decoder errors riêng |
| Content-Type sai coi như @Valid fail | Thực ra route/predicate không match | Test HTTP routing/status |
| `bodyToFlux` mà đọc file binary bằng DTO | Codec không phù hợp | FilePart/DataBuffer extractor |
| Đọc body hai lần để log | Stream một lần, buffers bị tiêu thụ | Một pipeline; decorator bounded nếu cần |
| `flatMap(save)` cho nghiệp vụ tuần tự | Order thay đổi, concurrency/race | `concatMap` hoặc transaction |
| Stream lỗi dòng 100 nhưng 99 dòng đã commit | Partial batch | Staging/transaction/job design |
| Chỉ giới hạn record size | Tổng upload vẫn có thể quá lớn | Gateway/request body quota |
| `take(1000)` coi là đã “reject” upload quá hạn | Nó có thể cancel sau 1000 mà không báo vượt | Explicit reject/count policy |
| @Valid nested mà không có @NotNull | Null nested object có thể qua | `@NotNull @Valid` |
| `@Email` coi là xác minh sở hữu địa chỉ | Identity spoofing | Verify email/authorization riêng |
| HTTP 200 đã ghi rồi mới gặp lỗi | Không đổi status sang 400 được | Streaming error protocol/retry |
| Thử case input trực tiếp mà không HTTP test | Bỏ sót codec/media type | WebTestClient RANDOM_PORT |

## 21. Checklist trước khi dùng trong sản phẩm

- [ ] Chọn `bodyToMono` cho single-value representation và `bodyToFlux` cho multi-record streaming phù hợp.
- [ ] `Content-Type`, Accept và body framing được document/test.
- [ ] Không nhầm WebFlux.fn với Spring MVC.fn.
- [ ] Có validation provider + chủ động gọi Bean Validator trong handler.
- [ ] Nested DTO fields bắt buộc có `@NotNull` bên cạnh `@Valid` khi cần.
- [ ] Xử lý Mono.empty/Flux.empty rõ ràng.
- [ ] Bắt decoder error và Bean Validation error riêng, không catch-all 400.
- [ ] Side effects chỉ chạy sau khi validate item/command tương ứng.
- [ ] Không tự subscribe/block trong handler.
- [ ] Không đọc request body hai lần nếu chưa có caching decorator an toàn.
- [ ] Import stream có per-record và batch-level limits/quota, transaction semantics.
- [ ] `flatMap` concurrency, `concatMap` order được chọn có chủ đích.
- [ ] Error response không lộ rejected values/secret/parser stack trace.
- [ ] Authn/authz, tenant boundary và mass assignment được xử lý độc lập.
- [ ] Codec max memory, total bytes, maximum records, timeout và per-user rate limits rõ ràng.
- [ ] Multipart file xử lý qua Part/FilePart/PartEvent và private storage policy.
- [ ] Trước khi lưu, số lượng/giá trị được kiểm tra overflow nếu accumulator có thể rất lớn.
- [ ] WebTestClient tests bao phủ success, invalid, empty, malformed, nested, stream.
- [ ] Có monitoring cancel/error/latency/queue bytes, không log raw DTO có PII.
- [ ] Migration Spring Boot/Framework version được đối chiếu Javadoc và properties tương ứng.

## 22. Bài tập tự thực hành

1. So sánh `bodyToMono(CreateBook.class)` và `bodyToFlux(ImportLine.class)`: publishers khác nhau thế nào?
2. Nếu body JSON là `null` hoặc request không có body, `Mono.empty` ảnh hưởng `map(this::validate)` ra sao?
3. Vì sao Bean Validation annotations trên DTO không đủ cho WebFlux.fn khi thiếu lời gọi Validator?
4. Hãy thay `jakarta.validation.Validator` bằng Spring `Validator` + `BeanPropertyBindingResult`.
5. Tạo nested DTO có `@NotNull @Valid`; xóa `@NotNull` rồi test payload `contact=null`.
6. Thêm `@Size(max=20)` vào SKU và kiểm tra dòng NDJSON nào sai.
7. Đổi `.index().map(...)` thành `.map(...)`; nếu không giữ index thì lỗi UI sẽ định vị dòng như thế nào?
8. Chuyển import thành `concatMap(repository::save)` và mô phỏng fail tại record thứ ba. Bao nhiêu dòng có thể đã commit?
9. Nếu import phải atomic, thiết kế staging/transaction/job thay cho save từng dòng.
10. Vì sao `onErrorResume(Throwable.class,...)` là lỗi khi DB outage?
11. So sánh body malformed JSON với valid JSON có title blank; trả codes nào và lỗi được phát ở đâu?
12. Khi request có Content-Type `text/plain` nhưng route yêu cầu JSON, status nào có thể xuất hiện và cần test gì?
13. Body là `List<CreateBook>`: viết overload dùng `ParameterizedTypeReference` để giữ generic type.
14. Vì sao `request.bodyToFlux(...)` rồi `collectList()` phá lợi ích streaming?
15. Thử một NDJSON line 1 MiB; giới hạn codec nào liên quan? Nếu 10.000 lines nhỏ, tổng body quota ở đâu?
16. Vì sao `@Size(max=80)` không tự chặn 100 MB JSON?
17. Một client ngắt sau khi gửi hai dòng. Bạn cleanup repository stream/subscription bằng API Reactor nào?
18. Dùng `doOnCancel` và `doFinally`, so sánh complete/error/cancel khi client đóng.
19. Thêm query parameter page ở functional request với `request.queryParam("page")`; parse/validate thế nào?
20. Nếu một sản phẩm có upload binary/multipart, tại sao không dùng `bodyToFlux(MyDto.class)` thay `FilePart`?
21. Thiết kế response ProblemDetail cho `INPUT_VALIDATION` không lộ password/token.
22. Nếu một WebFlux app scale 3 nodes với in-memory map, GET Location có thể lỗi vì sao?
23. Khi `Mono<ServerResponse>` đã tạo nhưng chưa subscribe, repository side effect có bắt buộc đã chạy không? Phân biệt những side effects nằm trước và trong operators.
24. Viết WebTestClient test empty body, malformed JSON, nested validation và invalid NDJSON line.
25. So sánh `@Valid @RequestBody Mono<DTO>` của annotated WebFlux controller với manual validation trong WebFlux.fn.
26. Trình bày kế hoạch chuyển demo thành production: auth/tenant, database uniqueness/atomic import, total quotas, codec limits, error codes và observability.

## 23. Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints WebFlux.fn](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): ServerRequest, bodyToMono/bodyToFlux, BodyExtractors, functional Bean Validation, routing và filters.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): overloads `bodyToMono(Class)`, `bodyToMono(ParameterizedTypeReference)`, `bodyToFlux`, formData, multipartData.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): Mono response, created, ok, bodyValue và error responses.
- [Spring Framework 6.2 — BodyExtractors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/BodyExtractors.html): `toMono`, `toFlux`, raw DataBuffer, form/multipart.
- [Spring Framework 6.2 — WebFlux HTTP Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): Reader/Decoder, byte buffers, aggregation limit, backpressure.
- [Spring Framework 6.2 — Annotated Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): khác biệt automatic validation khi dùng `@Valid` trên annotated method arguments.
- [Spring Framework 6.2 — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): FilePart, PartEvent và upload safety.
- [Spring Boot 3.5 — Servlet/Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): reactive web stack và WebFlux setup.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.max-in-memory-size`.
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html): Jakarta Validation provider/autoconfiguration.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): WebFlux HTTP integration testing.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested cascade and groups.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, cancellation và publisher/subscriber contracts.
